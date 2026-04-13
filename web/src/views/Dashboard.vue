<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MainLayout from '@/layouts/MainLayout.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Loader2, RefreshCw, Server, Waves, TerminalSquare, Flame, Siren, Rocket, Filter } from 'lucide-vue-next'
import {
  forceProcessQueue,
  getAdminLogTail,
  getAdminMetrics,
  getAdminUsageTrend,
  getStoredAuthUser,
  triggerPluginSyncApi,
  type AdminMetricsResponse,
  type AdminUsageTrendResponse,
  type PluginHealthItem,
} from '@/lib/api'
import { useToast } from '@/components/ui/toast/use-toast'
import { Toaster } from '@/components/ui/toast'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent])

type LogService = 'hub' | 'worker' | 'scheduler'
type HighlightLevel = 'debug' | 'info' | 'warning' | 'error' | 'critical'
type LogFilterLevel = 'debug' | 'info' | 'warning' | 'error' | 'critical'

const { toast } = useToast()
const currentUser = computed(() => getStoredAuthUser())
const isAdmin = computed(() => ['admin', 'super_admin'].includes(currentUser.value.role || ''))
const metrics = ref<AdminMetricsResponse | null>(null)
const usageTrend = ref<AdminUsageTrendResponse | null>(null)
const isLoadingMetrics = ref(false)
const isForceProcessing = ref(false)
const activeLogTab = ref<LogService>('hub')
const logContent = ref<Record<LogService, string>>({
  hub: '',
  worker: '',
  scheduler: '',
})
const loadingLog = ref<Record<LogService, boolean>>({
  hub: false,
  worker: false,
  scheduler: false,
})
const retryingPlugins = ref<Record<string, boolean>>({})
const logTerminalRef = ref<HTMLElement | null>(null)
const logFilterLevel = ref<LogFilterLevel>('info')
let pollTimer: number | undefined

const LOG_LEVEL_PRIORITY: Record<LogFilterLevel, number> = {
  debug: 10,
  info: 20,
  warning: 30,
  error: 40,
  critical: 50,
}

const logFilterOptions: Array<{ label: string; value: LogFilterLevel }> = [
  { label: 'DEBUG+', value: 'debug' },
  { label: 'INFO+', value: 'info' },
  { label: 'WARNING+', value: 'warning' },
  { label: 'ERROR+', value: 'error' },
  { label: 'CRITICAL', value: 'critical' },
]

const cards = computed(() => [
  {
    title: 'RAG 积压数',
    value: metrics.value?.rag_backlog_count ?? 0,
    description: '等待摘要、OCR 或向量补齐的内容',
    icon: Waves,
  },
  {
    title: 'API 今日总消耗',
    value: `${metrics.value?.billing_currency || 'USD'} ${(metrics.value?.api_today_total_cost || 0).toFixed(4)}`,
    description: '按当前主要货币折算',
    icon: Flame,
  },
  {
    title: '异常插件数',
    value: metrics.value?.abnormal_plugin_count ?? 0,
    description: '状态为 Stale 或 Error 的插件',
    icon: Server,
  },
])

const warningBanner = computed(() => {
  const data = usageTrend.value
  if (!data || data.api_limit_value <= 0) return null

  const usedValue = data.api_limit_type === 'token' ? data.used_tokens : data.used_cost
  const ratio = usedValue / data.api_limit_value
  if (ratio >= 1) {
    return {
      variant: 'critical' as const,
      title: 'API 熔断器已触发 / 额度耗尽',
      description: `本月已使用 ${usedValue} / ${data.api_limit_value} ${data.api_limit_type === 'token' ? 'tokens' : data.currency}，新的模型请求会被直接拦截。`,
    }
  }
  if (ratio >= (data.warning_threshold_ratio || 0.9)) {
    return {
      variant: 'warning' as const,
      title: 'API 熔断预警',
      description: `当前已使用 ${usedValue} / ${data.api_limit_value} ${data.api_limit_type === 'token' ? 'tokens' : data.currency}，请留意预算消耗。`,
    }
  }
  return null
})

const chartOption = computed(() => {
  const data = usageTrend.value
  const points = data?.points || []
  const isCostMode = data?.api_limit_type === 'cost'
  const values = points.map((point) => (isCostMode ? point.total_cost : point.total_tokens))
  const axisLabels = points.map((point) => point.date.slice(5))
  const color = warningBanner.value?.variant === 'critical' ? '#ef4444' : '#f97316'

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#111827',
      borderColor: '#374151',
      textStyle: { color: '#f9fafb' },
      valueFormatter: (value: number) =>
        isCostMode ? `${data?.currency || 'USD'} ${Number(value || 0).toFixed(4)}` : `${Math.round(Number(value || 0))} tokens`,
    },
    grid: {
      top: 28,
      left: 16,
      right: 16,
      bottom: 10,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: axisLabels,
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: { color: '#6b7280' },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#e5e7eb' } },
      axisLabel: {
        color: '#6b7280',
        formatter: (value: number) =>
          isCostMode ? `${Number(value || 0).toFixed(3)}` : `${Math.round(Number(value || 0))}`,
      },
    },
    series: [
      {
        name: isCostMode ? `API 消耗 (${data?.currency || 'USD'})` : 'API Token 消耗',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        data: values,
        lineStyle: { width: 3, color },
        itemStyle: { color },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: warningBanner.value?.variant === 'critical' ? 'rgba(239,68,68,0.35)' : 'rgba(249,115,22,0.28)' },
              { offset: 1, color: 'rgba(249,115,22,0.02)' },
            ],
          },
        },
      },
    ],
  }
})

const parsedLogLines = computed(() => {
  const raw = logContent.value[activeLogTab.value] || '暂无日志'
  return raw.split('\n').map((line) => ({
    text: line,
    level: classifyLogLine(line),
  }))
})

const filteredLogLines = computed(() => {
  const threshold = LOG_LEVEL_PRIORITY[logFilterLevel.value]
  return parsedLogLines.value.filter((line) => {
    return LOG_LEVEL_PRIORITY[line.level] >= threshold
  })
})

function classifyLogLine(line: string): HighlightLevel {
  if (/CRITICAL|FATAL/i.test(line)) return 'critical'
  if (/\[CIRCUIT BREAKER\]|ERROR|Exception|Traceback/i.test(line)) return 'error'
  if (/WARNING/i.test(line)) return 'warning'
  if (/DEBUG/i.test(line)) return 'debug'
  return 'info'
}

function formatTime(value?: string | null) {
  if (!value) return '从未成功同步'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未知时间'
  return date.toLocaleString()
}

function statusVariant(status: PluginHealthItem['status']) {
  if (status === 'Healthy') return 'default'
  if (status === 'Stale') return 'secondary'
  return 'destructive'
}

async function scrollLogToBottom() {
  await nextTick()
  if (logTerminalRef.value) {
    logTerminalRef.value.scrollTop = logTerminalRef.value.scrollHeight
  }
}

async function loadMetrics() {
  if (!isAdmin.value || isLoadingMetrics.value) return
  isLoadingMetrics.value = true
  try {
    const [metricsResponse, usageTrendResponse] = await Promise.all([
      getAdminMetrics(),
      getAdminUsageTrend(),
    ])
    metrics.value = metricsResponse
    usageTrend.value = usageTrendResponse
  } catch (error: any) {
    console.error('加载监控指标失败:', error)
    toast({
      title: '加载监控指标失败',
      description: error?.response?.data?.detail || '无法获取管理员监控数据。',
      variant: 'destructive',
    })
  } finally {
    isLoadingMetrics.value = false
  }
}

async function loadLog(service: LogService) {
  if (!isAdmin.value || loadingLog.value[service]) return
  loadingLog.value[service] = true
  try {
    const response = await getAdminLogTail(service)
    logContent.value[service] = response.content || '暂无日志'
  } catch (error: any) {
    console.error(`加载 ${service} 日志失败:`, error)
    logContent.value[service] = error?.response?.data?.detail || '日志读取失败'
  } finally {
    loadingLog.value[service] = false
    await scrollLogToBottom()
  }
}

async function handleRefresh() {
  await Promise.all([loadMetrics(), loadLog(activeLogTab.value)])
}

async function handleRetryPlugin(plugin: PluginHealthItem) {
  retryingPlugins.value[plugin.plugin_id] = true
  try {
    await triggerPluginSyncApi(plugin.plugin_id)
    toast({
      title: '手动重试已触发',
      description: `${plugin.name} 已加入同步队列。`,
    })
    await loadMetrics()
  } catch (error: any) {
    toast({
      title: '重试失败',
      description: error?.response?.data?.detail || '无法触发插件同步。',
      variant: 'destructive',
    })
  } finally {
    retryingPlugins.value[plugin.plugin_id] = false
  }
}

async function handleForceProcess() {
  if (isForceProcessing.value) return
  isForceProcessing.value = true
  try {
    const response = await forceProcessQueue()
    toast({
      title: '队列已唤醒',
      description: response.message,
    })
    await Promise.all([loadMetrics(), loadLog('worker')])
    activeLogTab.value = 'worker'
  } catch (error: any) {
    toast({
      title: '唤醒失败',
      description: error?.response?.data?.detail || '无法重投待处理队列。',
      variant: 'destructive',
    })
  } finally {
    isForceProcessing.value = false
  }
}

watch(activeLogTab, async (service) => {
  await loadLog(service)
})

watch(
  () => [logContent.value[activeLogTab.value], logFilterLevel.value],
  async () => {
    await scrollLogToBottom()
  },
)

onMounted(async () => {
  if (!isAdmin.value) return
  await handleRefresh()
  pollTimer = window.setInterval(() => {
    void loadMetrics()
    void loadLog(activeLogTab.value)
  }, 15000)
})

onBeforeUnmount(() => {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
  }
})
</script>

<template>
  <MainLayout search-placeholder="搜索中控数据..." @search="void 0" @add-content="void 0">
    <div class="space-y-8">
      <div class="flex items-center justify-between gap-4">
        <div>
          <h1 class="text-3xl font-bold tracking-tight">Homelab Dashboard</h1>
          <p class="mt-1 text-sm text-muted-foreground">
            管理员统一查看预算熔断、队列积压、插件健康与多容器日志。
          </p>
        </div>
        <Button :disabled="isLoadingMetrics" @click="handleRefresh">
          <Loader2 v-if="isLoadingMetrics" class="mr-2 h-4 w-4 animate-spin" />
          <RefreshCw v-else class="mr-2 h-4 w-4" />
          刷新看板
        </Button>
      </div>

      <div v-if="!isAdmin" class="rounded-2xl border bg-card p-8 text-center text-muted-foreground">
        当前账号不是管理员，无法查看系统监控看板。
      </div>

      <template v-else>
        <section class="space-y-4">
          <div
            v-if="warningBanner"
            :class="[
              'rounded-2xl border px-5 py-4 shadow-sm',
              warningBanner.variant === 'critical'
                ? 'border-red-500/40 bg-red-500/10 text-red-100'
                : 'border-orange-400/40 bg-orange-500/10 text-orange-100',
            ]"
          >
            <div class="flex items-start gap-3">
              <Siren class="mt-0.5 h-5 w-5 shrink-0" />
              <div>
                <div class="font-semibold">
                  {{ warningBanner.title }}
                </div>
                <p class="mt-1 text-sm opacity-90">
                  {{ warningBanner.description }}
                </p>
              </div>
            </div>
          </div>

          <Card class="border-border/60 overflow-hidden">
            <CardHeader class="flex flex-row items-start justify-between gap-4">
              <div>
                <CardTitle class="flex items-center gap-2">
                  <Flame class="h-5 w-5 text-primary" />
                  API 燃烧雷达
                </CardTitle>
                <p class="mt-1 text-sm text-muted-foreground">
                  展示最近 7 天的 API 消耗趋势，并结合当前限额状态给出预警。
                </p>
              </div>
              <Badge variant="outline">
                {{ usageTrend?.api_limit_type === 'cost' ? '按金额熔断' : '按 Token 熔断' }}
              </Badge>
            </CardHeader>
            <CardContent>
              <VChart class="h-[20rem] w-full" :option="chartOption" autoresize />
            </CardContent>
          </Card>
        </section>

        <section class="grid gap-4 md:grid-cols-3">
          <Card v-for="card in cards" :key="card.title" class="border-border/60">
            <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle class="text-sm font-medium text-muted-foreground">{{ card.title }}</CardTitle>
              <component :is="card.icon" class="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-3xl font-bold tracking-tight">{{ card.value }}</div>
                  <p class="mt-2 text-xs text-muted-foreground">{{ card.description }}</p>
                </div>
                <Button
                  v-if="card.title === 'RAG 积压数'"
                  variant="destructive"
                  size="sm"
                  class="shrink-0"
                  :disabled="isForceProcessing"
                  @click="handleForceProcess"
                >
                  <Loader2 v-if="isForceProcessing" class="mr-2 h-3.5 w-3.5 animate-spin" />
                  <Rocket v-else class="mr-2 h-3.5 w-3.5" />
                  唤醒队列
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        <section class="grid gap-6 xl:grid-cols-[1.1fr,1fr]">
          <Card class="border-border/60">
            <CardHeader class="flex flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>插件健康墙</CardTitle>
                <p class="mt-1 text-sm text-muted-foreground">
                  根据最后成功同步时间、自动同步周期与最近执行结果综合判断。
                </p>
              </div>
              <Badge variant="outline">{{ metrics?.plugins.length || 0 }} 个插件</Badge>
            </CardHeader>
            <CardContent>
              <div class="space-y-3">
                <div
                  v-for="plugin in metrics?.plugins || []"
                  :key="plugin.plugin_id"
                  class="rounded-2xl border border-border/60 bg-muted/20 p-4"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="flex items-center gap-2">
                        <h3 class="truncate font-semibold">{{ plugin.name }}</h3>
                        <Badge :variant="statusVariant(plugin.status)">{{ plugin.status }}</Badge>
                      </div>
                      <p class="mt-1 text-xs text-muted-foreground">
                        上次成功同步：{{ formatTime(plugin.last_successful_sync_at) }}
                      </p>
                      <p class="mt-1 text-xs text-muted-foreground">
                        最近任务状态：{{ plugin.sync_status }}<span v-if="plugin.auto_sync"> · 自动同步 {{ plugin.auto_sync_interval }} 分钟</span>
                      </p>
                      <p v-if="plugin.last_error" class="mt-2 text-xs text-destructive line-clamp-2">
                        最近错误：{{ plugin.last_error }}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      :disabled="retryingPlugins[plugin.plugin_id]"
                      @click="handleRetryPlugin(plugin)"
                    >
                      <Loader2 v-if="retryingPlugins[plugin.plugin_id]" class="mr-2 h-3.5 w-3.5 animate-spin" />
                      <RefreshCw v-else class="mr-2 h-3.5 w-3.5" />
                      手动重试
                    </Button>
                  </div>
                </div>

                <div v-if="!(metrics?.plugins.length)" class="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">
                  当前没有可监控的启用插件。
                </div>
              </div>
            </CardContent>
          </Card>

          <Card class="border-border/60">
            <CardHeader>
              <CardTitle class="flex items-center gap-2">
                <TerminalSquare class="h-5 w-5 text-primary" />
                深渊终端
              </CardTitle>
              <p class="mt-1 text-sm text-muted-foreground">
                黑底终端视图，自动滚动到底部，并支持按日志等级筛选与高亮。
              </p>
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="flex flex-wrap gap-2">
                  <Button
                    v-for="service in (['hub', 'worker', 'scheduler'] as LogService[])"
                    :key="service"
                    :variant="activeLogTab === service ? 'default' : 'outline'"
                    size="sm"
                    @click="activeLogTab = service"
                  >
                    {{ service.toUpperCase() }}
                  </Button>
                </div>

                <label class="flex items-center gap-2 rounded-md border border-border/70 bg-background/70 px-3 py-1.5 text-xs text-muted-foreground">
                  <Filter class="h-3.5 w-3.5" />
                  <span>Filter</span>
                  <select
                    v-model="logFilterLevel"
                    class="bg-transparent text-foreground outline-none"
                  >
                    <option
                      v-for="option in logFilterOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                </label>
              </div>

              <div class="overflow-hidden rounded-2xl border border-zinc-800 bg-[#1e1e1e]">
                <div class="flex items-center justify-between border-b border-zinc-800 px-4 py-2 text-xs text-zinc-400">
                  <span>{{ activeLogTab.toUpperCase() }} LOG TAIL</span>
                  <span>{{ filteredLogLines.length }} / {{ parsedLogLines.length }} lines</span>
                </div>
                <div
                  ref="logTerminalRef"
                  class="abyss-terminal-scroll h-[32rem] overflow-auto px-4 py-3 font-mono text-xs leading-6"
                  style="font-family: 'Fira Code', ui-monospace, SFMono-Regular, Consolas, monospace;"
                >
                  <div v-if="loadingLog[activeLogTab]" class="flex h-full min-h-[28rem] items-center justify-center text-sm text-zinc-300">
                    <Loader2 class="mr-2 h-4 w-4 animate-spin" />
                    正在读取 {{ activeLogTab }} 日志...
                  </div>
                  <div v-else-if="filteredLogLines.length" class="space-y-0.5">
                    <div
                      v-for="(line, index) in filteredLogLines"
                      :key="`${activeLogTab}-${index}`"
                      :class="[
                        'whitespace-pre-wrap break-words',
                        line.level === 'critical'
                          ? 'text-fuchsia-300'
                          : line.level === 'error'
                            ? 'text-red-400'
                            : line.level === 'warning'
                              ? 'text-yellow-300'
                              : line.level === 'info'
                                ? 'text-emerald-300'
                                : 'text-sky-300',
                      ]"
                    >
                      {{ line.text || ' ' }}
                    </div>
                  </div>
                  <div v-else class="flex h-full min-h-[28rem] items-center justify-center text-sm text-zinc-400">
                    当前筛选等级下没有可显示的日志。
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>
      </template>
    </div>

    <Toaster />
  </MainLayout>
</template>

<style scoped>
.abyss-terminal-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgba(113, 113, 122, 0.78) rgba(24, 24, 27, 0.88);
}

.abyss-terminal-scroll::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.abyss-terminal-scroll::-webkit-scrollbar-track {
  background: rgba(24, 24, 27, 0.9);
  border-left: 1px solid rgba(63, 63, 70, 0.85);
}

.abyss-terminal-scroll::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(82, 82, 91, 0.92), rgba(113, 113, 122, 0.82));
  border: 2px solid rgba(24, 24, 27, 0.9);
  border-radius: 999px;
}

.abyss-terminal-scroll::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, rgba(113, 113, 122, 0.98), rgba(161, 161, 170, 0.88));
}

.abyss-terminal-scroll::-webkit-scrollbar-corner {
  background: rgba(24, 24, 27, 0.9);
}
</style>
