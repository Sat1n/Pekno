<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Blocks, User, ChevronRight, Database, Trash2, Loader2, HardDrive, Puzzle, Plus, MailPlus, LogOut, KeyRound, Copy, BrainCircuit, SlidersHorizontal, Cpu, Save, Search, Sparkles, GalleryVerticalEnd, Shield, Server } from 'lucide-vue-next'
import { usePluginStore } from '@/store/usePluginStore'
import { changePassword, clearStoredToken, createInvitationCode, getDataSources, getInvitationCodes, getModelProviders, getStoredAuthUser, clearDataSource, saveModelAssignments, saveModelProvider, getPATs, createPAT, deletePAT, type DataSourceStat, type InvitationCodeInfo, type ModelAssignmentInfo, type ModelProviderInfo, type PATItem } from '@/lib/api'
import { useToast } from '@/components/ui/toast/use-toast'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import PluginInstallDialog from './PluginInstallDialog.vue'

const props = defineProps<{ open: boolean; initialTab?: string }>()
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
const modelProviders = ref<ModelProviderInfo[]>([])
const modelAssignments = ref<ModelAssignmentInfo[]>([])
const isLoadingModels = ref(false)
const isSavingModelProvider = ref(false)
const isSavingModelAssignments = ref(false)
const selectedProviderId = ref('ollama')
const providerDraft = ref<Record<string, string>>({})
const modelSettingsTab = ref<'providers' | 'assignments'>('providers')
const providerSearch = ref('')
const providerCapabilityFilter = ref<'all' | string>('all')

const currentPassword = ref('')
const newPassword = ref('')

// PAT state
const pats = ref<PATItem[]>([])
const isLoadingPats = ref(false)
const isCreatingPat = ref(false)
const newPatAlias = ref('')
const newPatExpiry = ref<number | null>(null)
const newPatScopes = ref<string[]>(['read:knowledge', 'write:star'])
const newPatIsAdmin = ref(false)
const justCreatedToken = ref<string | null>(null)
const selectedMcpToken = ref('')
const isChangingPassword = ref(false)

const availablePatScopes = [
  {
    value: 'read:knowledge',
    label: '知识读取',
    description: '允许 Agent 搜索知识库与读取内容详情',
  },
  {
    value: 'write:star',
    label: '收藏写入',
    description: '允许将条目标记为收藏/稍后再看',
  },
  {
    value: 'write:system_config',
    label: '系统配置写入',
    description: '允许修改插件底层配置。仅建议与管理员令牌一起使用。',
  },
]

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
      { id: 'models', label: '模型设置', icon: BrainCircuit },
      { id: 'data', label: '数据管理', icon: Database },
      { id: 'invites', label: '邀请管理', icon: MailPlus },
      { id: 'tokens', label: '访问令牌', icon: Shield },
      { id: 'mcp', label: 'MCP 服务', icon: Server },
      { id: 'account', label: '账户信息', icon: User },
    ]
  }

  return [
    { id: 'plugins', label: '插件管理', icon: Blocks },
    { id: 'tokens', label: '访问令牌', icon: Shield },
    { id: 'mcp', label: 'MCP 服务', icon: Server },
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

const selectedProvider = computed(() => {
  return modelProviders.value.find((provider) => provider.id === selectedProviderId.value) || null
})

const providerCapabilities = computed(() => {
  const values = new Set<string>()
  for (const provider of modelProviders.value) {
    for (const capability of provider.capabilities || []) {
      values.add(capability)
    }
  }
  return ['all', ...Array.from(values)]
})

const filteredProviders = computed(() => {
  const keyword = providerSearch.value.trim().toLowerCase()
  return modelProviders.value.filter((provider) => {
    const matchesKeyword =
      !keyword ||
      provider.name.toLowerCase().includes(keyword) ||
      provider.description.toLowerCase().includes(keyword) ||
      provider.badge?.toLowerCase().includes(keyword)

    const matchesCapability =
      providerCapabilityFilter.value === 'all' ||
      provider.capabilities.includes(providerCapabilityFilter.value)

    return matchesKeyword && matchesCapability
  })
})

const groupedAssignments = computed(() => {
  const groups = new Map<string, ModelAssignmentInfo[]>()
  for (const assignment of modelAssignments.value) {
    const list = groups.get(assignment.group) || []
    list.push(assignment)
    groups.set(assignment.group, list)
  }
  return Array.from(groups.entries()).map(([group, items]) => ({
    group,
    items,
  }))
})

async function loadModelSettings() {
  if (!isAdmin.value) return
  isLoadingModels.value = true
  try {
    const providerState = await getModelProviders()
    modelProviders.value = providerState.providers
    modelAssignments.value = providerState.assignments
    const hasSelectedProvider = providerState.providers.some((provider) => provider.id === selectedProviderId.value)
    const firstProvider = providerState.providers[0]
    if (!hasSelectedProvider && firstProvider) {
      selectedProviderId.value = firstProvider.id
    }
    providerDraft.value = { ...(selectedProvider.value?.config || {}) }
  } catch (error) {
    console.error('加载模型设置失败:', error)
    toast({
      title: '加载失败',
      description: '无法获取模型设置',
      variant: 'destructive',
    })
  } finally {
    isLoadingModels.value = false
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

watch(selectedProvider, (provider) => {
  providerDraft.value = { ...(provider?.config || {}) }
})

watch(filteredProviders, (providers) => {
  if (providers.length === 0) return
  const exists = providers.some((provider) => provider.id === selectedProviderId.value)
  const firstProvider = providers[0]
  if (!exists) {
    selectedProviderId.value = firstProvider?.id || selectedProviderId.value
  }
})

async function handleSaveModelProvider() {
  if (!selectedProvider.value) return
  isSavingModelProvider.value = true
  try {
    const state = await saveModelProvider(selectedProvider.value.id, providerDraft.value)
    modelProviders.value = state.providers
    modelAssignments.value = state.assignments
    toast({
      title: '提供商配置已保存',
      description: selectedProvider.value.name,
    })
  } catch (error: any) {
    toast({
      title: '保存失败',
      description: error?.response?.data?.detail || '无法保存模型提供商配置',
      variant: 'destructive',
    })
  } finally {
    isSavingModelProvider.value = false
  }
}

async function handleSaveAssignments() {
  isSavingModelAssignments.value = true
  try {
    const response = await saveModelAssignments(modelAssignments.value)
    modelAssignments.value = response.assignments
    toast({
      title: '系统模型设置已保存',
      description: '新的模型用途配置已生效',
    })
  } catch (error: any) {
    toast({
      title: '保存失败',
      description: error?.response?.data?.detail || '无法保存系统模型设置',
      variant: 'destructive',
    })
  } finally {
    isSavingModelAssignments.value = false
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
    activeTab.value = props.initialTab || 'plugins'
    await loadAllPlugins()
  }
)

watch(activeTab, (newTab) => {
  if (newTab === 'models') {
    void loadModelSettings()
  }
  if (newTab === 'data') {
    void loadDataSources()
  }
  if (newTab === 'invites') {
    void loadInvitations()
  }
  if (newTab === 'tokens' || newTab === 'mcp') {
    void loadPats()
  }
})

async function loadPats() {
  isLoadingPats.value = true
  try {
    pats.value = await getPATs()
  } catch (error) {
    console.error('加载令牌失败:', error)
  } finally {
    isLoadingPats.value = false
  }
}

async function handleCreatePat() {
  if (!newPatAlias.value.trim()) {
    toast({ title: '请输入令牌别名', variant: 'destructive' })
    return
  }
  if (newPatScopes.value.length === 0) {
    toast({ title: '请至少选择一个权限', variant: 'destructive' })
    return
  }
  isCreatingPat.value = true
  try {
    const res = await createPAT(newPatAlias.value.trim(), newPatExpiry.value, {
      is_admin: newPatIsAdmin.value,
      scopes: newPatScopes.value,
    })
    justCreatedToken.value = res.token
    pats.value.unshift(res.pat)
    newPatAlias.value = ''
    newPatExpiry.value = null
    newPatScopes.value = ['read:knowledge', 'write:star']
    newPatIsAdmin.value = false
    toast({ title: '令牌已创建', description: '请立即复制并妥善保管，关闭后将无法再次查看完整令牌。' })
  } catch (error: any) {
    toast({ title: '创建失败', description: error?.response?.data?.detail || '请稍后重试', variant: 'destructive' })
  } finally {
    isCreatingPat.value = false
  }
}

async function handleDeletePat(id: string) {
  try {
    await deletePAT(id)
    pats.value = pats.value.filter(p => p.id !== id)
    toast({ title: '令牌已删除' })
  } catch {
    toast({ title: '删除失败', variant: 'destructive' })
  }
}

async function copyText(text: string, label: string = '内容') {
  try {
    await navigator.clipboard.writeText(text)
    toast({ title: `${label}已复制到剪贴板` })
  } catch {
    toast({ title: '复制失败', variant: 'destructive' })
  }
}

const mcpJsonConfig = computed(() => {
  const token = selectedMcpToken.value || (pats.value.length > 0 ? (pats.value[0]?.token ?? '') : '')
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8001'
  return JSON.stringify({
    "mcpServers": {
      "iris-hub": {
        "url": `${baseUrl}/api/mcp/sse`,
        "headers": {
          "Authorization": `Bearer ${token || '<your-token>'}`
        }
      }
    }
  }, null, 2)
})

const mcpBaseUrl = computed(() => {
  return typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8001'
})

const mcpStreamableEndpoint = computed(() => `${mcpBaseUrl.value}/api/mcp/v2/stream`)
const mcpLegacySseEndpoint = computed(() => `${mcpBaseUrl.value}/api/mcp/sse`)

function formatPatExpiry(expiresAt: string | null): string {
  if (!expiresAt) return '永久有效'
  const d = new Date(expiresAt)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }) + ' 过期'
}

function formatPatLastUsed(lastUsedAt: string | null): string {
  if (!lastUsedAt) return '从未使用'
  const d = new Date(lastUsedAt)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatPatScopes(scopes: string[]): string {
  if (!scopes || scopes.length === 0) return '无权限'
  const labels: Record<string, string> = {
    'read:knowledge': '知识读取',
    'write:star': '收藏写入',
    'write:system_config': '系统配置写入',
  }
  return scopes.map((scope) => labels[scope] || scope).join(' / ')
}
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

              <div v-else-if="activeTab === 'models'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div class="flex items-center justify-between">
                  <div>
                    <h3 class="text-2xl font-bold tracking-tight">模型设置</h3>
                    <p class="text-muted-foreground text-sm mt-1 text-balance">统一管理服务器的模型提供商，以及标签、总结、向量检索等用途所使用的模型。</p>
                  </div>
                </div>

                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="flex flex-wrap items-center gap-2">
                    <Button :variant="modelSettingsTab === 'providers' ? 'default' : 'outline'" @click="modelSettingsTab = 'providers'">
                      <Cpu class="w-4 h-4 mr-2" />
                      模型提供商
                    </Button>
                    <Button :variant="modelSettingsTab === 'assignments' ? 'default' : 'outline'" @click="modelSettingsTab = 'assignments'">
                      <SlidersHorizontal class="w-4 h-4 mr-2" />
                      系统模型设置
                    </Button>
                  </div>

                  <Button
                    v-if="modelSettingsTab === 'assignments'"
                    @click="handleSaveAssignments"
                    :disabled="isSavingModelAssignments"
                  >
                    <Loader2 v-if="isSavingModelAssignments" class="w-4 h-4 mr-2 animate-spin" />
                    <Save v-else class="w-4 h-4 mr-2" />
                    保存系统模型设置
                  </Button>
                </div>

                <div v-if="isLoadingModels" class="flex justify-center items-center py-12">
                  <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
                </div>

                <template v-else-if="modelSettingsTab === 'providers'">
                  <div class="grid grid-cols-1 xl:grid-cols-[1.15fr_0.95fr] gap-6">
                    <div class="rounded-2xl border bg-card p-5 flex flex-col">
                      <div class="flex flex-col gap-4 pb-4 border-b">
                        <div class="flex items-center justify-between gap-3">
                          <div>
                            <h4 class="text-lg font-semibold">提供商列表</h4>
                            <p class="text-sm text-muted-foreground mt-1">后续继续增加模型供应商时，依旧可以通过搜索与能力筛选快速定位。</p>
                          </div>
                          <div class="text-xs text-muted-foreground whitespace-nowrap">
                            共 {{ filteredProviders.length }} / {{ modelProviders.length }} 家
                          </div>
                        </div>

                        <div class="grid gap-3 md:grid-cols-[1fr_auto]">
                          <div class="relative">
                            <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                            <Input v-model="providerSearch" class="pl-9" placeholder="搜索提供商、描述或标签" />
                          </div>
                          <select v-model="providerCapabilityFilter" class="rounded-md border bg-background px-3 py-2 text-sm">
                            <option v-for="capability in providerCapabilities" :key="capability" :value="capability">
                              {{ capability === 'all' ? '全部能力' : capability }}
                            </option>
                          </select>
                        </div>
                      </div>

                      <ScrollArea class="mt-4 max-h-[52vh] pr-2">
                        <div class="grid md:grid-cols-2 gap-4">
                          <button
                            v-for="provider in filteredProviders"
                            :key="provider.id"
                            class="text-left rounded-2xl border p-5 transition-all bg-card hover:border-primary/40"
                            :class="provider.id === selectedProviderId ? 'border-primary shadow-md bg-primary/5' : ''"
                            @click="selectedProviderId = provider.id"
                          >
                            <div class="flex items-center justify-between gap-3">
                              <div>
                                <div class="font-semibold text-base">{{ provider.name }}</div>
                                <div class="text-xs text-muted-foreground mt-1">{{ provider.badge }}</div>
                              </div>
                              <div class="h-2.5 w-2.5 rounded-full" :class="provider.is_configured ? 'bg-green-500' : 'bg-muted-foreground/40'"></div>
                            </div>
                            <p class="text-sm text-muted-foreground leading-relaxed mt-3">{{ provider.description }}</p>
                            <div class="flex flex-wrap gap-2 mt-4">
                              <span v-for="capability in provider.capabilities" :key="capability" class="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium">
                                {{ capability }}
                              </span>
                            </div>
                          </button>
                        </div>

                        <div v-if="filteredProviders.length === 0" class="rounded-2xl border border-dashed py-14 text-center text-sm text-muted-foreground">
                          当前筛选条件下没有匹配的模型提供商
                        </div>
                      </ScrollArea>
                    </div>

                    <div v-if="selectedProvider" class="rounded-2xl border bg-card p-6 space-y-5 h-fit sticky top-0">
                      <div class="space-y-2">
                        <div class="flex items-start justify-between gap-3">
                          <div>
                            <h4 class="text-lg font-semibold">{{ selectedProvider.name }}</h4>
                            <p class="text-sm text-muted-foreground mt-1">{{ selectedProvider.description }}</p>
                          </div>
                          <span class="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium">{{ selectedProvider.badge }}</span>
                        </div>
                        <div class="flex flex-wrap gap-2">
                          <span v-for="capability in selectedProvider.capabilities" :key="capability" class="rounded-full bg-primary/10 text-primary px-2.5 py-1 text-[11px] font-medium">
                            {{ capability }}
                          </span>
                        </div>
                      </div>

                      <div class="rounded-xl border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
                        推荐先完成供应商接入，再到“系统模型设置”里为不同任务分配模型。
                      </div>

                      <div v-for="field in selectedProvider.config_fields" :key="field.key" class="space-y-2">
                        <Label>{{ field.label }}</Label>
                        <Input
                          v-model="providerDraft[field.key]"
                          :type="field.secret ? 'password' : 'text'"
                          :placeholder="field.default || ''"
                        />
                        <p v-if="field.secret && selectedProvider.secret_preview" class="text-xs text-muted-foreground">
                          当前已保存: <code class="bg-muted px-1.5 py-0.5 rounded text-[10px]">{{ selectedProvider.secret_preview }}</code>
                        </p>
                      </div>

                      <Button class="w-full" @click="handleSaveModelProvider" :disabled="isSavingModelProvider">
                        <Loader2 v-if="isSavingModelProvider" class="w-4 h-4 mr-2 animate-spin" />
                        <Save v-else class="w-4 h-4 mr-2" />
                        保存提供商配置
                      </Button>
                    </div>
                  </div>
                </template>

                <div v-else class="space-y-6">
                  <div class="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
                    <div class="rounded-2xl border bg-card p-5">
                      <div class="flex items-start gap-3">
                        <div class="rounded-xl bg-primary/10 p-2 text-primary">
                          <Sparkles class="w-5 h-5" />
                        </div>
                        <div>
                          <h4 class="font-semibold">当前工作流</h4>
                          <p class="text-sm text-muted-foreground mt-1">这些设置已经接入后端，修改后会直接影响标签提取、摘要生成与向量检索。</p>
                        </div>
                      </div>
                    </div>

                    <div class="rounded-2xl border bg-card p-5">
                      <div class="flex items-start gap-3">
                        <div class="rounded-xl bg-muted p-2 text-muted-foreground">
                          <GalleryVerticalEnd class="w-5 h-5" />
                        </div>
                        <div>
                          <h4 class="font-semibold">多模态占位</h4>
                          <p class="text-sm text-muted-foreground mt-1">先把未来的视频工作流入口预留好，后续接语音转文字、视觉理解和视频理解时不需要重做设置结构。</p>
                        </div>
                      </div>
                    </div>
                  </div>

                  <ScrollArea class="max-h-[52vh] pr-2">
                    <div class="space-y-6">
                      <div
                        v-for="section in groupedAssignments"
                        :key="section.group"
                        class="space-y-4"
                      >
                        <div class="flex items-center justify-between gap-3">
                          <div>
                            <h4 class="text-lg font-semibold">{{ section.group }}</h4>
                              <p class="text-sm text-muted-foreground mt-1">
                                {{ section.items.some((item) => item.status === 'active') ? '已落地并正在使用的模型用途。' : '未来多模态链路的预留模型用途。' }}
                              </p>
                          </div>
                          <span class="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium">
                            {{ section.items.length }} 项
                          </span>
                        </div>

                        <div
                          v-for="assignment in section.items"
                          :key="assignment.key"
                          class="rounded-2xl border bg-card p-5 space-y-4"
                        >
                          <div class="flex items-start justify-between gap-3">
                            <div>
                              <div class="font-semibold text-base">{{ assignment.label }}</div>
                              <p class="text-sm text-muted-foreground mt-1">{{ assignment.description }}</p>
                            </div>
                            <span
                              class="rounded-full px-2.5 py-1 text-[11px] font-medium"
                              :class="assignment.status === 'active' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'"
                            >
                              {{ assignment.status === 'active' ? '已接入' : '占位中' }}
                            </span>
                          </div>

                          <div class="grid md:grid-cols-2 gap-4">
                            <div class="space-y-2">
                              <Label>模型提供商</Label>
                              <select v-model="assignment.provider" class="w-full rounded-md border bg-background px-3 py-2 text-sm">
                                <option v-for="provider in modelProviders" :key="provider.id" :value="provider.id">
                                  {{ provider.name }}
                                </option>
                              </select>
                            </div>

                            <div class="space-y-2">
                              <Label>模型名称</Label>
                              <Input v-model="assignment.model" :placeholder="assignment.default_model" />
                            </div>
                          </div>

                          <p v-if="assignment.status === 'planned'" class="text-xs text-muted-foreground">
                            这个设置当前主要用于预留 UI 和配置结构，后续接入对应能力时会直接复用这里的值。
                          </p>
                        </div>
                      </div>
                    </div>
                  </ScrollArea>
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

              <div v-else-if="activeTab === 'tokens'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div class="flex items-center justify-between">
                  <div>
                    <h3 class="text-2xl font-bold tracking-tight">访问令牌</h3>
                    <p class="text-muted-foreground text-sm mt-1 text-balance">创建个人访问令牌 (PAT) 用于 MCP 服务等外部 AI Agent 接入。删除令牌将立即使其失效。</p>
                  </div>
                </div>

                <div class="rounded-xl border bg-card p-5 space-y-4">
                  <div class="flex items-center gap-2 mb-2">
                    <Shield class="w-4 h-4 text-primary" />
                    <h4 class="font-semibold">创建新令牌</h4>
                  </div>
                  <div class="grid gap-4 md:grid-cols-[1fr_auto_auto]">
                    <Input v-model="newPatAlias" placeholder="令牌别名，如 Claude Desktop" />
                    <select v-model="newPatExpiry" class="rounded-md border bg-background px-3 py-2 text-sm min-w-[140px]">
                      <option :value="null">永久有效</option>
                      <option :value="30">30 天</option>
                      <option :value="90">90 天</option>
                      <option :value="180">180 天</option>
                      <option :value="365">365 天</option>
                    </select>
                    <Button @click="handleCreatePat" :disabled="isCreatingPat">
                      <Loader2 v-if="isCreatingPat" class="w-4 h-4 mr-2 animate-spin" />
                      <Plus v-else class="w-4 h-4 mr-2" />
                      创建令牌
                    </Button>
                  </div>
                  <div class="grid gap-3 md:grid-cols-2">
                    <label
                      v-for="scope in availablePatScopes"
                      :key="scope.value"
                      class="flex items-start gap-3 rounded-lg border p-3 cursor-pointer hover:bg-muted/30 transition-colors"
                    >
                      <input
                        v-model="newPatScopes"
                        :value="scope.value"
                        type="checkbox"
                        class="mt-1"
                      />
                      <div>
                        <div class="font-medium text-sm">{{ scope.label }}</div>
                        <p class="text-xs text-muted-foreground mt-1">{{ scope.description }}</p>
                      </div>
                    </label>
                  </div>
                  <label
                    v-if="isAdmin"
                    class="flex items-start gap-3 rounded-lg border p-3 cursor-pointer hover:bg-muted/30 transition-colors"
                  >
                    <input v-model="newPatIsAdmin" type="checkbox" class="mt-1" />
                    <div>
                      <div class="font-medium text-sm">管理员令牌</div>
                      <p class="text-xs text-muted-foreground mt-1">令牌将以管理员身份访问系统，请仅用于受信任的本地 Agent 或服务。</p>
                    </div>
                  </label>
                </div>

                <div v-if="justCreatedToken" class="rounded-xl border-2 border-green-500/40 bg-green-500/5 p-5 space-y-3">
                  <div class="flex items-center gap-2">
                    <Shield class="w-4 h-4 text-green-500" />
                    <span class="font-semibold text-green-600 dark:text-green-400">令牌已生成 — 请立即复制！</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <code class="flex-1 bg-background rounded-lg px-3 py-2 text-xs font-mono break-all border">{{ justCreatedToken }}</code>
                    <Button size="sm" variant="outline" @click="copyText(justCreatedToken!, '令牌'); justCreatedToken = null">
                      <Copy class="w-4 h-4 mr-1" />
                      复制并关闭
                    </Button>
                  </div>
                </div>

                <div v-if="isLoadingPats" class="flex justify-center items-center py-12">
                  <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
                </div>

                <div v-else-if="pats.length === 0" class="flex flex-col items-center justify-center py-16 text-muted-foreground border rounded-xl border-dashed">
                  <Shield class="w-12 h-12 opacity-20 mb-4" />
                  <p class="text-sm">暂未创建任何访问令牌</p>
                </div>

                <div v-else class="border rounded-xl overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-muted/40">
                      <tr class="text-left">
                        <th class="px-4 py-3 font-medium">别名</th>
                        <th class="px-4 py-3 font-medium">权限</th>
                        <th class="px-4 py-3 font-medium">最近使用</th>
                        <th class="px-4 py-3 font-medium">有效期</th>
                        <th class="px-4 py-3 font-medium">创建时间</th>
                        <th class="px-4 py-3 font-medium">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="pat in pats" :key="pat.id" class="border-t">
                        <td class="px-4 py-3">
                          <div class="font-medium">{{ pat.alias }}</div>
                          <div v-if="pat.is_admin" class="text-xs text-amber-600 mt-1">管理员</div>
                        </td>
                        <td class="px-4 py-3 text-muted-foreground">{{ formatPatScopes(pat.scopes) }}</td>
                        <td class="px-4 py-3 text-muted-foreground">{{ formatPatLastUsed(pat.last_used_at) }}</td>
                        <td class="px-4 py-3 text-muted-foreground">{{ formatPatExpiry(pat.expires_at) }}</td>
                        <td class="px-4 py-3 text-muted-foreground">{{ new Date(pat.created_at).toLocaleDateString('zh-CN') }}</td>
                        <td class="px-4 py-3">
                          <div class="flex items-center gap-1">
                            <Button variant="ghost" size="sm" @click="copyText(pat.token, '令牌')">
                              <Copy class="w-4 h-4 mr-1" />
                              复制
                            </Button>
                            <Button variant="ghost" size="sm" class="text-destructive hover:text-destructive" @click="handleDeletePat(pat.id)">
                              <Trash2 class="w-4 h-4 mr-1" />
                              删除
                            </Button>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div v-else-if="activeTab === 'mcp'" class="animate-in fade-in slide-in-from-right-4 duration-300">
                <ScrollArea class="max-h-[calc(90vh-10rem)] pr-4">
                  <div class="space-y-8">
                    <div>
                      <h3 class="text-2xl font-bold tracking-tight">MCP 服务</h3>
                      <p class="text-muted-foreground text-sm mt-1 text-balance">启用 MCP (Model Context Protocol) 后，外部 AI Client（如 Claude Desktop）可直接搜索和操作你的 Iris Hub 数据。</p>
                    </div>

                    <div class="rounded-xl border bg-card p-5 space-y-4">
                      <div class="flex items-center gap-2">
                        <Server class="w-4 h-4 text-primary" />
                        <h4 class="font-semibold">连接方式</h4>
                      </div>
                      <div class="grid gap-4 md:grid-cols-2">
                        <div class="rounded-lg border p-4 space-y-3">
                          <div>
                            <div class="text-sm font-semibold">推荐：Streamable HTTP</div>
                            <p class="text-xs text-muted-foreground mt-1">适合新一代 Agent 平台、云端网关与支持新版 MCP 单端点协议的客户端。</p>
                          </div>
                          <div class="rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs break-all">{{ mcpStreamableEndpoint }}</div>
                          <Button size="sm" variant="outline" @click="copyText(mcpStreamableEndpoint, 'Streamable HTTP Endpoint')">
                            <Copy class="w-4 h-4 mr-2" />
                            复制 Endpoint
                          </Button>
                        </div>

                        <div class="rounded-lg border p-4 space-y-3">
                          <div>
                            <div class="text-sm font-semibold">兼容：Legacy SSE</div>
                            <p class="text-xs text-muted-foreground mt-1">适合仍使用旧版 MCP SSE 协议的客户端，通常还会配合下方 JSON 配置一起使用。</p>
                          </div>
                          <div class="rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs break-all">{{ mcpLegacySseEndpoint }}</div>
                          <Button size="sm" variant="outline" @click="copyText(mcpLegacySseEndpoint, 'Legacy SSE Endpoint')">
                            <Copy class="w-4 h-4 mr-2" />
                            复制 Endpoint
                          </Button>
                        </div>
                      </div>
                      <div class="rounded-lg border border-dashed bg-muted/20 p-4 text-xs text-muted-foreground leading-6">
                        所有 MCP 请求都需要在请求头中携带 <span class="font-mono text-foreground">Authorization: Bearer pekno_pat_xxx</span>。
                        如果你的客户端支持新版协议，优先使用 Streamable HTTP；只有在客户端明确要求 SSE 时，再使用 Legacy SSE。
                      </div>
                    </div>

                    <div class="rounded-xl border bg-card p-5 space-y-4">
                      <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2">
                          <Shield class="w-4 h-4 text-primary" />
                          <h4 class="font-semibold">Personal access token</h4>
                        </div>
                        <Button v-if="pats.length === 0" size="sm" @click="activeTab = 'tokens'">
                          <Plus class="w-4 h-4 mr-2" />
                          创建令牌
                        </Button>
                      </div>
                      <p class="text-sm text-muted-foreground">此访问令牌用于 MCP 服务的身份验证，请妥善保管。删除令牌将立即使连接失效。</p>
                      <div v-if="pats.length > 0">
                        <select v-model="selectedMcpToken" class="w-full rounded-md border bg-background px-3 py-2 text-sm">
                          <option v-for="pat in pats" :key="pat.id" :value="pat.token">{{ pat.alias }} ({{ formatPatExpiry(pat.expires_at) }})</option>
                        </select>
                      </div>
                      <div v-else class="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
                        未发现可用的访问令牌，请先创建一个。
                      </div>
                    </div>

                    <div class="rounded-xl border bg-card p-5 space-y-4">
                      <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2">
                          <Server class="w-4 h-4 text-primary" />
                          <h4 class="font-semibold">Legacy SSE JSON 配置</h4>
                        </div>
                        <Button size="sm" variant="outline" @click="copyText(mcpJsonConfig, 'MCP 配置')">
                          <Copy class="w-4 h-4 mr-2" />
                          Copy JSON
                        </Button>
                      </div>
                      <p class="text-xs text-muted-foreground">如果你的 MCP 客户端要求粘贴旧版 SSE 风格的 JSON 配置，可直接复制下面这一段。</p>
                      <pre class="bg-muted/50 rounded-lg p-4 text-xs font-mono overflow-x-auto border"><code>{{ mcpJsonConfig }}</code></pre>
                    </div>

                    <div class="rounded-xl border bg-card p-5 space-y-4">
                      <div class="flex items-center gap-2">
                        <BrainCircuit class="w-4 h-4 text-primary" />
                        <h4 class="font-semibold">Support Tools</h4>
                      </div>
                      <div class="grid gap-3">
                        <div class="rounded-lg border p-4">
                          <div class="font-semibold text-sm">get_recent_items</div>
                          <p class="text-xs text-muted-foreground mt-1">获取最近指定小时数内的信息流条目；支持按信息源类型（如 bilibili, github）过滤。</p>
                        </div>
                        <div class="rounded-lg border p-4">
                          <div class="font-semibold text-sm">add_to_watch_later</div>
                          <p class="text-xs text-muted-foreground mt-1">将指定条目加入"稍后再看"收藏列表，相当于在前端点击星标。</p>
                        </div>
                        <div class="rounded-lg border p-4">
                          <div class="font-semibold text-sm">fetch_item_content</div>
                          <p class="text-xs text-muted-foreground mt-1">获取指定条目的完整内容或服务器缓存的 AI 摘要，支持按文章/视频类型智能返回不同格式。</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </ScrollArea>
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
