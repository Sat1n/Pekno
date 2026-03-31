<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'
import { useColorMode } from '@vueuse/core'
import { Skeleton } from '@/components/ui/skeleton'
import { Pin } from 'lucide-vue-next'
import { API_BASE_URL } from '@/lib/api'
import { renderMarkdown, type MarkdownMode, type MarkdownTheme } from '@/lib/markdown'

const props = withDefaults(
  defineProps<{
    content?: string | null
    mode?: MarkdownMode
    class?: string
    quoteable?: boolean
  }>(),
  {
    content: '',
    mode: 'readme',
    class: '',
    quoteable: false,
  },
)

const emit = defineEmits<{
  quote: [payload: {
    text: string
    mode: MarkdownMode
    heading: string
    excerpt: string
  }]
}>()

const mode = useColorMode()
const renderedHtml = ref('')
const isRendering = ref(false)
const markdownRoot = useTemplateRef<HTMLElement>('markdownRoot')
const containerRef = useTemplateRef<HTMLElement>('container')
const cleanupListeners: Array<() => void> = []
const selectedText = ref('')
const quoteButton = ref<{ top: number; left: number } | null>(null)

const resolvedTheme = computed<MarkdownTheme>(() => {
  if (mode.value === 'dark') return 'dark'
  if (mode.value === 'light') return 'light'
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
})

const proseClass = computed(() => {
  const base =
    'vault-markdown prose prose-sm max-w-none text-foreground prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground prose-a:text-primary prose-code:text-foreground prose-pre:p-0 prose-pre:bg-transparent prose-table:w-full'
  const tone = resolvedTheme.value === 'dark' ? 'prose-invert' : ''
  const density = props.mode === 'summary' ? 'prose-p:leading-7 prose-li:leading-7' : 'prose-p:leading-7 prose-li:leading-7'
  return [base, tone, density, props.class].filter(Boolean).join(' ')
})

function clearCodeBlockEnhancements() {
  while (cleanupListeners.length > 0) {
    cleanupListeners.pop()?.()
  }
}

function hideQuoteButton() {
  quoteButton.value = null
  selectedText.value = ''
}

function clearSelection() {
  const selection = window.getSelection()
  selection?.removeAllRanges()
}

async function copyCode(code: string, button: HTMLButtonElement) {
  try {
    await navigator.clipboard.writeText(code)
    const original = button.innerHTML
    button.innerHTML = '<span aria-hidden="true">✓</span>'
    window.setTimeout(() => {
      button.innerHTML = original || '<span aria-hidden="true">⧉</span>'
    }, 1600)
  } catch {
    button.innerHTML = '<span aria-hidden="true">!</span>'
    window.setTimeout(() => {
      button.innerHTML = '<span aria-hidden="true">⧉</span>'
    }, 1600)
  }
}

function enhanceCodeBlocks() {
  clearCodeBlockEnhancements()
  const root = markdownRoot.value
  if (!root) return

  const blocks = root.querySelectorAll('pre.shiki, pre.vault-shiki-fallback')
  blocks.forEach((block) => {
    if (!(block instanceof HTMLElement)) return

    const wrapper = document.createElement('div')
    wrapper.className = 'vault-code-wrapper'
    block.parentNode?.insertBefore(wrapper, block)
    wrapper.appendChild(block)

    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'vault-copy-button'
    button.setAttribute('aria-label', '复制代码')
    button.innerHTML = '<span aria-hidden="true">⧉</span>'
    wrapper.appendChild(button)

    const onClick = () => {
      void copyCode(block.innerText, button)
    }
    button.addEventListener('click', onClick)
    cleanupListeners.push(() => button.removeEventListener('click', onClick))
  })
}

function toAbsoluteAssetUrl(rawUrl: string) {
  if (!rawUrl) return rawUrl
  if (/^https?:\/\//i.test(rawUrl)) return rawUrl
  if (!rawUrl.startsWith('/')) return rawUrl
  if (!rawUrl.startsWith('/api/static/') && !rawUrl.startsWith('/uploads/')) return rawUrl
  return `${API_BASE_URL}${rawUrl}`
}

function normalizeSrcsetValue(value: string) {
  return value
    .split(',')
    .map((candidate) => {
      const trimmed = candidate.trim()
      if (!trimmed) return ''
      const parts = trimmed.split(/\s+/)
      const rawUrl = parts.shift() ?? ''
      const descriptor = parts.join(' ')
      let normalizedUrl = rawUrl
      if (rawUrl.startsWith('/api/static/') || rawUrl.startsWith('/uploads/')) {
        normalizedUrl = toAbsoluteAssetUrl(rawUrl)
      }
      return descriptor ? `${normalizedUrl} ${descriptor}` : normalizedUrl
    })
    .filter(Boolean)
    .join(', ')
}

function sanitizeRenderedHtml(html: string) {
  if (!html || typeof window === 'undefined') return html

  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  doc.querySelectorAll('[src]').forEach((element) => {
    const src = element.getAttribute('src')
    if (!src) return
    element.setAttribute('src', toAbsoluteAssetUrl(src))
  })
  doc.querySelectorAll('[poster]').forEach((element) => {
    const poster = element.getAttribute('poster')
    if (!poster) return
    element.setAttribute('poster', toAbsoluteAssetUrl(poster))
  })
  doc.querySelectorAll('[srcset]').forEach((element) => {
    const srcset = element.getAttribute('srcset')
    if (!srcset) return
    element.setAttribute('srcset', normalizeSrcsetValue(srcset))
  })

  return doc.body.innerHTML
}

async function refreshMarkdown() {
  if (!props.content?.trim()) {
    isRendering.value = false
    renderedHtml.value = '<p class="text-sm text-muted-foreground">暂无内容。</p>'
    await nextTick()
    enhanceCodeBlocks()
    hideQuoteButton()
    return
  }

  isRendering.value = true
  try {
    const html = await renderMarkdown(props.content, resolvedTheme.value, props.mode)
    renderedHtml.value = sanitizeRenderedHtml(html)
  } finally {
    isRendering.value = false
  }

  await nextTick()
  enhanceCodeBlocks()
  hideQuoteButton()
}

function getNearestHeadingText(root: HTMLElement, targetNode: Node) {
  const headings = Array.from(root.querySelectorAll('h1, h2, h3, h4, h5, h6'))
  let latestHeading = ''
  const targetElement = targetNode.nodeType === Node.ELEMENT_NODE ? targetNode as Element : targetNode.parentElement
  if (!targetElement) return latestHeading

  for (const heading of headings) {
    const position = heading.compareDocumentPosition(targetElement)
    if (position & Node.DOCUMENT_POSITION_FOLLOWING || heading === targetElement) {
      latestHeading = heading.textContent?.trim() || latestHeading
      continue
    }
    break
  }

  return latestHeading
}

function getExcerptFromTarget(targetNode: Node) {
  const element = targetNode.nodeType === Node.ELEMENT_NODE ? targetNode as HTMLElement : targetNode.parentElement
  const excerptHost = element?.closest('p, li, blockquote, td, th') as HTMLElement | null
  const text = excerptHost?.innerText?.replace(/\s+/g, ' ').trim() || ''
  if (!text) return ''
  return text.length <= 220 ? text : `${text.slice(0, 220).trimEnd()}...`
}

function updateSelectionState() {
  if (!props.quoteable || !markdownRoot.value || !containerRef.value) return

  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
    hideQuoteButton()
    return
  }

  const text = selection.toString().trim()
  if (!text) {
    hideQuoteButton()
    return
  }

  const range = selection.getRangeAt(0)
  const commonNode = range.commonAncestorContainer
  const targetNode =
    commonNode.nodeType === Node.ELEMENT_NODE ? commonNode as Element : commonNode.parentElement

  if (!targetNode || !markdownRoot.value.contains(targetNode)) {
    hideQuoteButton()
    return
  }

  const rect = range.getBoundingClientRect()
  const containerRect = containerRef.value.getBoundingClientRect()
  const left = Math.min(
    Math.max(rect.left - containerRect.left, 12),
    Math.max(containerRect.width - 120, 12),
  )
  const top = Math.max(rect.top - containerRect.top - 40, 12)

  selectedText.value = text
  quoteButton.value = { top, left }
}

function handleMouseUp() {
  if (!props.quoteable) return
  window.setTimeout(() => updateSelectionState(), 0)
}

function handleSelectionChange() {
  if (!props.quoteable) return
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) {
    hideQuoteButton()
  }
}

function emitQuote() {
  if (!selectedText.value.trim() || !markdownRoot.value) return

  const selection = window.getSelection()
  const range = selection?.rangeCount ? selection.getRangeAt(0) : null
  const commonNode = range?.commonAncestorContainer
  const targetNode = commonNode
    ? commonNode.nodeType === Node.ELEMENT_NODE ? commonNode : commonNode.parentNode
    : markdownRoot.value

  emit('quote', {
    text: selectedText.value.trim(),
    mode: props.mode,
    heading: targetNode ? getNearestHeadingText(markdownRoot.value, targetNode) : '',
    excerpt: targetNode ? getExcerptFromTarget(targetNode) : '',
  })

  clearSelection()
  hideQuoteButton()
}

watch(
  () => [props.content, props.mode, resolvedTheme.value],
  async () => {
    await refreshMarkdown()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  clearCodeBlockEnhancements()
  document.removeEventListener('selectionchange', handleSelectionChange)
  clearSelection()
})

watch(
  () => props.quoteable,
  (enabled) => {
    document.removeEventListener('selectionchange', handleSelectionChange)
    if (enabled) {
      document.addEventListener('selectionchange', handleSelectionChange)
      return
    }
    hideQuoteButton()
  },
  { immediate: true },
)
</script>

<template>
  <div ref="container" class="relative min-w-0">
    <div v-if="isRendering" class="space-y-3">
      <Skeleton class="h-5 w-1/3" />
      <Skeleton class="h-24 w-full" />
      <Skeleton class="h-5 w-5/6" />
      <Skeleton class="h-5 w-3/4" />
    </div>
    <div
      v-else
      ref="markdownRoot"
      :class="proseClass"
      @mouseup="handleMouseUp"
      v-html="renderedHtml"
    />
    <button
      v-if="quoteButton"
      type="button"
      class="absolute z-20 inline-flex items-center gap-1 rounded-full border bg-background/95 px-3 py-1.5 text-xs font-medium shadow-sm backdrop-blur"
      :style="{ top: `${quoteButton.top}px`, left: `${quoteButton.left}px` }"
      @click="emitQuote"
    >
      <Pin class="h-3.5 w-3.5" />
      引用
    </button>
  </div>
</template>

<style scoped>
.vault-markdown {
  --vault-code-bg: #f6f8fa;
  --vault-code-border: #d0d7de;
  --vault-table-border: #d0d7de;
  --vault-table-head-bg: #f6f8fa;
  --vault-hr-color: #d8dee4;
  --vault-heading-gutter: 1.35rem;
  --vault-copy-bg: #ffffff;
  --vault-copy-bg-overlay: rgba(255, 255, 255, 0.85);
  --vault-copy-hover: #f3f4f6;
  --vault-copy-icon: #656d76;
  --vault-copy-icon-hover: #24292f;
}

:global(.dark) .vault-markdown,
.vault-markdown.prose-invert {
  --vault-code-bg: #161b22;
  --vault-code-border: #30363d;
  --vault-table-border: #30363d;
  --vault-table-head-bg: #1f2630;
  --vault-hr-color: #30363d;
  --vault-copy-bg: #21262d;
  --vault-copy-bg-overlay: rgba(33, 38, 45, 0.85);
  --vault-copy-hover: #30363d;
  --vault-copy-icon: #8b949e;
  --vault-copy-icon-hover: #c9d1d9;
}

.vault-markdown :deep(p),
.vault-markdown :deep(li) {
  line-height: 1.85;
}

.vault-markdown :deep(p) {
  margin-top: 0.9rem;
  margin-bottom: 0.9rem;
}

.vault-markdown :deep(h1),
.vault-markdown :deep(h2),
.vault-markdown :deep(h3),
.vault-markdown :deep(h4) {
  letter-spacing: -0.015em;
}

.vault-markdown :deep(h1) {
  position: relative;
  margin-top: 2rem;
  margin-bottom: 1rem;
  padding-left: var(--vault-heading-gutter);
  font-size: 2rem;
  line-height: 1.2;
  font-weight: 800;
}

.vault-markdown :deep(h2) {
  position: relative;
  margin-top: 1.75rem;
  margin-bottom: 0.85rem;
  padding-left: var(--vault-heading-gutter);
  font-size: 1.55rem;
  line-height: 1.25;
  font-weight: 750;
}

.vault-markdown :deep(h3) {
  position: relative;
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  padding-left: var(--vault-heading-gutter);
  font-size: 1.25rem;
  line-height: 1.3;
  font-weight: 700;
}

.vault-markdown :deep(h4) {
  position: relative;
  margin-top: 1.25rem;
  margin-bottom: 0.65rem;
  padding-left: var(--vault-heading-gutter);
  font-size: 1.05rem;
  line-height: 1.35;
  font-weight: 650;
}

.vault-markdown :deep(.contains-task-list) {
  list-style: none;
  padding-left: 0;
}

.vault-markdown :deep(.task-list-item) {
  display: flex;
  align-items: start;
  gap: 0.625rem;
}

.vault-markdown :deep(.task-list-item-checkbox) {
  margin-top: 0.35rem;
}

.vault-markdown :deep(.vault-code-wrapper) {
  position: relative;
  margin: 1.25rem 0;
  border: 1px solid var(--vault-code-border);
  border-radius: 0.875rem;
  background: var(--vault-code-bg) !important;
}

.vault-markdown :deep(pre.shiki),
.vault-markdown :deep(pre.vault-shiki-fallback) {
  margin: 0;
  padding: 0;
  background: transparent !important;
  border: none;
  box-shadow: none;
}

.vault-markdown :deep(pre.shiki),
.vault-markdown :deep(pre.shiki code),
.vault-markdown :deep(pre.shiki span) {
  background-color: transparent !important;
}

.vault-markdown :deep(pre.shiki code),
.vault-markdown :deep(pre.vault-shiki-fallback code) {
  display: block;
  overflow-x: auto;
  padding: 1rem 1rem 1rem 1.25rem;
  margin-right: 3rem;
  font-size: 0.875rem;
  line-height: 1.65;
  scrollbar-width: thin;
}

.vault-markdown :deep(.vault-copy-button) {
  position: absolute;
  top: 0.8rem;
  right: 0.8rem;
  z-index: 1;
  border: 1px solid var(--vault-code-border);
  border-radius: 0.4rem;
  background: var(--vault-copy-bg-overlay);
  backdrop-filter: blur(4px);
  width: 1.8rem;
  height: 1.8rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  font-size: 0.95rem;
  line-height: 1.1;
  white-space: nowrap;
  color: var(--vault-copy-icon);
  transition: all 0.15s ease;
}

.vault-markdown :deep(.vault-copy-button:hover) {
  background: var(--vault-copy-hover);
  color: var(--vault-copy-icon-hover);
}

.vault-markdown :deep(:not(pre) > code) {
  border: 1px solid hsl(var(--border));
  border-radius: 0.375rem;
  background: color-mix(in oklab, hsl(var(--muted)) 88%, black 12%);
  padding: 0.15rem 0.4rem;
  font-size: 0.875em;
  font-family: "JetBrains Mono", "Fira Code", "SFMono-Regular", Consolas, monospace;
}

.vault-markdown :deep(table) {
  display: table;
  overflow-x: auto;
  width: 100%;
  border-collapse: collapse;
  border: 0;
  border-radius: 0.875rem;
  background: hsl(var(--background));
  box-shadow: inset 0 0 0 1px var(--vault-table-border);
  overflow: hidden;
}

.vault-markdown :deep(table thead th) {
  background: transparent;
  color: hsl(var(--foreground));
}

.vault-markdown :deep(table th),
.vault-markdown :deep(table td) {
  min-width: 8rem;
  border: 1px solid var(--vault-table-border) !important;
  padding: 0.7rem 0.9rem;
  vertical-align: top;
}

.vault-markdown :deep(table thead tr:first-child th) {
  border-top: 0 !important;
}

.vault-markdown :deep(table tbody tr:last-child td) {
  border-bottom: 0 !important;
}

.vault-markdown :deep(table tr > :first-child) {
  border-left: 0 !important;
}

.vault-markdown :deep(table tr > :last-child) {
  border-right: 0 !important;
}

@media (max-width: 640px) {
  .vault-markdown :deep(.vault-copy-button) {
    top: 0.55rem;
    right: 0.55rem;
    width: 1.6rem;
    height: 1.6rem;
    padding: 0;
    font-size: 0.85rem;
  }
}

.vault-markdown :deep(blockquote) {
  border-left: 4px solid hsl(var(--border));
  padding-left: 1rem;
  color: hsl(var(--muted-foreground));
}

.vault-markdown :deep(blockquote > p:first-child > strong:first-child) {
  color: hsl(var(--foreground));
}

.vault-markdown :deep(.markdown-alert) {
  margin: 1.25rem 0;
  border: 1px solid hsl(var(--border));
  border-left: 4px solid hsl(var(--primary));
  border-radius: 0.875rem;
  background: color-mix(in oklab, hsl(var(--muted)) 92%, white 8%);
  padding: 0.875rem 1rem;
}

.vault-markdown :deep(.markdown-alert-title) {
  margin: 0 0 0.5rem;
  font-weight: 700;
  color: hsl(var(--foreground));
}

.vault-markdown :deep(.markdown-alert-warning),
.vault-markdown :deep(.markdown-alert-caution) {
  border-left-color: hsl(var(--destructive));
}

.vault-markdown :deep(.markdown-alert-tip),
.vault-markdown :deep(.markdown-alert-note),
.vault-markdown :deep(.markdown-alert-important) {
  border-left-color: hsl(var(--primary));
}

.vault-markdown :deep(.header-anchor),
.vault-markdown :deep(.vault-heading-anchor) {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  margin-right: 0;
  width: 1rem;
  text-align: center;
  color: hsl(var(--muted-foreground));
  text-decoration: none;
  transition: color 0.15s ease;
}

.vault-markdown :deep(h1:hover .header-anchor),
.vault-markdown :deep(h2:hover .header-anchor),
.vault-markdown :deep(h3:hover .header-anchor),
.vault-markdown :deep(h4:hover .header-anchor),
.vault-markdown :deep(h1:hover .vault-heading-anchor),
.vault-markdown :deep(h2:hover .vault-heading-anchor),
.vault-markdown :deep(h3:hover .vault-heading-anchor),
.vault-markdown :deep(h4:hover .vault-heading-anchor) {
  color: hsl(var(--foreground));
}

.vault-markdown :deep(p[align="center"]) {
  text-align: center;
}

.vault-markdown :deep(picture) {
  display: block;
  margin: 0.35rem 0;
}

.vault-markdown :deep(picture img),
.vault-markdown :deep(p:not([align="center"]) > img) {
  margin-left: auto;
  margin-right: auto;
}

.vault-markdown :deep(img) {
  display: block;
  max-width: 100%;
  border: 1px solid var(--vault-code-border);
  border-radius: 0.875rem;
}

.vault-markdown :deep(a > img),
.vault-markdown :deep(picture img),
.vault-markdown :deep(p[align="center"] > img) {
  display: inline-block;
  margin: 0.2rem;
  border: none;
  border-radius: 0;
  vertical-align: middle;
}

.vault-markdown :deep(hr) {
  border: 0;
  border-top: 1px solid var(--vault-hr-color);
  height: 0;
  margin: 2.4rem 0 2rem;
  background: none;
}
</style>
