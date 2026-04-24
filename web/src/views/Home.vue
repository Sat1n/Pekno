<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import MainLayout from '@/layouts/MainLayout.vue'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle
} from '@/components/ui/sheet'
import { Github, Tv, FileText, MoreVertical, Sparkles, Clock3, Clock4, ExternalLink, Trash2, Star, Loader2, Download, X, Upload, Link2, Heart, HeartOff, UserRound, ArrowUp } from 'lucide-vue-next'
import { API_BASE_URL, getItems, search, summarizeItem, getItemSummaryStatus, getStoredAuthUser, toggleItemWatchLater, toggleItemFavorite, markItemsReadBatch, getActivePlugins, getParsePlugins, getHoverBlocks, uploadItem, parseItemUrl, resolveApiErrorMessage, type RawItem, type SearchResult, type ActivePlugin, type HoverResponse, type UploadDedupResponse } from '@/lib/api'
import HoverPreview from '@/components/HoverPreview.vue'
import { useToast } from '@/components/ui/toast/use-toast'
import { Toaster } from '@/components/ui/toast'

interface LocalSearchResult extends SearchResult {
  hasSummary?: boolean
  raw_link?: string
  authorName?: string
  displayTags?: string[]
  isRead: boolean
  isWatchLater: boolean
  isFavorited: boolean
  keyframes?: string[]
  intentType: string
  metadataExtra?: Record<string, any>
  isLocalUpload?: boolean
  uploadMimeType?: string
}

interface TranscriptSegment {
  id: string
  start: number
  end: number
  text: string
}

const savedLayout = (localStorage.getItem('pekno-layout') as 'list' | 'grid' | 'compact') || 'list'
const layoutMode = ref<'list' | 'grid' | 'compact'>(savedLayout)
watch(layoutMode, (val) => localStorage.setItem('pekno-layout', val))
const searchQuery = ref('')
const searchResults = ref<LocalSearchResult[]>([])
const activeSource = ref<string>('all')
const activePlugins = ref<ActivePlugin[]>([])
const parsePlugins = ref<ActivePlugin[]>([])
const isLoading = ref(false)
const isSheetOpen = ref(false)
const selectedItem = ref<LocalSearchResult | null>(null)
const isSummarizing = ref(false)
const currentTaskId = ref<string | null>(null)
const pollInterval = ref<number | undefined>(undefined)
const pendingSummaryItemId = ref<string | null>(null)
const keyframePreviewUrl = ref<string | null>(null)
const keyframePreviewLabel = ref<string>('')
const keyframePreviewIndex = ref<number>(0)
const isAddDialogOpen = ref(false)
const addContentTab = ref<'upload' | 'parse'>('upload')
const uploadFile = ref<File | null>(null)
const uploadTitle = ref('')
const uploadSummary = ref('')
const retentionDays = ref<number>(-1)
const parsePluginName = ref('bilibili_sync')
const parseUrl = ref('')
const isSubmittingContent = ref(false)
const route = useRoute()
const currentUsername = computed(() => getStoredAuthUser().username || t('common.guest'))
const initialAnchorItemId = ref<string | null>(null)
const isWatchLaterPage = computed(() => route.name === 'watch-later')
const pageTitle = computed(() => isWatchLaterPage.value ? t('home.watchLaterTitle') : t('home.welcomeBack', { username: currentUsername.value }))
const pageSubtitle = computed(() => {
  if (isLoading.value) {
    return t('home.loadingData')
  }
  if (isWatchLaterPage.value) {
    return t('home.watchLaterCount', { username: currentUsername.value, count: searchResults.value.length })
  }
  
  let unreadCount = searchResults.value.length
  if (initialAnchorItemId.value) {
    const anchorIndex = searchResults.value.findIndex(item => item.id === initialAnchorItemId.value)
    if (anchorIndex !== -1) {
      unreadCount = anchorIndex
    }
  } else {
    const readIndex = searchResults.value.findIndex(item => item.isRead)
    if (readIndex !== -1) {
      unreadCount = readIndex
    }
  }

  if (activeSource.value === 'all') {
    return t('home.updatesReady', { count: unreadCount })
  } else {
    const plugin = activePlugins.value.find(p => p.source_type === activeSource.value)
    const pluginName = plugin ? plugin.name : activeSource.value
    return t('home.pluginUpdates', { pluginName, count: unreadCount })
  }
})

let observer: IntersectionObserver | null = null
let flushReadsInterval: number | undefined
const cardElements = new Map<string, HTMLElement>()
const visibilityTimers = new Map<string, number>()
const pendingReadIds = new Set<string>()

const renderedSummary = computed(() => {
  const raw = selectedItem.value?.long_summary || selectedItem.value?.summary || ''
  if (!raw) return `<p class="text-muted-foreground">${t('home.aiSummaryMissing')}</p>`
  const normalized = raw.replace(/\\n/g, '\n')
  return marked.parse(normalized) as string
})

function parseTimestampValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function parseTranscriptSegments(rawTranscript: unknown): TranscriptSegment[] {
  if (!rawTranscript) return []

  let parsed: unknown = rawTranscript
  if (typeof rawTranscript === 'string') {
    try {
      parsed = JSON.parse(rawTranscript)
    } catch {
      return []
    }
  }

  if (!Array.isArray(parsed)) return []

  return parsed
    .map((entry, index) => {
      if (!entry || typeof entry !== 'object') return null
      const record = entry as Record<string, unknown>
      const start = parseTimestampValue(record.start ?? record.start_time ?? record.timestamp)
      const end = parseTimestampValue(record.end ?? record.end_time)
      const text = String(record.text || '').trim()
      if (start === null || !text) return null
      return {
        id: `segment-${index}-${start}`,
        start,
        end: end ?? start,
        text,
      } satisfies TranscriptSegment
    })
    .filter((segment): segment is TranscriptSegment => Boolean(segment))
}

function formatMediaTimestamp(seconds: number) {
  const whole = Math.max(0, Math.floor(seconds))
  const secs = whole % 60
  const minutes = Math.floor(whole / 60) % 60
  const hours = Math.floor(whole / 3600)
  if (hours > 0) {
    return [hours, minutes, secs].map((value) => String(value).padStart(2, '0')).join(':')
  }
  return [minutes, secs].map((value) => String(value).padStart(2, '0')).join(':')
}

const selectedTranscriptSegments = computed(() =>
  parseTranscriptSegments(selectedItem.value?.metadataExtra?.raw_transcript),
)

const hoverTimers = new Map<string, number>()
const hoverDataMap = ref<Record<string, HoverResponse>>({})
const activeHoverItemId = ref<string | null>(null)
const hoverSuppressedItemId = ref<string | null>(null)
const showBackToTop = ref(false)
let scrollContainer: HTMLElement | null = null

function extractAuthorName(source: string, metadata: Record<string, any>, item: Record<string, any>) {
  const candidates = source === 'bilibili'
    ? [
        metadata.up_name,
        metadata.author,
        item.author,
      ]
    : [
        item.author,
        metadata.author,
        metadata.owner,
        metadata.creator,
        metadata.uploader,
        metadata.user_name,
        metadata.username,
        metadata.channel,
      ]

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate.trim()
    }
  }

  return undefined
}

function updateBackToTopVisibility() {
  const currentScrollTop = scrollContainer?.scrollTop ?? 0
  const viewportHeight = scrollContainer?.clientHeight ?? window.innerHeight
  showBackToTop.value = currentScrollTop > viewportHeight
}

function handleCardMouseEnter(item: LocalSearchResult) {
  // 只在 list/grid 模式下，或者你有空间才显示，compact 先不用管
  if (hoverSuppressedItemId.value === item.id) return
  if (activeHoverItemId.value === item.id) return
  
  const timer = window.setTimeout(async () => {
    if (hoverSuppressedItemId.value === item.id) return
    activeHoverItemId.value = item.id
    if (!hoverDataMap.value[item.id]) {
      try {
        const blocks = await getHoverBlocks(item.id)
        if (blocks && blocks.length > 0) {
          hoverDataMap.value[item.id] = blocks
        } else {
          // Empty state fallback or clear if not supported
          activeHoverItemId.value = null
        }
      } catch (e) {
        console.error("Failed to fetch hover blocks", e)
        activeHoverItemId.value = null
      }
    }
  }, 500)
  hoverTimers.set(item.id, timer)
}

function handleCardMouseLeave(item: LocalSearchResult) {
  const timer = hoverTimers.get(item.id)
  if (timer) {
    window.clearTimeout(timer)
    hoverTimers.delete(item.id)
  }
  if (activeHoverItemId.value === item.id) {
    activeHoverItemId.value = null
  }
}

function suppressCardHover(itemId: string) {
  hoverSuppressedItemId.value = itemId
  clearHoverTimer(itemId)
  if (activeHoverItemId.value === itemId) {
    activeHoverItemId.value = null
  }
}

function releaseCardHover(itemId: string) {
  if (hoverSuppressedItemId.value === itemId) {
    hoverSuppressedItemId.value = null
  }
}

function clearHoverTimer(itemId: string) {
  const timer = hoverTimers.get(itemId)
  if (timer) {
    window.clearTimeout(timer)
    hoverTimers.delete(itemId)
  }
}

function scrollToTop() {
  if (scrollContainer) {
    scrollContainer.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const { toast } = useToast()
const { t } = useI18n()

const SUPPORTED_STATIC_IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'webp', 'bmp'])
const SUPPORTED_VIDEO_EXTENSIONS = new Set(['mp4', 'webm', 'mov', 'm4v', 'mkv', 'avi'])
const SUPPORTED_AUDIO_EXTENSIONS = new Set(['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'webm'])
const SUPPORTED_TEXT_EXTENSIONS = new Set(['txt', 'md', 'markdown', 'pdf'])
const SUPPORTED_STATIC_IMAGE_MIME_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/bmp'])
const SUPPORTED_VIDEO_MIME_TYPES = new Set(['video/mp4', 'video/webm', 'video/quicktime', 'video/x-matroska', 'video/x-msvideo', 'video/mpeg'])
const SUPPORTED_AUDIO_MIME_TYPES = new Set(['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/x-m4a', 'audio/aac', 'audio/flac', 'audio/ogg', 'audio/webm'])
const SUPPORTED_TEXT_MIME_TYPES = new Set(['text/plain', 'text/markdown', 'text/x-markdown', 'application/pdf'])
const SUPPORTED_DOCX_MIME_TYPES = new Set(['application/vnd.openxmlformats-officedocument.wordprocessingml.document'])
const UPLOAD_ACCEPT = '.png,.jpg,.jpeg,.webp,.bmp,.mp4,.webm,.mov,.m4v,.mkv,.avi,.mp3,.wav,.m4a,.aac,.flac,.ogg,.pdf,.txt,.md,.markdown,.docx'

function validateUploadFile(file: File): string | null {
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  const mime = (file.type || '').toLowerCase()

  if (ext === 'gif' || mime === 'image/gif') {
    return t('home.validation.gifNotSupported')
  }

  if (SUPPORTED_STATIC_IMAGE_EXTENSIONS.has(ext) || SUPPORTED_STATIC_IMAGE_MIME_TYPES.has(mime)) {
    return null
  }

  if (mime.startsWith('image/')) {
    return t('home.validation.staticImageOnly')
  }

  if (SUPPORTED_VIDEO_EXTENSIONS.has(ext) || SUPPORTED_VIDEO_MIME_TYPES.has(mime)) {
    return null
  }

  if (mime.startsWith('video/')) {
    return t('home.validation.commonVideoOnly')
  }

  if (SUPPORTED_AUDIO_EXTENSIONS.has(ext) || SUPPORTED_AUDIO_MIME_TYPES.has(mime)) {
    return null
  }

  if (mime.startsWith('audio/')) {
    return t('home.validation.commonAudioOnly')
  }

  if (SUPPORTED_TEXT_EXTENSIONS.has(ext) || SUPPORTED_TEXT_MIME_TYPES.has(mime)) {
    return null
  }

  if (ext === 'docx' || SUPPORTED_DOCX_MIME_TYPES.has(mime)) {
    return null
  }

  if (['doc', 'docm', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) {
    return t('home.validation.docxOnly')
  }

  return t('home.validation.unsupportedType')
}

function formatRelativeTime(input?: string) {
  if (!input) return t('common.unknownTime')

  const date = new Date(input)
  if (Number.isNaN(date.getTime())) return t('common.unknownTime')

  const diffMs = Date.now() - date.getTime()
  const diffMinutes = Math.max(0, Math.floor(diffMs / 60000))

  if (diffMinutes < 1) return t('common.justNow')
  if (diffMinutes < 60) return t('common.minutesAgo', { count: diffMinutes })

  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return t('common.hoursAgo', { count: diffHours })
  if (diffHours < 48) return t('common.yesterday')

  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return t('common.daysAgo', { count: diffDays })
  if (diffDays < 30) return t('common.weeksAgo', { count: Math.floor(diffDays / 7) })
  if (diffDays < 365) return t('common.monthsAgo', { count: Math.floor(diffDays / 30) })
  return t('common.yearsAgo', { count: Math.floor(diffDays / 365) })
}

function mapSourceType(sourceType: string) {
  const sourceMap: Record<string, string> = {
    github_star: 'github',
    bilibili: 'bilibili',
    bilibili_subscribed: 'bilibili',
    article: 'article',
    upload: 'upload',
  }

  return sourceMap[sourceType] || sourceType
}

function getAbsoluteMediaUrl(url?: string) {
  if (!url) return '#'
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url
  }
  const normalizedPath = url.startsWith('/') ? url : `/${url}`
  return `${API_BASE_URL}${normalizedPath}`
}

function isPdfDocument(item?: LocalSearchResult | null) {
  if (!item) return false
  return item.intentType === 'document' && item.uploadMimeType === 'application/pdf'
}

const parseSupportedPlugins = computed(() => parsePlugins.value)

function toPlainTextSnippet(input?: string | null, fallback: string = '', maxLength: number = 180) {
  const effectiveFallback = fallback || t('common.noDescription')
  if (!input) return effectiveFallback

  const plainText = input
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/<[^>]+>/g, ' ')
    .replace(/[#>*_`~-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  if (!plainText) return effectiveFallback
  if (plainText.length <= maxLength) return plainText
  return `${plainText.slice(0, maxLength).trimEnd()}...`
}

function normalizeRawItem(item: RawItem, index: number): LocalSearchResult {
  const metadata = item.metadata_extra || {}
  const source = mapSourceType(item.source_type)
  const tags = Array.isArray(item.tags) && item.tags.length > 0 ? [...item.tags] : []
  const lang = typeof metadata.lang === 'string' ? metadata.lang : ''

  if (lang && !tags.includes(lang)) {
    tags.unshift(lang)
  }

  const hasLongSummary = Boolean(metadata.has_long_summary)
  const authorName = extractAuthorName(source, metadata, item)
  const time = source === 'github' && typeof metadata.pushed_at === 'string'
    ? formatRelativeTime(metadata.pushed_at)
    : formatRelativeTime(item.created_at)

  return {
    id: item.id,
    title: item.title,
    summary: toPlainTextSnippet(item.summary || ((item as any).content_text as string | undefined) || '', t('common.noDescription')),
    long_summary: hasLongSummary ? (typeof metadata.long_summary === 'string' ? metadata.long_summary : item.summary || undefined) : undefined,
    has_long_summary: hasLongSummary,
    cover_url: typeof metadata.cover_url === 'string' ? metadata.cover_url : undefined,
    score: Math.max(0.5, 1 - index * 0.03),
    source,
    tags: tags.slice(0, 5).length > 0 ? tags.slice(0, 5) : [t('common.uncategorized')],
    authorName,
    displayTags: tags.slice(0, 5).length > 0 ? tags.slice(0, 5) : [t('common.uncategorized')],
    time,
    raw_link: item.raw_link || '#',
    isRead: Boolean(item.is_read),
    isWatchLater: Boolean(item.is_watch_later),
    isFavorited: Boolean(item.is_favorited),
    keyframes: metadata.keyframes || [],
    intentType: item.intent,
    metadataExtra: metadata,
    isLocalUpload: item.source_type === 'upload',
    uploadMimeType: typeof metadata.mime_type === 'string' ? metadata.mime_type : undefined,
  }
}

function normalizeSearchResult(item: SearchResult): LocalSearchResult {
  const metadataExtra = (item as any).metadata_extra || {}
  const authorName = extractAuthorName(item.source, metadataExtra, item)
  const hasLongSummary = Boolean(item.has_long_summary)
  const displaySummary = toPlainTextSnippet(item.summary || ((item as any).content_text as string | undefined), t('common.noDescription'))

  return {
    ...item,
    summary: displaySummary,
    long_summary: hasLongSummary && typeof item.long_summary === 'string' ? item.long_summary : undefined,
    has_long_summary: hasLongSummary,
    authorName,
      displayTags: item.tags.length > 0 ? item.tags : [t('common.uncategorized')],
    raw_link: item.raw_link || (item.source === 'github' ? `https://github.com/${item.title}` : '#'),
    isRead: Boolean(item.is_read),
    isWatchLater: Boolean(item.is_watch_later),
    isFavorited: Boolean(item.is_favorited),
    keyframes: (item as any).keyframes || [],
    intentType: (item as any).intent || 'article',
    metadataExtra,
    isLocalUpload: (item as any).source_type === 'upload',
    uploadMimeType: metadataExtra?.mime_type,
  }
}

function getDisplayTags(item: LocalSearchResult) {
  return item.displayTags && item.displayTags.length > 0 ? item.displayTags : item.tags
}

function syncSelectedItemFromRoute() {
  const targetItemId = typeof route.query.item === 'string' ? route.query.item : ''
  if (!targetItemId) return
  const matchedItem = searchResults.value.find((item) => item.id === targetItemId)
  if (!matchedItem) return
  selectedItem.value = matchedItem
  isSheetOpen.value = true
}

async function loadData(query: string = '') {
  await flushPendingReads()
  isLoading.value = true
  try {
    const sourceFilter = activeSource.value === 'all' ? undefined : activeSource.value

    if (isWatchLaterPage.value) {
      const items = await getItems(undefined, 0, { watchLaterOnly: true, source_type: sourceFilter })
      const normalized = items.map((item, index) => normalizeRawItem(item, index))
      initialAnchorItemId.value = null
      if (query.trim()) {
        const keyword = query.trim().toLowerCase()
        searchResults.value = normalized.filter((item) =>
          item.title.toLowerCase().includes(keyword) ||
          item.summary.toLowerCase().includes(keyword) ||
          item.tags.some((tag) => tag.toLowerCase().includes(keyword))
        )
      } else {
        searchResults.value = normalized
      }
      syncSelectedItemFromRoute()
      return
    }

    if (query.trim()) {
      const results = await search({ q: query, source_type: sourceFilter })
      initialAnchorItemId.value = null
      searchResults.value = results.map(normalizeSearchResult)
      syncSelectedItemFromRoute()
      return
    }

    const items = await getItems(undefined, 0, { source_type: sourceFilter })
    const normalized = items.map((item, index) => normalizeRawItem(item, index))
    initialAnchorItemId.value = normalized.find((item) => item.isRead)?.id ?? null
    searchResults.value = normalized
    syncSelectedItemFromRoute()
  } catch (error) {
    console.error('Search failed:', error)
    initialAnchorItemId.value = null
    searchResults.value = []
  } finally {
    isLoading.value = false
  }
}

async function handleSearch() {
  await loadData(searchQuery.value)
}

async function handleSourceClick(sourceId: string) {
  if (activeSource.value === sourceId) return
  activeSource.value = sourceId
  searchResults.value = []
  await loadData(searchQuery.value)
}

onMounted(async () => {
  try {
    activePlugins.value = await getActivePlugins()
    parsePlugins.value = await getParsePlugins()
  } catch (e) {
    console.error('Failed to load plugin list:', e)
  }
  void loadData()
  flushReadsInterval = window.setInterval(() => {
    void flushPendingReads()
  }, 5000)
  scrollContainer = document.querySelector('main.custom-scrollbar')
  scrollContainer?.addEventListener('scroll', updateBackToTopVisibility, { passive: true })
  updateBackToTopVisibility()
})

onBeforeUnmount(() => {
  if (observer) {
    observer.disconnect()
    observer = null
  }

  visibilityTimers.forEach((timerId) => window.clearTimeout(timerId))
  visibilityTimers.clear()

  if (flushReadsInterval !== undefined) {
    clearInterval(flushReadsInterval)
    flushReadsInterval = undefined
  }

  scrollContainer?.removeEventListener('scroll', updateBackToTopVisibility)
  scrollContainer = null
  void flushPendingReads()
})

const getSourceIcon = (source: string) => {
  if (source === 'github') return Github
  if (source === 'bilibili') return Tv
  if (source === 'upload') return Upload
  return FileText
}

const gridClass = computed(() => {
  if (layoutMode.value === 'list') return 'grid-cols-1 max-w-4xl mx-auto gap-8'
  if (layoutMode.value === 'grid') return 'grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-6'
  if (layoutMode.value === 'compact') return 'grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3'
  return ''
})

const skeletonCount = 6

function handleCardClick(item: LocalSearchResult) {
  if (item.isLocalUpload) {
    selectedItem.value = item
    isSheetOpen.value = true
    return
  }
  if (item.raw_link && item.raw_link !== '#') {
    window.open(item.raw_link, '_blank')
  }
}

function handleAISummary(item: LocalSearchResult) {
  selectedItem.value = item
  isSheetOpen.value = true
  isSummarizing.value = pendingSummaryItemId.value === item.id

  if (pendingSummaryItemId.value === item.id) {
    startPollingSummaryStatus(item.id)
    return
  }

  if (!item.has_long_summary) {
    setTimeout(() => {
      handleGenerateSummary()
    }, 300)
  }
}

async function handleAddToWatchLater(item: LocalSearchResult) {
  try {
    const response = await toggleItemWatchLater(item.id)
    updateLocalItemState(item.id, {
      isRead: response.is_read,
      isWatchLater: response.is_watch_later,
      isFavorited: response.is_favorited,
    })
    toast({
      title: response.is_watch_later ? t('home.addedToWatchLater') : t('home.removedFromWatchLater'),
      description: item.title,
    })
  } catch (error) {
    console.error('Failed to toggle watch later state:', error)
    toast({
      title: t('home.actionFailed'),
      description: resolveApiErrorMessage(error),
      variant: 'destructive',
    })
  }
}

async function handleToggleFavorite(item: LocalSearchResult) {
  try {
    const response = await toggleItemFavorite(item.id)
    updateLocalItemState(item.id, {
      isRead: response.is_read,
      isWatchLater: response.is_watch_later,
      isFavorited: response.is_favorited,
    })
    toast({
      title: response.is_favorited ? t('home.favoritedSuccess') : t('home.unfavoritedSuccess'),
      description: item.title,
    })
  } catch (error) {
    console.error('Failed to toggle favorite state:', error)
    toast({
      title: t('home.actionFailed'),
      description: resolveApiErrorMessage(error),
      variant: 'destructive',
    })
  }
}

function handleClearRecord() {
  console.log('Clearing preview item:', selectedItem.value?.title)
  isSheetOpen.value = false
  selectedItem.value = null
}

function getKeyframeAbsoluteUrl(frameUrl: string) {
  return getAbsoluteMediaUrl(frameUrl)
}

function openKeyframePreview(frameUrl: string, index: number) {
  keyframePreviewUrl.value = getKeyframeAbsoluteUrl(frameUrl)
  keyframePreviewLabel.value = `${t('home.keyframes')} ${index + 1}`
  keyframePreviewIndex.value = index
}

function closeKeyframePreview() {
  keyframePreviewUrl.value = null
  keyframePreviewLabel.value = ''
  keyframePreviewIndex.value = 0
}

async function downloadKeyframe(frameUrl: string, index: number) {
  try {
    const absoluteUrl = getKeyframeAbsoluteUrl(frameUrl)
    const response = await fetch(absoluteUrl)
    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = `Pekno-keyframe-${selectedItem.value?.id || 'frame'}-${index + 1}.jpg`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(objectUrl)
  } catch (error) {
    console.error('Failed to save keyframe image:', error)
    toast({
      title: t('home.saveFailed'),
      description: t('home.saveKeyframeFailed'),
      variant: 'destructive',
    })
  }
}

async function handleGenerateSummary() {
  if (!selectedItem.value || isSummarizing.value) return

  try {
    isSummarizing.value = true
    const itemId = selectedItem.value.id

    if (pendingSummaryItemId.value === itemId) {
      startPollingSummaryStatus(itemId)
      return
    }

    const response = await summarizeItem(itemId)
    if (response.status === 'skipped') {
      isSummarizing.value = false
      toast({
        title: t('home.skipped'),
        description: response.message,
      })
      return
    }
    currentTaskId.value = response.task_id
    pendingSummaryItemId.value = itemId

    toast({
      title: t('home.aiSummaryRunningTitle'),
      description: t('home.aiSummaryRunningDesc'),
    })

    startPollingSummaryStatus(itemId)
  } catch (error) {
    console.error('Failed to start AI summary generation:', error)
    isSummarizing.value = false
    toast({
      title: t('home.aiSummaryFailedTitle'),
      description: resolveApiErrorMessage(error),
      variant: 'destructive',
    })
  }
}

function startPollingSummaryStatus(itemId: string) {
  if (pollInterval.value !== undefined) {
    clearInterval(pollInterval.value)
  }

  pollInterval.value = window.setInterval(async () => {
    try {
      const status = await getItemSummaryStatus(itemId)

      if (status.status === 'completed') {
        if (pollInterval.value !== undefined) {
          clearInterval(pollInterval.value)
          pollInterval.value = undefined
        }
        pendingSummaryItemId.value = null
        isSummarizing.value = selectedItem.value?.id === itemId ? false : isSummarizing.value
        await loadData(searchQuery.value)

        if (selectedItem.value && selectedItem.value.id === itemId) {
          const updatedItem = searchResults.value.find(r => r.id === itemId)
          if (updatedItem) {
            selectedItem.value = updatedItem
          }
        }

        toast({
          title: t('home.aiSummaryCompletedTitle'),
          description: t('home.aiSummaryCompletedDesc'),
        })
      } else if (status.status === 'not_found') {
        if (pollInterval.value !== undefined) {
          clearInterval(pollInterval.value)
          pollInterval.value = undefined
        }
        pendingSummaryItemId.value = null
        isSummarizing.value = false
      }
    } catch (error) {
      console.error('Failed to query summary status:', error)
    }
  }, 3000)
}

watch(isSheetOpen, (newVal) => {
  if (!newVal) {
    isSummarizing.value = false
    closeKeyframePreview()
  } else if (selectedItem.value && pendingSummaryItemId.value === selectedItem.value.id) {
    isSummarizing.value = true
  }
})

function isCardActive(item: LocalSearchResult) {
  return selectedItem.value?.id === item.id && isSheetOpen.value
}

function openExternalLink(url?: string) {
  if (url && url !== '#') {
    window.open(getAbsoluteMediaUrl(url), '_blank')
  }
}

function handleUploadFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const nextFile = target.files?.[0] || null
  if (!nextFile) {
    uploadFile.value = null
    return
  }

  const validationError = validateUploadFile(nextFile)
  if (validationError) {
    uploadFile.value = null
    target.value = ''
    toast({
      title: t('errors.ERR_UPLOAD_UNSUPPORTED_TYPE'),
      description: validationError,
      variant: 'destructive',
    })
    return
  }

  uploadFile.value = nextFile
}

function resetAddContentDialog() {
  addContentTab.value = 'upload'
  uploadFile.value = null
  uploadTitle.value = ''
  uploadSummary.value = ''
  retentionDays.value = -1
  parsePluginName.value = parseSupportedPlugins.value[0]?.id || 'bilibili_sync'
  parseUrl.value = ''
  isSubmittingContent.value = false
}

async function handleSubmitUpload(autoFavorite: boolean = false) {
  if (!uploadFile.value || isSubmittingContent.value) return
  const validationError = validateUploadFile(uploadFile.value)
  if (validationError) {
    toast({
      title: t('errors.ERR_UPLOAD_UNSUPPORTED_TYPE'),
      description: validationError,
      variant: 'destructive',
    })
    return
  }
  try {
    isSubmittingContent.value = true
    const createdItem = await uploadItem(uploadFile.value, {
      title: uploadTitle.value.trim() || undefined,
      summary: uploadSummary.value.trim() || undefined,
      retention_days: retentionDays.value,
      auto_favorite: autoFavorite,
    })
    const normalized = normalizeRawItem(createdItem, 0)
    isAddDialogOpen.value = false
    resetAddContentDialog()
    await loadData(searchQuery.value)
    selectedItem.value = normalized
    isSheetOpen.value = true
    toast({
      title: autoFavorite ? t('home.uploadAndFavorited') : t('home.uploaded'),
      description: t('home.uploadQueuedDesc', { title: normalized.title }),
    })
  } catch (error: any) {
    if (error?.response?.status === 409 && error?.response?.data?.deduplicated) {
      const dedup = error.response.data as UploadDedupResponse
      const normalized = normalizeRawItem(dedup.item, 0)
      isAddDialogOpen.value = false
      resetAddContentDialog()
      await loadData(searchQuery.value)
      selectedItem.value = normalized
      isSheetOpen.value = true
      toast({
        title: autoFavorite ? t('home.linkedExistingAndFavorited') : t('home.fileAlreadyExists'),
        description: dedup.message,
      })
      return
    }
    toast({
      title: t('home.uploadFailed'),
      description: resolveApiErrorMessage(error),
      variant: 'destructive',
    })
  } finally {
    isSubmittingContent.value = false
  }
}

async function handleSubmitParse() {
  if (!parseUrl.value.trim() || isSubmittingContent.value) return
  try {
    isSubmittingContent.value = true
    const response = await parseItemUrl(parsePluginName.value, parseUrl.value.trim(), retentionDays.value)
    isAddDialogOpen.value = false
    resetAddContentDialog()
    toast({
      title: t('home.parseSubmitted'),
      description: response.message,
    })
    void loadData(searchQuery.value)
    window.setTimeout(() => {
      void loadData(searchQuery.value)
    }, 3000)
    window.setTimeout(() => {
      void loadData(searchQuery.value)
    }, 7000)
  } catch (error: any) {
    toast({
      title: t('home.parseFailed'),
      description: resolveApiErrorMessage(error),
      variant: 'destructive',
    })
  } finally {
    isSubmittingContent.value = false
  }
}

function updateLocalItemState(itemId: string, patch: Partial<Pick<LocalSearchResult, 'isRead' | 'isWatchLater' | 'isFavorited'>>) {
  searchResults.value = searchResults.value.map((entry) =>
    entry.id === itemId ? { ...entry, ...patch } : entry
  )

  if (selectedItem.value?.id === itemId) {
    selectedItem.value = {
      ...selectedItem.value,
      ...patch,
    }
  }
}

function queuePendingRead(itemId: string) {
  const item = searchResults.value.find((entry) => entry.id === itemId)
  if (!item || item.isRead) {
    return
  }
  pendingReadIds.add(itemId)
}

async function flushPendingReads() {
  const itemIds = Array.from(pendingReadIds).filter((itemId) => {
    const item = searchResults.value.find((entry) => entry.id === itemId)
    return item && !item.isRead
  })

  if (itemIds.length === 0) {
    pendingReadIds.clear()
    return
  }

  try {
    await markItemsReadBatch(itemIds)
    for (const itemId of itemIds) {
      pendingReadIds.delete(itemId)
      updateLocalItemState(itemId, { isRead: true })
    }
  } catch (error) {
    console.error('Failed to sync batch read state:', error)
  }
}

function clearVisibilityTimer(itemId: string) {
  const timerId = visibilityTimers.get(itemId)
  if (timerId !== undefined) {
    window.clearTimeout(timerId)
    visibilityTimers.delete(itemId)
  }
}

function setCardRef(itemId: string, el: Element | null) {
  clearVisibilityTimer(itemId)

  if (observer) {
    const oldElement = cardElements.get(itemId)
    if (oldElement) {
      observer.unobserve(oldElement)
    }
  }

  if (el instanceof HTMLElement) {
    cardElements.set(itemId, el)
    el.dataset.itemId = itemId
    if (observer) {
      observer.observe(el)
    }
  } else {
    cardElements.delete(itemId)
  }
}

function setupIntersectionObserver() {
  if (observer) {
    observer.disconnect()
  }

  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const itemId = (entry.target as HTMLElement).dataset.itemId
        if (!itemId) {
          continue
        }

        const item = searchResults.value.find((record) => record.id === itemId)
        if (!item || item.isRead) {
          clearVisibilityTimer(itemId)
          continue
        }

        if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
          if (!visibilityTimers.has(itemId)) {
            const timerId = window.setTimeout(() => {
              queuePendingRead(itemId)
              visibilityTimers.delete(itemId)
            }, 1500)
            visibilityTimers.set(itemId, timerId)
          }
        } else {
          clearVisibilityTimer(itemId)
        }
      }
    },
    {
      threshold: [0.6],
    }
  )

  cardElements.forEach((element) => observer?.observe(element))
}

watch(
  searchResults,
  async () => {
    await nextTick()
    setupIntersectionObserver()
    syncSelectedItemFromRoute()
  },
  { flush: 'post' }
)

watch(
  () => route.name,
  async () => {
    searchQuery.value = ''
    activeSource.value = 'all'
    initialAnchorItemId.value = null
    await loadData()
  }
)

watch(
  () => route.query.item,
  async () => {
    await nextTick()
    syncSelectedItemFromRoute()
  }
)

watch(parseUrl, (value) => {
  const normalized = value.toLowerCase()
  if (normalized.includes('bilibili.com') || normalized.includes('b23.tv')) {
    parsePluginName.value = 'bilibili_sync'
  } else if (normalized.includes('github.com')) {
    parsePluginName.value = 'github_stars'
  }
})

watch(isAddDialogOpen, (isOpen) => {
  if (isOpen && parseSupportedPlugins.value.length > 0 && !parseSupportedPlugins.value.find((item) => item.id === parsePluginName.value)) {
    parsePluginName.value = parseSupportedPlugins.value[0]?.id || 'bilibili_sync'
  }
  if (!isOpen) {
    resetAddContentDialog()
  }
})
</script>

<template>
  <MainLayout
    v-model:layout="layoutMode"
    v-model:search-query="searchQuery"
    @search="handleSearch"
    @add-content="isAddDialogOpen = true"
  >
    <div class="mb-4">
      <h2 class="text-2xl font-bold">{{ pageTitle }}</h2>
      <p class="text-muted-foreground">{{ pageSubtitle }}</p>
    </div>

    <!-- Pill Navigation (Filters) -->
    <div class="flex overflow-x-auto gap-2 mb-6 hide-scrollbar pb-2">
      <button 
        @click="handleSourceClick('all')"
        :class="[
          'rounded-full px-4 py-1.5 text-sm font-medium whitespace-nowrap transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary/20',
          activeSource === 'all' 
            ? 'bg-primary text-primary-foreground shadow-md' 
            : 'bg-muted/50 text-muted-foreground hover:bg-muted/80 hover:text-foreground'
        ]"
      >
        {{ t('home.allSources') }}
      </button>
      <button 
        v-for="plugin in activePlugins" 
        :key="plugin.id"
        @click="handleSourceClick(plugin.source_type)"
        :class="[
          'rounded-full px-4 py-1.5 text-sm font-medium whitespace-nowrap transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary/20 cursor-pointer',
          activeSource === plugin.source_type
            ? 'bg-primary text-primary-foreground shadow-md' 
            : 'bg-muted/50 text-muted-foreground hover:bg-muted/80 hover:text-foreground'
        ]"
      >
        {{ plugin.name }}
      </button>
    </div>

    <div v-if="isLoading" :class="['grid transition-all duration-300', gridClass]">
      <Card v-for="i in skeletonCount" :key="i" class="bg-card border-border overflow-hidden flex flex-col">
        <div v-if="layoutMode !== 'compact'" class="aspect-video bg-muted/30 flex-shrink-0">
          <Skeleton class="w-full h-full" />
        </div>
        <CardHeader :class="layoutMode === 'compact' ? 'p-3' : 'p-5 space-y-3'">
          <Skeleton :class="layoutMode === 'compact' ? 'h-4 w-3/4' : 'h-6 w-full'" />
          <div v-if="layoutMode !== 'compact'" class="space-y-2">
            <Skeleton class="h-4 w-full" />
            <Skeleton class="h-4 w-2/3" />
          </div>
        </CardHeader>
        <CardContent v-if="layoutMode !== 'compact'" class="px-5 pb-5 pt-0 mt-auto">
          <div class="flex items-center justify-between border-t border-border/40 pt-4 gap-3">
            <div class="flex gap-2 flex-wrap flex-1">
              <Skeleton v-for="j in 3" :key="j" class="h-5 w-16" />
            </div>
            <Skeleton class="h-4 w-20" />
          </div>
        </CardContent>
      </Card>
    </div>

    <div v-else :class="['grid transition-all duration-300', gridClass]">
      <template v-for="item in searchResults" :key="item.id">
        <div
          v-if="!isWatchLaterPage && initialAnchorItemId === item.id"
          class="col-span-full flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-primary"
        >
          <span class="text-base">👇</span>
          <span class="font-medium">{{ t('home.resumeHere') }}</span>
        </div>

        <Card
          :ref="(el) => setCardRef(item.id, ((el as any)?.$el ?? el) as Element | null)"
          :class="[
            'bg-card text-card-foreground border-border transition-all cursor-pointer overflow-visible group flex flex-col relative',
            isCardActive(item) ? 'border-primary ring-2 ring-primary/20 shadow-md' : 'hover:border-primary/20 shadow-sm hover:shadow-md',
            item.isFavorited ? 'border-red-300/70 shadow-red-100/20' : '',
            item.isWatchLater && !item.isFavorited ? 'border-amber-300/60 shadow-amber-100/20' : '',
            layoutMode === 'compact' ? 'rounded-lg' : 'rounded-xl'
          ]"
          @click="handleCardClick(item)"
          @mouseenter="handleCardMouseEnter(item)"
          @mouseleave="handleCardMouseLeave(item)"
        >
        <HoverPreview 
          v-if="activeHoverItemId === item.id && hoverDataMap[item.id]"
          :blocks="hoverDataMap[item.id] || []"
          class="absolute z-[100] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 cursor-auto pointer-events-auto"
          @click.stop
        />
        <div
          v-if="item.has_long_summary || item.isFavorited || item.isWatchLater"
          class="absolute top-2 left-2 z-10 flex items-center gap-1.5"
        >
          <div
            v-if="item.has_long_summary"
            class="flex h-7 w-7 items-center justify-center rounded-full bg-background/90 shadow-sm backdrop-blur-sm"
            :title="t('home.alreadySummarized')"
          >
            <Star class="h-4 w-4 text-yellow-500 fill-yellow-500 animate-pulse" />
          </div>
          <div
            v-if="item.isFavorited"
            class="flex h-7 w-7 items-center justify-center rounded-full bg-background/90 shadow-sm backdrop-blur-sm"
            :title="t('home.alreadyFavorited')"
          >
            <Heart class="h-4 w-4 text-red-500 fill-red-500" />
          </div>
          <div
            v-if="item.isWatchLater"
            class="flex h-7 w-7 items-center justify-center rounded-full bg-background/90 shadow-sm backdrop-blur-sm"
            :title="t('home.alreadyWatchLater')"
          >
              <Clock3 class="h-4 w-4 text-amber-600" />
          </div>
        </div>

        <div
          class="absolute top-2 right-2 z-20"
          @click.stop
          @mouseenter.stop="suppressCardHover(item.id)"
          @mouseleave.stop="releaseCardHover(item.id)"
        >
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="h-8 w-8 bg-background/80 backdrop-blur-sm hover:bg-background"
                @click.stop
              >
                <MoreVertical class="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="w-48">
              <DropdownMenuItem @click.stop="handleAISummary(item)">
                <Sparkles class="mr-2 h-4 w-4 text-primary" />
                <span>{{ t('home.aiSummary') }}</span>
              </DropdownMenuItem>
              <DropdownMenuItem @click.stop="handleAddToWatchLater(item)">
                  <component :is="item.isWatchLater ? Clock4 : Clock3" class="mr-2 h-4 w-4" />
                <span>{{ item.isWatchLater ? t('home.removeWatchLater') : t('home.addWatchLater') }}</span>
              </DropdownMenuItem>
              <DropdownMenuItem @click.stop="handleToggleFavorite(item)">
                <component :is="item.isFavorited ? HeartOff : Heart" class="mr-2 h-4 w-4" />
                <span>{{ item.isFavorited ? t('home.cancelFavorite') : t('home.favorite') }}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div
          v-if="layoutMode !== 'compact' && item.isLocalUpload && item.intentType === 'video'"
          class="h-44 flex items-center justify-center relative overflow-hidden border-b border-border/40 flex-shrink-0 rounded-t-xl bg-black"
        >
          <video
            :src="getAbsoluteMediaUrl(item.raw_link)"
            class="w-full h-full object-cover"
            muted
            preload="metadata"
          />
        </div>

        <div v-else-if="layoutMode !== 'compact' && item.cover_url" class="h-44 flex items-center justify-center relative overflow-hidden border-b border-border/40 flex-shrink-0 rounded-t-xl">
          <img
            :src="getAbsoluteMediaUrl(item.cover_url)"
            alt="Cover"
            class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            @error="(e) => { (e.target as HTMLImageElement).parentElement!.style.display = 'none'; item.cover_url = undefined }"
          />
        </div>

        <CardHeader :class="layoutMode === 'compact' ? 'p-3 flex-row items-center gap-3 space-y-0' : 'p-5 space-y-3'">
          <component v-if="layoutMode === 'compact'" :is="getSourceIcon(item.source)" class="w-4 h-4 text-primary shrink-0" />

          <div class="min-w-0 flex-1">
            <CardTitle
              :class="[
                'font-bold tracking-tight group-hover:text-primary transition-colors',
                layoutMode === 'compact' ? 'text-sm truncate' : 'text-xl line-clamp-2 break-all'
              ]"
              :title="item.title"
            >
              {{ item.title }}
            </CardTitle>

            <p v-if="layoutMode === 'list'" class="text-muted-foreground leading-relaxed text-base mt-3 line-clamp-3">
              {{ item.summary }}
            </p>
            <p v-else-if="layoutMode === 'grid'" class="text-muted-foreground mt-2 text-sm line-clamp-2">
              {{ item.summary }}
            </p>
          </div>
        </CardHeader>

        <CardContent v-if="layoutMode !== 'compact'" class="px-5 pb-5 pt-0 mt-auto">
          <div class="flex items-center justify-between border-t border-border/40 pt-4 gap-3 min-w-0">
            <div class="flex min-w-0 flex-1 gap-2 flex-wrap">
              <Badge
                v-for="tag in getDisplayTags(item)"
                :key="tag"
                variant="secondary"
                class="min-w-0 max-w-[8.5rem] justify-start bg-muted hover:bg-muted/80 text-xs font-normal"
                :title="tag"
              >
                <span class="min-w-0 truncate">{{ tag }}</span>
              </Badge>
            </div>

            <div class="flex min-w-0 max-w-[48%] flex-shrink-0 flex-col items-end gap-1 text-muted-foreground">
              <div
                v-if="item.authorName"
                class="inline-flex min-w-0 max-w-full items-center gap-1.5"
                :title="item.authorName"
              >
                <UserRound class="h-3.5 w-3.5 shrink-0" />
                <span class="truncate text-xs font-medium">{{ item.authorName }}</span>
              </div>
              <div class="flex min-w-0 items-center justify-end gap-2">
                <Badge variant="outline" class="h-5 px-1.5 py-0 font-mono text-[10px] border-primary/20 bg-primary/5 text-primary">
                  {{ Math.floor(item.score * 100) }}%
                </Badge>
                <component :is="getSourceIcon(item.source)" class="h-4 w-4 shrink-0" :title="t('home.source')" />
                <span class="truncate text-xs font-medium">{{ item.time }}</span>
              </div>
            </div>
          </div>
        </CardContent>
        </Card>
      </template>
    </div>

    <div v-if="!isLoading && searchResults.length === 0" class="text-center py-20">
      <div class="text-muted-foreground text-lg">{{ t('home.emptyTitle') }}</div>
      <p class="text-muted-foreground/60 text-sm mt-2">{{ t('home.emptyDescription') }}</p>
    </div>

    <transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="translate-y-3 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="translate-y-3 opacity-0"
    >
      <Button
        v-if="showBackToTop"
        size="icon"
        class="fixed bottom-6 right-6 z-40 h-11 w-11 rounded-full shadow-lg"
        :title="t('home.backToTop')"
        @click="scrollToTop"
      >
        <ArrowUp class="h-4 w-4" />
      </Button>
    </transition>
  </MainLayout>

  <Sheet v-model:open="isSheetOpen">
    <SheetContent
      class="w-full sm:max-w-xl p-0 flex flex-col h-full max-h-screen"
      side="right"
      @interact-outside="(event) => { if (keyframePreviewUrl) event.preventDefault() }"
    >
      <SheetHeader class="p-6 border-b border-border shrink-0">
        <div class="flex items-start justify-between">
          <div class="flex-1 min-w-0">
            <SheetTitle class="text-xl font-bold truncate">
              {{ selectedItem?.title }}
            </SheetTitle>
            <SheetDescription class="flex items-center gap-2 mt-2">
              <component v-if="selectedItem" :is="getSourceIcon(selectedItem.source)" class="w-4 h-4" />
              <span>{{ selectedItem?.source }}</span>
              <span class="text-muted-foreground">•</span>
              <span>{{ selectedItem?.time }}</span>
            </SheetDescription>
          </div>
          <Button
            v-if="selectedItem?.raw_link && selectedItem.raw_link !== '#'"
            variant="ghost"
            size="sm"
            class="ml-2"
            @click="openExternalLink(selectedItem.raw_link)"
          >
            <ExternalLink class="w-4 h-4 mr-1" />
            {{ t('home.visit') }}
          </Button>
        </div>
      </SheetHeader>

      <ScrollArea class="flex-1 overflow-y-auto p-4">
        <div class="space-y-6">
          <div v-if="selectedItem?.isLocalUpload">
            <div class="flex items-center gap-2 mb-3">
              <Upload class="w-5 h-5 text-primary" />
              <h3 class="font-semibold text-lg">{{ t('home.contentPreview') }}</h3>
            </div>
            <div class="rounded-lg border bg-muted/30 p-3">
              <img
                v-if="selectedItem.intentType === 'image'"
                :src="getAbsoluteMediaUrl(selectedItem.raw_link)"
                :alt="selectedItem.title"
                class="w-full max-h-[50vh] object-contain rounded-md"
              />
              <video
                v-else-if="selectedItem.intentType === 'video'"
                :src="getAbsoluteMediaUrl(selectedItem.raw_link)"
                controls
                class="w-full max-h-[50vh] rounded-md bg-black"
              />
              <audio
                v-else-if="selectedItem.intentType === 'audio'"
                :src="getAbsoluteMediaUrl(selectedItem.raw_link)"
                controls
                class="w-full"
              />
              <div v-else-if="isPdfDocument(selectedItem)" class="flex flex-col gap-3">
                <p class="text-sm text-muted-foreground">{{ t('home.pdfUploaded') }}</p>
                <div class="flex gap-2">
                  <Button variant="outline" @click="openExternalLink(selectedItem.raw_link)">
                    <ExternalLink class="w-4 h-4 mr-2" />
                    {{ t('home.openPdf') }}
                  </Button>
                  <Button variant="outline" @click="openExternalLink(selectedItem.raw_link)">
                    <Download class="w-4 h-4 mr-2" />
                    {{ t('home.downloadFile') }}
                  </Button>
                </div>
              </div>
              <div v-else class="flex flex-col gap-3">
                <p class="text-sm text-muted-foreground">{{ t('home.docPreviewUnsupported') }}</p>
                <Button variant="outline" class="w-fit" @click="openExternalLink(selectedItem.raw_link)">
                  <ExternalLink class="w-4 h-4 mr-2" />
                  {{ t('home.openFile') }}
                </Button>
              </div>
            </div>
          </div>

          <div>
            <div class="flex items-center gap-2 mb-3">
              <Sparkles class="w-5 h-5 text-primary" />
              <h3 class="font-semibold text-lg">{{ t('home.aiSummaryPanel') }}</h3>
            </div>
            <div class="bg-muted/50 rounded-lg p-4 max-h-[50vh] overflow-y-auto markdown-body">
              <div v-html="renderedSummary"></div>
            </div>
          </div>

          <div v-if="selectedItem?.keyframes?.length" class="mt-4">
            <h4 class="font-medium mb-3">{{ t('home.keyframes') }}</h4>
            <div class="overflow-x-auto pb-4">
              <div class="inline-flex min-w-max gap-3 pr-2">
                <div
                  v-for="(frameUrl, index) in selectedItem.keyframes"
                  :key="index"
                  class="group relative shrink-0 w-48 h-28 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-all duration-300 hover:scale-[1.03] cursor-zoom-in"
                  @click="openKeyframePreview(frameUrl, index)"
                >
                  <img :src="getKeyframeAbsoluteUrl(frameUrl)" class="w-full h-full object-cover rounded-lg" />
                  <div class="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors duration-200" />
                  <div class="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex gap-2">
                    <Button
                      size="icon"
                      variant="secondary"
                      class="h-7 w-7"
                      @click.stop="downloadKeyframe(frameUrl, index)"
                    >
                      <Download class="w-3.5 h-3.5" />
                    </Button>
                  </div>
                  <Badge variant="secondary" class="absolute bottom-1 right-1 text-[10px] px-1.5 py-0 opacity-80 backdrop-blur-sm shadow-sm">Keyframe</Badge>
                </div>
              </div>
            </div>
          </div>

          <Separator />

          <div>
            <h4 class="font-medium mb-2">{{ t('home.tags') }}</h4>
            <div class="flex flex-wrap gap-2">
              <Badge v-for="tag in selectedItem?.tags" :key="tag" variant="secondary">
                {{ tag }}
              </Badge>
            </div>
          </div>

          <div v-if="selectedItem?.intentType === 'video'">
            <h4 class="font-medium mb-2">{{ t('vault.videoTranscript') }}</h4>
            <div
              v-if="selectedTranscriptSegments.length"
              class="max-h-64 space-y-2 overflow-y-auto rounded-lg border bg-muted/30 p-3"
            >
              <div
                v-for="segment in selectedTranscriptSegments"
                :key="segment.id"
                class="rounded-md border border-border/60 bg-background/80 px-3 py-2"
              >
                <div class="text-xs font-medium text-primary">
                  {{ formatMediaTimestamp(segment.start) }}
                </div>
                <div class="mt-1 whitespace-pre-wrap break-words text-sm text-muted-foreground">
                  {{ segment.text }}
                </div>
              </div>
            </div>
            <div
              v-else
              class="rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground"
            >
              {{ t('vault.transcriptUnavailable') }}
            </div>
          </div>
        </div>
      </ScrollArea>

      <div class="shrink-0 p-4 border-t bg-background mt-auto sticky bottom-0 space-y-3">
        <Button
          class="w-full"
          variant="default"
          :disabled="isSummarizing"
          @click="handleGenerateSummary"
        >
          <Loader2 v-if="isSummarizing" class="w-4 h-4 mr-2 animate-spin" />
          <Sparkles v-else class="w-4 h-4 mr-2" />
          {{ isSummarizing ? t('home.generatingAiSummary') : t('home.generateAiSummary') }}
        </Button>
        <Button
          class="w-full"
          variant="destructive"
          @click="handleClearRecord"
        >
          <Trash2 class="w-4 h-4 mr-2" />
          {{ t('home.clearRecord') }}
        </Button>
      </div>
    </SheetContent>
  </Sheet>

  <Dialog v-model:open="isAddDialogOpen">
    <DialogContent class="sm:max-w-2xl">
      <div class="space-y-6">
        <div>
          <h3 class="text-xl font-bold">{{ t('home.addContentTitle') }}</h3>
          <p class="text-sm text-muted-foreground mt-1">{{ t('home.addContentDesc') }}</p>
        </div>

        <div class="flex gap-2 rounded-lg bg-muted/50 p-1">
          <Button :variant="addContentTab === 'upload' ? 'default' : 'ghost'" class="flex-1" @click="addContentTab = 'upload'">
            <Upload class="w-4 h-4 mr-2" />
            {{ t('home.localUpload') }}
          </Button>
          <Button :variant="addContentTab === 'parse' ? 'default' : 'ghost'" class="flex-1" @click="addContentTab = 'parse'">
            <Link2 class="w-4 h-4 mr-2" />
            {{ t('home.linkParse') }}
          </Button>
        </div>

        <div v-if="addContentTab === 'upload'" class="space-y-4">
          <label class="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-6 py-10 text-center hover:bg-muted/40 transition-colors">
            <Upload class="w-8 h-8 mb-3 text-primary" />
            <div class="font-medium">{{ uploadFile ? uploadFile.name : t('home.selectOrDropFile') }}</div>
            <div class="text-sm text-muted-foreground mt-1">{{ t('home.uploadSupportDesc') }}</div>
            <input type="file" class="hidden" :accept="UPLOAD_ACCEPT" @change="handleUploadFileChange" />
          </label>

          <div class="space-y-2">
            <label class="text-sm font-medium">{{ t('home.optionalTitle') }}</label>
            <input v-model="uploadTitle" type="text" class="w-full rounded-md border bg-background px-3 py-2 text-sm" :placeholder="t('home.defaultUseFilename')" />
          </div>

          <div class="space-y-2">
            <label class="text-sm font-medium">{{ t('home.optionalDescription') }}</label>
            <textarea v-model="uploadSummary" class="min-h-24 w-full rounded-md border bg-background px-3 py-2 text-sm" :placeholder="t('home.uploadSummaryPlaceholder')"></textarea>
          </div>

          <div class="space-y-2">
            <label class="text-sm font-medium">{{ t('home.retentionDays') }}</label>
            <select v-model="retentionDays" class="w-full rounded-md border bg-background px-3 py-2 text-sm">
              <option :value="-1">{{ t('home.keepForever') }}</option>
              <option :value="7">{{ t('settings.daysOption', { count: 7 }) }}</option>
              <option :value="30">{{ t('settings.daysOption', { count: 30 }) }}</option>
              <option :value="90">{{ t('settings.daysOption', { count: 90 }) }}</option>
            </select>
          </div>

          <div class="flex justify-end gap-2">
            <Button variant="outline" @click="isAddDialogOpen = false">{{ t('common.cancel') }}</Button>
            <Button :disabled="!uploadFile || isSubmittingContent" @click="handleSubmitUpload(false)">
              <Loader2 v-if="isSubmittingContent" class="w-4 h-4 mr-2 animate-spin" />
              {{ t('home.upload') }}
            </Button>
            <Button
              :disabled="!uploadFile || isSubmittingContent"
              class="bg-red-600 text-white hover:bg-red-600/90"
              @click="handleSubmitUpload(true)"
            >
              <Loader2 v-if="isSubmittingContent" class="w-4 h-4 mr-2 animate-spin" />
              <Heart v-else class="w-4 h-4 mr-2" />
              {{ t('home.uploadAndFavorite') }}
            </Button>
          </div>
        </div>

        <div v-else class="space-y-4">
          <div class="space-y-2">
            <label class="text-sm font-medium">{{ t('home.parsePlugin') }}</label>
            <select v-model="parsePluginName" class="w-full rounded-md border bg-background px-3 py-2 text-sm">
              <option v-for="plugin in parseSupportedPlugins" :key="plugin.id" :value="plugin.id">
                {{ plugin.name }}
              </option>
            </select>
          </div>

          <div class="space-y-2">
            <label class="text-sm font-medium">{{ t('home.linkAddress') }}</label>
            <input v-model="parseUrl" type="url" class="w-full rounded-md border bg-background px-3 py-2 text-sm" placeholder="https://www.bilibili.com/video/... or https://github.com/owner/repo" />
            <p class="text-xs text-muted-foreground">{{ t('home.autoPluginHint') }}</p>
          </div>

          <div class="space-y-2">
            <label class="text-sm font-medium">{{ t('home.retentionDays') }}</label>
            <select v-model="retentionDays" class="w-full rounded-md border bg-background px-3 py-2 text-sm">
              <option :value="-1">{{ t('home.keepForever') }}</option>
              <option :value="7">{{ t('settings.daysOption', { count: 7 }) }}</option>
              <option :value="30">{{ t('settings.daysOption', { count: 30 }) }}</option>
              <option :value="90">{{ t('settings.daysOption', { count: 90 }) }}</option>
            </select>
          </div>

          <div class="flex justify-end gap-2">
            <Button variant="outline" @click="isAddDialogOpen = false">{{ t('common.cancel') }}</Button>
            <Button :disabled="!parseUrl.trim() || isSubmittingContent || parseSupportedPlugins.length === 0" @click="handleSubmitParse">
              <Loader2 v-if="isSubmittingContent" class="w-4 h-4 mr-2 animate-spin" />
              {{ t('home.parseAndAdd') }}
            </Button>
          </div>
        </div>
      </div>
    </DialogContent>
  </Dialog>

  <Toaster />

  <div
    v-if="keyframePreviewUrl"
    class="fixed inset-0 z-[100] bg-black/80 backdrop-blur-sm flex items-center justify-center p-6"
    @click.self="closeKeyframePreview"
  >
    <div class="relative w-full max-w-6xl">
      <div class="absolute right-0 top-0 z-10 flex gap-2">
        <Button
          variant="secondary"
          class="bg-background/90 backdrop-blur-sm"
          @click="downloadKeyframe(keyframePreviewUrl, keyframePreviewIndex)"
        >
          <Download class="w-4 h-4 mr-2" />
          {{ t('home.saveScreenshot') }}
        </Button>
        <Button
          size="icon"
          variant="secondary"
          class="bg-background/90 backdrop-blur-sm"
          @click="closeKeyframePreview"
        >
          <X class="w-4 h-4" />
        </Button>
      </div>
      <div class="rounded-2xl overflow-hidden border border-white/10 shadow-2xl bg-black">
        <img :src="keyframePreviewUrl" :alt="keyframePreviewLabel" class="w-full max-h-[85vh] object-contain" />
      </div>
      <p class="mt-3 text-center text-sm text-white/80">{{ keyframePreviewLabel }}</p>
    </div>
  </div>
</template>

<style scoped>
.hide-scrollbar::-webkit-scrollbar {
  display: none;
}
.hide-scrollbar {
  -ms-overflow-style: none; /* IE and Edge */
  scrollbar-width: none;  /* Firefox */
}
:deep(.animate-pulse) {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

@keyframes star-pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(1.1);
  }
}

.star-breathe {
  animation: star-pulse 2s ease-in-out infinite;
}

:deep(.markdown-body) {
  font-size: 0.875rem;
  line-height: 1.7;
  color: hsl(var(--foreground));
}

:deep(.markdown-body h1),
:deep(.markdown-body h2),
:deep(.markdown-body h3),
:deep(.markdown-body h4) {
  font-weight: 700;
  margin-bottom: 0.6em;
  color: hsl(var(--foreground));
  line-height: 1.3;
}

:deep(.markdown-body h1) {
  font-size: 1.5em;
  margin-top: 0.5em;
  padding: 0.4em 0.6em;
  background: hsl(var(--primary) / 0.1);
  border-left: 4px solid hsl(var(--primary));
  border-radius: 4px;
}

:deep(.markdown-body h2) {
  font-size: 1.25em;
  margin-top: 1.4em;
  padding: 0.3em 0.6em;
  border-left: 3px solid hsl(var(--primary) / 0.6);
}

:deep(.markdown-body h3) {
  font-size: 1.1em;
  margin-top: 1.2em;
  padding-left: 0.6em;
  border-left: 2px solid hsl(var(--primary) / 0.3);
}

:deep(.markdown-body h4) {
  font-size: 1em;
  margin-top: 1em;
  color: hsl(var(--muted-foreground));
}

:deep(.markdown-body p) {
  margin-bottom: 0.75em;
}

:deep(.markdown-body ul),
:deep(.markdown-body ol) {
  padding-left: 1.5em;
  margin-bottom: 0.75em;
}

:deep(.markdown-body li) {
  margin-bottom: 0.25em;
}

:deep(.markdown-body strong) {
  font-weight: 600;
  color: hsl(var(--foreground));
}

:deep(.markdown-body code) {
  background: hsl(var(--muted));
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-size: 0.85em;
  font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
}

:deep(.markdown-body pre) {
  background: hsl(var(--muted));
  border: 1px solid hsl(var(--primary) / 0.3);
  padding: 0.85em 1em;
  border-radius: 8px;
  overflow-x: auto;
  margin-bottom: 0.85em;
}

:deep(.markdown-body pre code) {
  background: none;
  padding: 0;
  font-size: 0.82em;
  line-height: 1.6;
}

:deep(.markdown-body blockquote) {
  border-left: 3px solid hsl(var(--primary));
  padding-left: 1em;
  margin-left: 0;
  margin-bottom: 0.75em;
  color: hsl(var(--muted-foreground));
}

:deep(.markdown-body a) {
  color: hsl(var(--primary));
  text-decoration: underline;
}

:deep(.markdown-body table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1em;
  font-size: 0.85em;
}

:deep(.markdown-body thead th) {
  background: hsl(var(--muted));
  font-weight: 600;
  text-align: left;
  padding: 0.5em 0.75em;
  border: 1px solid hsl(var(--border));
}

:deep(.markdown-body tbody td) {
  padding: 0.45em 0.75em;
  border: 1px solid hsl(var(--border));
}

:deep(.markdown-body tbody tr:nth-child(even)) {
  background: hsl(var(--muted) / 0.4);
}

:deep(.markdown-body hr) {
  border: none;
  border-top: 1px solid hsl(var(--border));
  margin: 1.2em 0;
}
</style>
