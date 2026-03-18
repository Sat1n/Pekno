<script setup lang="ts">
import { ref, watch, computed } from 'vue'
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
} from '@/components/ui/dialog'
import { Settings, Save, RefreshCw, Loader2, AlertCircle, Check, Trash2 } from 'lucide-vue-next'
import { useToast } from '@/components/ui/toast/use-toast'
import { usePluginStore } from '@/store/usePluginStore'
import { uninstallPluginApi } from '@/lib/api'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'

const props = defineProps<{
  open: boolean
  pluginId: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { toast } = useToast()
const pluginStore = usePluginStore()

// 状态
const isSaving = ref(false)
const isSyncing = ref(false)
const isUninstalling = ref(false)
const isUninstallDialogOpen = ref(false)
const formData = ref<Record<string, any>>({})

// 获取当前插件信息
const currentPlugin = computed(() => {
  return pluginStore.pluginsManifests.value.find(p => p.manifest.id === props.pluginId)
})

// 卸载插件
async function handleUninstall() {
  if (!currentPlugin.value) return
  
  isUninstalling.value = true
  try {
    await uninstallPluginApi(props.pluginId)
    toast({
      title: '卸载成功',
      description: `${currentPlugin.value.manifest.name} 已移除`,
    })
    
    // 刷新列表并关闭所有弹窗
    await pluginStore.loadAllPlugins()
    isUninstallDialogOpen.value = false
    emit('update:open', false)
  } catch (error: any) {
    toast({
      title: '卸载失败',
      description: error.response?.data?.detail || '无法完成卸载',
      variant: 'destructive',
    })
  } finally {
    isUninstalling.value = false
  }
}


const schema = computed(() => currentPlugin.value?.manifest.settings_schema || {})

// 初始化表单数据
function initForm() {
  if (!currentPlugin.value) return
  const config = currentPlugin.value.config || {}
  
  formData.value = {}
  for (const key in schema.value) {
    const fieldConfig = schema.value[key]
    if (fieldConfig.secret) {
      // 密码字段不回填，留空
      formData.value[key] = ''
    } else {
      formData.value[key] = config[key] ?? fieldConfig.default
    }
  }
}

watch(() => props.open, (newVal) => {
  if (newVal) {
    initForm()
  }
})

// 监听插件 ID 变化
watch(() => props.pluginId, () => {
  if (props.open) {
    initForm()
  }
})

// 动态表单项是否需要必填（若是密码字段，则有token时不必填，否则必填）
function isRequired(key: string, field: any) {
  if (field.secret && currentPlugin.value?.has_token) {
    return false
  }
  return field.required
}

// 保存配置
async function handleSave() {
  if (!currentPlugin.value) return

  // 验证必填项
  for (const key in schema.value) {
    const field = schema.value[key]
    if (isRequired(key, field) && (formData.value[key] === undefined || formData.value[key] === null || formData.value[key] === '')) {
      toast({
        title: '表单校验失败',
        description: `${field.label || key} 是必填项`,
        variant: 'destructive',
      })
      return
    }
  }

  isSaving.value = true
  try {
    const savePayload: Record<string, any> = {}
    for (const key in formData.value) {
      const val = formData.value[key]
      const field = schema.value[key]
      // 密码字段为空时不提交
      if (field.secret && (val === '' || val === null || val === undefined)) {
        continue
      }
      savePayload[key] = val
    }

    await pluginStore.savePluginConfig(props.pluginId, savePayload)
    // 保存成功后刷新所有插件状态
    await pluginStore.loadAllPlugins()
    
    toast({
      title: '配置已保存',
      description: `${currentPlugin.value.manifest.name} 配置已更新`,
    })
    
    // 如果想要保存后自动关闭可以解开下面注释
    // emit('update:open', false)
  } catch (error: any) {
    toast({
      title: '保存失败',
      description: error.message || '请稍后重试',
      variant: 'destructive',
    })
  } finally {
    isSaving.value = false
  }
}

// 手动同步
async function handleSync() {
  if (!currentPlugin.value) return
  
  isSyncing.value = true
  try {
    await pluginStore.triggerPluginSync(props.pluginId)
    toast({
      title: '同步已触发',
      description: `${currentPlugin.value.manifest.name} 数据同步任务已加入队列`,
    })
  } catch (error: any) {
    toast({
      title: '同步触发失败',
      description: error.message || '请检查配置或重试',
      variant: 'destructive',
    })
  } finally {
    isSyncing.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="$emit('update:open', $event)">
    <DialogContent v-if="currentPlugin" class="sm:max-w-[500px] p-0 overflow-hidden bg-background border-none shadow-2xl">
      <DialogHeader class="p-6 pb-0">
        <div class="flex items-center gap-4">
          <div class="p-3 bg-primary/10 rounded-xl">
            <Settings class="w-6 h-6 text-primary" />
          </div>
          <div class="space-y-1">
            <DialogTitle class="text-xl font-bold flex items-center gap-2">
              {{ currentPlugin.manifest.name }}
              <Badge :variant="currentPlugin.has_token ? 'default' : 'secondary'" class="text-[10px] font-medium px-1.5 py-0">
                <Check v-if="currentPlugin.has_token" class="w-3 h-3 mr-1" />
                <AlertCircle v-else class="w-3 h-3 mr-1" />
                {{ currentPlugin.has_token ? '已配置' : '未配置' }}
              </Badge>
            </DialogTitle>
            <DialogDescription>
              {{ currentPlugin.manifest.description || '配置该插件的参数' }}
            </DialogDescription>
          </div>
        </div>
      </DialogHeader>

      <Separator class="my-6" />

      <div class="px-6 space-y-6 max-h-[60vh] overflow-y-auto pb-6">
        <div v-for="(fieldConfig, fieldKey) in schema" :key="fieldKey" class="space-y-3">
          <!-- 布尔类型：Switch -->
          <div v-if="fieldConfig.type === 'boolean'" class="flex items-center justify-between p-4 rounded-lg border bg-card">
            <div class="space-y-0.5">
              <Label class="text-base">{{ fieldConfig.label || fieldKey }}</Label>
              <p v-if="fieldConfig.description" class="text-sm text-muted-foreground">{{ fieldConfig.description }}</p>
            </div>
            <Switch v-model="formData[fieldKey]" />
          </div>

          <!-- 字符串类型 & 密码：Input password -->
          <div v-else-if="fieldConfig.type === 'string' && fieldConfig.secret" class="space-y-2">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <Input 
              type="password" 
              v-model="formData[fieldKey]" 
              :placeholder="currentPlugin.has_token ? '已设置（留空不修改）' : `请输入 ${fieldConfig.label || fieldKey}`" 
            />
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
            <p v-if="currentPlugin.token_preview" class="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <Check class="w-3 h-3 text-green-500" />
              当前 Token: <code class="bg-muted px-1.5 py-0.5 rounded text-[10px]">{{ currentPlugin.token_preview }}</code>
            </p>
          </div>

          <!-- 整数类型：Input number -->
          <div v-else-if="fieldConfig.type === 'integer'" class="space-y-2">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <Input 
              type="number" 
              v-model.number="formData[fieldKey]" 
              :min="fieldConfig.min" 
              :max="fieldConfig.max"
            />
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>

          <!-- 普通字符串类型：Input text -->
          <div v-else-if="fieldConfig.type === 'string' && !fieldConfig.secret" class="space-y-2">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <Input 
              type="text" 
              v-model="formData[fieldKey]" 
            />
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>
        </div>
      </div>

      <div class="p-6 bg-muted/30 border-t flex justify-between items-center mt-auto">
        <div class="flex gap-2">
          <!-- 卸载按钮（仅对第三方插件显示，假设非 github_stars 为第三方，或者简单起见都显示） -->
          <Button 
            v-if="currentPlugin.manifest.id !== 'github_stars'"
            variant="ghost" 
            class="text-destructive hover:text-destructive hover:bg-destructive/10"
            @click="isUninstallDialogOpen = true"
          >
            <Trash2 class="w-4 h-4 mr-2" />
            卸载
          </Button>

          <Button 
            variant="outline" 
            @click="handleSync" 
            :disabled="isSyncing || !currentPlugin.has_token"
          >
            <Loader2 v-if="isSyncing" class="w-4 h-4 mr-2 animate-spin" />
            <RefreshCw v-else class="w-4 h-4 mr-2" />
            手动同步
          </Button>
        </div>

        <div class="flex gap-2">
          <Button variant="ghost" @click="$emit('update:open', false)">取消</Button>
          <Button @click="handleSave" :disabled="isSaving">
            <Loader2 v-if="isSaving" class="w-4 h-4 mr-2 animate-spin" />
            <Save v-else class="w-4 h-4 mr-2" />
            保存配置
          </Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>

  <!-- 卸载确认对话框 -->
  <AlertDialog :open="isUninstallDialogOpen" @update:open="isUninstallDialogOpen = $event">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>确认卸载插件？</AlertDialogTitle>
        <AlertDialogDescription>
          这将删除插件文件及其所有配置数据。此操作不可撤销。
        </AlertDialogDescription>
      </AlertDialogHeader>
      <div class="flex gap-3 justify-end">
        <AlertDialogCancel>取消</AlertDialogCancel>
        <AlertDialogAction 
          class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          @click="handleUninstall"
        >
          <Loader2 v-if="isUninstalling" class="w-4 h-4 mr-2 animate-spin" />
          {{ isUninstalling ? '卸载中...' : '确认卸载' }}
        </AlertDialogAction>
      </div>
    </AlertDialogContent>
  </AlertDialog>
</template>
