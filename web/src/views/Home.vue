<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import MainLayout from '@/layouts/MainLayout.vue'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
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
import { Github, Tv, FileText, MoreVertical, Sparkles, Bookmark, BookmarkCheck, ExternalLink, Trash2, Star, Loader2 } from 'lucide-vue-next'
import { getItems, search, summarizeItem, getItemSummaryStatus, getStoredAuthUser, toggleItemStar, markItemsReadBatch, getActivePlugins, getHoverBlocks, type RawItem, type SearchResult, type ActivePlugin, type HoverResponse } from '@/lib/api'
import HoverPreview from '@/components/HoverPreview.vue'
import { useToast } from '@/components/ui/toast/use-toast'
import { Toaster } from '@/components/ui/toast'

interface LocalSearchResult extends SearchResult {
  hasSummary?: boolean
  raw_link?: string
  authorName?: string
  displayTags?: string[]
  isRead: boolean
  isStarred: boolean
}

const savedLayout = (localStorage.getItem('pekno-layout') as 'list' | 'grid' | 'compact') || 'list'
const layoutMode = ref<'list' | 'grid' | 'compact'>(savedLayout)
watch(layoutMode, (val) => localStorage.setItem('pekno-layout', val))
const searchQuery = ref('')
const searchResults = ref<LocalSearchResult[]>([])
const activeSource = ref<string>('all')
const activePlugins = ref<ActivePlugin[]>([])
const isLoading = ref(false)
const isSheetOpen = ref(false)
const selectedItem = ref<LocalSearchResult | null>(null)
const isSummarizing = ref(false)
const currentTaskId = ref<string | null>(null)
const pollInterval = ref<number | undefined>(undefined)
const route = useRoute()
const currentUsername = computed(() => getStoredAuthUser().username || '管理员')
const initialAnchorItemId = ref<string | null>(null)
const isWatchLaterPage = computed(() => route.name === 'watch-later')
const pageTitle = computed(() => isWatchLaterPage.value ? '稍后再看' : `欢迎回来，${currentUsername.value}`)
const pageSubtitle = computed(() => {
  if (isLoading.value) {
    return '正在加载数据...'
  }
  if (isWatchLaterPage.value) {
    return `${currentUsername.value} 当前收藏了 ${searchResults.value.length} 条稍后再看`
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
    return `iris 更新并整理了 ${unreadCount} 条资料`
  } else {
    const plugin = activePlugins.value.find(p => p.source_type === activeSource.value)
    const pluginName = plugin ? plugin.name : activeSource.value
    return `${pluginName} 有 ${unreadCount} 条更新`
  }
})

let observer: IntersectionObserver | null = null
let flushReadsInterval: number | undefined
const cardElements = new Map<string, HTMLElement>()
const visibilityTimers = new Map<string, number>()
const pendingReadIds = new Set<string>()

const renderedSummary = computed(() => {
  const raw = selectedItem.value?.long_summary || selectedItem.value?.summary || ''
  if (!raw) return '<p class="text-muted-foreground">暂无 AI 总结，点击生成按钮开始总结...</p>'
  const normalized = raw.replace(/\\n/g, '\n')
  return marked.parse(normalized) as string
})

const hoverTimers = new Map<string, number>()
const hoverDataMap = ref<Record<string, HoverResponse>>({})
const activeHoverItemId = ref<string | null>(null)

function handleCardMouseEnter(item: LocalSearchResult) {
  // 只在 list/grid 模式下，或者你有空间才显示，compact 先不用管
  if (activeHoverItemId.value === item.id) return
  
  const timer = window.setTimeout(async () => {
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

const { toast } = useToast()

function formatRelativeTime(input?: string) {
  if (!input) return '未知时间'

  const date = new Date(input)
  if (Number.isNaN(date.getTime())) return '未知时间'

  const diffMs = Date.now() - date.getTime()
  const diffMinutes = Math.max(0, Math.floor(diffMs / 60000))

  if (diffMinutes < 1) return '刚刚'
  if (diffMinutes < 60) return `${diffMinutes}分钟前`

  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffHours < 48) return '昨天'

  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays}天前`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}周前`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}个月前`
  return `${Math.floor(diffDays / 365)}年前`
}

function mapSourceType(sourceType: string) {
  const sourceMap: Record<string, string> = {
    github_star: 'github',
    bilibili: 'bilibili',
    bilibili_subscribed: 'bilibili',
    article: 'article',
  }

  return sourceMap[sourceType] || sourceType
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
  const authorName = source === 'bilibili'
    ? (typeof metadata.up_name === 'string' ? metadata.up_name : typeof metadata.author === 'string' ? metadata.author : undefined)
    : undefined
  const time = source === 'github' && typeof metadata.pushed_at === 'string'
    ? formatRelativeTime(metadata.pushed_at)
    : formatRelativeTime(item.created_at)

  return {
    id: item.id,
    title: item.title,
    summary: item.summary || item.content_text || '暂无描述',
    long_summary: hasLongSummary ? item.summary || undefined : undefined,
    has_long_summary: hasLongSummary,
    cover_url: typeof metadata.cover_url === 'string' ? metadata.cover_url : undefined,
    score: Math.max(0.5, 1 - index * 0.03),
    source,
    tags: tags.slice(0, 5).length > 0 ? tags.slice(0, 5) : ['未分类'],
    authorName,
    displayTags: tags.slice(0, 5).length > 0 ? tags.slice(0, 5) : ['未分类'],
    time,
    raw_link: item.raw_link || '#',
    isRead: Boolean(item.is_read),
    isStarred: Boolean(item.is_starred),
  }
}

function normalizeSearchResult(item: SearchResult): LocalSearchResult {
  const authorName = item.source === 'bilibili' ? item.author : undefined

  return {
    ...item,
    authorName,
    displayTags: item.tags.length > 0 ? item.tags : ['未分类'],
    raw_link: item.raw_link || (item.source === 'github' ? `https://github.com/${item.title}` : '#'),
    isRead: Boolean(item.is_read),
    isStarred: Boolean(item.is_starred),
  }
}

function getDisplayTags(item: LocalSearchResult) {
  return item.displayTags && item.displayTags.length > 0 ? item.displayTags : item.tags
}

async function loadData(query: string = '') {
  await flushPendingReads()
  isLoading.value = true
  try {
    const sourceFilter = activeSource.value === 'all' ? undefined : activeSource.value

    if (isWatchLaterPage.value) {
      const items = await getItems(undefined, 0, { starredOnly: true, source_type: sourceFilter })
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
      return
    }

    if (query.trim()) {
      const results = await search({ q: query, source_type: sourceFilter })
      initialAnchorItemId.value = null
      searchResults.value = results.map(normalizeSearchResult)
      return
    }

    const items = await getItems(undefined, 0, { source_type: sourceFilter })
    const normalized = items.map((item, index) => normalizeRawItem(item, index))
    initialAnchorItemId.value = normalized.find((item) => item.isRead)?.id ?? null
    searchResults.value = normalized
  } catch (error) {
    console.error('搜索失败:', error)
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
  } catch (e) {
    console.error('获取插件列表失败:', e)
  }
  void loadData()
  flushReadsInterval = window.setInterval(() => {
    void flushPendingReads()
  }, 5000)
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

  void flushPendingReads()
})

const getSourceIcon = (source: string) => {
  if (source === 'github') return Github
  if (source === 'bilibili') return Tv
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
  if (item.raw_link && item.raw_link !== '#') {
    window.open(item.raw_link, '_blank')
  }
}

function handleAISummary(item: LocalSearchResult) {
  selectedItem.value = item
  isSheetOpen.value = true

  if (!item.has_long_summary) {
    setTimeout(() => {
      handleGenerateSummary()
    }, 300)
  }
}

async function handleAddToWatchLater(item: LocalSearchResult) {
  try {
    const response = await toggleItemStar(item.id)
    updateLocalItemState(item.id, {
      isRead: response.is_read,
      isStarred: response.is_starred,
    })
    toast({
      title: response.is_starred ? '已加入稍后再看' : '已取消稍后再看',
      description: item.title,
    })
  } catch (error) {
    console.error('切换稍后再看失败:', error)
    toast({
      title: '操作失败',
      description: '无法更新稍后再看状态，请稍后重试',
      variant: 'destructive',
    })
  }
}

function handleClearRecord() {
  console.log('清空记录:', selectedItem.value?.title)
  isSheetOpen.value = false
  selectedItem.value = null
}

async function handleGenerateSummary() {
  if (!selectedItem.value || isSummarizing.value) return

  try {
    isSummarizing.value = true
    const itemId = selectedItem.value.id
    const response = await summarizeItem(itemId)
    currentTaskId.value = response.task_id

    toast({
      title: '🔄 AI 总结生成中',
      description: '请稍候，正在抓取并分析仓库内容...',
    })

    startPollingSummaryStatus(itemId)
  } catch (error) {
    console.error('生成 AI 总结失败:', error)
    isSummarizing.value = false
    toast({
      title: '❌ 生成失败',
      description: '无法启动 AI 总结，请检查网络连接',
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
        isSummarizing.value = false
        await loadData(searchQuery.value)

        if (selectedItem.value && selectedItem.value.id === itemId) {
          const updatedItem = searchResults.value.find(r => r.id === itemId)
          if (updatedItem) {
            selectedItem.value = updatedItem
          }
        }

        toast({
          title: '✨ AI 总结完成',
          description: '已为仓库生成 AI 总结',
        })
      }
    } catch (error) {
      console.error('查询总结状态失败:', error)
    }
  }, 3000)
}

watch(isSheetOpen, (newVal) => {
  if (!newVal) {
    if (pollInterval.value !== undefined) {
      clearInterval(pollInterval.value)
      pollInterval.value = undefined
    }
    isSummarizing.value = false
  }
})

function isCardActive(item: LocalSearchResult) {
  return selectedItem.value?.id === item.id && isSheetOpen.value
}

function openExternalLink(url?: string) {
  if (url && url !== '#') {
    window.open(url, '_blank')
  }
}

function updateLocalItemState(itemId: string, patch: Partial<Pick<LocalSearchResult, 'isRead' | 'isStarred'>>) {
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
    console.error('批量已读同步失败:', error)
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
</script>

<template>
  <MainLayout
    v-model:layout="layoutMode"
    v-model:search-query="searchQuery"
    @search="handleSearch"
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
        全部 (All)
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
          <span class="font-medium">上次阅读到这</span>
        </div>

        <Card
          :ref="(el) => setCardRef(item.id, ((el as any)?.$el ?? el) as Element | null)"
          :class="[
            'bg-card text-card-foreground border-border transition-all cursor-pointer overflow-visible group flex flex-col relative',
            isCardActive(item) ? 'border-primary ring-2 ring-primary/20 shadow-md' : 'hover:border-primary/20 shadow-sm hover:shadow-md',
            item.isStarred ? 'border-amber-300/60 shadow-amber-100/20' : '',
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
          v-if="item.has_long_summary"
          class="absolute top-2 left-2 z-10"
          title="已有 AI 总结"
        >
          <Star class="w-4 h-4 text-yellow-500 fill-yellow-500 animate-pulse" />
        </div>

        <div
          v-if="item.isStarred"
          class="absolute top-2 left-10 z-10 rounded-full bg-amber-500/15 px-2 py-1 text-[10px] font-semibold text-amber-700"
        >
          稍后再看
        </div>

        <div class="absolute top-2 right-2 z-10" @click.stop>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="h-8 w-8 bg-background/80 backdrop-blur-sm hover:bg-background"
              >
                <MoreVertical class="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="w-48">
              <DropdownMenuItem @click.stop="handleAISummary(item)">
                <Sparkles class="mr-2 h-4 w-4 text-primary" />
                <span>✨ AI 总结</span>
              </DropdownMenuItem>
              <DropdownMenuItem @click.stop="handleAddToWatchLater(item)">
                <component :is="item.isStarred ? BookmarkCheck : Bookmark" class="mr-2 h-4 w-4" />
                <span>{{ item.isStarred ? '移出稍后再看' : '添加到稍后再看' }}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div v-if="layoutMode !== 'compact' && item.cover_url" class="h-44 flex items-center justify-center relative overflow-hidden border-b border-border/40 flex-shrink-0 rounded-t-xl">
          <img
            :src="item.cover_url"
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

            <div v-if="item.source === 'bilibili' && item.authorName && layoutMode !== 'compact'" class="mt-2 flex items-center gap-2 text-sm text-sky-700 dark:text-sky-300">
              <Tv class="w-3.5 h-3.5 shrink-0" />
              <span class="truncate font-medium">{{ item.authorName }}</span>
            </div>

            <p v-if="layoutMode === 'list'" class="text-muted-foreground leading-relaxed text-base mt-3 line-clamp-3">
              {{ item.summary }}
            </p>
            <p v-else-if="layoutMode === 'grid'" class="text-muted-foreground mt-2 text-sm line-clamp-2">
              {{ item.summary }}
            </p>
          </div>
        </CardHeader>

        <CardContent v-if="layoutMode !== 'compact'" class="px-5 pb-5 pt-0 mt-auto">
          <div class="flex items-center justify-between border-t border-border/40 pt-4 gap-3">
            <div class="flex gap-2 flex-wrap flex-1">
              <Badge
                v-for="tag in getDisplayTags(item)"
                :key="tag"
                variant="secondary"
                class="bg-muted hover:bg-muted/80 text-xs font-normal"
              >
                {{ tag }}
              </Badge>
            </div>

            <div class="flex items-center gap-2 text-muted-foreground flex-shrink-0">
              <Badge variant="outline" class="font-mono px-1.5 py-0 text-[10px] h-5 border-primary/20 bg-primary/5 text-primary">
                {{ Math.floor(item.score * 100) }}%
              </Badge>
              <component :is="getSourceIcon(item.source)" class="w-4 h-4" title="来源" />
              <span class="text-xs font-medium whitespace-nowrap">{{ item.time }}</span>
            </div>
          </div>
        </CardContent>
        </Card>
      </template>
    </div>

    <div v-if="!isLoading && searchResults.length === 0" class="text-center py-20">
      <div class="text-muted-foreground text-lg">暂无数据</div>
      <p class="text-muted-foreground/60 text-sm mt-2">尝试搜索其他关键词或检查后端服务是否运行</p>
    </div>
  </MainLayout>

  <Sheet v-model:open="isSheetOpen">
    <SheetContent class="w-full sm:max-w-xl p-0 flex flex-col h-full max-h-screen" side="right">
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
            访问
          </Button>
        </div>
      </SheetHeader>

      <ScrollArea class="flex-1 overflow-y-auto p-4">
        <div class="space-y-6">
          <div>
            <div class="flex items-center gap-2 mb-3">
              <Sparkles class="w-5 h-5 text-primary" />
              <h3 class="font-semibold text-lg">AI 智能总结</h3>
            </div>
            <div class="bg-muted/50 rounded-lg p-4 max-h-[50vh] overflow-y-auto markdown-body">
              <div v-html="renderedSummary"></div>
            </div>
          </div>

          <Separator />

          <div>
            <h4 class="font-medium mb-2">标签</h4>
            <div class="flex flex-wrap gap-2">
              <Badge v-for="tag in selectedItem?.tags" :key="tag" variant="secondary">
                {{ tag }}
              </Badge>
            </div>
          </div>

          <Separator />

          <div>
            <div class="flex items-center gap-2 mb-3">
              <div class="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center">
                <span class="text-xs">💬</span>
              </div>
              <h4 class="font-medium">针对此内容提问</h4>
            </div>
            <div class="bg-muted/30 rounded-lg p-4 text-center text-muted-foreground text-sm">
              <p>对话功能开发中...</p>
              <p class="text-xs mt-1">即将支持针对此内容进行 AI 问答</p>
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
          {{ isSummarizing ? 'AI 总结生成中...' : '生成 AI 总结' }}
        </Button>
        <Button
          class="w-full"
          variant="destructive"
          @click="handleClearRecord"
        >
          <Trash2 class="w-4 h-4 mr-2" />
          清空此记录
        </Button>
      </div>
    </SheetContent>
  </Sheet>

  <Toaster />
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
