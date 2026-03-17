<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Github, Blocks, Settings, User, ChevronRight, Database, Trash2, Loader2, HardDrive, Puzzle } from 'lucide-vue-next'
import { usePluginStore } from '@/store/usePluginStore'
import { getDataSources, clearDataSource, type DataSourceStat } from '@/lib/api'
import { useToast } from '@/components/ui/toast/use-toast' 
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'

const props = defineProps<{ open: boolean }>()
defineEmits(['close', 'open-plugin-settings'])

const { pluginsManifests, loadAllPlugins } = usePluginStore()

const activeTab = ref('plugins')

// 数据管理相关状态
const { toast } = useToast()
const dataSources = ref<DataSourceStat[]>([])
const isLoadingData = ref(false)
const isClearingData = ref<Record<string, boolean>>({})

const loadDataSources = async () => {
  isLoadingData.value = true
  try {
    dataSources.value = await getDataSources()
  } catch (error) {
    console.error('加载数据源失败:', error)
  } finally {
    isLoadingData.value = false
  }
}

const isClearDialogOpen = ref(false)
const sourceToClear = ref('')

const openClearDialog = (sourceType: string) => {
  sourceToClear.value = sourceType
  isClearDialogOpen.value = true
}

const confirmClearData = async () => {
  const sourceType = sourceToClear.value
  isClearDialogOpen.value = false
  
  isClearingData.value[sourceType] = true
  try {
    const res = await clearDataSource(sourceType)
    toast({
      title: '清理成功',
      description: res.message || `已成功清理 ${res.deleted_count} 条记录`
    })
    await loadDataSources() // 重新加载数据
  } catch (error) {
    toast({
      title: '清理失败',
      description: '请查看控制台错误日志',
      variant: 'destructive'
    })
  } finally {
    isClearingData.value[sourceType] = false
  }
}

// 字典映射显示名称
const sourceNames: Record<string, string> = {
  'github_star': 'GitHub 收藏',
  'bilibili': 'Bilibili 视频',
  'article': '本地文章'
}

// 页面加载时加载配置
onMounted(async () => {
  await loadAllPlugins()
})

// 监听 Tab 切换
watch(activeTab, (newTab) => {
  if (newTab === 'data') {
    loadDataSources()
  }
})

const menuItems = [
  { id: 'general', label: '外观设置', icon: Settings },
  { id: 'plugins', label: '插件管理', icon: Blocks },
  { id: 'data', label: '数据管理', icon: Database },
  { id: 'account', label: '账户信息', icon: User },
]
</script>

<template>
  <Dialog :open="open" @update:open="$emit('close')">
    <DialogContent class="w-[90vw] max-w-6xl h-[90vh] p-0 gap-0 overflow-hidden flex flex-col bg-background border-none shadow-2xl">
      <div class="flex flex-1 overflow-hidden min-h-0">
        
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
                    v-for="plugin in pluginsManifests"
                    :key="plugin.manifest.id"
                    class="group border rounded-xl p-4 flex items-center justify-between hover:border-primary/50 hover:bg-muted/30 transition-all cursor-pointer"
                    @click="$emit('open-plugin-settings', plugin.manifest.id)"
                  >
                    <div class="flex items-center gap-4">
                      <div class="p-2.5 bg-muted rounded-xl group-hover:bg-background transition-colors shadow-sm">
                        <!-- 可以根据插件ID或其它标识渲染不同的图标，默认用 Puzzle -->
                        <Github v-if="plugin.manifest.id === 'github'" class="w-6 h-6" />
                        <Puzzle v-else class="w-6 h-6" />
                      </div>
                      <div>
                        <div class="flex items-center gap-2">
                          <span class="font-bold text-sm">{{ plugin.manifest.name }}</span>
                          <div 
                            class="w-1.5 h-1.5 rounded-full"
                            :class="plugin.has_token ? 'bg-green-500' : 'bg-gray-400'"
                          ></div>
                        </div>
                        <p class="text-xs text-muted-foreground mt-0.5 leading-relaxed">{{ plugin.manifest.description }}</p>
                      </div>
                    </div>
                    <ChevronRight class="w-4 h-4 text-muted-foreground group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>

              <!-- 数据管理 Tab -->
              <div v-else-if="activeTab === 'data'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div>
                  <h3 class="text-2xl font-bold tracking-tight">数据管理</h3>
                  <p class="text-muted-foreground text-sm mt-1 text-balance">统一管理系统各插件从外部同步收集的数据。</p>
                </div>

                <div v-if="isLoadingData" class="flex justify-center items-center py-12">
                  <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
                </div>
                
                <div v-else-if="dataSources.length === 0" class="flex flex-col items-center justify-center py-20 text-muted-foreground border rounded-xl border-dashed">
                  <HardDrive class="w-12 h-12 opacity-20 mb-4" />
                  <p class="text-sm">暂无任何缓存数据</p>
                </div>

                <div v-else class="grid gap-4">
                  <div 
                    v-for="source in dataSources" 
                    :key="source.source_type"
                    class="group border rounded-xl p-5 flex items-center justify-between bg-card hover:border-primary/50 transition-all"
                  >
                    <div class="flex items-center gap-4">
                      <div class="p-3 bg-primary/10 text-primary rounded-xl">
                        <Database class="w-6 h-6" />
                      </div>
                      <div>
                        <div class="font-bold text-base">{{ sourceNames[source.source_type] || source.source_type }}</div>
                        <p class="text-sm text-muted-foreground mt-1">
                          共缓存了 <span class="text-primary font-medium">{{ source.count }}</span> 项数据记录
                        </p>
                      </div>
                    </div>
                    
                    <Button 
                      variant="destructive" 
                      size="sm" 
                      class="opacity-0 group-hover:opacity-100 transition-opacity gap-2"
                      :disabled="isClearingData[source.source_type]"
                      @click="openClearDialog(source.source_type)"
                    >
                      <Loader2 v-if="isClearingData[source.source_type]" class="w-4 h-4 animate-spin" />
                      <Trash2 v-else class="w-4 h-4" />
                      <span>清空数据</span>
                    </Button>
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

  <!-- Clear Data Confirmation Dialog -->
  <AlertDialog :open="isClearDialogOpen" @update:open="isClearDialogOpen = $event">
    <AlertDialogContent class="max-w-[400px]">
      <AlertDialogHeader>
        <AlertDialogTitle>清空确认</AlertDialogTitle>
        <AlertDialogDescription>
          确定要清空 <span class="font-bold text-foreground">{{ sourceNames[sourceToClear] || sourceToClear }}</span> 下的所有缓存数据吗？此操作将永久抹除这些记录且不可恢复。
        </AlertDialogDescription>
      </AlertDialogHeader>
      <div class="flex gap-3 justify-end mt-2">
        <AlertDialogCancel>取消</AlertDialogCancel>
        <AlertDialogAction class="bg-destructive hover:bg-destructive/90 text-destructive-foreground" @click="confirmClearData">
          确认清空
        </AlertDialogAction>
      </div>
    </AlertDialogContent>
  </AlertDialog>

</template>