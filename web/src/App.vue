<script setup lang="ts">
import { ref, computed } from 'vue'
import MainLayout from '@/layouts/MainLayout.vue'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Github, Tv, FileText } from 'lucide-vue-next'

const layoutMode = ref<'list' | 'grid' | 'compact'>('list')

// 模拟数据增加来源字段和更多tag
const mockResults = ref([
  { 
    title: 'immich-app/immich', 
    source: 'github', 
    score: 0.98, 
    summary: 'High performance self-hosted photo and video management solution. 你的开源照片管家。', 
    tags: ['Starred', 'Self-hosted', 'TypeScript', 'Docker'], 
    time: '2小时前' 
  },
  { 
    title: '如何用 Vue 3 实现侧边栏', 
    source: 'article', 
    score: 0.85, 
    summary: '基于 Shadcn UI 和 Tailwind CSS 的现代响应式布局实践指南，包含动画细节。', 
    tags: ['Vue', 'Tutorial', 'CSS'], 
    time: '昨天' 
  },
  { 
    title: 'GitHub Copilot 2026 特性', 
    source: 'github', 
    score: 0.92, 
    summary: '探索最新的 AI 编程助手功能，包括更智能的代码补全和上下文理解。', 
    tags: ['AI', 'Productivity', 'DevTools', 'Copilot', 'GitHub'], 
    time: '3小时前' 
  },
  { 
    title: 'TypeScript 5.5 发布', 
    source: 'article', 
    score: 0.88, 
    summary: '新的类型推断改进和性能优化，让开发体验更上一层楼。', 
    tags: ['TypeScript', 'Release'], 
    time: '1天前' 
  },
  { 
    title: 'Bilibili 视频推荐算法解析', 
    source: 'bilibili', 
    score: 0.76, 
    summary: '深入分析 B 站推荐系统的工作原理和优化策略。', 
    tags: ['Algorithm', 'Machine Learning', 'Bilibili'], 
    time: '5小时前' 
  },
  { 
    title: 'Vue 3 Composition API 最佳实践', 
    source: 'article', 
    score: 0.91, 
    summary: '从实际项目中总结的 Composition API 使用技巧和常见陷阱。', 
    tags: ['Vue', 'Composition API', 'Best Practices', 'Frontend'], 
    time: '2天前' 
  },
  { 
    title: 'React 19 新特性详解', 
    source: 'article', 
    score: 0.89, 
    summary: 'React 19 带来了许多激动人心的新特性，包括服务端组件和自动记忆化。', 
    tags: ['React', 'Frontend', 'JavaScript'], 
    time: '4小时前' 
  },
  { 
    title: 'Node.js 性能优化指南', 
    source: 'github', 
    score: 0.82, 
    summary: '从内存管理到异步编程，全面提升 Node.js 应用性能的实用技巧。', 
    tags: ['Node.js', 'Performance', 'Backend', 'Optimization'], 
    time: '6小时前' 
  },
])

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
</script>

<template>
  <MainLayout v-model:layout="layoutMode">
    <div class="mb-8">
      <h2 class="text-2xl font-bold">欢迎回来, natis</h2>
      <p class="text-muted-foreground">今天 Iris 为你整理了 {{ mockResults.length }} 条新情报</p>
    </div>

    <div :class="['grid transition-all duration-300', gridClass]">
      
      <Card v-for="item in mockResults" :key="item.title" 
        class="bg-card text-card-foreground border-border hover:border-primary/20 transition-all cursor-pointer overflow-hidden group shadow-md flex flex-col">
        
        <!-- 封面图区域 -->
        <div v-if="layoutMode !== 'compact'" class="aspect-video bg-muted/30 flex items-center justify-center relative overflow-hidden border-b border-border/40 flex-shrink-0">
          <component :is="getSourceIcon(item.source)" class="w-16 h-16 text-muted-foreground/10 group-hover:scale-105 transition-transform duration-500" />
          
          <!-- 修复后的百分数 Badge -->
          <div class="absolute top-3 right-3">
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
            <CardTitle :class="[
              'font-bold tracking-tight group-hover:text-primary transition-colors',
              layoutMode === 'compact' ? 'text-sm truncate' : 'text-xl'
            ]">
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

        <!-- 卡片底部：标签和来源/时间 - 使用 mt-auto 固定在底部 -->
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
  </MainLayout>
</template>

<style scoped>
</style>