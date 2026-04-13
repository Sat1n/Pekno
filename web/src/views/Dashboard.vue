<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import MainLayout from '@/layouts/MainLayout.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Loader2, RefreshCw, Server, Waves, Zap } from 'lucide-vue-next'
import {
  getAdminLogTail,
  getAdminMetrics,
  getStoredAuthUser,
  triggerPluginSyncApi,
  type AdminMetricsResponse,
  type PluginHealthItem,
} from '@/lib/api'
import { useToast } from '@/components/ui/toast/use-toast'
import { Toaster } from '@/components/ui/toast'

type LogService = 'hub' | 'worker' | 'scheduler'

const { toast } = useToast()
const currentUser = computed(() => getStoredAuthUser())
const isAdmin = computed(() => ['admin', 'super_admin'].includes(currentUser.value.role || ''))
const metrics = ref<AdminMetricsResponse | null>(null)
const isLoadingMetrics = ref(false)
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
let pollTimer: number | undefined

const cards = computed(() => [
  {
    title: 'RAG 积压数',
    value: metrics.value?.rag_backlog_count ?? 0,
    description: '等待摘要或向量补齐的内容',
    icon: Waves,
  },
  {
    title: 'API 今日总消耗',
    value: `${metrics.value?.billing_currency || 'USD'} ${(metrics.value?.api_today_total_cost || 0).toFixed(4)}`,
    description: '按当前主要货币折算',
    icon: Zap,
  },
  {
    title: '异常插件数',
    value: metrics.value?.abnormal_plugin_count ?? 0,
    description: '状态为 Stale 或 Error 的插件',
    icon: Server,
  },
])

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

async function loadMetrics() {
  if (!isAdmin.value || isLoadingMetrics.value) return
  isLoadingMetrics.value = true
  try {
    metrics.value = await getAdminMetrics()
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

onMounted(async () => {
  if (!isAdmin.value) return
  await handleRefresh()
  pollTimer = window.setInterval(() => {
    void loadMetrics()
  }, 45000)
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
            管理员统一查看队列积压、插件健康与多容器日志。
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
        <section class="grid gap-4 md:grid-cols-3">
          <Card v-for="card in cards" :key="card.title" class="border-border/60">
            <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle class="text-sm font-medium text-muted-foreground">{{ card.title }}</CardTitle>
              <component :is="card.icon" class="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div class="text-3xl font-bold tracking-tight">{{ card.value }}</div>
              <p class="mt-2 text-xs text-muted-foreground">{{ card.description }}</p>
            </CardContent>
          </Card>
        </section>

        <section class="grid gap-6 xl:grid-cols-[1.2fr,1fr]">
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
              <CardTitle>日志预览区</CardTitle>
              <p class="mt-1 text-sm text-muted-foreground">
                每次切换标签会读取最近 200 行日志，便于快速排障。
              </p>
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="flex flex-wrap gap-2">
                <Button
                  v-for="service in (['hub', 'worker', 'scheduler'] as LogService[])"
                  :key="service"
                  :variant="activeLogTab === service ? 'default' : 'outline'"
                  size="sm"
                  @click="activeLogTab = service; void loadLog(service)"
                >
                  {{ service.toUpperCase() }}
                </Button>
              </div>

              <div class="min-h-[32rem] rounded-2xl border bg-black px-4 py-3">
                <div v-if="loadingLog[activeLogTab]" class="flex h-full min-h-[28rem] items-center justify-center text-sm text-zinc-300">
                  <Loader2 class="mr-2 h-4 w-4 animate-spin" />
                  正在读取 {{ activeLogTab }} 日志...
                </div>
                <pre
                  v-else
                  class="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-zinc-100"
                >{{ logContent[activeLogTab] || '暂无日志' }}</pre>
              </div>
            </CardContent>
          </Card>
        </section>
      </template>
    </div>

    <Toaster />
  </MainLayout>
</template>
