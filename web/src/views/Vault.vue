<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import MainLayout from '@/layouts/MainLayout.vue'
import MarkdownContent from '@/components/MarkdownContent.vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Archive, ChevronDown, FileAudio, FileImage, FileText, Film, FolderOpen, MessageSquareText, Sparkles, ExternalLink } from 'lucide-vue-next'
import { API_BASE_URL, createAnnotation, getAnnotations, getItems, type AnnotationItem, type RawItem } from '@/lib/api'

type InspectorTab = 'summary' | 'notes'

interface IntentGroup {
  key: string
  title: string
  icon: any
  items: RawItem[]
}

const favoritedItems = ref<RawItem[]>([])
const activeItem = ref<RawItem | null>(null)
const isLoading = ref(true)
const activeInspectorTab = ref<InspectorTab>('summary')
const annotationDraft = ref('')
const annotations = ref<AnnotationItem[]>([])
const annotationsLoading = ref(false)
const savingAnnotation = ref(false)

const groupState = ref<Record<string, boolean>>({
  video: true,
  article: true,
  document: true,
  image: true,
  audio: true,
  other: true,
})

function intentGroupKey(intent?: string | null) {
  switch (intent) {
    case 'video':
      return 'video'
    case 'article':
      return 'article'
    case 'document':
      return 'document'
    case 'image':
      return 'image'
    case 'audio':
      return 'audio'
    default:
      return 'other'
  }
}

function groupMeta(groupKey: string) {
  switch (groupKey) {
    case 'video':
      return { title: 'Videos', icon: Film }
    case 'article':
      return { title: 'Articles', icon: FileText }
    case 'document':
      return { title: 'Documents', icon: FolderOpen }
    case 'image':
      return { title: 'Images', icon: FileImage }
    case 'audio':
      return { title: 'Audio', icon: FileAudio }
    default:
      return { title: 'Other', icon: Archive }
  }
}

function toAbsoluteUrl(url?: string | null) {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  const normalizedPath = url.startsWith('/') ? url : `/${url}`
  return `${API_BASE_URL}${normalizedPath}`
}

const groupedItems = computed<IntentGroup[]>(() => {
  const buckets = new Map<string, RawItem[]>()
  for (const item of favoritedItems.value) {
    const key = intentGroupKey(item.intent)
    const list = buckets.get(key) ?? []
    list.push(item)
    buckets.set(key, list)
  }

  const order = ['video', 'article', 'document', 'image', 'audio', 'other']
  return order
    .filter((key) => (buckets.get(key)?.length ?? 0) > 0)
    .map((key) => {
      const meta = groupMeta(key)
      const items = (buckets.get(key) ?? []).slice().sort((a, b) => {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      })
      return { key, title: meta.title, icon: meta.icon, items }
    })
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

const openableDocumentUrl = computed(() => {
  return toAbsoluteUrl(activeItem.value?.local_asset_url || activeItem.value?.raw_link || '')
})

async function loadFavoritedItems() {
  isLoading.value = true
  try {
    favoritedItems.value = await getItems(undefined, 0, { favoritedOnly: true })
    if (!activeItem.value && favoritedItems.value.length > 0) {
      activeItem.value = favoritedItems.value[0] || null
    }
    if (activeItem.value) {
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
      anchor_data: {},
    })
    annotationDraft.value = ''
    await loadAnnotations()
  } finally {
    savingAnnotation.value = false
  }
}

function selectItem(item: RawItem) {
  activeItem.value = item
}

function toggleGroup(groupKey: string) {
  groupState.value[groupKey] = !groupState.value[groupKey]
}

watch(
  () => activeItem.value?.id,
  async () => {
    if (activeInspectorTab.value === 'notes') {
      await loadAnnotations()
    }
  }
)

watch(activeInspectorTab, async (tab) => {
  if (tab === 'notes') {
    await loadAnnotations()
  }
})

onMounted(async () => {
  await loadFavoritedItems()
  if (activeInspectorTab.value === 'notes') {
    await loadAnnotations()
  }
})
</script>

<template>
  <MainLayout>
    <div class="flex h-[calc(100vh-8.5rem)] min-h-[640px] flex-col gap-4 overflow-hidden">
      <div class="space-y-1">
        <h1 class="text-3xl font-semibold tracking-tight">Vault</h1>
        <p class="text-sm text-muted-foreground">第二大脑收藏库。集中阅读、回放并沉淀你的高价值内容。</p>
      </div>

      <div class="grid min-h-0 flex-1 grid-cols-[minmax(220px,20%)_minmax(0,55%)_minmax(280px,25%)] gap-4 overflow-hidden">
        <section class="flex min-h-0 flex-col overflow-hidden rounded-2xl border bg-muted/30">
          <div class="flex items-center justify-between border-b px-4 py-3">
            <div>
              <h2 class="text-sm font-semibold">Library Tree</h2>
              <p class="text-xs text-muted-foreground">按内容类型整理你的收藏</p>
            </div>
            <Badge variant="secondary">{{ favoritedItems.length }}</Badge>
          </div>
          <div class="min-h-0 flex-1">
            <ScrollArea class="h-full">
            <div class="space-y-4 p-3">
              <template v-if="isLoading">
                <Skeleton class="h-6 w-full" />
                <Skeleton class="h-24 w-full" />
                <Skeleton class="h-16 w-full" />
              </template>
              <template v-else-if="groupedItems.length === 0">
                <div class="rounded-xl border border-dashed bg-background/80 p-4 text-sm text-muted-foreground">
                  你还没有收藏任何内容，先去信息流里收藏几条，再回来搭建自己的 Vault。
                </div>
              </template>
              <template v-else>
                <div v-for="group in groupedItems" :key="group.key" class="rounded-xl border bg-background/90">
                  <button
                    class="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium transition-colors hover:bg-muted/50 rounded-lg"
                    @click="toggleGroup(group.key)"
                  >
                    <span class="flex items-center gap-2">
                      <component :is="group.icon" class="h-4 w-4 text-muted-foreground" />
                      {{ group.title }}
                    </span>
                    <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
                      {{ group.items.length }}
                      <ChevronDown
                        class="h-4 w-4 transition-transform duration-200"
                        :class="!groupState[group.key] ? '-rotate-90' : 'rotate-0'"
                      />
                    </span>
                  </button>
                  <div v-if="groupState[group.key]" class="space-y-1 px-2 pb-2">
                    <button
                      v-for="item in group.items"
                      :key="item.id"
                      class="w-full rounded-lg px-2 py-2 text-left transition hover:bg-muted"
                      :class="activeItem?.id === item.id ? 'bg-primary/10 text-foreground' : 'text-muted-foreground'"
                      @click="selectItem(item)"
                    >
                      <div class="truncate text-sm font-medium text-foreground">{{ item.title }}</div>
                      <div class="truncate text-xs text-muted-foreground">{{ item.summary || item.content_text || item.source_type }}</div>
                    </button>
                  </div>
                </div>
              </template>
            </div>
            </ScrollArea>
          </div>
        </section>

        <section class="flex min-h-0 flex-col overflow-hidden rounded-2xl border bg-background">
          <div class="border-b px-5 py-4">
            <h2 class="text-lg font-semibold">{{ activeItem?.title || 'Reader Pane' }}</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              {{ activeItem?.summary || '选择左侧一个收藏条目，开始阅读或回放。' }}
            </p>
          </div>
          <div class="min-h-0 flex-1">
            <ScrollArea class="h-full">
            <div class="p-5">
              <template v-if="!activeItem">
                <div class="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">
                  从左侧选择一条收藏内容。
                </div>
              </template>
              <template v-else-if="activeItem.intent === 'video'">
                <video
                  controls
                  class="w-full rounded-xl bg-black"
                  :src="toAbsoluteUrl(activeItem.local_asset_url || activeItem.raw_link)"
                />
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
              <template v-else-if="activeItem.intent === 'document'">
                  <div class="space-y-4">
                    <div class="rounded-xl border bg-muted/20 p-4">
                      <h3 class="text-base font-medium">{{ activeItem.title }}</h3>
                      <MarkdownContent
                        :content="articleContent"
                        mode="readme"
                        class="mt-2 text-sm text-muted-foreground"
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
                  <MarkdownContent :content="articleContent" mode="readme" class="text-sm" />
                </div>
              </template>
            </div>
            </ScrollArea>
          </div>
        </section>

        <section class="flex min-h-0 flex-col overflow-hidden rounded-2xl border bg-background">
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
                  <MarkdownContent :content="summaryContent" mode="summary" />
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
                      v-model="annotationDraft"
                      placeholder="写下一条你的想法、摘要或行动项..."
                      class="min-h-28 w-full rounded-xl border bg-background px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    />
                    <Button :disabled="savingAnnotation || !annotationDraft.trim()" @click="saveAnnotation">
                      保存思考
                    </Button>
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
