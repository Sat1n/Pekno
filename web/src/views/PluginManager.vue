<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Github, ArrowRight, Loader2, Tv, FileText, AlertCircle } from 'lucide-vue-next'
import { getGitHubConfig, type GitHubConfig } from '@/lib/api'
import { useRouter } from 'vue-router'

const router = useRouter()

// 插件列表
const plugins = ref([
  {
    id: 'github',
    name: 'GitHub',
    description: '同步你的 GitHub Star 仓库，自动抓取 README 和项目信息',
    icon: Github,
    status: 'available' as const,
    config: null as GitHubConfig | null,
  },
  {
    id: 'bilibili',
    name: 'Bilibili',
    description: '同步你的 Bilibili 收藏夹和视频（开发中）',
    icon: Tv,
    status: 'coming_soon' as const,
    config: null,
  },
  {
    id: 'article',
    name: '文章收藏',
    description: '保存和管理你的文章收藏（开发中）',
    icon: FileText,
    status: 'coming_soon' as const,
    config: null,
  },
])

// 加载状态
const isLoading = ref(false)

// 加载 GitHub 配置
async function loadGitHubConfig() {
  try {
    const config = await getGitHubConfig()
    const githubPlugin = plugins.value.find(p => p.id === 'github')
    if (githubPlugin) {
      githubPlugin.config = config
    }
  } catch (error) {
    console.error('加载 GitHub 配置失败:', error)
  }
}

// 跳转到插件设置页面
function goToPluginSettings(pluginId: string) {
  if (pluginId === 'github') {
    router.push('/settings/github')
  }
}

// 页面加载
onMounted(() => {
  loadGitHubConfig()
})
</script>

<template>
  <div class="container max-w-4xl mx-auto py-8 px-4">
    <!-- 页面标题 -->
    <div class="mb-8">
      <h1 class="text-3xl font-bold">插件管理</h1>
      <p class="text-muted-foreground mt-2">
        管理和配置 Iris 的数据源插件
      </p>
    </div>

    <!-- 插件列表 -->
    <div class="grid gap-4">
      <Card
        v-for="plugin in plugins"
        :key="plugin.id"
        :class="[
          'transition-all cursor-pointer',
          plugin.status === 'available' ? 'hover:border-primary' : 'opacity-60'
        ]"
        @click="plugin.status === 'available' && goToPluginSettings(plugin.id)"
      >
        <CardContent class="p-6">
          <div class="flex items-start gap-4">
            <!-- 插件图标 -->
            <div class="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
              <component :is="plugin.icon" class="w-6 h-6 text-primary" />
            </div>

            <!-- 插件信息 -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <h3 class="font-semibold text-lg">{{ plugin.name }}</h3>
                
                <!-- 状态标签 -->
                <Badge v-if="plugin.status === 'coming_soon'" variant="secondary">
                  即将上线
                </Badge>
                <Badge v-else-if="plugin.config?.has_token" variant="default" class="bg-green-500">
                  已配置
                </Badge>
                <Badge v-else variant="outline">
                  未配置
                </Badge>
              </div>
              
              <p class="text-muted-foreground text-sm">
                {{ plugin.description }}
              </p>

              <!-- 配置预览 -->
              <div v-if="plugin.config?.has_token" class="mt-3 flex items-center gap-4 text-sm text-muted-foreground">
                <span>Token: {{ plugin.config.token_preview }}</span>
                <span>•</span>
                <span>同步数量: {{ plugin.config.sync_limit }}</span>
                <span>•</span>
                <span>自动同步: {{ plugin.config.auto_sync ? '开启' : '关闭' }}</span>
              </div>
            </div>

            <!-- 操作按钮 -->
            <Button
              v-if="plugin.status === 'available'"
              variant="ghost"
              size="icon"
              class="flex-shrink-0"
            >
              <ArrowRight class="w-5 h-5" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- 提示信息 -->
    <Card class="mt-6 bg-muted/50">
      <CardContent class="p-6">
        <div class="flex items-start gap-3">
          <AlertCircle class="w-5 h-5 text-muted-foreground flex-shrink-0 mt-0.5" />
          <div>
            <h4 class="font-medium mb-1">关于插件配置</h4>
            <p class="text-sm text-muted-foreground">
              所有敏感信息（如 Token）都会经过加密后存储在数据库中，确保你的数据安全。
              配置完成后，系统会自动开始同步数据。
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
