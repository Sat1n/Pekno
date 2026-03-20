<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Blocks, User, ChevronRight, Database, Trash2, Loader2, HardDrive, Puzzle, Plus, MailPlus, LogOut, KeyRound, Copy } from 'lucide-vue-next'
import { usePluginStore } from '@/store/usePluginStore'
import { changePassword, clearStoredToken, createInvitationCode, getDataSources, getInvitationCodes, getStoredAuthUser, clearDataSource, type DataSourceStat, type InvitationCodeInfo } from '@/lib/api'
import { useToast } from '@/components/ui/toast/use-toast'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import PluginInstallDialog from './PluginInstallDialog.vue'

const props = defineProps<{ open: boolean }>()
defineEmits(['close', 'open-plugin-settings'])

const router = useRouter()
const { toast } = useToast()
const { pluginsManifests, loadAllPlugins } = usePluginStore()
const currentUser = computed(() => getStoredAuthUser())
const isAdmin = computed(() => ['admin', 'super_admin'].includes(currentUser.value.role || ''))

const activeTab = ref('plugins')
const isInstallDialogOpen = ref(false)

const dataSources = ref<DataSourceStat[]>([])
const isLoadingData = ref(false)
const isClearingData = ref<Record<string, boolean>>({})
const invitations = ref<InvitationCodeInfo[]>([])
const isLoadingInvitations = ref(false)
const isCreatingInvitation = ref(false)

const currentPassword = ref('')
const newPassword = ref('')
const isChangingPassword = ref(false)

const isClearDialogOpen = ref(false)
const sourceToClear = ref('')

const sourceNames: Record<string, string> = {
  github_star: 'GitHub 收藏',
  bilibili: 'Bilibili 视频',
  article: '本地文章',
}

const menuItems = computed(() => {
  if (isAdmin.value) {
    return [
      { id: 'plugins', label: '插件管理', icon: Blocks },
      { id: 'data', label: '数据管理', icon: Database },
      { id: 'invites', label: '邀请管理', icon: MailPlus },
      { id: 'account', label: '账户信息', icon: User },
    ]
  }

  return [
    { id: 'plugins', label: '插件管理', icon: Blocks },
    { id: 'account', label: '账户信息', icon: User },
  ]
})

async function loadDataSources() {
  isLoadingData.value = true
  try {
    dataSources.value = await getDataSources()
  } catch (error) {
    console.error('加载数据源失败:', error)
  } finally {
    isLoadingData.value = false
  }
}

async function loadInvitations() {
  if (!isAdmin.value) return
  isLoadingInvitations.value = true
  try {
    invitations.value = await getInvitationCodes()
  } catch (error) {
    console.error('加载邀请码失败:', error)
    toast({
      title: '加载失败',
      description: '无法获取邀请码列表',
      variant: 'destructive',
    })
  } finally {
    isLoadingInvitations.value = false
  }
}

async function handleCreateInvitation() {
  isCreatingInvitation.value = true
  try {
    const invitation = await createInvitationCode()
    invitations.value.unshift(invitation)
    await navigator.clipboard.writeText(invitation.code)
    toast({
      title: '邀请码已生成',
      description: `${invitation.code} 已复制到剪贴板`,
    })
  } catch (error) {
    toast({
      title: '生成失败',
      description: '请稍后重试',
      variant: 'destructive',
    })
  } finally {
    isCreatingInvitation.value = false
  }
}

async function copyInviteCode(code: string) {
  try {
    await navigator.clipboard.writeText(code)
    toast({
      title: '已复制邀请码',
      description: code,
    })
  } catch {
    toast({
      title: '复制失败',
      description: '请手动复制邀请码',
      variant: 'destructive',
    })
  }
}

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
      description: res.message || `已成功清理 ${res.deleted_count} 条记录`,
    })
    await loadDataSources()
  } catch (error) {
    toast({
      title: '清理失败',
      description: '请稍后重试',
      variant: 'destructive',
    })
  } finally {
    isClearingData.value[sourceType] = false
  }
}

async function handleChangePassword() {
  if (!currentPassword.value || !newPassword.value) {
    toast({
      title: '表单不完整',
      description: '请填写当前密码和新密码',
      variant: 'destructive',
    })
    return
  }

  isChangingPassword.value = true
  try {
    const response = await changePassword({
      current_password: currentPassword.value,
      new_password: newPassword.value,
    })
    currentPassword.value = ''
    newPassword.value = ''
    toast({
      title: '密码已更新',
      description: response.message,
    })
  } catch (error: any) {
    toast({
      title: '修改失败',
      description: error?.response?.data?.detail || '请稍后重试',
      variant: 'destructive',
    })
  } finally {
    isChangingPassword.value = false
  }
}

async function logout() {
  clearStoredToken()
  await router.replace('/login')
}

onMounted(async () => {
  await loadAllPlugins()
})

watch(
  () => props.open,
  async (newVal) => {
    if (!newVal) return
    activeTab.value = 'plugins'
    await loadAllPlugins()
  }
)

watch(activeTab, (newTab) => {
  if (newTab === 'data') {
    void loadDataSources()
  }
  if (newTab === 'invites') {
    void loadInvitations()
  }
})
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
                <div class="flex items-center justify-between">
                  <div>
                    <h3 class="text-2xl font-bold tracking-tight">插件管理</h3>
                    <p class="text-muted-foreground text-sm mt-1 text-balance">连接并配置第三方服务，让 Iris 自动同步并分析你的数字内容。</p>
                  </div>
                  <Button v-if="isAdmin" size="sm" variant="outline" @click="isInstallDialogOpen = true">
                    <Plus class="w-4 h-4 mr-2" />
                    安装插件
                  </Button>
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
                        <Puzzle class="w-6 h-6" />
                      </div>
                      <div>
                        <div class="flex items-center gap-2">
                          <span class="font-bold text-sm">{{ plugin.manifest.name }}</span>
                          <div class="w-1.5 h-1.5 rounded-full" :class="plugin.has_token ? 'bg-green-500' : 'bg-gray-400'"></div>
                        </div>
                        <p class="text-xs text-muted-foreground mt-0.5 leading-relaxed">{{ plugin.manifest.description }}</p>
                      </div>
                    </div>
                    <ChevronRight class="w-4 h-4 text-muted-foreground group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>

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

              <div v-else-if="activeTab === 'invites'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div class="flex items-center justify-between">
                  <div>
                    <h3 class="text-2xl font-bold tracking-tight">邀请管理</h3>
                    <p class="text-muted-foreground text-sm mt-1 text-balance">生成并追踪邀请码，用于安全邀请新用户注册。</p>
                  </div>
                  <Button @click="handleCreateInvitation" :disabled="isCreatingInvitation">
                    <Loader2 v-if="isCreatingInvitation" class="w-4 h-4 mr-2 animate-spin" />
                    <MailPlus v-else class="w-4 h-4 mr-2" />
                    生成邀请码
                  </Button>
                </div>

                <div class="border rounded-xl overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-muted/40">
                      <tr class="text-left">
                        <th class="px-4 py-3 font-medium">邀请码</th>
                        <th class="px-4 py-3 font-medium">状态</th>
                        <th class="px-4 py-3 font-medium">使用者</th>
                        <th class="px-4 py-3 font-medium">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="isLoadingInvitations">
                        <td colspan="4" class="px-4 py-8 text-center text-muted-foreground">
                          <Loader2 class="w-5 h-5 animate-spin inline mr-2" />
                          正在加载邀请码...
                        </td>
                      </tr>
                      <tr v-else-if="invitations.length === 0">
                        <td colspan="4" class="px-4 py-8 text-center text-muted-foreground">暂未生成任何邀请码</td>
                      </tr>
                      <tr v-for="invitation in invitations" :key="invitation.id" class="border-t">
                        <td class="px-4 py-3 font-mono">{{ invitation.code }}</td>
                        <td class="px-4 py-3">
                          <span :class="invitation.is_used ? 'text-muted-foreground' : 'text-green-600'" class="font-medium">
                            {{ invitation.is_used ? '已使用' : '未使用' }}
                          </span>
                        </td>
                        <td class="px-4 py-3">{{ invitation.used_by_username || '-' }}</td>
                        <td class="px-4 py-3">
                          <Button variant="ghost" size="sm" @click="copyInviteCode(invitation.code)">
                            <Copy class="w-4 h-4 mr-1" />
                            复制
                          </Button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div v-else-if="activeTab === 'account'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div>
                  <h3 class="text-2xl font-bold tracking-tight">账户信息</h3>
                  <p class="text-muted-foreground text-sm mt-1 text-balance">管理当前登录账户的基础信息与安全设置。</p>
                </div>

                <div class="rounded-xl border p-5 space-y-3 bg-card">
                  <div>
                    <div class="text-sm text-muted-foreground">用户名</div>
                    <div class="text-lg font-semibold">{{ currentUser.username }}</div>
                  </div>
                  <div>
                    <div class="text-sm text-muted-foreground">角色</div>
                    <div class="text-base font-medium">{{ currentUser.role }}</div>
                  </div>
                </div>

                <div class="rounded-xl border p-5 space-y-4 bg-card max-w-xl">
                  <div class="flex items-center gap-2">
                    <KeyRound class="w-4 h-4 text-primary" />
                    <h4 class="font-semibold">修改密码</h4>
                  </div>

                  <div class="space-y-2">
                    <Label>当前密码</Label>
                    <Input v-model="currentPassword" type="password" />
                  </div>

                  <div class="space-y-2">
                    <Label>新密码</Label>
                    <Input v-model="newPassword" type="password" />
                  </div>

                  <div class="flex gap-3">
                    <Button @click="handleChangePassword" :disabled="isChangingPassword">
                      <Loader2 v-if="isChangingPassword" class="w-4 h-4 mr-2 animate-spin" />
                      <KeyRound v-else class="w-4 h-4 mr-2" />
                      更新密码
                    </Button>
                    <Button variant="destructive" @click="logout">
                      <LogOut class="w-4 h-4 mr-2" />
                      退出登录
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </ScrollArea>
        </div>
      </div>
    </DialogContent>
  </Dialog>

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

  <PluginInstallDialog
    v-if="isAdmin"
    v-model:open="isInstallDialogOpen"
    @install-success="loadAllPlugins"
  />
</template>
