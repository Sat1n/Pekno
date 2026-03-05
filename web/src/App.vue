<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
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
  SheetTitle,
  SheetClose,
} from '@/components/ui/sheet'
import { Github, Tv, FileText, MoreVertical, Sparkles, Bookmark, ExternalLink, X, Trash2, Star, Loader2 } from 'lucide-vue-next'
import { search, summarizeItem, getTaskStatus, type SearchResult } from '@/lib/api'
import { useToast } from '@/components/ui/toast/use-toast'
import { Toaster } from '@/components/ui/toast'

// 扩展 SearchResult 类型，添加本地状态
interface LocalSearchResult extends SearchResult {
  hasSummary?: boolean
  raw_link?: string
}

const layoutMode = ref<'list' | 'grid' | 'compact'>('list')
const searchQuery = ref('')
const searchResults = ref<LocalSearchResult[]>([])
const isLoading = ref(false)

// 侧边栏状态
const isSheetOpen = ref(false)
const selectedItem = ref<LocalSearchResult | null>(null)

// AI 总结相关状态
const isSummarizing = ref(false)
const currentTaskId = ref<string | null>(null)
const pollInterval = ref<number | null>(null)

// Toast 通知
const { toast } = useToast()

// 加载数据函数
async function loadData(query: string = '') {
  isLoading.value = true
  try {
    const results = await search({ q: query })
    // 添加模拟的 hasSummary 和 raw_link 状态
    searchResults.value = results.map(item => ({
      ...item,
      hasSummary: Math.random() > 0.7, // 随机模拟是否有总结
      raw_link: item.source === 'github' 
        ? `https://github.com/${item.title}` 
        : '#'
    }))
  } catch (error) {
    console.error('搜索失败:', error)
    searchResults.value = []
  } finally {
    isLoading.value = false
  }
}

// 处理搜索（从顶栏触发）
async function handleSearch() {
  await loadData(searchQuery.value)
}

// 页面加载时获取数据
onMounted(() => {
  loadData()
})

// 根据来源返回图标
const getSourceIcon = (source: string) => {
  if (source === 'github') return Github
  if (source === 'bilibili') return Tv
  return FileText
}

// 优化的响应式类名
const gridClass = computed(() => {
  if (layoutMode.value === 'list') return 'grid-cols-1 max-w-4xl mx-auto gap-8'
  if (layoutMode.value === 'grid') return 'grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-6'
  if (layoutMode.value === 'compact') return 'grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3'
  return ''
})

// 骨架屏数量
const skeletonCount = 6

// 点击卡片主体 - 跳转到原始链接
function handleCardClick(item: LocalSearchResult) {
  if (item.raw_link && item.raw_link !== '#') {
    window.open(item.raw_link, '_blank')
  }
}

// 点击菜单项 - AI 总结
function handleAISummary(item: LocalSearchResult) {
  selectedItem.value = item
  isSheetOpen.value = true
}

// 点击菜单项 - 添加到稍后再看
function handleAddToWatchLater(item: LocalSearchResult) {
  console.log('添加到稍后再看:', item.title)
  // TODO: 实现添加到稍后再看逻辑
}

// 清空记录
function handleClearRecord() {
  console.log('清空记录:', selectedItem.value?.title)
  isSheetOpen.value = false
  selectedItem.value = null
}

// 生成 AI 总结
async function handleGenerateSummary() {
  if (!selectedItem.value) return
  
  try {
    isSummarizing.value = true
    
    // 生成 itemId（简化处理，实际应该从后端获取）
    const itemId = `gh_${selectedItem.value.title.replace('/', '_')}`
    
    // 调用后端 API 触发总结任务
    const response = await summarizeItem(itemId)
    currentTaskId.value = response.task_id
    
    // 显示正在生成的消息
    toast({
      title: '🔄 AI 总结生成中',
      description: '请稍候，正在抓取并分析仓库内容...',
    })
    
    // 开始轮询任务状态
    startPollingTaskStatus(response.task_id)
    
  } catch (error) {
    console.error('生成 AI 总结失败:', error)
    toast({
      title: '❌ 生成失败',
      description: '无法启动 AI 总结，请检查网络连接',
      variant: 'destructive',
    })
  } finally {
    isSummarizing.value = false
  }
}

// 开始轮询任务状态
function startPollingTaskStatus(taskId: string) {
  // 清除之前的轮询
  if (pollInterval.value) {
    clearInterval(pollInterval.value)
  }
  
  // 每 2 秒查询一次
  pollInterval.value = window.setInterval(async () => {
    try {
      const status = await getTaskStatus(taskId)
      
      if (status.status === 'completed') {
        // 任务完成，重新加载数据
        await loadData(searchQuery.value)
        
        // 清除轮询
        if (pollInterval.value) {
          clearInterval(pollInterval.value)
          pollInterval.value = null
        }
        
        // 显示成功消息
        toast({
          title: '✨ AI 总结完成',
          description: '已为仓库生成 AI 总结，点击查看详情',
        })
        
      } else if (status.status === 'failed') {
        // 任务失败
        clearInterval(pollInterval.value)
        pollInterval.value = null
        toast({
          title: '❌ AI 总结失败',
          description: '请稍后重试，或检查 GitHub Token 配置',
          variant: 'destructive',
        })
      }
      
    } catch (error) {
      console.error('查询任务状态失败:', error)
    }
  }, 2000)
}

// 判断卡片是否处于 Active 状态
function isCardActive(item: LocalSearchResult) {
  return selectedItem.value?.title === item.title && isSheetOpen.value
}
</script>

<template>
  <MainLayout 
    v-model:layout="layoutMode" 
    v-model:search-query="searchQuery"
    @search="handleSearch"
  >
    <div class="mb-8">
      <h2 class="text-2xl font-bold">欢迎回来, natis</h2>
      <p class="text-muted-foreground">
        {{ isLoading ? '正在加载数据...' : `今天 Iris 为你整理了 ${searchResults.length} 条新情报` }}
      </p>
    </div>

    <!-- 加载状态 - 骨架屏 -->
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

    <!-- 实际内容 -->
    <div v-else :class="['grid transition-all duration-300', gridClass]">
      <Card 
        v-for="item in searchResults" 
        :key="item.title" 
        :class="[
          'bg-card text-card-foreground border-border transition-all cursor-pointer overflow-hidden group shadow-md flex flex-col relative',
          isCardActive(item) ? 'border-primary ring-2 ring-primary/20' : 'hover:border-primary/20'
        ]"
        @click="handleCardClick(item)"
      >
        <!-- 已总结标识 - 星星动画 -->
        <div 
          v-if="item.hasSummary" 
          class="absolute top-2 left-2 z-10"
          title="已有 AI 总结"
        >
          <Star class="w-4 h-4 text-yellow-500 fill-yellow-500 animate-pulse" />
        </div>

        <!-- 操作菜单 - 右上角 -->
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
                <Bookmark class="mr-2 h-4 w-4" />
                <span>🔖 添加到稍后再看</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        
        <!-- 封面图区域 -->
        <div v-if="layoutMode !== 'compact'" class="aspect-video bg-muted/30 flex items-center justify-center relative overflow-hidden border-b border-border/40 flex-shrink-0">
          <!-- 显示抓取的封面图或回退到图标/源图标 -->
          <img 
            v-if="item.cover_url" 
            :src="item.cover_url" 
            alt="Cover" 
            class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            @error="(e) => (e.target as HTMLImageElement).style.display = 'none'"
          />
          <component v-else :is="getSourceIcon(item.source)" class="w-16 h-16 text-muted-foreground/10 group-hover:scale-105 transition-transform duration-500" />
          
          <!-- 百分数 Badge -->
          <div class="absolute bottom-3 right-3">
            <Badge class="bg-primary text-primary-foreground font-mono shadow-lg border-none px-2 py-0.5">
              {{ Math.floor(item.score * 100) }}%
            </Badge>
          </div>
        </div>

        <!-- 卡片头部 -->
        <CardHeader :class="layoutMode === 'compact' ? 'p-3 flex-row items-center gap-3 space-y-0' : 'p-5 space-y-3'">
          <!-- 紧凑模式下的来源图标 -->
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
            
            <!-- 列表模式：完整摘要 -->
            <p v-if="layoutMode === 'list'" class="text-muted-foreground leading-relaxed text-base mt-3">
              {{ item.summary }}
            </p>
            <!-- 网格模式：两行摘要 -->
            <p v-else-if="layoutMode === 'grid'" class="text-muted-foreground mt-2 text-sm line-clamp-2">
              {{ item.summary }}
            </p>
          </div>
        </CardHeader>

        <!-- 卡片底部：标签和来源/时间 -->
        <CardContent v-if="layoutMode !== 'compact'" class="px-5 pb-5 pt-0 mt-auto">
          <div class="flex items-center justify-between border-t border-border/40 pt-4 gap-3">
            <div class="flex gap-2 flex-wrap flex-1">
              <Badge v-for="tag in item.tags" :key="tag" variant="secondary" class="bg-muted hover:bg-muted/80 text-xs font-normal">
                {{ tag }}
              </Badge>
            </div>

            <!-- 来源图标与时间整合 -->
            <div class="flex items-center gap-2 text-muted-foreground flex-shrink-0">
              <component :is="getSourceIcon(item.source)" class="w-4 h-4" title="来源" />
              <span class="text-xs font-medium whitespace-nowrap">{{ item.time }}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- 空状态 -->
    <div v-if="!isLoading && searchResults.length === 0" class="text-center py-20">
      <div class="text-muted-foreground text-lg">暂无数据</div>
      <p class="text-muted-foreground/60 text-sm mt-2">尝试搜索其他关键词或检查后端服务是否运行</p>
    </div>
  </MainLayout>

  <!-- AI 详情侧边栏 -->
  <Sheet v-model:open="isSheetOpen">
    <SheetContent class="w-full sm:max-w-lg p-0 flex flex-col" side="right">
      <!-- 顶部：标题和关闭按钮 -->
      <SheetHeader class="p-6 border-b border-border">
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
            @click="window.open(selectedItem.raw_link, '_blank')"
          >
            <ExternalLink class="w-4 h-4 mr-1" />
            访问
          </Button>
        </div>
      </SheetHeader>

      <!-- 中部：AI 总结内容 -->
      <ScrollArea class="flex-1 p-6">
        <div class="space-y-6">
          <!-- AI 智能总结 -->
          <div>
            <div class="flex items-center gap-2 mb-3">
              <Sparkles class="w-5 h-5 text-primary" />
              <h3 class="font-semibold text-lg">AI 智能总结</h3>
            </div>
            <div class="bg-muted/50 rounded-lg p-4 space-y-3">
              <p class="text-sm leading-relaxed">
                {{ selectedItem?.summary || '暂无 AI 总结，点击生成按钮开始总结...' }}
              </p>
            </div>
          </div>

          <Separator />

          <!-- 标签 -->
          <div>
            <h4 class="font-medium mb-2">标签</h4>
            <div class="flex flex-wrap gap-2">
              <Badge v-for="tag in selectedItem?.tags" :key="tag" variant="secondary">
                {{ tag }}
              </Badge>
            </div>
          </div>

          <Separator />

          <!-- 预留：对话区域 -->
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

      <!-- 底部：操作按钮 -->
      <div class="p-6 border-t border-border space-y-3">
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

  <Sheet v-model:open="isSheetOpen">
    </Sheet>
</template>

<style scoped>
/* 骨架屏动画 */
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

/* 星星呼吸动画 */
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
</style>
