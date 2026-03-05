<script setup lang="ts">
import { ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Github, Check, AlertCircle, Loader2, Trash2, Save, ExternalLink, RefreshCw } from 'lucide-vue-next'
import { getGitHubConfig, saveGitHubConfig, testGitHubToken, triggerGitHubSync, getGitHubSyncStatus, type GitHubConfig } from '@/lib/api'
import { useToast } from '@/components/ui/toast/use-toast'
import { usePluginStore } from '@/store/usePluginStore'

const { toast } = useToast()
const { githubConfig, loadGitHubConfig, updateGitHubConfig } = usePluginStore()

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'open-delete-dialog': []
}>()

// 配置状态 - 使用全局状态
const config = githubConfig

// 表单状态
const token = ref('')
const syncLimit = ref(100)
const autoSync = ref(false)
const autoSyncInterval = ref(60)

// 加载状态
const isSaving = ref(false)
const isTesting = ref(false)
const isSyncing = ref(false)
let syncIntervalTimer: number | null = null

// 加载配置
async function loadConfig() {
  await loadGitHubConfig()
  syncLimit.value = config.value.sync_limit
  autoSync.value = config.value.auto_sync
  autoSyncInterval.value = config.value.auto_sync_interval || 60
}

// 保存配置
async function handleSave() {
  // 1. 验证逻辑
  if (!config.value.has_token && !token.value) {
    toast({
      title: '请输入 Token',
      description: '首次配置需要输入 GitHub Personal Access Token',
      variant: 'destructive',
    })
    return
  }

  isSaving.value = true // 开始加载动画
  
  try {
    // 2. 构建并发送数据
    const saveData: any = {
      sync_limit: syncLimit.value,
      auto_sync: autoSync.value,
      auto_sync_interval: autoSyncInterval.value
    }
    if (token.value) {
      saveData.token = token.value
    }

    await saveGitHubConfig(saveData)

    // 3. ✨ 关键顺序：先刷新全局状态，再处理 UI 提示
    await loadGitHubConfig() // 先让全局知道已经有 Token 了
    await loadConfig()       // 同步本地状态

    toast({
      title: '保存成功',
      description: 'GitHub 配置已更新',
    })

    // 4. 最后清空输入框 (此时 has_token 已经是 true 了，所以按钮不会被禁用)
    token.value = ''
    
  } catch (error) {
    console.error('保存配置失败:', error)
    toast({
      title: '保存失败',
      description: '无法保存 GitHub 配置',
      variant: 'destructive',
    })
  } finally {
    isSaving.value = false // 结束加载动画，确保按钮恢复可点状态
  }
}

// 测试连接
async function handleTest() {
  isTesting.value = true
  try {
    const result = await testGitHubToken()
    toast({
      title: '测试成功',
      description: result.message,
    })
  } catch (error: any) {
    console.error('测试失败:', error)
    toast({
      title: '测试失败',
      description: error.response?.data?.detail || 'Token 无效或已过期',
      variant: 'destructive',
    })
  } finally {
    isTesting.value = false
  }
}

// 轮询同步状态
function pollSyncStatus() {
  if (syncIntervalTimer) clearInterval(syncIntervalTimer)
  syncIntervalTimer = window.setInterval(async () => {
    try {
      const { status } = await getGitHubSyncStatus()
      if (status === 'idle' && isSyncing.value) {
        toast({ title: '同步完成', description: 'GitHub Stars 同步已完成。' })
        isSyncing.value = false
        if (syncIntervalTimer) clearInterval(syncIntervalTimer)
      }
    } catch(e) { /* ignore */ }
  }, 3000)
}

// 立即同步
async function handleSyncNow() {
  if (isSyncing.value) return
  isSyncing.value = true
  toast({ title: '同步开始', description: '正在抓取最新的 GitHub Stars...' })
  try {
    await triggerGitHubSync(syncLimit.value)
    pollSyncStatus()
  } catch (err: any) {
    console.error('立即同步失败', err)
    toast({ title: '同步失败', description: '无法启动同步请求', variant: 'destructive' })
    isSyncing.value = false
  }
}

// 打开删除确认对话框
function openDeleteDialog() {
  emit('open-delete-dialog')
}

// 监听弹窗打开状态
watch(() => props.open, (newVal) => {
  if (newVal) {
    // --- ✨ 修改这一块的逻辑 ✨ ---
    loadGitHubConfig().then(() => {
      // 这里的 loadConfig() 如果你原来有，可以保留，但核心是要把 store 的值赋给表单
      syncLimit.value = githubConfig.value.sync_limit
      autoSync.value = githubConfig.value.auto_sync
      autoSyncInterval.value = githubConfig.value.auto_sync_interval || 60
      
      // 打开时主动查询一次同步状态
      getGitHubSyncStatus().then(({ status }) => {
        if (status === 'running') {
          isSyncing.value = true
          pollSyncStatus()
        }
      })
    })
  }
})
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-lg max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
            <Github class="w-5 h-5 text-primary" />
          </div>
          <div>
            <DialogTitle>GitHub 插件设置</DialogTitle>
            <DialogDescription>
              配置 GitHub Token 以同步你的 Star 仓库
            </DialogDescription>
          </div>
        </div>
      </DialogHeader>

      <div class="space-y-6 py-4">
        <!-- 状态标签 -->
        <div class="flex items-center gap-2">
          <Badge v-if="config.has_token" variant="default" class="bg-green-500">
            <Check class="w-3 h-3 mr-1" />
            已配置
          </Badge>
          <Badge v-else variant="secondary">
            <AlertCircle class="w-3 h-3 mr-1" />
            未配置
          </Badge>
        </div>

        <!-- Token 输入 -->
        <div class="space-y-2">
          <Label for="token">
            GitHub Personal Access Token
            <span class="text-red-500">*</span>
          </Label>
          <Input
              id="token"
              v-model="token"
              type="password"
              placeholder="ghp_xxxxxxxxxxxxxxxxx"
              :disabled="false"
            />
          <p class="text-sm text-muted-foreground">
            <template v-if="config.token_preview">
              当前 Token: {{ config.token_preview }}
            </template>
            <template v-else>
              在 GitHub Settings → Developer settings → Personal access tokens 中生成
            </template>
          </p>
        </div>

        <Separator />

        <!-- 同步设置 -->
        <div class="space-y-4">
          <h4 class="font-medium">同步设置</h4>
          
          <!-- 同步数量 -->
          <div class="space-y-2">
            <Label for="sync-limit">同步仓库数量</Label>
            <Input
              id="sync-limit"
              v-model.number="syncLimit"
              type="number"
              min="1"
              max="1000"
            />
            <p class="text-sm text-muted-foreground">
              每次同步时获取的最近 Star 仓库数量（默认：100）
            </p>
          </div>

          <!-- 自动同步 -->
          <div class="flex items-center justify-between">
            <div class="space-y-0.5">
              <Label for="auto-sync">自动同步</Label>
              <p class="text-sm text-muted-foreground">
                保存 Token 后自动开始同步 Star 仓库
              </p>
            </div>
            <Switch
              id="auto-sync"
              v-model="autoSync"
              :disabled="false"
            />
          </div>

          <!-- 自动同步间隔 -->
          <div class="space-y-2" v-if="autoSync">
            <Label for="auto-sync-interval">自动同步间隔 (分钟)</Label>
            <Input
              id="auto-sync-interval"
              v-model.number="autoSyncInterval"
              type="number"
              min="1"
              max="43200"
            />
            <p class="text-sm text-muted-foreground">
              默认 60 分钟。最大支持 43200 分钟 (30天)。
            </p>
          </div>
        </div>

        <Separator />

        <!-- 使用说明 -->
        <div class="space-y-2">
          <h4 class="font-medium text-sm">如何获取 GitHub Token</h4>
          <ol class="list-decimal list-inside space-y-1 text-xs text-muted-foreground">
            <li>登录 GitHub 账号</li>
            <li>点击右上角头像 → Settings</li>
            <li>滚动到最下方 → Developer settings</li>
            <li>Personal access tokens → Tokens (classic)</li>
            <li>点击 Generate new token</li>
            <li>选择有效期（建议 90 天）</li>
            <li>勾选 <code>repo</code> 和 <code>read:user</code> 权限</li>
            <li>点击 Generate token 并复制</li>
          </ol>
          <a
            href="https://github.com/settings/tokens"
            target="_blank"
            class="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-2"
          >
            <ExternalLink class="w-3 h-3" />
            打开 GitHub Token 设置页面
          </a>
        </div>
      </div>

      <div class="flex flex-col gap-3 py-4">
        <!-- 主要操作按钮 -->
        <div class="flex gap-3 w-full">
          <Button
            class="flex-1"
            :disabled="isSaving || (!token && !config.has_token)"
            @click="handleSave"
          >
            <Loader2 v-if="isSaving" class="w-4 h-4 mr-2 animate-spin" />
            <Save v-else class="w-4 h-4 mr-2" />
            {{ isSaving ? '保存中...' : '保存配置' }}
          </Button>

          <Button
            variant="outline"
            :disabled="isTesting || !config.has_token"
            @click="handleTest"
          >
            <Loader2 v-if="isTesting" class="w-4 h-4 mr-2 animate-spin" />
            <Check v-else class="w-4 h-4 mr-2" />
            {{ isTesting ? '测试中...' : '测试' }}
          </Button>

          <Button
            variant="outline"
            :disabled="isSyncing || !config.has_token"
            @click="handleSyncNow"
          >
            <Loader2 v-if="isSyncing" class="w-4 h-4 mr-2 animate-spin" />
            <RefreshCw v-else class="w-4 h-4 mr-2" />
            {{ isSyncing ? '同步中...' : '立即同步' }}
          </Button>
        </div>

        <!-- 删除按钮 -->
        <Button
            variant="destructive"
            class="w-full"
            :disabled="!config.has_token"
            @click="openDeleteDialog"
          >
          <Trash2 class="w-4 h-4 mr-2" />
          清除配置
        </Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
