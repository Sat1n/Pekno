<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import MainLayout from '@/layouts/MainLayout.vue'
import MarkdownContent from '@/components/MarkdownContent.vue'
import PdfViewer from '@/components/PdfViewer.vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Archive,
  Camera,
  Check,
  ChevronDown,
  ExternalLink,
  FileAudio,
  FileImage,
  FileText,
  Film,
  FolderOpen,
  MessageSquareText,
  Pencil,
  Pin,
  Plus,
  Sparkles,
  Trash2,
  X,
} from 'lucide-vue-next'
import {
  API_BASE_URL,
  assignItemVaultCategory,
  createAnnotation,
  createVaultCategory,
  deleteVaultCategory,
  ensureVaultAsset,
  getAnnotations,
  getItems,
  getVaultCategories,
  search,
  updateVaultCategory,
  uploadAnnotationAsset,
  type AnnotationItem,
  type RawItem,
  type SearchResult,
  type VaultCategory,
} from '@/lib/api'

type InspectorTab = 'summary' | 'notes'

interface VaultSection {
  id: string
  name: string
  color: string
  items: RawItem[]
  isSystem?: boolean
}

interface TranscriptSegment {
  id: string
  start: number
  end: number
  text: string
}

const UNCATEGORIZED_CATEGORY_ID = '__uncategorized__'
const DEFAULT_UNCATEGORIZED_COLOR = '#94A3B8'
const CATEGORY_COLORS = ['#3B82F6', '#F97316', '#10B981', '#EF4444', '#8B5CF6', '#EAB308']

const favoritedItems = ref<RawItem[]>([])
const vaultCategories = ref<VaultCategory[]>([])
const searchQuery = ref('')
const searchResults = ref<RawItem[]>([])
const activeItem = ref<RawItem | null>(null)
const isLoading = ref(true)
const isSearching = ref(false)
const categoriesLoading = ref(true)
const activeInspectorTab = ref<InspectorTab>('summary')
const annotationDraft = ref('')
const annotations = ref<AnnotationItem[]>([])
const annotationsLoading = ref(false)
const savingAnnotation = ref(false)
const annotationTextareaRef = useTemplateRef<HTMLTextAreaElement>('annotationTextarea')
const videoPlayerRef = useTemplateRef<HTMLVideoElement>('videoPlayer')
const pdfViewerRef = useTemplateRef<InstanceType<typeof PdfViewer>>('pdfViewer')
const pdfViewerState = ref({
  page: 1,
  totalPages: 0,
  canGoPrev: false,
  canGoNext: false,
  zoomMode: 'fit-page' as 'fit-width' | 'fit-page' | '100' | '125' | '150',
})
const pdfPageInput = ref('1')
const pdfCaptureMode = ref(false)
const pdfZoomOptions = [
  { value: 'fit-page' as const, label: '整页' },
  { value: 'fit-width' as const, label: '适宽' },
  { value: '100' as const, label: '100%' },
  { value: '125' as const, label: '125%' },
  { value: '150' as const, label: '150%' },
]
const pendingAnnotationAnchor = ref<Record<string, any>>({})
const videoAspect = ref<{ width: number; height: number }>({ width: 16, height: 9 })
const videoCurrentTime = ref(0)
const transcriptCollapsed = ref(false)
const categoryDraft = ref('')
const creatingCategory = ref(false)
const categoryMutationLoading = ref(false)
const editingCategoryId = ref<string | null>(null)
const editingCategoryName = ref('')
const sectionOpenState = ref<Record<string, boolean>>({
  [UNCATEGORIZED_CATEGORY_ID]: true,
})
let searchDebounceTimer: number | undefined
let activeSearchRequestId = 0
const transcriptRowRefs = new Map<string, HTMLElement>()
const ensuringVaultAssetIds = new Set<string>()
const intentPillClass = 'inline-flex min-w-[2.9rem] shrink-0 items-center justify-center rounded-full border bg-background px-2.5 py-1 text-[10px] font-medium leading-none text-foreground whitespace-nowrap'

function toAbsoluteUrl(url?: string | null) {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  const normalizedPath = url.startsWith('/') ? url : `/${url}`
  return `${API_BASE_URL}${normalizedPath}`
}

function toPlainTextSnippet(input?: string | null, fallback: string = '暂无描述', maxLength: number = 180) {
  if (!input) return fallback

  const plainText = input
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/<[^>]+>/g, ' ')
    .replace(/[#>*_`~-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  if (!plainText) return fallback
  if (plainText.length <= maxLength) return plainText
  return `${plainText.slice(0, maxLength).trimEnd()}...`
}

function intentMeta(intent?: string | null) {
  switch (intent) {
    case 'video':
      return { label: '视频', icon: Film }
    case 'article':
      return { label: '文章', icon: FileText }
    case 'document':
      return { label: '文档', icon: FolderOpen }
    case 'image':
      return { label: '图片', icon: FileImage }
    case 'audio':
      return { label: '音频', icon: FileAudio }
    default:
      return { label: '其他', icon: Archive }
  }
}

function sortItemsByDate(items: RawItem[]) {
  return items.slice().sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
}

function parseTimestampValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(0, value)
  }

  if (typeof value === 'string') {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) {
      return Math.max(0, numeric)
    }

    const parts = value.split(':').map((segment) => Number(segment.trim()))
    if (parts.every((segment) => Number.isFinite(segment))) {
      if (parts.length === 3) {
        return (parts[0] as number) * 3600 + (parts[1] as number) * 60 + (parts[2] as number)
      }
      if (parts.length === 2) {
        return (parts[0] as number) * 60 + (parts[1] as number)
      }
    }
  }

  return null
}

function parseTranscriptSegments(rawTranscript: unknown): TranscriptSegment[] {
  if (!rawTranscript) return []

  let segments: unknown[] = []
  try {
    segments = Array.isArray(rawTranscript)
      ? rawTranscript
      : (JSON.parse(String(rawTranscript)) as unknown[])
  } catch {
    return []
  }

  if (!Array.isArray(segments)) return []

  return segments
    .map((segment, index) => {
      const data = typeof segment === 'object' && segment ? segment as Record<string, unknown> : {}
      const start = parseTimestampValue(data.start ?? data.start_time ?? data.timestamp)
      const end = parseTimestampValue(data.end ?? data.end_time)
      const text = String(data.text ?? data.content ?? '').trim()
      if (start === null || !text) return null
      return {
        id: `${index}-${start}`,
        start,
        end: end === null ? start : Math.max(start, end),
        text,
      } satisfies TranscriptSegment
    })
    .filter((segment): segment is TranscriptSegment => Boolean(segment))
}

function formatTimestamp(totalSeconds: number) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(safeSeconds / 3600)
  const minutes = Math.floor((safeSeconds % 3600) / 60)
  const seconds = safeSeconds % 60

  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }

  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function ensureSectionOpenState(sectionIds: string[]) {
  const nextState = { ...sectionOpenState.value }
  for (const sectionId of sectionIds) {
    if (!(sectionId in nextState)) {
      nextState[sectionId] = true
    }
  }
  sectionOpenState.value = nextState
}

const displayCount = computed(() => (isSearchMode.value ? searchResults.value.length : favoritedItems.value.length))
const isSearchMode = computed(() => searchQuery.value.trim().length > 0)
const hasNoSearchResults = computed(() => isSearchMode.value && !isSearching.value && searchResults.value.length === 0)
const favoritedItemMap = computed(() => new Map(favoritedItems.value.map((item) => [item.id, item])))

const uncategorizedSection = computed<VaultSection>(() => ({
  id: UNCATEGORIZED_CATEGORY_ID,
  name: '未分类',
  color: DEFAULT_UNCATEGORIZED_COLOR,
  isSystem: true,
  items: sortItemsByDate(favoritedItems.value.filter((item) => !item.vault_category_id)),
}))

const categorySections = computed<VaultSection[]>(() => {
  return [
    uncategorizedSection.value,
    ...vaultCategories.value
      .slice()
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name))
      .map((category) => ({
        id: category.id,
        name: category.name,
        color: category.color || CATEGORY_COLORS[category.sort_order % CATEGORY_COLORS.length] || CATEGORY_COLORS[0] || '#3B82F6',
        items: sortItemsByDate(favoritedItems.value.filter((item) => item.vault_category_id === category.id)),
      })),
  ]
})

const searchResultItems = computed(() => {
  return searchResults.value.map((item) => ({
    ...item,
    cardSummary: toPlainTextSnippet(item.content_text || item.summary || item.source_type || '', '暂无描述'),
    intentLabel: intentMeta(item.intent).label,
  }))
})

const activeKeyframes = computed<string[]>(() => {
  const keyframes = activeItem.value?.metadata_extra?.keyframes
  return Array.isArray(keyframes) ? keyframes : []
})

const summaryContent = computed(() => {
  const metadata = activeItem.value?.metadata_extra || {}
  return String(metadata.long_summary || activeItem.value?.summary || '')
})

const articleContent = computed(() => {
  const metadata = activeItem.value?.metadata_extra || {}
  return metadata.vault_readme_text || activeItem.value?.content_text || activeItem.value?.summary || '暂无可阅读内容。'
})

const openableDocumentUrl = computed(() => toAbsoluteUrl(activeItem.value?.local_asset_url || activeItem.value?.raw_link || ''))

const isPdfDocument = computed(() => {
  if (!activeItem.value || activeItem.value.intent !== 'document') return false
  const metadata = activeItem.value.metadata_extra || {}
  const mime = typeof metadata.mime_type === 'string' ? metadata.mime_type.toLowerCase() : ''
  const url = openableDocumentUrl.value.toLowerCase()
  return mime === 'application/pdf' || url.endsWith('.pdf')
})

const isVideoItem = computed(() => activeItem.value?.intent === 'video')
const isPortraitVideo = computed(() => videoAspect.value.height > videoAspect.value.width)
const transcriptSegments = computed(() => parseTranscriptSegments(activeItem.value?.metadata_extra?.raw_transcript))
const transcriptAvailable = computed(() => transcriptSegments.value.length > 0)
const currentCategoryValue = computed(() => activeItem.value?.vault_category_id || UNCATEGORIZED_CATEGORY_ID)

const activeTranscriptIndex = computed(() => {
  const currentTime = videoCurrentTime.value
  return transcriptSegments.value.findIndex((segment, index, allSegments) => {
    const nextStart = allSegments[index + 1]?.start ?? Number.POSITIVE_INFINITY
    return currentTime >= segment.start && currentTime < Math.max(segment.end, nextStart)
  })
})

function setTranscriptRowRef(id: string, element: Element | object | null) {
  if (element instanceof HTMLElement) {
    transcriptRowRefs.set(id, element)
    return
  }
  transcriptRowRefs.delete(id)
}

async function loadVaultCategories() {
  categoriesLoading.value = true
  try {
    vaultCategories.value = await getVaultCategories()
    ensureSectionOpenState([UNCATEGORIZED_CATEGORY_ID, ...vaultCategories.value.map((category) => category.id)])
  } finally {
    categoriesLoading.value = false
  }
}

function syncActiveItem(candidateItems: RawItem[]) {
  if (candidateItems.length === 0) {
    activeItem.value = null
    return
  }

  if (!activeItem.value) {
    activeItem.value = candidateItems[0] || null
    return
  }

  const matched = candidateItems.find((item) => item.id === activeItem.value?.id)
  if (matched) {
    activeItem.value = matched
    return
  }

  activeItem.value = candidateItems[0] || null
}

async function loadFavoritedItems() {
  isLoading.value = true
  try {
    favoritedItems.value = await getItems(undefined, 0, { favoritedOnly: true })
    if (!searchQuery.value.trim()) {
      syncActiveItem(favoritedItems.value)
    } else if (activeItem.value) {
      const refreshed = favoritedItems.value.find((item) => item.id === activeItem.value?.id)
      if (refreshed) {
        activeItem.value = refreshed
      }
    }
  } finally {
    isLoading.value = false
  }
}

async function loadAnnotations() {
  if (!activeItem.value) {
    annotations.value = []
    return
  }
  annotationsLoading.value = true
  try {
    annotations.value = await getAnnotations(activeItem.value.id)
  } finally {
    annotationsLoading.value = false
  }
}

async function saveAnnotation() {
  if (!activeItem.value || !annotationDraft.value.trim()) return
  savingAnnotation.value = true
  try {
    await createAnnotation(activeItem.value.id, {
      type: 'general',
      content_raw: annotationDraft.value.trim(),
      anchor_data: pendingAnnotationAnchor.value,
    })
    annotationDraft.value = ''
    pendingAnnotationAnchor.value = {}
    await loadAnnotations()
  } finally {
    savingAnnotation.value = false
  }
}

async function fillAnnotationDraft(nextDraft: string) {
  activeInspectorTab.value = 'notes'
  annotationDraft.value = nextDraft
  await nextTick()
  annotationTextareaRef.value?.focus()
  annotationTextareaRef.value?.setSelectionRange(annotationDraft.value.length, annotationDraft.value.length)
}

function mergeSearchResultIntoItem(result: SearchResult): RawItem {
  const existing = favoritedItemMap.value.get(result.id)
  if (existing) {
    return {
      ...existing,
      title: result.title,
      raw_link: result.raw_link || existing.raw_link,
      local_asset_url: result.local_asset_url ?? existing.local_asset_url,
      summary: existing.summary,
      content_text: existing.content_text,
      tags: result.tags?.length ? result.tags : existing.tags,
      intent: result.intent || existing.intent,
      metadata_extra: result.metadata_extra || existing.metadata_extra,
      vault_category_id: existing.vault_category_id,
      is_read: Boolean(result.is_read ?? existing.is_read),
      is_watch_later: Boolean(result.is_watch_later ?? existing.is_watch_later),
      is_favorited: Boolean(result.is_favorited ?? existing.is_favorited),
    }
  }

  return {
    id: result.id,
    title: result.title,
    source_type: result.source_type || result.source,
    raw_link: result.raw_link || '',
    local_asset_url: result.local_asset_url,
    summary: toPlainTextSnippet(result.summary, '暂无描述'),
    content_text: '',
    tags: result.tags || [],
    intent: result.intent || 'article',
    created_at: new Date().toISOString(),
    metadata_extra: result.metadata_extra || {},
    vault_category_id: null,
    is_read: Boolean(result.is_read),
    is_watch_later: Boolean(result.is_watch_later),
    is_favorited: Boolean(result.is_favorited),
  }
}

async function performVaultSearch(rawQuery: string) {
  const query = rawQuery.trim()
  const requestId = ++activeSearchRequestId

  if (!query) {
    isSearching.value = false
    searchResults.value = []
    syncActiveItem(favoritedItems.value)
    return
  }

  isSearching.value = true

  try {
    const results = await search({ q: query, favorited_only: true })
    if (requestId !== activeSearchRequestId) return

    const mappedResults = results
      .filter((item) => item.is_favorited !== false)
      .map(mergeSearchResultIntoItem)

    searchResults.value = mappedResults
    syncActiveItem(mappedResults)
  } catch (error) {
    if (requestId !== activeSearchRequestId) return
    console.error('Vault 搜索失败:', error)
    searchResults.value = []
    activeItem.value = null
  } finally {
    if (requestId === activeSearchRequestId) {
      isSearching.value = false
    }
  }
}

function scheduleVaultSearch(rawQuery: string) {
  if (searchDebounceTimer !== undefined) {
    window.clearTimeout(searchDebounceTimer)
  }

  searchDebounceTimer = window.setTimeout(() => {
    void performVaultSearch(rawQuery)
  }, 320)
}

function selectItem(item: RawItem) {
  activeItem.value = item
}

function toggleSection(sectionId: string) {
  sectionOpenState.value = {
    ...sectionOpenState.value,
    [sectionId]: !sectionOpenState.value[sectionId],
  }
}

function handleVideoMetadataLoaded() {
  const video = videoPlayerRef.value
  if (!video) return
  videoAspect.value = {
    width: video.videoWidth || 16,
    height: video.videoHeight || 9,
  }
}

function handleVideoTimeUpdate() {
  const video = videoPlayerRef.value
  if (!video) return
  videoCurrentTime.value = video.currentTime
}

function findNearestTranscriptSegment(seconds: number) {
  let best: TranscriptSegment | null = null
  let bestDistance = Number.POSITIVE_INFINITY

  for (const segment of transcriptSegments.value) {
    const distance = seconds < segment.start
      ? segment.start - seconds
      : seconds > segment.end
        ? seconds - segment.end
        : 0

    if (distance < bestDistance) {
      best = segment
      bestDistance = distance
    }
  }

  if (best && bestDistance <= 6) {
    return best
  }
  return null
}

function jumpToVideoTimestamp(seconds: number) {
  const video = videoPlayerRef.value
  if (!video) return
  video.currentTime = Math.max(0, seconds)
  videoCurrentTime.value = Math.max(0, seconds)
  void video.play().catch(() => {
    // Ignore autoplay restrictions; seeking is the important part.
  })
}

function captureVideoTimestamp() {
  const video = videoPlayerRef.value
  if (!video) return

  const currentSeconds = Math.max(0, Math.floor(video.currentTime))
  const transcript = findNearestTranscriptSegment(currentSeconds)
  pendingAnnotationAnchor.value = {
    media_type: 'video',
    quote_type: 'timestamp',
    timestamp_seconds: currentSeconds,
    timestamp_label: formatTimestamp(currentSeconds),
    ...(transcript
      ? {
        transcript_text: transcript.text,
        transcript_start: transcript.start,
        transcript_end: transcript.end,
      }
      : {}),
  }

  const transcriptLine = transcript ? `> 转录：${transcript.text}\n` : ''
  void fillAnnotationDraft(`> [${formatTimestamp(currentSeconds)}] 视频时间点\n${transcriptLine}\n我的思考：`)
}

function jumpToPdfAnnotationPage(page: number) {
  pdfViewerRef.value?.goToPage(page)
}

function handlePdfStateChange(payload: {
  page: number
  totalPages: number
  canGoPrev: boolean
  canGoNext: boolean
  zoomMode: 'fit-width' | 'fit-page' | '100' | '125' | '150'
}) {
  pdfViewerState.value = payload
  pdfPageInput.value = String(payload.page)
}

function commitPdfPageInput() {
  const total = pdfViewerState.value.totalPages
  if (!total) {
    pdfPageInput.value = '1'
    return
  }

  const raw = Number.parseInt(pdfPageInput.value.trim(), 10)
  if (Number.isNaN(raw)) {
    pdfPageInput.value = String(pdfViewerState.value.page)
    return
  }

  const target = Math.min(Math.max(raw, 1), total)
  pdfPageInput.value = String(target)
  pdfViewerRef.value?.goToPage(target)
}

function handlePdfPagerWheel(event: WheelEvent) {
  if (!isPdfDocument.value || !activeItem.value || pdfViewerState.value.totalPages <= 0) return
  event.preventDefault()
  if (Math.abs(event.deltaY) < 3) return
  if (event.deltaY > 0) {
    pdfViewerRef.value?.goNext()
    return
  }
  pdfViewerRef.value?.goPrev()
}

function handlePdfKeydown(event: KeyboardEvent) {
  if (!activeItem.value || !isPdfDocument.value) return

  const target = event.target as HTMLElement | null
  const tagName = target?.tagName?.toLowerCase()
  const isTypingTarget =
    tagName === 'input'
    || tagName === 'textarea'
    || target?.isContentEditable

  if (isTypingTarget) return

  if (event.key === 'PageDown' || (event.key === 'ArrowRight' && !event.altKey && !event.ctrlKey && !event.metaKey)) {
    event.preventDefault()
    pdfViewerRef.value?.goNext()
    return
  }

  if (event.key === 'PageUp' || (event.key === 'ArrowLeft' && !event.altKey && !event.ctrlKey && !event.metaKey)) {
    event.preventDefault()
    pdfViewerRef.value?.goPrev()
  }
}

async function handleQuote(payload: { text: string; page: number }) {
  pendingAnnotationAnchor.value = {
    media_type: 'pdf',
    quote_type: 'text-selection',
    page: payload.page,
    selected_text: payload.text,
  }
  await fillAnnotationDraft(`> [Page ${payload.page}] ${payload.text}\n\n我的思考：`)
}

async function handleMarkdownQuote(payload: {
  text: string
  mode: 'readme' | 'summary'
  heading: string
  excerpt: string
}) {
  const sourceLabel = payload.mode === 'summary' ? 'AI 总结' : 'Markdown'
  pendingAnnotationAnchor.value = {
    media_type: 'markdown',
    quote_type: 'text-selection',
    selected_text: payload.text,
    heading: payload.heading,
    excerpt: payload.excerpt,
    source_mode: payload.mode,
  }
  const headingLine = payload.heading ? ` · ${payload.heading}` : ''
  await fillAnnotationDraft(`> [${sourceLabel}${headingLine}] ${payload.text}\n\n我的思考：`)
}

async function handlePdfScreenshotCapture(payload: {
  blob: Blob
  page: number
  rectNorm: { x: number; y: number; width: number; height: number }
  imageWidth: number
  imageHeight: number
}) {
  if (!activeItem.value) return

  try {
    const upload = await uploadAnnotationAsset(activeItem.value.id, payload.blob, {
      filename: `pdf-page-${payload.page}-capture.png`,
      page: payload.page,
      rect_norm: payload.rectNorm,
    })

    pendingAnnotationAnchor.value = {
      media_type: 'pdf',
      quote_type: 'screenshot',
      page: payload.page,
      image_url: upload.asset_url,
      image_width: payload.imageWidth,
      image_height: payload.imageHeight,
      rect_norm: payload.rectNorm,
    }

    await fillAnnotationDraft(`> [Page ${payload.page}] PDF 截图引用\n\n我的思考：`)
  } catch (error) {
    console.error('上传 PDF 截图引用失败:', error)
  }
}

function togglePdfCaptureMode() {
  const nextMode = !pdfCaptureMode.value
  pdfCaptureMode.value = nextMode
  pdfViewerRef.value?.setCaptureMode(nextMode)
}

function updateLocalItemCategory(itemId: string, categoryId: string | null) {
  favoritedItems.value = favoritedItems.value.map((item) => (
    item.id === itemId ? { ...item, vault_category_id: categoryId } : item
  ))
  searchResults.value = searchResults.value.map((item) => (
    item.id === itemId ? { ...item, vault_category_id: categoryId } : item
  ))
  if (activeItem.value?.id === itemId) {
    activeItem.value = { ...activeItem.value, vault_category_id: categoryId }
  }
}

function hasUnresolvedMarkdownAssets(content?: string | null) {
  if (!content) return false
  const markdownMatches = content.match(/!\[[^\]]*\]\(([^)]+)\)/g) || []
  const htmlMatches = content.match(/<img\b[^>]*src=["'][^"']+["'][^>]*>/gi) || []
  const assetCandidates = [
    ...markdownMatches.map((entry) => entry.match(/\(([^)]+)\)/)?.[1] || ''),
    ...htmlMatches.map((entry) => entry.match(/src=["']([^"']+)["']/i)?.[1] || ''),
  ]

  return assetCandidates.some((assetUrl) => {
    const normalized = String(assetUrl || '').trim().replace(/\\/g, '/').toLowerCase()
    if (!normalized) return false
    if (normalized.startsWith('http://') || normalized.startsWith('https://') || normalized.startsWith('//') || normalized.startsWith('data:')) {
      return false
    }
    return !normalized.startsWith('/api/static/vault/')
  })
}

async function ensureActiveVaultAsset() {
  const item = activeItem.value
  if (!item || item.source_type !== 'github_star') return

  const metadata = item.metadata_extra || {}
  const needsLocalization =
    !metadata.vault_readme_assets_localized
    || !metadata.vault_readme_text
    || Boolean(metadata.vault_readme_asset_failures?.length)
    || hasUnresolvedMarkdownAssets(String(metadata.vault_readme_text || ''))
  if (!needsLocalization || ensuringVaultAssetIds.has(item.id)) return

  ensuringVaultAssetIds.add(item.id)
  try {
    await ensureVaultAsset(item.id)

    window.setTimeout(() => {
      void loadFavoritedItems()
    }, 1400)

    window.setTimeout(() => {
      void loadFavoritedItems()
    }, 3200)
  } catch (error) {
    console.error('补齐 Vault README 资源失败:', error)
  } finally {
    ensuringVaultAssetIds.delete(item.id)
  }
}

async function assignActiveItemCategory(nextCategoryId: string) {
  if (!activeItem.value) return
  try {
    const response = await assignItemVaultCategory(
      activeItem.value.id,
      nextCategoryId === UNCATEGORIZED_CATEGORY_ID ? null : nextCategoryId,
    )
    updateLocalItemCategory(activeItem.value.id, response.vault_category_id ?? null)
  } catch (error) {
    console.error('更新 Vault 分类失败:', error)
  }
}

async function handleCreateCategory() {
  const name = categoryDraft.value.trim()
  if (!name || categoryMutationLoading.value) return

  categoryMutationLoading.value = true
  try {
    const created = await createVaultCategory({ name })
    vaultCategories.value = [...vaultCategories.value, created].sort((a, b) => a.sort_order - b.sort_order)
    ensureSectionOpenState([created.id])
    categoryDraft.value = ''
    creatingCategory.value = false
  } catch (error) {
    console.error('创建分类失败:', error)
  } finally {
    categoryMutationLoading.value = false
  }
}

function beginRenameCategory(category: VaultCategory) {
  editingCategoryId.value = category.id
  editingCategoryName.value = category.name
}

function beginRenameCategoryById(categoryId: string) {
  const category = vaultCategories.value.find((entry) => entry.id === categoryId)
  if (!category) return
  beginRenameCategory(category)
}

function cancelRenameCategory() {
  editingCategoryId.value = null
  editingCategoryName.value = ''
}

async function saveCategoryRename(categoryId: string) {
  const name = editingCategoryName.value.trim()
  if (!name || categoryMutationLoading.value) return

  categoryMutationLoading.value = true
  try {
    const updated = await updateVaultCategory(categoryId, { name })
    vaultCategories.value = vaultCategories.value.map((category) => (
      category.id === categoryId ? updated : category
    ))
    cancelRenameCategory()
  } catch (error) {
    console.error('重命名分类失败:', error)
  } finally {
    categoryMutationLoading.value = false
  }
}

async function removeCategory(categoryId: string) {
  if (categoryMutationLoading.value) return
  const category = vaultCategories.value.find((entry) => entry.id === categoryId)
  if (!category) return
  if (!window.confirm(`删除分类“${category.name}”后，其中的收藏会回到“未分类”。确定继续吗？`)) {
    return
  }

  categoryMutationLoading.value = true
  try {
    await deleteVaultCategory(categoryId)
    vaultCategories.value = vaultCategories.value.filter((entry) => entry.id !== categoryId)
    favoritedItems.value = favoritedItems.value.map((item) => (
      item.vault_category_id === categoryId ? { ...item, vault_category_id: null } : item
    ))
    searchResults.value = searchResults.value.map((item) => (
      item.vault_category_id === categoryId ? { ...item, vault_category_id: null } : item
    ))
    if (activeItem.value?.vault_category_id === categoryId) {
      activeItem.value = { ...activeItem.value, vault_category_id: null }
    }
    if (editingCategoryId.value === categoryId) {
      cancelRenameCategory()
    }
  } catch (error) {
    console.error('删除分类失败:', error)
  } finally {
    categoryMutationLoading.value = false
  }
}

async function handleSearch() {
  if (searchDebounceTimer !== undefined) {
    window.clearTimeout(searchDebounceTimer)
  }
  await performVaultSearch(searchQuery.value)
}

watch(
  () => activeItem.value?.id,
  async () => {
    pendingAnnotationAnchor.value = {}
    pdfCaptureMode.value = false
    videoAspect.value = { width: 16, height: 9 }
    videoCurrentTime.value = 0
    transcriptCollapsed.value = false
    void ensureActiveVaultAsset()
    if (activeInspectorTab.value === 'notes') {
      await loadAnnotations()
    }
  },
)

watch(activeInspectorTab, async (tab) => {
  if (tab === 'notes') {
    await loadAnnotations()
  }
})

watch(searchQuery, (value) => {
  scheduleVaultSearch(value)
})

watch(
  () => vaultCategories.value.map((category) => category.id),
  (categoryIds) => {
    ensureSectionOpenState([UNCATEGORIZED_CATEGORY_ID, ...categoryIds])
  },
  { immediate: true },
)

watch(favoritedItems, (items) => {
  if (!searchQuery.value.trim()) {
    syncActiveItem(items)
  }
})

watch(
  () => activeItem.value?.id,
  () => {
    pdfPageInput.value = String(pdfViewerState.value.page)
  },
)

watch(activeTranscriptIndex, async (index) => {
  if (index < 0) return
  await nextTick()
  const segment = transcriptSegments.value[index]
  if (!segment) return
  transcriptRowRefs.get(segment.id)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})

onMounted(async () => {
  window.addEventListener('keydown', handlePdfKeydown)
  await Promise.all([loadVaultCategories(), loadFavoritedItems()])
  if (activeInspectorTab.value === 'notes') {
    await loadAnnotations()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handlePdfKeydown)
  if (searchDebounceTimer !== undefined) {
    window.clearTimeout(searchDebounceTimer)
  }
})
</script>

<template>
  <MainLayout
    v-model:search-query="searchQuery"
    search-placeholder="搜索收藏内容..."
    @search="handleSearch"
  >
    <div class="flex h-[calc(100vh-5.75rem)] min-h-[640px] flex-col overflow-hidden">
      <div class="grid min-h-0 flex-1 grid-cols-[minmax(240px,20%)_minmax(0,57%)_minmax(260px,23%)] gap-4 overflow-hidden 2xl:grid-cols-[minmax(260px,19%)_minmax(0,58%)_minmax(280px,23%)]">
        <section class="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border bg-muted/30">
          <div class="flex items-center justify-between border-b px-4 py-3">
            <div>
              <h2 class="text-sm font-semibold">Vault</h2>
              <p class="text-xs text-muted-foreground">
                {{ isSearchMode ? '搜索结果按相关性直接展示。' : '按你的自定义分类组织高价值收藏。' }}
              </p>
            </div>
            <div class="flex items-center gap-2">
              <Badge variant="secondary">{{ displayCount }}</Badge>
              <Button
                v-if="!isSearchMode"
                size="icon"
                variant="outline"
                class="h-8 w-8"
                title="新建分类"
                @click="creatingCategory = !creatingCategory"
              >
                <Plus class="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div class="min-h-0 flex-1">
            <ScrollArea class="h-full">
              <div class="space-y-4 p-3">
                <template v-if="isLoading || isSearching || categoriesLoading">
                  <Skeleton class="h-6 w-full" />
                  <Skeleton class="h-24 w-full" />
                  <Skeleton class="h-16 w-full" />
                </template>
                <template v-else-if="creatingCategory && !isSearchMode">
                  <div class="rounded-xl border bg-background/90 p-3">
                    <div class="mb-2 text-xs text-muted-foreground">创建一个新的 Vault 分类</div>
                    <div class="flex items-center gap-2">
                      <input
                        v-model="categoryDraft"
                        type="text"
                        maxlength="40"
                        placeholder="例如：研究灵感 / 论文 / 产品案例"
                        class="flex-1 rounded-lg border bg-background px-3 py-2 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                        @keydown.enter.prevent="handleCreateCategory"
                      >
                      <Button size="icon" :disabled="categoryMutationLoading || !categoryDraft.trim()" @click="handleCreateCategory">
                        <Check class="h-4 w-4" />
                      </Button>
                      <Button size="icon" variant="outline" @click="creatingCategory = false; categoryDraft = ''">
                        <X class="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </template>

                <template v-if="hasNoSearchResults">
                  <div class="rounded-xl border border-dashed bg-background/80 p-4 text-sm text-muted-foreground">
                    没有找到与你的搜索匹配的收藏内容，试试换个关键词。
                  </div>
                </template>
                <template v-else-if="isSearchMode">
                  <div class="space-y-1 rounded-xl border bg-background/90 p-2">
                    <div class="px-2 pb-2 text-xs text-muted-foreground">
                      搜索结果按相关性排序展示
                    </div>
                    <button
                      v-for="item in searchResultItems"
                      :key="item.id"
                      class="w-full rounded-lg px-2 py-2 text-left transition hover:bg-muted"
                      :class="activeItem?.id === item.id ? 'bg-primary/10 text-foreground' : 'text-muted-foreground'"
                      @click="selectItem(item)"
                    >
                      <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                          <div class="truncate text-sm font-medium text-foreground">{{ item.title }}</div>
                          <div class="line-clamp-2 text-xs text-muted-foreground">{{ item.cardSummary }}</div>
                        </div>
                        <span :class="intentPillClass">
                          {{ item.intentLabel }}
                        </span>
                      </div>
                    </button>
                  </div>
                </template>
                <template v-else-if="favoritedItems.length === 0">
                  <div class="rounded-xl border border-dashed bg-background/80 p-4 text-sm text-muted-foreground">
                    你还没有收藏任何内容，先去信息流里收藏几条，再回来搭建自己的 Vault。
                  </div>
                </template>
                <template v-else>
                  <div v-for="section in categorySections" :key="section.id" class="rounded-xl border bg-background/90">
                    <div v-if="editingCategoryId === section.id && !section.isSystem" class="space-y-2 px-3 py-3">
                      <div class="text-xs text-muted-foreground">重命名分类</div>
                      <div class="flex items-center gap-2">
                        <input
                          v-model="editingCategoryName"
                          type="text"
                          maxlength="40"
                          class="flex-1 rounded-lg border bg-background px-3 py-2 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                          @keydown.enter.prevent="saveCategoryRename(section.id)"
                        >
                        <Button size="icon" :disabled="categoryMutationLoading || !editingCategoryName.trim()" @click="saveCategoryRename(section.id)">
                          <Check class="h-4 w-4" />
                        </Button>
                        <Button size="icon" variant="outline" @click="cancelRenameCategory">
                          <X class="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    <template v-else>
                      <div class="flex items-center gap-2 px-3 py-2">
                        <button
                          class="flex min-w-0 flex-1 items-center justify-between rounded-lg text-left transition-colors hover:bg-muted/50"
                          @click="toggleSection(section.id)"
                        >
                          <span class="flex min-w-0 items-center gap-2 px-2 py-1.5">
                            <span class="h-2.5 w-2.5 rounded-full" :style="{ backgroundColor: section.color }" />
                            <span class="truncate text-sm font-medium">{{ section.name }}</span>
                          </span>
                          <span class="flex items-center gap-1.5 px-2 text-xs text-muted-foreground">
                            {{ section.items.length }}
                            <ChevronDown
                              class="h-4 w-4 transition-transform duration-200"
                              :class="!sectionOpenState[section.id] ? '-rotate-90' : 'rotate-0'"
                            />
                          </span>
                        </button>
                        <div v-if="!section.isSystem" class="flex items-center gap-1">
                          <Button size="icon" variant="ghost" class="h-7 w-7" title="重命名分类" @click="beginRenameCategoryById(section.id)">
                            <Pencil class="h-3.5 w-3.5" />
                          </Button>
                          <Button size="icon" variant="ghost" class="h-7 w-7 text-destructive hover:text-destructive" title="删除分类" @click="removeCategory(section.id)">
                            <Trash2 class="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                      <div v-if="sectionOpenState[section.id]" class="space-y-1 px-2 pb-2">
                        <template v-if="section.items.length === 0">
                          <div class="rounded-lg border border-dashed px-3 py-3 text-xs text-muted-foreground">
                            这个分类里还没有收藏内容。
                          </div>
                        </template>
                        <button
                          v-for="item in section.items"
                          :key="item.id"
                          class="w-full rounded-lg px-2 py-2 text-left transition hover:bg-muted"
                          :class="activeItem?.id === item.id ? 'bg-primary/10 text-foreground' : 'text-muted-foreground'"
                          @click="selectItem(item)"
                        >
                          <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0">
                              <div class="truncate text-sm font-medium text-foreground">{{ item.title }}</div>
                              <div class="line-clamp-2 text-xs text-muted-foreground">
                                {{ toPlainTextSnippet(item.summary || item.content_text || item.source_type, '暂无描述', 90) }}
                              </div>
                            </div>
                            <span :class="intentPillClass">
                              {{ intentMeta(item.intent).label }}
                            </span>
                          </div>
                        </button>
                      </div>
                    </template>
                  </div>
                </template>
              </div>
            </ScrollArea>
          </div>
        </section>

        <section class="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border bg-background">
          <div class="border-b px-4 py-2.5">
            <div class="flex items-center justify-between gap-4">
              <h2 class="truncate text-base font-semibold">{{ activeItem?.title || 'Reader Pane' }}</h2>
              <div v-if="activeItem" class="flex shrink-0 flex-wrap items-center justify-end gap-2">
                <div class="flex items-center gap-2 rounded-full border bg-muted/30 px-3 py-1.5 text-sm">
                  <span class="text-muted-foreground">归类</span>
                  <select
                    :value="currentCategoryValue"
                    class="rounded-md border bg-background px-2 py-1 text-sm text-foreground outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    @change="assignActiveItemCategory(($event.target as HTMLSelectElement).value)"
                  >
                    <option :value="UNCATEGORIZED_CATEGORY_ID">未分类</option>
                    <option
                      v-for="category in vaultCategories"
                      :key="category.id"
                      :value="category.id"
                    >
                      {{ category.name }}
                    </option>
                  </select>
                </div>

                <template v-if="activeItem.intent === 'document' && isPdfDocument">
                  <Button
                    size="sm"
                    :variant="pdfCaptureMode ? 'default' : 'outline'"
                    title="框选当前 PDF 页面区域并创建截图引用"
                    @click="togglePdfCaptureMode"
                  >
                    <Camera class="mr-2 h-4 w-4" />
                    截图引用
                  </Button>
                  <div
                    class="flex items-center gap-2 rounded-full border bg-muted/30 px-3 py-1.5 text-sm text-muted-foreground"
                    title="在这里滚动鼠标滚轮可快速翻页"
                    @wheel.prevent="handlePdfPagerWheel"
                  >
                    <span>第</span>
                    <input
                      v-model="pdfPageInput"
                      inputmode="numeric"
                      class="w-14 rounded-md border bg-background px-2 py-1 text-center text-sm text-foreground outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      @blur="commitPdfPageInput"
                      @keydown.enter.prevent="commitPdfPageInput"
                    >
                    <span>/ {{ pdfViewerState.totalPages || 0 }} 页</span>
                  </div>
                  <div class="flex items-center gap-1 rounded-full border bg-muted/40 p-1">
                    <Button
                      v-for="option in pdfZoomOptions"
                      :key="option.value"
                      size="sm"
                      :variant="pdfViewerState.zoomMode === option.value ? 'default' : 'ghost'"
                      class="h-8 rounded-full px-3 text-xs"
                      @click="pdfViewerRef?.setZoomMode(option.value)"
                    >
                      {{ option.label }}
                    </Button>
                  </div>
                  <div class="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      :disabled="!pdfViewerState.canGoPrev"
                      title="上一页，支持 PageUp 或左方向键"
                      @click="pdfViewerRef?.goPrev()"
                    >
                      上一页
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      :disabled="!pdfViewerState.canGoNext"
                      title="下一页，支持 PageDown 或右方向键"
                      @click="pdfViewerRef?.goNext()"
                    >
                      下一页
                    </Button>
                  </div>
                </template>
              </div>
            </div>
          </div>
          <div class="min-h-0 flex-1">
            <ScrollArea class="h-full">
              <div
                class="min-w-0"
                :class="activeItem?.intent === 'document' && isPdfDocument ? 'h-full p-2' : 'p-5'"
              >
                <template v-if="!activeItem">
                  <div class="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">
                    {{ hasNoSearchResults ? '没有匹配的收藏内容可供阅读。' : '从左侧选择一条收藏内容。' }}
                  </div>
                </template>
                <template v-else-if="activeItem.intent === 'video'">
                  <div class="space-y-4">
                    <div class="flex min-h-[420px] items-center justify-center rounded-2xl border bg-muted/20 p-4">
                      <video
                        ref="videoPlayer"
                        controls
                        class="rounded-xl bg-black"
                        :class="isPortraitVideo ? 'h-full max-h-[calc(100vh-24rem)] w-auto max-w-full' : 'max-h-[calc(100vh-24rem)] w-full object-contain'"
                        :src="toAbsoluteUrl(activeItem.local_asset_url || activeItem.raw_link)"
                        @loadedmetadata="handleVideoMetadataLoaded"
                        @timeupdate="handleVideoTimeUpdate"
                      />
                    </div>

                    <div class="rounded-2xl border bg-background">
                      <button
                        class="flex w-full items-center justify-between px-4 py-3 text-left"
                        @click="transcriptCollapsed = !transcriptCollapsed"
                      >
                        <span class="flex items-center gap-2 text-sm font-medium">
                          <FileText class="h-4 w-4 text-muted-foreground" />
                          视频转录
                        </span>
                        <span class="flex items-center gap-2 text-xs text-muted-foreground">
                          <span v-if="transcriptAvailable">{{ transcriptSegments.length }} 段</span>
                          <span v-else>暂无转录</span>
                          <ChevronDown
                            class="h-4 w-4 transition-transform duration-200"
                            :class="transcriptCollapsed ? '-rotate-90' : 'rotate-0'"
                          />
                        </span>
                      </button>
                      <div v-if="!transcriptCollapsed" class="border-t">
                        <div v-if="transcriptAvailable" class="p-2">
                          <ScrollArea class="h-72">
                            <div class="space-y-2 p-2">
                              <button
                                v-for="(segment, index) in transcriptSegments"
                                :key="segment.id"
                                :ref="(el) => setTranscriptRowRef(segment.id, el)"
                                class="w-full rounded-xl border px-3 py-2 text-left transition"
                                :class="activeTranscriptIndex === index ? 'border-primary bg-primary/5' : 'bg-background hover:bg-muted/50'"
                                @click="jumpToVideoTimestamp(segment.start)"
                              >
                                <div class="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                                  <span class="rounded-full border bg-background px-2 py-0.5 font-medium text-foreground">
                                    {{ formatTimestamp(segment.start) }}
                                  </span>
                                  <span v-if="segment.end > segment.start">
                                    - {{ formatTimestamp(segment.end) }}
                                  </span>
                                </div>
                                <div class="text-sm leading-6 text-foreground">{{ segment.text }}</div>
                              </button>
                            </div>
                          </ScrollArea>
                        </div>
                        <div v-else class="px-4 py-6 text-sm text-muted-foreground">
                          这个视频还没有可用的转录文本。只要它完成 AI 总结，多媒体转录就会自动出现在这里。
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <template v-else-if="activeItem.intent === 'image'">
                  <div class="flex justify-center">
                    <img
                      class="max-h-[70vh] rounded-xl border object-contain"
                      :src="toAbsoluteUrl(activeItem.local_asset_url || activeItem.raw_link)"
                      :alt="activeItem.title"
                    />
                  </div>
                </template>
                <template v-else-if="activeItem.intent === 'audio'">
                  <audio
                    controls
                    class="w-full"
                    :src="toAbsoluteUrl(activeItem.local_asset_url || activeItem.raw_link)"
                  />
                </template>
                <template v-else-if="activeItem.intent === 'document' && isPdfDocument">
                  <div class="h-[calc(100vh-11rem)] min-h-[640px]">
                    <PdfViewer
                      ref="pdfViewer"
                      :url="openableDocumentUrl"
                      @quote="handleQuote"
                      @screenshot-capture="handlePdfScreenshotCapture"
                      @capture-mode-change="pdfCaptureMode = $event"
                      @state-change="handlePdfStateChange"
                    />
                  </div>
                </template>
                <template v-else-if="activeItem.intent === 'document'">
                  <div class="space-y-4">
                    <div class="rounded-xl border bg-muted/20 p-4">
                      <h3 class="text-base font-medium">{{ activeItem.title }}</h3>
                      <MarkdownContent
                        :content="articleContent"
                        mode="readme"
                        quoteable
                        class="mt-2 text-sm text-muted-foreground"
                        @quote="handleMarkdownQuote"
                      />
                    </div>
                    <Button as-child>
                      <a :href="openableDocumentUrl" target="_blank" rel="noopener noreferrer">
                        <ExternalLink class="mr-2 h-4 w-4" />
                        在新标签页打开
                      </a>
                    </Button>
                  </div>
                </template>
                <template v-else>
                  <div class="rounded-xl border bg-muted/20 p-4">
                    <MarkdownContent
                      :content="articleContent"
                      mode="readme"
                      quoteable
                      class="text-sm"
                      @quote="handleMarkdownQuote"
                    />
                  </div>
                </template>
              </div>
            </ScrollArea>
          </div>
        </section>

        <section class="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border bg-background">
          <div class="border-b px-4 py-4">
            <div class="flex items-center gap-2">
              <Button
                size="sm"
                :variant="activeInspectorTab === 'summary' ? 'default' : 'outline'"
                @click="activeInspectorTab = 'summary'"
              >
                <Sparkles class="mr-2 h-4 w-4" />
                AI 总结
              </Button>
              <Button
                size="sm"
                :variant="activeInspectorTab === 'notes' ? 'default' : 'outline'"
                @click="activeInspectorTab = 'notes'"
              >
                <MessageSquareText class="mr-2 h-4 w-4" />
                内化日志
              </Button>
            </div>
          </div>
          <div class="min-h-0 flex-1">
            <ScrollArea class="h-full">
              <div class="space-y-4 p-4">
                <template v-if="activeInspectorTab === 'summary'">
                  <div v-if="!activeItem" class="text-sm text-muted-foreground">选择内容后查看总结。</div>
                  <template v-else>
                    <MarkdownContent
                      :content="summaryContent"
                      mode="summary"
                      quoteable
                      @quote="handleMarkdownQuote"
                    />
                    <template v-if="activeKeyframes.length > 0">
                      <Separator />
                      <div class="space-y-3">
                        <div class="text-sm font-medium">关键帧</div>
                        <div class="grid grid-cols-1 gap-3">
                          <img
                            v-for="(frame, index) in activeKeyframes"
                            :key="`${frame}-${index}`"
                            :src="toAbsoluteUrl(frame)"
                            :alt="`关键帧 ${index + 1}`"
                            class="w-full rounded-xl border object-cover"
                          />
                        </div>
                      </div>
                    </template>
                  </template>
                </template>
                <template v-else>
                  <div v-if="!activeItem" class="text-sm text-muted-foreground">选择内容后记录你的思考。</div>
                  <template v-else>
                    <div class="space-y-3">
                      <textarea
                        ref="annotationTextarea"
                        v-model="annotationDraft"
                        placeholder="写下一条你的想法、摘要或行动项..."
                        class="min-h-28 w-full rounded-xl border bg-background px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      />
                      <div class="flex flex-wrap items-center gap-2">
                        <Button
                          v-if="isVideoItem"
                          variant="outline"
                          :disabled="!videoPlayerRef"
                          @click="captureVideoTimestamp"
                        >
                          引用当前时间
                        </Button>
                        <div
                          v-if="pendingAnnotationAnchor.quote_type === 'screenshot' && pendingAnnotationAnchor.image_url"
                          class="inline-flex items-center gap-2 rounded-full border bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground"
                        >
                          <Camera class="h-3.5 w-3.5" />
                          已附加截图引用
                        </div>
                        <Button :disabled="savingAnnotation || !annotationDraft.trim()" @click="saveAnnotation">
                          保存思考
                        </Button>
                      </div>
                    </div>
                    <Separator />
                    <div class="space-y-3">
                      <div class="text-sm font-medium">历史思考</div>
                      <template v-if="annotationsLoading">
                        <Skeleton class="h-16 w-full" />
                        <Skeleton class="h-16 w-full" />
                      </template>
                      <template v-else-if="annotations.length === 0">
                        <div class="rounded-xl border border-dashed p-3 text-sm text-muted-foreground">
                          还没有任何思考记录，写下第一条吧。
                        </div>
                      </template>
                      <div
                        v-for="annotation in annotations"
                        :key="annotation.id"
                        class="rounded-xl border bg-muted/20 p-3"
                      >
                        <button
                          v-if="annotation.anchor_data?.media_type === 'pdf' && annotation.anchor_data?.quote_type === 'text-selection' && typeof annotation.anchor_data?.page === 'number'"
                          type="button"
                          class="mb-2 inline-flex rounded-full border bg-background px-2.5 py-1 text-xs font-medium text-foreground transition hover:bg-muted"
                          @click="jumpToPdfAnnotationPage(annotation.anchor_data.page)"
                        >
                          <Pin class="mr-1 h-3.5 w-3.5" />
                          Page {{ annotation.anchor_data.page }}
                        </button>
                        <div
                          v-if="annotation.anchor_data?.media_type === 'markdown' && annotation.anchor_data?.quote_type === 'text-selection'"
                          class="mb-2 inline-flex rounded-full border bg-background px-2.5 py-1 text-xs font-medium text-foreground"
                        >
                          <Pin class="mr-1 h-3.5 w-3.5" />
                          {{ annotation.anchor_data?.source_mode === 'summary' ? 'AI 总结引用' : 'Markdown 引用' }}
                        </div>
                        <div
                          v-if="annotation.anchor_data?.media_type === 'video' && typeof annotation.anchor_data?.timestamp_seconds === 'number'"
                          class="mb-3 space-y-2"
                        >
                          <button
                            type="button"
                            class="inline-flex rounded-full border bg-background px-2.5 py-1 text-xs font-medium text-foreground transition hover:bg-muted"
                            @click="jumpToVideoTimestamp(annotation.anchor_data.timestamp_seconds)"
                          >
                            {{ annotation.anchor_data?.timestamp_label || formatTimestamp(annotation.anchor_data.timestamp_seconds) }}
                          </button>
                          <div
                            v-if="annotation.anchor_data?.transcript_text"
                            class="rounded-lg border bg-background/70 px-3 py-2 text-xs leading-6 text-muted-foreground"
                          >
                            {{ annotation.anchor_data.transcript_text }}
                          </div>
                        </div>
                        <div
                          v-if="annotation.anchor_data?.media_type === 'pdf' && annotation.anchor_data?.quote_type === 'screenshot' && annotation.anchor_data?.image_url"
                          class="mb-3 space-y-2"
                        >
                          <button
                            type="button"
                            class="inline-flex rounded-full border bg-background px-2.5 py-1 text-xs font-medium text-foreground transition hover:bg-muted"
                            @click="jumpToPdfAnnotationPage(annotation.anchor_data.page)"
                          >
                            <Camera class="mr-1 h-3.5 w-3.5" />
                            Page {{ annotation.anchor_data.page }}
                          </button>
                          <a
                            :href="toAbsoluteUrl(annotation.anchor_data.image_url)"
                            target="_blank"
                            rel="noopener noreferrer"
                            class="block"
                          >
                            <img
                              :src="toAbsoluteUrl(annotation.anchor_data.image_url)"
                              alt="PDF 截图引用"
                              class="max-h-40 rounded-lg border object-contain"
                            >
                          </a>
                        </div>
                        <div class="whitespace-pre-wrap text-sm">{{ annotation.content_raw }}</div>
                        <div class="mt-2 text-xs text-muted-foreground">
                          {{ new Date(annotation.created_at).toLocaleString() }}
                        </div>
                      </div>
                    </div>
                  </template>
                </template>
              </div>
            </ScrollArea>
          </div>
        </section>
      </div>
    </div>
  </MainLayout>
</template>
