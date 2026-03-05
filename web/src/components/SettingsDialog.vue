<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Github, Blocks, Settings, User, ChevronRight } from 'lucide-vue-next'
import { usePluginStore } from '@/store/usePluginStore' 

const props = defineProps<{ open: boolean }>()
defineEmits(['close', 'open-github-settings'])

const { githubConfig, loadGitHubConfig } = usePluginStore()

const activeTab = ref('plugins')

// 页面加载时加载配置
onMounted(async () => {
  await loadGitHubConfig()
})

const menuItems = [
  { id: 'general', label: '外观设置', icon: Settings },
  { id: 'plugins', label: '插件管理', icon: Blocks },
  { id: 'account', label: '账户信息', icon: User },
]
</script>

<template>
  <Dialog :open="open" @update:open="$emit('close')">
    <DialogContent class="max-w-4xl p-0 gap-0 overflow-hidden flex flex-col h-auto max-h-[85vh] bg-background border-none shadow-2xl z-[50]">
      <div class="flex flex-1 overflow-hidden min-h-[500px]">
        
        <div class="w-60 border-r bg-muted/20 p-4 flex flex-col gap-1 shrink-0">
          <div class="px-2 py-6 flex items-center gap-2 mb-2">
            <div class="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-bold italic">I</div>
            <span class="font-bold tracking-tight text-lg">Iris Settings</span>
          </div>
          
          <Button 
            v-for="item in menuItems" 
            :key="item.id"
            variant="ghost" 
            :class="['justify-start gap-3 h-11 px-3 rounded-lg transition-all', activeTab === item.id ? 'bg-secondary text-secondary-foreground shadow-sm' : 'text-muted-foreground hover:bg-secondary/50']"
            @click="activeTab = item.id"
          >
            <component :is="item.icon" class="w-4 h-4" />
            <span class="font-medium text-sm">{{ item.label }}</span>
          </Button>
        </div>

        <div class="flex-1 flex flex-col min-w-0">
          <ScrollArea class="flex-1">
            <div class="p-8">
              <div v-if="activeTab === 'plugins'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div>
                  <h3 class="text-2xl font-bold tracking-tight">插件管理</h3>
                  <p class="text-muted-foreground text-sm mt-1 text-balance">连接并配置第三方服务，让 Iris 自动同步并分析你的数字内容。</p>
                </div>

                <div class="grid gap-3">
                  <div 
                    class="group border rounded-xl p-4 flex items-center justify-between hover:border-primary/50 hover:bg-muted/30 transition-all cursor-pointer"
                    @click="$emit('open-github-settings')"
                  >
                    <div class="flex items-center gap-4">
                      <div class="p-2.5 bg-muted rounded-xl group-hover:bg-background transition-colors shadow-sm">
                        <Github class="w-6 h-6" />
                      </div>
                      <div>
                        <div class="flex items-center gap-2">
                          <span class="font-bold text-sm">GitHub Stars</span>
                          <div 
                            class="w-1.5 h-1.5 rounded-full"
                            :class="githubConfig.has_token ? 'bg-green-500' : 'bg-gray-400'"
                          ></div>
                        </div>
                        <p class="text-xs text-muted-foreground mt-0.5 leading-relaxed">同步 GitHub 仓库并使用 AI 生成 README 摘要。</p>
                      </div>
                    </div>
                    <ChevronRight class="w-4 h-4 text-muted-foreground group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>
              
              <div v-else class="flex flex-col items-center justify-center py-20 text-muted-foreground">
                <Settings class="w-12 h-12 opacity-10 mb-4" />
                <p class="text-sm">该模块正在开发中，敬请期待...</p>
              </div>
            </div>
          </ScrollArea>
        </div>
      </div>
    </DialogContent>
  </Dialog>


</template>