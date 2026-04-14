<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { HoverResponse } from '@/lib/api'

defineProps<{
  blocks: HoverResponse
}>()

const { t } = useI18n()

// Default colors for progress block if none provided
const langColors = [
  '#f1e05a', '#2b7489', '#b07219', '#e34c26', '#563d7c', '#3572A5', '#89e051'
]
</script>

<template>
  <div class="hover-preview-container w-72 bg-card/85 backdrop-blur-2xl border border-border/50 rounded-xl shadow-2xl overflow-hidden p-4 space-y-4 animate-in fade-in zoom-in-95 duration-300">
    
    <template v-for="(block, index) in blocks" :key="index">
      
      <!-- KV Block -->
      <div v-if="block.block_type === 'kv'" class="kv-block grid grid-cols-3 gap-2">
        <div 
          v-for="(val, key) in block.kv_data" 
          :key="key"
          class="flex flex-col items-center justify-center p-2 rounded-lg bg-muted/40"
        >
          <span class="text-lg font-bold text-foreground">{{ val }}</span>
          <span class="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">{{ key }}</span>
        </div>
      </div>

      <!-- Markdown Block -->
      <div v-else-if="block.block_type === 'markdown'" class="markdown-block text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
        {{ block.text }}
      </div>

      <!-- Quote Block -->
      <div v-else-if="block.block_type === 'quote'" class="quote-block flex gap-3 p-3 rounded-lg bg-muted/40">
        <img :src="block.avatar_url" class="w-8 h-8 rounded-full shadow-sm" alt="avatar" v-if="block.avatar_url" />
        <div class="flex-1 min-w-0">
          <div class="flex justify-between items-baseline mb-1">
            <span class="font-medium text-sm text-foreground truncate">{{ block.author }}</span>
            <span class="text-[10px] text-muted-foreground" v-if="block.date">{{ block.date }}</span>
          </div>
          <p class="text-xs text-muted-foreground leading-tight">{{ block.content }}</p>
        </div>
      </div>

      <!-- Progress Block (Segmented Bar) -->
      <div v-else-if="block.block_type === 'progress'" class="progress-block space-y-2">
        <div class="flex h-2.5 w-full rounded-full overflow-hidden bg-muted">
          <div 
            v-for="(item, i) in block.items" 
            :key="item.label"
            class="h-full transition-all duration-500 ease-out"
            :style="{ 
              width: `${item.value}%`, 
              backgroundColor: item.color || langColors[i % langColors.length] 
            }"
            :title="`${item.label} ${parseFloat(item.value.toFixed(1))}%`"
          ></div>
        </div>
        <div class="flex flex-wrap gap-x-3 gap-y-1 mt-2">
          <div v-for="(item, i) in block.items" :key="item.label" class="flex items-center gap-1.5 min-w-0">
            <div class="w-2 h-2 rounded-full shrink-0" :style="{ backgroundColor: item.color || langColors[i % langColors.length] }"></div>
            <span class="text-[10px] text-muted-foreground truncate">{{ item.label }} <span class="opacity-70">{{ parseFloat(item.value.toFixed(1)) }}%</span></span>
          </div>
        </div>
      </div>

    </template>
    
    <div v-if="!blocks || blocks.length === 0" class="text-center py-4 text-xs text-muted-foreground">
      {{ t('common.noPreviewData') }}
    </div>
  </div>
</template>
