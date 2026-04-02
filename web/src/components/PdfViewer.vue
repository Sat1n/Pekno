<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, useTemplateRef, watch } from 'vue'
import { useColorMode } from '@vueuse/core'
import { Skeleton } from '@/components/ui/skeleton'
import { Camera, Pin } from 'lucide-vue-next'
import { getDocument, TextLayerBuilder, TextLayerImages, type PDFDocumentProxy } from '@/lib/pdfjs'
import { buildAuthorizedHeaders } from '@/lib/api'

const props = defineProps<{
  url: string
  highlights?: Array<{
    page: number
    rects: Array<{ x: number; y: number; width: number; height: number }>
    kind?: 'text' | 'screenshot'
    active?: boolean
  }>
}>()

const emit = defineEmits<{
  quote: [payload: {
    text: string
    page: number
    rects: Array<{ x: number; y: number; width: number; height: number }>
  }]
  screenshotCapture: [payload: {
    blob: Blob
    page: number
    rectNorm: { x: number; y: number; width: number; height: number }
    imageWidth: number
    imageHeight: number
  }]
  captureModeChange: [active: boolean]
  stateChange: [payload: {
    page: number
    totalPages: number
    canGoPrev: boolean
    canGoNext: boolean
    zoomMode: 'fit-width' | 'fit-page' | '100' | '125' | '150'
  }]
}>()

const viewerRef = useTemplateRef<HTMLElement>('viewer')
const pageShellRef = useTemplateRef<HTMLElement>('pageShell')
const canvasRef = useTemplateRef<HTMLCanvasElement>('canvas')
const textLayerRef = useTemplateRef<HTMLDivElement>('textLayer')

const pdfDoc = shallowRef<PDFDocumentProxy | null>(null)
const totalPages = ref(0)
const currentPage = ref(1)
const loading = ref(false)
const errorMessage = ref('')
const selectedText = ref('')
const quoteButton = ref<{ top: number; left: number } | null>(null)
const selectedRects = ref<Array<{ x: number; y: number; width: number; height: number }>>([])
const zoomMode = ref<'fit-width' | 'fit-page' | '100' | '125' | '150'>('fit-page')
const captureMode = ref(false)
const captureRect = ref<{ x: number; y: number; width: number; height: number } | null>(null)
const captureStart = ref<{ x: number; y: number } | null>(null)
const currentScale = ref(1)
const currentViewportSize = ref({ width: 0, height: 0 })

let renderToken = 0
let activeTextLayer: TextLayerBuilder | null = null
let resizeObserver: ResizeObserver | null = null
let activePageRenderTask: { cancel: () => void; promise: Promise<void> } | null = null
let resizeRaf = 0
let lastViewportWidth = 0
let delayedRenderTimer = 0

const canGoPrev = computed(() => currentPage.value > 1)
const canGoNext = computed(() => currentPage.value < totalPages.value)
const colorMode = useColorMode()
const isDarkMode = computed(() => colorMode.value === 'dark')
const isFitZoomMode = computed(() => zoomMode.value === 'fit-width' || zoomMode.value === 'fit-page')
const pageHighlights = computed(() => {
  return (props.highlights || [])
    .filter((highlight) => highlight.page === currentPage.value)
    .flatMap((highlight, groupIndex) =>
      (highlight.rects || []).map((rect, rectIndex) => ({
        ...rect,
        kind: highlight.kind || 'text',
        active: Boolean(highlight.active),
        key: `${highlight.page}-${highlight.kind || 'text'}-${groupIndex}-${rectIndex}`,
      })),
    )
})
const zoomOptions = [
  { value: 'fit-page', label: '整页' },
  { value: 'fit-width', label: '适宽' },
  { value: '100', label: '100%' },
  { value: '125', label: '125%' },
  { value: '150', label: '150%' },
] as const

function setZoomMode(mode: typeof zoomMode.value) {
  if (zoomMode.value === mode) return
  zoomMode.value = mode
}

function emitViewerState() {
  emit('stateChange', {
    page: currentPage.value,
    totalPages: totalPages.value,
    canGoPrev: canGoPrev.value,
    canGoNext: canGoNext.value,
    zoomMode: zoomMode.value,
  })
}

function hideQuoteButton() {
  quoteButton.value = null
  selectedText.value = ''
  selectedRects.value = []
}

function setCaptureMode(active: boolean) {
  captureMode.value = active
  if (!active) {
    captureRect.value = null
    captureStart.value = null
  }
  hideQuoteButton()
  clearSelection()
  emit('captureModeChange', active)
}

function clearSelection() {
  const selection = window.getSelection()
  selection?.removeAllRanges()
}

async function blobFromCanvas(canvas: HTMLCanvasElement) {
  return await new Promise<Blob | null>((resolve) => {
    canvas.toBlob((blob) => resolve(blob), 'image/png')
  })
}

function queueRender(delay = 0) {
  if (delayedRenderTimer) {
    window.clearTimeout(delayedRenderTimer)
    delayedRenderTimer = 0
  }

  const run = () => {
    delayedRenderTimer = 0
    void renderPage()
  }

  if (delay > 0) {
    delayedRenderTimer = window.setTimeout(run, delay)
    return
  }

  run()
}

async function waitForStableLayout() {
  await nextTick()

  for (let attempt = 0; attempt < 4; attempt += 1) {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

    const host = viewerRef.value
    const canvas = canvasRef.value
    const textLayer = textLayerRef.value
    if (!host || !canvas || !textLayer) {
      return null
    }

    const width = host.clientWidth || host.getBoundingClientRect().width
    if (width > 40) {
      return { host, canvas, textLayer }
    }
  }

  return null
}

async function loadDocument() {
  hideQuoteButton()
  errorMessage.value = ''
  loading.value = true
  let loaded = false

  try {
    activeTextLayer?.cancel()
    activeTextLayer = null

    const previousDoc = pdfDoc.value
    pdfDoc.value = null
    if (previousDoc) {
      await previousDoc.destroy()
    }

    const task = getDocument({
      url: props.url,
      httpHeaders: buildAuthorizedHeaders(),
    })
    const doc = await task.promise
    pdfDoc.value = markRaw(doc)
    totalPages.value = doc.numPages
    currentPage.value = 1
    loaded = true
  } catch (error) {
    console.error('加载 PDF 失败:', error)
    errorMessage.value = '无法加载 PDF，请确认文件路径和格式正常。'
  } finally {
    loading.value = false
    if (loaded && pdfDoc.value) {
      await nextTick()
      queueRender()
      queueRender(120)
    }
  }
}

async function renderPage() {
  if (!pdfDoc.value || !pageShellRef.value) return

  const token = ++renderToken
  hideQuoteButton()
  errorMessage.value = ''

  try {
    if (activePageRenderTask) {
      activePageRenderTask.cancel()
      try {
        await activePageRenderTask.promise
      } catch {
        // Swallow cancellation-related errors from the previous render.
      }
      activePageRenderTask = null
    }

    const page = await pdfDoc.value.getPage(currentPage.value)
    if (token !== renderToken) return

    const layout = await waitForStableLayout()
    if (token !== renderToken) return
    if (!layout) {
      queueRender(60)
      return
    }

    const baseViewport = page.getViewport({ scale: 1 })
    const hostWidth = layout.host.clientWidth || layout.host.getBoundingClientRect().width
    const shellWidth = Math.max(hostWidth - 32, 280)
    const availableHeight = Math.max(layout.host.clientHeight - 24, 320)
    const fitWidthScale = shellWidth / baseViewport.width
    const fitPageScale = Math.min((shellWidth - 8) / baseViewport.width, availableHeight / baseViewport.height)

    let scale = fitPageScale
    switch (zoomMode.value) {
      case 'fit-width':
        scale = fitWidthScale
        break
      case '100':
        scale = 1
        break
      case '125':
        scale = 1.25
        break
      case '150':
        scale = 1.5
        break
      default:
        scale = fitPageScale
        break
    }

    scale = Math.max(Math.min(scale, 2.2), 0.45)
    currentScale.value = scale
    const viewport = page.getViewport({ scale })
    currentViewportSize.value = { width: viewport.width, height: viewport.height }
    const canvas = layout.canvas
    const textLayerHost = layout.textLayer
    if (
      token === renderToken
      && Math.abs(viewport.width - lastViewportWidth) < 1
      && canvas.width > 0
      && canvas.height > 0
      && currentPage.value <= totalPages.value
    ) {
      // Keep the current bitmap when the resize observer fires without a meaningful width change.
    }
    lastViewportWidth = viewport.width
    const context = canvas.getContext('2d')
    if (!context) {
      errorMessage.value = '无法初始化 PDF 画布。'
      return
    }

    const outputScaleBase = window.devicePixelRatio || 1
    const outputScale = isFitZoomMode.value
      ? outputScaleBase
      : Math.min(outputScaleBase * 1.5, 3)
    canvas.width = Math.floor(viewport.width * outputScale)
    canvas.height = Math.floor(viewport.height * outputScale)
    canvas.style.width = `${viewport.width}px`
    canvas.style.height = `${viewport.height}px`

    context.setTransform(outputScale, 0, 0, outputScale, 0, 0)
    context.clearRect(0, 0, canvas.width, canvas.height)

    const renderTask = page.render({
      canvas,
      canvasContext: context,
      viewport,
    })
    activePageRenderTask = renderTask

    await renderTask.promise
    activePageRenderTask = null

    if (token !== renderToken) return

    textLayerHost.innerHTML = ''
    textLayerHost.style.width = `${viewport.width}px`
    textLayerHost.style.height = `${viewport.height}px`
    textLayerHost.style.setProperty('--scale-factor', String(scale))
    textLayerHost.style.setProperty('--total-scale-factor', String(scale))
    textLayerHost.style.setProperty('--user-unit', '1')
    layout.host.style.setProperty('--scale-factor', String(scale))
    layout.host.style.setProperty('--total-scale-factor', String(scale))
    layout.host.style.setProperty('--user-unit', '1')

    activeTextLayer?.cancel()
    activeTextLayer = null

    try {
      activeTextLayer = new TextLayerBuilder({
        pdfPage: page,
        onAppend: (div: HTMLDivElement) => {
          textLayerHost.appendChild(div)
        },
      })

      await activeTextLayer.render({
        viewport,
        images: new TextLayerImages(0, [], viewport, () => canvas),
      })
    } catch (textLayerError) {
      console.warn('PDF 文本层渲染失败，已降级为仅画布模式:', textLayerError)
      textLayerHost.innerHTML = ''
    }
  } catch (error) {
    if (
      typeof error === 'object'
      && error
      && 'name' in error
      && (error as { name?: string }).name === 'RenderingCancelledException'
    ) {
      return
    }
    console.error('渲染 PDF 页面失败:', error)
    queueRender(80)
    errorMessage.value = 'PDF 页面正在准备渲染，请稍候...'
  }
}

function updateSelectionState() {
  if (captureMode.value) {
    hideQuoteButton()
    return
  }
  if (!viewerRef.value || !textLayerRef.value) return

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
    commonNode.nodeType === Node.ELEMENT_NODE ? commonNode : commonNode.parentNode
  const withinTextLayer = !!targetNode && textLayerRef.value.contains(targetNode)
  if (!withinTextLayer) {
    hideQuoteButton()
    return
  }

  const rect = range.getBoundingClientRect()
  const viewerRect = viewerRef.value.getBoundingClientRect()
  const textLayerRect = textLayerRef.value.getBoundingClientRect()
  const normalizedRects = Array.from(range.getClientRects())
    .map((clientRect) => {
      const left = Math.max(clientRect.left, textLayerRect.left)
      const top = Math.max(clientRect.top, textLayerRect.top)
      const right = Math.min(clientRect.right, textLayerRect.right)
      const bottom = Math.min(clientRect.bottom, textLayerRect.bottom)
      const width = right - left
      const height = bottom - top
      if (width <= 1 || height <= 1 || textLayerRect.width <= 0 || textLayerRect.height <= 0) {
        return null
      }
      return {
        x: (left - textLayerRect.left) / textLayerRect.width,
        y: (top - textLayerRect.top) / textLayerRect.height,
        width: width / textLayerRect.width,
        height: height / textLayerRect.height,
      }
    })
    .filter((item): item is { x: number; y: number; width: number; height: number } => Boolean(item))

  if (normalizedRects.length === 0) {
    hideQuoteButton()
    return
  }

  const left = Math.min(
    Math.max(rect.left - viewerRect.left, 12),
    Math.max(viewerRect.width - 120, 12),
  )
  const top = Math.max(rect.top - viewerRect.top - 40, 12)

  selectedText.value = text
  selectedRects.value = normalizedRects
  quoteButton.value = { top, left }
}

function handleMouseUp() {
  if (captureMode.value) return
  window.setTimeout(() => updateSelectionState(), 0)
}

function handleSelectionChange() {
  if (captureMode.value) {
    hideQuoteButton()
    return
  }
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) {
    hideQuoteButton()
  }
}

function emitQuote() {
  if (!selectedText.value.trim() || selectedRects.value.length === 0) return
  emit('quote', {
    text: selectedText.value.trim(),
    page: currentPage.value,
    rects: selectedRects.value,
  })
  clearSelection()
  hideQuoteButton()
}

function highlightRectStyle(rect: { x: number; y: number; width: number; height: number }) {
  const width = currentViewportSize.value.width
  const height = currentViewportSize.value.height
  return {
    left: `${rect.x * width}px`,
    top: `${rect.y * height}px`,
    width: `${rect.width * width}px`,
    height: `${rect.height * height}px`,
  }
}

function goPrev() {
  if (!canGoPrev.value) return
  currentPage.value -= 1
}

function goNext() {
  if (!canGoNext.value) return
  currentPage.value += 1
}

function handleCapturePointerDown(event: PointerEvent) {
  if (!captureMode.value || !pageShellRef.value) return

  const shellRect = pageShellRef.value.getBoundingClientRect()
  captureStart.value = {
    x: Math.max(0, Math.min(event.clientX - shellRect.left, shellRect.width)),
    y: Math.max(0, Math.min(event.clientY - shellRect.top, shellRect.height)),
  }
  captureRect.value = {
    x: captureStart.value.x,
    y: captureStart.value.y,
    width: 0,
    height: 0,
  }
}

function handleCapturePointerMove(event: PointerEvent) {
  if (!captureMode.value || !captureStart.value || !pageShellRef.value) return

  const shellRect = pageShellRef.value.getBoundingClientRect()
  const currentX = Math.max(0, Math.min(event.clientX - shellRect.left, shellRect.width))
  const currentY = Math.max(0, Math.min(event.clientY - shellRect.top, shellRect.height))
  const x = Math.min(captureStart.value.x, currentX)
  const y = Math.min(captureStart.value.y, currentY)
  const width = Math.abs(currentX - captureStart.value.x)
  const height = Math.abs(currentY - captureStart.value.y)

  captureRect.value = { x, y, width, height }
}

async function handleCapturePointerUp() {
  if (!captureMode.value || !captureRect.value || !canvasRef.value) {
    captureStart.value = null
    return
  }

  const canvas = canvasRef.value
  const shellRect = pageShellRef.value?.getBoundingClientRect()
  if (!shellRect) {
    setCaptureMode(false)
    return
  }

  const rect = captureRect.value
  captureStart.value = null

  if (rect.width < 12 || rect.height < 12) {
    captureRect.value = null
    return
  }

  const scaleX = canvas.width / shellRect.width
  const scaleY = canvas.height / shellRect.height
  const sourceX = Math.max(0, Math.floor(rect.x * scaleX))
  const sourceY = Math.max(0, Math.floor(rect.y * scaleY))
  const sourceWidth = Math.max(1, Math.floor(rect.width * scaleX))
  const sourceHeight = Math.max(1, Math.floor(rect.height * scaleY))

  const exportCanvas = document.createElement('canvas')
  exportCanvas.width = sourceWidth
  exportCanvas.height = sourceHeight
  const exportContext = exportCanvas.getContext('2d')
  if (!exportContext) {
    setCaptureMode(false)
    return
  }

  exportContext.drawImage(
    canvas,
    sourceX,
    sourceY,
    sourceWidth,
    sourceHeight,
    0,
    0,
    sourceWidth,
    sourceHeight,
  )

  const blob = await blobFromCanvas(exportCanvas)
  const rectNorm = {
    x: rect.x / shellRect.width,
    y: rect.y / shellRect.height,
    width: rect.width / shellRect.width,
    height: rect.height / shellRect.height,
  }

  if (blob) {
    emit('screenshotCapture', {
      blob,
      page: currentPage.value,
      rectNorm,
      imageWidth: sourceWidth,
      imageHeight: sourceHeight,
    })
  }

  setCaptureMode(false)
}

function handleCapturePointerCancel() {
  captureStart.value = null
  captureRect.value = null
}

watch(
  () => props.url,
  async () => {
    if (props.url) {
      await loadDocument()
    }
  },
  { immediate: true },
)

watch(currentPage, async () => {
  if (captureMode.value) {
    setCaptureMode(false)
  }
  emitViewerState()
  await nextTick()
  queueRender()
})

watch(zoomMode, async () => {
  if (captureMode.value) {
    setCaptureMode(false)
  }
  lastViewportWidth = 0
  const canvas = canvasRef.value
  if (canvas) {
    canvas.width = 0
    canvas.height = 0
    canvas.style.width = '0px'
    canvas.style.height = '0px'
  }
  emitViewerState()
  await nextTick()
  queueRender()
})

watch(totalPages, () => {
  emitViewerState()
})

onMounted(() => {
  emitViewerState()
  document.addEventListener('selectionchange', handleSelectionChange)
  document.addEventListener('keydown', handleViewerKeydown)
  if (typeof ResizeObserver !== 'undefined' && viewerRef.value) {
    resizeObserver = new ResizeObserver(async () => {
      if (!pdfDoc.value || loading.value) return
      if (resizeRaf) {
        cancelAnimationFrame(resizeRaf)
      }
      resizeRaf = requestAnimationFrame(() => {
        resizeRaf = 0
        queueRender()
      })
    })
    resizeObserver.observe(viewerRef.value)
  }
})

onBeforeUnmount(async () => {
  document.removeEventListener('selectionchange', handleSelectionChange)
  document.removeEventListener('keydown', handleViewerKeydown)
  if (resizeRaf) {
    cancelAnimationFrame(resizeRaf)
    resizeRaf = 0
  }
  if (delayedRenderTimer) {
    window.clearTimeout(delayedRenderTimer)
    delayedRenderTimer = 0
  }
  resizeObserver?.disconnect()
  activeTextLayer?.cancel()
  if (activePageRenderTask) {
    activePageRenderTask.cancel()
    activePageRenderTask = null
  }
  clearSelection()
  const currentDoc = pdfDoc.value
  pdfDoc.value = null
  if (currentDoc) {
    try {
      await currentDoc.destroy()
    } catch (error) {
      console.warn('销毁 PDF 文档实例失败:', error)
    }
  }
})

defineExpose({
  goPrev,
  goNext,
  goToPage: (page: number) => {
    if (!Number.isFinite(page)) return
    const target = Math.min(Math.max(Math.round(page), 1), totalPages.value || 1)
    if (target === currentPage.value) return
    currentPage.value = target
  },
  setZoomMode,
  setCaptureMode,
  zoomOptions,
})

function handleViewerKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && captureMode.value) {
    event.preventDefault()
    setCaptureMode(false)
  }
}
</script>

<template>
  <div class="h-full min-h-0">
    <div
      ref="viewer"
      class="pdf-viewer relative h-full min-h-0 min-w-0 overflow-auto rounded-2xl border bg-muted/10 p-3"
      :class="{ 'pdf-viewer--dark': isDarkMode }"
      :style="{ '--scale-factor': String(currentScale) }"
    >
      <div v-if="loading" class="space-y-3">
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-[70vh] w-full" />
      </div>

      <div v-else-if="errorMessage" class="rounded-xl border border-dashed bg-background/70 p-6 text-sm text-muted-foreground">
        {{ errorMessage }}
      </div>

      <div
        v-else
        ref="pageShell"
        class="pdf-page-shell relative mx-auto w-fit max-w-full"
        :class="{ 'pdf-page-shell--fit': isFitZoomMode, 'pdf-page-shell--manual': !isFitZoomMode }"
        :style="{ '--scale-factor': String(currentScale), '--total-scale-factor': String(currentScale), '--user-unit': '1' }"
        @mouseup="handleMouseUp"
      >
        <canvas
          ref="canvas"
          class="pdf-page-canvas block rounded-lg shadow-sm"
          :class="{ 'pdf-page-canvas--fit': isFitZoomMode, 'pdf-page-canvas--manual': !isFitZoomMode }"
        />
        <div ref="textLayer" class="pdf-text-layer absolute inset-0 overflow-hidden rounded-lg" />
        <div class="pdf-highlight-layer pointer-events-none absolute inset-0 overflow-hidden rounded-lg">
          <div
            v-for="rect in pageHighlights"
            :key="rect.key"
            class="pdf-highlight-rect absolute"
            :class="{
              'pdf-highlight-rect--text': rect.kind === 'text',
              'pdf-highlight-rect--screenshot': rect.kind === 'screenshot',
              'pdf-highlight-rect--active': rect.active,
            }"
            :style="highlightRectStyle(rect)"
          />
        </div>
        <div
          v-if="captureMode"
          class="absolute inset-0 z-10 cursor-crosshair rounded-lg bg-black/5"
          @pointerdown.prevent="handleCapturePointerDown"
          @pointermove.prevent="handleCapturePointerMove"
          @pointerup.prevent="handleCapturePointerUp"
          @pointerleave.prevent="handleCapturePointerCancel"
          @pointercancel.prevent="handleCapturePointerCancel"
        >
          <div
            v-if="captureRect"
            class="absolute border-2 border-primary bg-primary/15 shadow-sm"
            :style="{
              left: `${captureRect.x}px`,
              top: `${captureRect.y}px`,
              width: `${captureRect.width}px`,
              height: `${captureRect.height}px`,
            }"
          />
          <div class="absolute left-3 top-3 inline-flex items-center gap-1 rounded-full border bg-background/95 px-3 py-1.5 text-xs font-medium shadow-sm backdrop-blur">
            <Camera class="h-3.5 w-3.5" />
            拖拽框选截图区域，按 Esc 退出
          </div>
        </div>

        <button
          v-if="quoteButton && !captureMode"
          type="button"
          class="absolute z-20 inline-flex items-center gap-1 rounded-full border bg-background/95 px-3 py-1.5 text-xs font-medium shadow-sm backdrop-blur"
          :style="{ top: `${quoteButton.top}px`, left: `${quoteButton.left}px` }"
          @click="emitQuote"
        >
          <Pin class="h-3.5 w-3.5" />
          引用
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-viewer {
  height: 100%;
  min-height: 100%;
}

.pdf-page-shell {
  border-radius: 0.9rem;
}

.pdf-viewer canvas {
  height: auto;
}

.pdf-page-shell--fit {
  max-width: 100%;
}

.pdf-page-shell--manual {
  max-width: none;
}

.pdf-page-canvas--fit {
  max-width: 100%;
}

.pdf-page-canvas--manual {
  max-width: none;
}

.pdf-viewer--dark {
  background: rgba(11, 15, 23, 0.92);
  border-color: rgba(71, 85, 105, 0.45);
}

.pdf-viewer--dark .pdf-page-shell {
  background:
    radial-gradient(circle at top, rgba(148, 163, 184, 0.08), transparent 42%),
    linear-gradient(180deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.92));
  box-shadow:
    0 18px 40px rgba(2, 6, 23, 0.32),
    inset 0 0 0 1px rgba(148, 163, 184, 0.08);
}

.pdf-viewer--dark .pdf-page-canvas {
  filter: invert(1) hue-rotate(180deg) brightness(0.9) contrast(0.92);
  box-shadow:
    0 12px 30px rgba(2, 6, 23, 0.34),
    0 0 0 1px rgba(148, 163, 184, 0.08);
}

.pdf-viewer--dark .pdf-text-layer {
  opacity: 0.9;
}

.pdf-text-layer :deep(.textLayer) {
  position: absolute;
  inset: 0;
}

.pdf-text-layer :deep(.endOfContent) {
  display: none;
}

.pdf-text-layer :deep(span),
.pdf-text-layer :deep(br) {
  cursor: text;
}

.pdf-highlight-rect {
  border-radius: 0.25rem;
}

.pdf-highlight-rect--text {
  border: none;
  background: rgb(248 113 113 / 0.24);
  mix-blend-mode: multiply;
}

.pdf-highlight-rect--text.pdf-highlight-rect--active {
  background: rgb(239 68 68 / 0.3);
}

.pdf-highlight-rect--screenshot {
  border: 2px solid rgb(239 68 68 / 0.92);
  background: rgb(248 113 113 / 0.08);
  box-shadow: 0 0 0 1px rgb(254 242 242 / 0.35);
}

.pdf-highlight-rect--screenshot.pdf-highlight-rect--active {
  background: rgb(248 113 113 / 0.14);
}

.pdf-viewer--dark .pdf-highlight-rect--text {
  background: rgb(248 113 113 / 0.2);
  mix-blend-mode: screen;
}

.pdf-viewer--dark .pdf-highlight-rect--text.pdf-highlight-rect--active {
  background: rgb(248 113 113 / 0.28);
}

.pdf-viewer--dark .pdf-highlight-rect--screenshot {
  border-color: rgb(248 113 113 / 0.96);
  background: rgb(248 113 113 / 0.05);
}
</style>
