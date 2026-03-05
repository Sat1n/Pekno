<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Github, Check, AlertCircle, Loader2, Trash2, Save, RefreshCw } from 'lucide-vue-next'
import { getGitHubConfig, saveGitHubConfig, testGitHubToken, deleteGitHubConfig, triggerGitHubSync, getGitHubSyncStatus, type GitHubConfig } from '@/lib/api'
import { useToast } from '@/components/ui/toast/use-toast'

const { toast } = useToast()

// 配置状态
const config = ref<GitHubConfig>({
  has_token: false,
  sync_limit: 100,
  auto_sync: false,
  auto_sync_interval: 60,
})

// 表单状态
const token = ref('')
const syncLimit = ref(100)
const autoSync = ref(false)
const autoSyncInterval = ref(60)

// 加载状态
const isLoading = ref(false)
const isSaving = ref(false)
const isTesting = ref(false)
const isDeleting = ref(false)
const isSyncing = ref(false)
let syncIntervalTimer: number | null = null

// 加载配置
async function loadConfig() {
  isLoading.value = true
  try {
    const data = await getGitHubConfig()
    config.value = data
    syncLimit.value = data.sync_limit
    autoSync.value = data.auto_sync
    autoSyncInterval.value = data.auto_sync_interval || 60
    
    // 打开时主动查询一次同步状态
    const { status } = await getGitHubSyncStatus()
    if (status === 'running') {
      isSyncing.value = true
      pollSyncStatus()
    }
  } catch (error) {
    console.error('加载配置失败:', error)
    toast({
      title: '加载失败',
      description: '无法加载 GitHub 配置',
      variant: 'destructive',
    })
  } finally {
    isLoading.value = false
  }
}

// 保存配置
async function handleSave() {
  // 如果是首次配置，必须输入token
  if (!config.value.has_token && !token.value) {
    toast({
      title: '请输入 Token',
      description: '首次配置需要输入 GitHub Personal Access Token',
      variant: 'destructive',
    })
    return
  }

  isSaving.value = true
  try {
    // 构建保存的数据：如果有新token则使用新token，否则不传token（后端保留原有token）
    const saveData: any = {
      sync_limit: syncLimit.value,
      auto_sync: autoSync.value,
      auto_sync_interval: autoSyncInterval.value
    }
    
    // 只有输入了新token才传递token字段
    if (token.value) {
      saveData.token = token.value
    }
    
    await saveGitHubConfig(saveData)
    
    toast({
      title: '保存成功',
      description: 'GitHub 配置已保存',
    })
    
    // 清空输入框
    token.value = ''
    
    // 重新加载配置
    await loadConfig()
  } catch (error) {
    console.error('保存配置失败:', error)
    toast({
      title: '保存失败',
      description: '无法保存 GitHub 配置',
      variant: 'destructive',
    })
  } finally {
    isSaving.value = false
  }
}

// 测试连接
async function handleTest() {
  isTesting.value = true
  try {
    // 测试已保存的token
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

// 删除配置
async function handleDelete() {
  if (!confirm('确定要删除 GitHub 配置吗？这将清除所有相关的 Token 和设置。')) {
    return
  }

  isDeleting.value = true
  try {
    await deleteGitHubConfig()
    
    toast({
      title: '删除成功',
      description: 'GitHub 配置已清除',
    })
    
    // 重新加载配置
    await loadConfig()
  } catch (error) {
    console.error('删除配置失败:', error)
    toast({
      title: '删除失败',
      description: '无法清除 GitHub 配置',
      variant: 'destructive',
    })
  } finally {
    isDeleting.value = false
  }
}

// 页面加载时获取配置
onMounted(() => {
  loadConfig()
})
</script>

<template>
  <div class="container max-w-2xl mx-auto py-8 px-4">
    <!-- 页面标题 -->
    <div class="mb-8">
      <h1 class="text-3xl font-bold flex items-center gap-3">
        <Github class="w-8 h-8" />
        GitHub 插件设置
      </h1>
      <p class="text-muted-foreground mt-2">
        配置 GitHub Personal Access Token 以同步你的 Star 仓库
      </p>
    </div>

    <!-- 配置卡片 -->
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <div>
            <CardTitle>GitHub 配置</CardTitle>
            <CardDescription>
              配置你的 GitHub Token 和同步选项
            </CardDescription>
          </div>
          <Badge v-if="config.has_token" variant="default" class="bg-green-500">
            <Check class="w-3 h-3 mr-1" />
            已配置
          </Badge>
          <Badge v-else variant="secondary">
            <AlertCircle class="w-3 h-3 mr-1" />
            未配置
          </Badge>
        </div>
      </CardHeader>

      <CardContent class="space-y-6">
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
            placeholder="github-token-placeholder"
            :disabled="isLoading"
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
              :disabled="isLoading"
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
              :disabled="isLoading"
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
              :disabled="isLoading"
            />
            <p class="text-sm text-muted-foreground">
              默认 60 分钟。最大支持 43200 分钟 (30天)。
            </p>
          </div>
        </div>
      </CardContent>

      <CardFooter class="flex flex-col gap-3">
        <!-- 主要操作按钮 -->
        <div class="flex gap-3 w-full">
          <Button
            class="flex-1"
            :disabled="isLoading || isSaving || (!token && !config.has_token)"
            @click="handleSave"
          >
            <Loader2 v-if="isSaving" class="w-4 h-4 mr-2 animate-spin" />
            <Save v-else class="w-4 h-4 mr-2" />
            {{ isSaving ? '保存中...' : '保存配置' }}
          </Button>

          <Button
            variant="outline"
            :disabled="isLoading || isTesting || !config.has_token"
            @click="handleTest"
          >
            <Loader2 v-if="isTesting" class="w-4 h-4 mr-2 animate-spin" />
            <Check v-else class="w-4 h-4 mr-2" />
            {{ isTesting ? '测试中...' : '测试连接' }}
          </Button>

          <Button
            variant="outline"
            :disabled="isLoading || isSyncing || !config.has_token"
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
          :disabled="isLoading || isDeleting || !config.has_token"
          @click="handleDelete"
        >
          <Loader2 v-if="isDeleting" class="w-4 h-4 mr-2 animate-spin" />
          <Trash2 v-else class="w-4 h-4 mr-2" />
          {{ isDeleting ? '删除中...' : '清除配置' }}
        </Button>
      </CardFooter>
    </Card>

    <!-- 使用说明 -->
    <Card class="mt-6">
      <CardHeader>
        <CardTitle>如何获取 GitHub Token</CardTitle>
      </CardHeader>
      <CardContent>
        <ol class="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
          <li>登录 GitHub 账号</li>
          <li>点击右上角头像 → Settings</li>
          <li>滚动到最下方 → Developer settings</li>
          <li>Personal access tokens → Tokens (classic)</li>
          <li>点击 Generate new token</li>
          <li>选择有效期（建议 90 天）</li>
          <li>勾选 <code>repo</code> 和 <code>read:user</code> 权限</li>
          <li>点击 Generate token 并复制</li>
        </ol>
      </CardContent>
    </Card>
  </div>
</template>
