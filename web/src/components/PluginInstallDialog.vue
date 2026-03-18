<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/toast/use-toast'
import { Upload, FileCode, ShieldAlert, Loader2, CheckCircle2, Box, Eye, EyeOff } from 'lucide-vue-next'
import { uploadPluginPreviewApi, confirmInstallPluginApi } from '@/lib/api'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'install-success': []
}>()

const { toast } = useToast()

// 状态管理
const step = ref<'upload' | 'review'>('upload')
const isUploading = ref(false)
const isInstalling = ref(false)
const showSourceCode = ref(false)
const riskAccepted = ref(false)

// 预览数据
const previewData = ref<{
  temp_token: string
  manifest: any
  source_code: string
  file_structure: string[]
} | null>(null)

// 处理文件上传
async function handleFileUpload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return

  // 校验文件类型
  if (!file.name.endsWith('.zip')) {
    toast({
      title: '格式错误',
      description: '仅支持 .zip 格式的插件包',
      variant: 'destructive'
    })
    return
  }

  isUploading.value = true
  try {
    const data = await uploadPluginPreviewApi(file)
    previewData.value = data
    step.value = 'review'
  } catch (error: any) {
    toast({
      title: '上传失败',
      description: error.response?.data?.detail || '预检请求失败',
      variant: 'destructive'
    })
  } finally {
    isUploading.value = false
    // 清空 input 方便下次选择
    ;(event.target as HTMLInputElement).value = ''
  }
}

// 确认安装
async function handleInstall() {
  if (!previewData.value || !riskAccepted.value) return

  isInstalling.value = true
  try {
    await confirmInstallPluginApi(previewData.value.temp_token)
    toast({
      title: '安装成功',
      description: `插件 ${previewData.value.manifest.name} 已就绪`,
    })
    emit('install-success')
    emit('update:open', false)
    resetState()
  } catch (error: any) {
    toast({
      title: '安装失败',
      description: error.response?.data?.detail || '无法完成安装',
      variant: 'destructive'
    })
  } finally {
    isInstalling.value = false
  }
}

function resetState() {
  step.value = 'upload'
  previewData.value = null
  showSourceCode.value = false
  riskAccepted.value = false
}
</script>

<template>
  <Dialog :open="open" @update:open="$emit('update:open', $event)">
    <DialogContent class="sm:max-w-[600px] max-h-[85vh] flex flex-col p-0 gap-0 overflow-hidden">
      <!-- 头部 -->
      <DialogHeader class="p-6 border-b shrink-0">
        <DialogTitle class="flex items-center gap-2">
          <Box class="w-5 h-5 text-primary" />
          {{ step === 'upload' ? '安装新插件' : '安全审查' }}
        </DialogTitle>
        <DialogDescription>
          {{ step === 'upload' ? '上传插件 ZIP 包以扩展 Iris 的能力' : '请仔细审查插件代码与权限' }}
        </DialogDescription>
      </DialogHeader>

      <!-- 步骤 1: 上传区域 -->
      <div v-if="step === 'upload'" class="flex-1 p-12 flex flex-col items-center justify-center text-center border-dashed border-2 m-6 rounded-xl bg-muted/20 hover:bg-muted/40 transition-colors">
        <div class="p-4 rounded-full bg-background shadow-sm mb-4">
          <Upload class="w-8 h-8 text-muted-foreground" />
        </div>
        <h3 class="font-semibold text-lg mb-1">点击上传插件包</h3>
        <p class="text-sm text-muted-foreground mb-6">仅支持标准的 .zip 格式插件包</p>
        
        <div class="relative">
          <Button :disabled="isUploading">
            <Loader2 v-if="isUploading" class="w-4 h-4 mr-2 animate-spin" />
            {{ isUploading ? '正在预检...' : '选择文件' }}
          </Button>
          <input 
            type="file" 
            accept=".zip" 
            class="absolute inset-0 opacity-0 cursor-pointer"
            @change="handleFileUpload"
            :disabled="isUploading"
          />
        </div>
      </div>

      <!-- 步骤 2: 审查区域 -->
      <ScrollArea v-else class="flex-1 p-6">
        <div class="space-y-6">
          <!-- 基本信息 -->
          <div class="flex items-start gap-4 p-4 border rounded-lg bg-card">
            <div class="p-3 bg-primary/10 rounded-lg">
              <Box class="w-6 h-6 text-primary" />
            </div>
            <div>
              <h3 class="font-bold text-lg flex items-center gap-2">
                {{ previewData?.manifest.name }}
                <Badge variant="outline" class="text-xs">v{{ previewData?.manifest.version }}</Badge>
              </h3>
              <p class="text-sm text-muted-foreground mt-1">{{ previewData?.manifest.description }}</p>
              <div class="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                <span>ID: {{ previewData?.manifest.id }}</span>
                <span>Author: {{ previewData?.manifest.author }}</span>
              </div>
            </div>
          </div>

          <!-- 权限警告 -->
          <div class="space-y-3">
            <h4 class="text-sm font-semibold flex items-center gap-2">
              <ShieldAlert class="w-4 h-4 text-orange-500" />
              权限声明
            </h4>
            <div class="flex flex-wrap gap-2">
              <Badge variant="secondary" class="text-xs font-normal">
                <CheckCircle2 class="w-3 h-3 mr-1 text-green-500" />
                读取配置
              </Badge>
              <Badge variant="secondary" class="text-xs font-normal">
                <CheckCircle2 class="w-3 h-3 mr-1 text-green-500" />
                访问数据库
              </Badge>
              <!-- 如果 manifest 有 permissions 字段可以在这里遍历 -->
              <Badge variant="destructive" class="text-xs font-normal bg-red-50 text-red-600 border-red-200 hover:bg-red-100">
                ⚠️ 可能访问外部网络
              </Badge>
            </div>
          </div>

          <Separator />

          <!-- 源码审计 -->
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <h4 class="text-sm font-semibold flex items-center gap-2">
                <FileCode class="w-4 h-4" />
                源码审计
              </h4>
              <Button variant="ghost" size="sm" class="h-8 text-xs" @click="showSourceCode = !showSourceCode">
                <component :is="showSourceCode ? EyeOff : Eye" class="w-3 h-3 mr-1" />
                {{ showSourceCode ? '收起源码' : '展开预览' }}
              </Button>
            </div>
            
            <div v-if="showSourceCode" class="relative">
              <pre class="p-4 rounded-lg bg-slate-950 text-slate-50 text-xs overflow-x-auto max-h-[300px] font-mono leading-relaxed border border-slate-800">{{ previewData?.source_code }}</pre>
            </div>
            <div v-else class="p-4 rounded-lg bg-muted text-center text-sm text-muted-foreground border border-dashed">
              点击上方按钮展开预览主入口源码
            </div>
          </div>
        </div>
      </ScrollArea>

      <!-- 底部操作栏 -->
      <div v-if="step === 'review'" class="p-6 border-t bg-muted/20 shrink-0 space-y-4">
        <!-- 风险确认 -->
        <div class="flex items-start gap-2">
          <Checkbox id="risk" :checked="riskAccepted" @update:checked="riskAccepted = $event" />
          <div class="grid gap-1.5 leading-none">
            <label
              for="risk"
              class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 text-destructive"
            >
              我已知晓此插件来自开源社区，并同意自行承担运行此代码的潜在风险
            </label>
            <p class="text-xs text-muted-foreground">
              插件代码将在您的服务器上以完全权限运行，请确保来源可信。
            </p>
          </div>
        </div>

        <div class="flex gap-2 justify-end">
          <Button variant="outline" @click="resetState" :disabled="isInstalling">取消</Button>
          <Button 
            variant="destructive" 
            @click="handleInstall" 
            :disabled="!riskAccepted || isInstalling"
          >
            <Loader2 v-if="isInstalling" class="w-4 h-4 mr-2 animate-spin" />
            {{ isInstalling ? '安装中...' : '确认安装' }}
          </Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
