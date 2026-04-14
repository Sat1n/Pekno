<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Blocks, User, ChevronRight, Database, Trash2, Loader2, HardDrive, Puzzle, Plus, MailPlus, LogOut, KeyRound, Copy, BrainCircuit, SlidersHorizontal, Cpu, Save, Search, Sparkles, GalleryVerticalEnd, Shield, Server } from 'lucide-vue-next'
import { usePluginStore } from '@/store/usePluginStore'
import { changePassword, clearStoredToken, createInvitationCode, getDataSources, getInvitationCodes, getModelProviders, getStoredAuthUser, clearDataSource, saveModelAssignments, saveModelProvider, getPATs, createPAT, deletePAT, getSystemBillingSettings, saveSystemBillingSettings, resolveApiErrorMessage, type DataSourceStat, type InvitationCodeInfo, type ModelAssignmentInfo, type ModelProviderInfo, type PATItem, type SystemBillingSettings } from '@/lib/api'
import { useToast } from '@/components/ui/toast/use-toast'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import PluginInstallDialog from './PluginInstallDialog.vue'

const props = defineProps<{ open: boolean; initialTab?: string }>()
defineEmits(['close', 'open-plugin-settings'])

const router = useRouter()
const { t, locale } = useI18n()
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
const billingSettings = ref<SystemBillingSettings | null>(null)
const billingDraft = ref<Pick<SystemBillingSettings, 'api_limit_type' | 'api_limit_value' | 'currency'>>({
  api_limit_type: 'token',
  api_limit_value: 0,
  currency: 'USD',
})
const isLoadingBilling = ref(false)
const isSavingBilling = ref(false)

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

const availablePatScopes = computed(() => [
  {
    value: 'read:knowledge',
    label: t('settings.patScopeReadKnowledge'),
    description: t('settings.patScopeReadKnowledgeDesc'),
  },
  {
    value: 'write:star',
    label: t('settings.patScopeWriteStar'),
    description: t('settings.patScopeWriteStarDesc'),
  },
  {
    value: 'write:system_config',
    label: t('settings.patScopeWriteSystemConfig'),
    description: t('settings.patScopeWriteSystemConfigDesc'),
  },
])

const isClearDialogOpen = ref(false)
const sourceToClear = ref('')

const sourceNames = computed<Record<string, string>>(() => ({
  github_star: t('settings.dataSourceGithubStars'),
  bilibili: t('settings.dataSourceBilibili'),
  article: t('settings.dataSourceLocalArticle'),
}))

const menuItems = computed(() => {
  if (isAdmin.value) {
    return [
      { id: 'plugins', label: t('settings.plugins'), icon: Blocks },
      { id: 'models', label: t('settings.models'), icon: BrainCircuit },
      { id: 'billing', label: t('settings.billing'), icon: Server },
      { id: 'data', label: t('settings.data'), icon: Database },
      { id: 'invites', label: t('settings.invites'), icon: MailPlus },
      { id: 'tokens', label: t('settings.tokens'), icon: Shield },
      { id: 'mcp', label: t('settings.mcp'), icon: Server },
      { id: 'account', label: t('settings.account'), icon: User },
    ]
  }

  return [
    { id: 'plugins', label: t('settings.plugins'), icon: Blocks },
    { id: 'tokens', label: t('settings.tokens'), icon: Shield },
    { id: 'mcp', label: t('settings.mcp'), icon: Server },
    { id: 'account', label: t('settings.account'), icon: User },
  ]
})

async function loadDataSources() {
  isLoadingData.value = true
  try {
    dataSources.value = await getDataSources()
  } catch (error) {
    console.error('Failed to load data sources:', error)
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
    console.error('Failed to load invitations:', error)
    toast({
      title: t('settings.loadFailedTitle'),
      description: t('settings.invitesLoadFailed'),
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
    console.error('Failed to load model settings:', error)
    toast({
      title: t('settings.loadFailedTitle'),
      description: t('settings.modelsLoadFailed'),
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
      title: t('settings.inviteGeneratedTitle'),
      description: t('settings.inviteGeneratedDesc', { code: invitation.code }),
    })
  } catch (error) {
    toast({
      title: t('settings.createFailedTitle'),
      description: t('settings.tryAgainLater'),
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
      title: t('settings.inviteCopiedTitle'),
      description: code,
    })
  } catch {
    toast({
      title: t('settings.copyFailedTitle'),
      description: t('settings.copyInviteManuallyDesc'),
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
      title: t('settings.providerSavedTitle'),
      description: selectedProvider.value.name,
    })
  } catch (error: any) {
    toast({
      title: t('settings.saveFailedTitle'),
      description: resolveApiErrorMessage(error, 'settings.providerSaveFailed'),
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
      title: t('settings.assignmentsSavedTitle'),
      description: t('settings.assignmentsSavedDesc'),
    })
  } catch (error: any) {
    toast({
      title: t('settings.saveFailedTitle'),
      description: resolveApiErrorMessage(error, 'settings.assignmentsSaveFailed'),
      variant: 'destructive',
    })
  } finally {
    isSavingModelAssignments.value = false
  }
}

async function loadBillingSettings() {
  if (!isAdmin.value) return
  isLoadingBilling.value = true
  try {
    const settings = await getSystemBillingSettings()
    billingSettings.value = settings
    billingDraft.value = {
      api_limit_type: settings.api_limit_type,
      api_limit_value: settings.api_limit_value,
      currency: settings.currency,
    }
  } catch (error) {
    console.error('Failed to load billing settings:', error)
    toast({
      title: t('settings.loadFailedTitle'),
      description: t('settings.billingLoadFailed'),
      variant: 'destructive',
    })
  } finally {
    isLoadingBilling.value = false
  }
}

async function handleSaveBillingSettings() {
  isSavingBilling.value = true
  try {
    const settings = await saveSystemBillingSettings({
      ...billingDraft.value,
      api_limit_value: Number(billingDraft.value.api_limit_value) || 0,
    })
    billingSettings.value = settings
    billingDraft.value = {
      api_limit_type: settings.api_limit_type,
      api_limit_value: settings.api_limit_value,
      currency: settings.currency,
    }
    toast({
      title: t('settings.billingSavedTitle'),
      description: settings.api_limit_value > 0 ? t('settings.billingSavedEnabled') : t('settings.billingSavedDisabled'),
    })
  } catch (error: any) {
    toast({
      title: t('settings.saveFailedTitle'),
      description: resolveApiErrorMessage(error, 'settings.billingSaveFailed'),
      variant: 'destructive',
    })
  } finally {
    isSavingBilling.value = false
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
      title: t('settings.dataClearedTitle'),
      description: res.message || t('settings.dataClearedDesc', { count: res.deleted_count }),
    })
    await loadDataSources()
  } catch (error) {
    toast({
      title: t('settings.clearFailedTitle'),
      description: t('settings.tryAgainLater'),
      variant: 'destructive',
    })
  } finally {
    isClearingData.value[sourceType] = false
  }
}

async function handleChangePassword() {
  if (!currentPassword.value || !newPassword.value) {
    toast({
      title: t('settings.formIncompleteTitle'),
      description: t('settings.passwordFormIncompleteDesc'),
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
      title: t('settings.passwordUpdatedTitle'),
      description: response.message,
    })
  } catch (error: any) {
    toast({
      title: t('settings.updateFailedTitle'),
      description: resolveApiErrorMessage(error, 'settings.tryAgainLater'),
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
  if (newTab === 'billing') {
    void loadBillingSettings()
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
    console.error('Failed to load access tokens:', error)
  } finally {
    isLoadingPats.value = false
  }
}

async function handleCreatePat() {
  if (!newPatAlias.value.trim()) {
    toast({ title: t('settings.enterTokenAliasTitle'), variant: 'destructive' })
    return
  }
  if (newPatScopes.value.length === 0) {
    toast({ title: t('settings.selectAtLeastOneScopeTitle'), variant: 'destructive' })
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
    toast({ title: t('settings.tokenCreatedTitle'), description: t('settings.tokenCreatedDesc') })
  } catch (error: any) {
    toast({ title: t('settings.createFailedTitle'), description: resolveApiErrorMessage(error, 'settings.tryAgainLater'), variant: 'destructive' })
  } finally {
    isCreatingPat.value = false
  }
}

async function handleDeletePat(id: string) {
  try {
    await deletePAT(id)
    pats.value = pats.value.filter(p => p.id !== id)
    toast({ title: t('settings.tokenDeletedTitle') })
  } catch {
    toast({ title: t('settings.deleteFailedTitle'), variant: 'destructive' })
  }
}

async function copyText(text: string, label: string = '') {
  try {
    await navigator.clipboard.writeText(text)
    toast({ title: t('settings.copiedToClipboardTitle', { label: label || t('settings.contentLabel') }) })
  } catch {
    toast({ title: t('settings.copyFailedTitle'), variant: 'destructive' })
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
  if (!expiresAt) return t('settings.neverExpires')
  const d = new Date(expiresAt)
  return `${d.toLocaleDateString(locale.value, { year: 'numeric', month: '2-digit', day: '2-digit' })} ${t('settings.expiresSuffix')}`
}

function formatPatLastUsed(lastUsedAt: string | null): string {
  if (!lastUsedAt) return t('settings.neverUsed')
  const d = new Date(lastUsedAt)
  return d.toLocaleString(locale.value, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatPatScopes(scopes: string[]): string {
  if (!scopes || scopes.length === 0) return t('settings.noScopes')
  const labels: Record<string, string> = {
    'read:knowledge': t('settings.patScopeReadKnowledge'),
    'write:star': t('settings.patScopeWriteStar'),
    'write:system_config': t('settings.patScopeWriteSystemConfig'),
  }
  return scopes.map((scope) => labels[scope] || scope).join(' / ')
}

function formatBillingCost(value: number | undefined, currency: string | undefined): string {
  return `${currency || 'USD'} ${(value || 0).toFixed(4)}`
}
</script>

<template>
  <Dialog :open="open" @update:open="$emit('close')">
    <DialogContent class="w-[90vw] max-w-6xl h-[90vh] p-0 gap-0 overflow-hidden flex flex-col bg-background border-none shadow-2xl">
      <div class="flex flex-1 overflow-hidden min-h-0">
        <div class="w-60 border-r bg-muted/20 p-4 flex flex-col gap-1 shrink-0">
          <div class="px-2 py-6 flex items-center gap-2 mb-2">
            <div class="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-bold italic">I</div>
            <span class="font-bold tracking-tight text-lg">{{ t('settings.title') }}</span>
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
                    <h3 class="text-2xl font-bold tracking-tight">{{ t('settings.pluginsHeading') }}</h3>
                    <p class="text-muted-foreground text-sm mt-1 text-balance">{{ t('settings.pluginsDesc') }}</p>
                  </div>
                  <Button v-if="isAdmin" size="sm" variant="outline" @click="isInstallDialogOpen = true">
                    <Plus class="w-4 h-4 mr-2" />
                    {{ t('settings.installPlugin') }}
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
                    <h3 class="text-2xl font-bold tracking-tight">{{ t('settings.modelsHeading') }}</h3>
                    <p class="text-muted-foreground text-sm mt-1 text-balance">{{ t('settings.modelsDesc') }}</p>
                  </div>
                </div>

                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="flex flex-wrap items-center gap-2">
                    <Button :variant="modelSettingsTab === 'providers' ? 'default' : 'outline'" @click="modelSettingsTab = 'providers'">
                      <Cpu class="w-4 h-4 mr-2" />
                      {{ t('settings.modelProviders') }}
                    </Button>
                    <Button :variant="modelSettingsTab === 'assignments' ? 'default' : 'outline'" @click="modelSettingsTab = 'assignments'">
                      <SlidersHorizontal class="w-4 h-4 mr-2" />
                      {{ t('settings.systemModelSettings') }}
                    </Button>
                  </div>

                  <Button
                    v-if="modelSettingsTab === 'assignments'"
                    @click="handleSaveAssignments"
                    :disabled="isSavingModelAssignments"
                  >
                    <Loader2 v-if="isSavingModelAssignments" class="w-4 h-4 mr-2 animate-spin" />
                    <Save v-else class="w-4 h-4 mr-2" />
                    {{ t('settings.saveSystemModelSettings') }}
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
                            <h4 class="text-lg font-semibold">{{ t('settings.providerList') }}</h4>
                            <p class="text-sm text-muted-foreground mt-1">{{ t('settings.providerListDesc') }}</p>
                          </div>
                          <div class="text-xs text-muted-foreground whitespace-nowrap">
                            {{ t('settings.providerCount', { filtered: filteredProviders.length, total: modelProviders.length }) }}
                          </div>
                        </div>

                        <div class="grid gap-3 md:grid-cols-[1fr_auto]">
                          <div class="relative">
                            <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                            <Input v-model="providerSearch" class="pl-9" :placeholder="t('settings.searchProvidersPlaceholder')" />
                          </div>
                          <select v-model="providerCapabilityFilter" class="rounded-md border bg-background px-3 py-2 text-sm">
                            <option v-for="capability in providerCapabilities" :key="capability" :value="capability">
                              {{ capability === 'all' ? t('settings.allCapabilities') : capability }}
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
                                <div class="font-semibold text-base">
                                  {{ t('settings.modelProviderMetadata.' + provider.id + '.name', provider.name) }}
                                </div>
                                <div class="text-xs text-muted-foreground mt-1">
                                  {{ t('settings.modelProviderMetadata.' + provider.id + '.badge', provider.badge || '') }}
                                </div>
                              </div>
                              <div class="h-2.5 w-2.5 rounded-full" :class="provider.is_configured ? 'bg-green-500' : 'bg-muted-foreground/40'"></div>
                            </div>
                            <p class="text-sm text-muted-foreground leading-relaxed mt-3">
                              {{ t('settings.modelProviderMetadata.' + provider.id + '.description', provider.description) }}
                            </p>
                            <div class="flex flex-wrap gap-2 mt-4">
                              <span v-for="capability in provider.capabilities" :key="capability" class="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium">
                                {{ capability }}
                              </span>
                            </div>
                          </button>
                        </div>

                        <div v-if="filteredProviders.length === 0" class="rounded-2xl border border-dashed py-14 text-center text-sm text-muted-foreground">
                          {{ t('settings.noMatchingProviders') }}
                        </div>
                      </ScrollArea>
                    </div>

                    <div v-if="selectedProvider" class="rounded-2xl border bg-card p-6 space-y-5 h-fit sticky top-0">
                      <div class="space-y-2">
                        <div class="flex items-start justify-between gap-3">
                          <div>
                            <h4 class="text-lg font-semibold">
                              {{ t('settings.modelProviderMetadata.' + selectedProvider.id + '.name', selectedProvider.name) }}
                            </h4>
                            <p class="text-sm text-muted-foreground mt-1">
                              {{ t('settings.modelProviderMetadata.' + selectedProvider.id + '.description', selectedProvider.description) }}
                            </p>
                          </div>
                          <span class="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium">
                            {{ t('settings.modelProviderMetadata.' + selectedProvider.id + '.badge', selectedProvider.badge || '') }}
                          </span>
                        </div>
                        <div class="flex flex-wrap gap-2">
                          <span v-for="capability in selectedProvider.capabilities" :key="capability" class="rounded-full bg-primary/10 text-primary px-2.5 py-1 text-[11px] font-medium">
                            {{ capability }}
                          </span>
                        </div>
                      </div>

                        <div
                          v-if="selectedProvider.config_fields.length > 0"
                          class="rounded-xl border bg-muted/30 px-4 py-3 text-sm text-muted-foreground"
                        >
                          {{ t('settings.providerConfigHint') }}
                        </div>

                      <div v-for="field in selectedProvider.config_fields" :key="field.key" class="space-y-2">
                        <Label>{{ t('settings.modelConfigFields.' + field.key, field.label) }}</Label>
                        <Input
                          v-model="providerDraft[field.key]"
                          :type="field.secret ? 'password' : 'text'"
                          :placeholder="field.default || ''"
                        />
                        <p v-if="field.secret && selectedProvider.secret_preview" class="text-xs text-muted-foreground">
                          {{ t('settings.currentlySaved') }}: <code class="bg-muted px-1.5 py-0.5 rounded text-[10px]">{{ selectedProvider.secret_preview }}</code>
                        </p>
                      </div>

                      <Button
                        v-if="selectedProvider.config_fields.length > 0"
                        class="w-full"
                        @click="handleSaveModelProvider"
                        :disabled="isSavingModelProvider"
                      >
                        <Loader2 v-if="isSavingModelProvider" class="w-4 h-4 mr-2 animate-spin" />
                        <Save v-else class="w-4 h-4 mr-2" />
                        {{ t('settings.saveProviderConfig') }}
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
                          <h4 class="font-semibold">{{ t('settings.currentWorkflows') }}</h4>
                          <p class="text-sm text-muted-foreground mt-1">{{ t('settings.currentWorkflowsDesc') }}</p>
                        </div>
                      </div>
                    </div>

                    <div class="rounded-2xl border bg-card p-5">
                      <div class="flex items-start gap-3">
                        <div class="rounded-xl bg-muted p-2 text-muted-foreground">
                          <GalleryVerticalEnd class="w-5 h-5" />
                        </div>
                        <div>
                          <h4 class="font-semibold">{{ t('settings.multimodalPlaceholder') }}</h4>
                          <p class="text-sm text-muted-foreground mt-1">{{ t('settings.multimodalPlaceholderDesc') }}</p>
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
                            <h4 class="text-lg font-semibold">
                              {{ t('settings.assignmentGroup.' + section.group, section.group) }}
                            </h4>
                              <p class="text-sm text-muted-foreground mt-1">
                                {{ section.items.some((item) => item.status === 'active') ? t('settings.activeAssignmentGroupDesc') : t('settings.placeholderAssignmentGroupDesc') }}
                              </p>
                          </div>
                          <span class="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium">
                            {{ t('settings.assignmentCount', { count: section.items.length }) }}
                          </span>
                        </div>

                        <div
                          v-for="assignment in section.items"
                          :key="assignment.key"
                          class="rounded-2xl border bg-card p-5 space-y-4"
                        >
                          <div class="flex items-start justify-between gap-3">
                            <div>
                              <div class="font-semibold text-base">
                                {{ t('settings.systemModelMetadata.' + assignment.key + '.label', assignment.label) }}
                              </div>
                              <p class="text-sm text-muted-foreground mt-1">
                                {{ t('settings.systemModelMetadata.' + assignment.key + '.description', assignment.description) }}
                              </p>
                            </div>
                            <span
                              class="rounded-full px-2.5 py-1 text-[11px] font-medium"
                              :class="assignment.status === 'active' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'"
                            >
                              {{ assignment.status === 'active' ? t('settings.assignmentActive') : t('settings.assignmentPlaceholder') }}
                            </span>
                          </div>

                          <div class="grid md:grid-cols-2 gap-4">
                            <div class="space-y-2">
                              <Label>{{ t('settings.modelProviderLabel') }}</Label>
                              <select v-model="assignment.provider" class="w-full rounded-md border bg-background px-3 py-2 text-sm">
                                <option v-for="provider in modelProviders" :key="provider.id" :value="provider.id">
                                  {{ t('settings.modelProviderMetadata.' + provider.id + '.name', provider.name) }}
                                </option>
                              </select>
                            </div>

                            <div class="space-y-2">
                              <Label>{{ t('settings.modelNameLabel') }}</Label>
                              <Input v-model="assignment.model" :placeholder="assignment.default_model" />
                            </div>
                          </div>

                          <p v-if="assignment.status === 'planned'" class="text-xs text-muted-foreground">
                            {{ t('settings.assignmentHint') }}
                          </p>
                        </div>
                      </div>
                    </div>
                  </ScrollArea>
                </div>
              </div>

              <div v-else-if="activeTab === 'billing'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div class="flex items-center justify-between">
                  <div>
                    <h3 class="text-2xl font-bold tracking-tight">{{ t('settings.billingHeading') }}</h3>
                    <p class="text-muted-foreground text-sm mt-1 text-balance">{{ t('settings.billingDesc') }}</p>
                  </div>
                  <Button @click="handleSaveBillingSettings" :disabled="isSavingBilling || isLoadingBilling">
                    <Loader2 v-if="isSavingBilling" class="w-4 h-4 mr-2 animate-spin" />
                    <Save v-else class="w-4 h-4 mr-2" />
                    {{ t('settings.saveSettings') }}
                  </Button>
                </div>

                <div v-if="isLoadingBilling" class="flex justify-center items-center py-12">
                  <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
                </div>

                <div v-else class="space-y-6">
                  <div class="grid gap-4 md:grid-cols-3">
                    <div class="rounded-2xl border bg-card p-5">
                      <div class="text-xs text-muted-foreground">{{ t('settings.monthlyTokens') }}</div>
                      <div class="text-2xl font-bold mt-2">{{ billingSettings?.used_tokens?.toLocaleString() || '0' }}</div>
                    </div>
                    <div class="rounded-2xl border bg-card p-5">
                      <div class="text-xs text-muted-foreground">{{ t('settings.monthlyEstimatedCost') }}</div>
                      <div class="text-2xl font-bold mt-2">{{ formatBillingCost(billingSettings?.used_cost, billingSettings?.currency) }}</div>
                    </div>
                    <div class="rounded-2xl border bg-card p-5">
                      <div class="text-xs text-muted-foreground">{{ t('settings.limitStatus') }}</div>
                      <div class="text-2xl font-bold mt-2" :class="billingSettings?.limit_exceeded ? 'text-destructive' : 'text-green-600'">
                        {{ billingSettings?.limit_exceeded ? t('settings.limitExceeded') : t('settings.limitNormal') }}
                      </div>
                    </div>
                  </div>

                  <div class="rounded-2xl border bg-card p-6 space-y-6 max-w-2xl">
                    <div class="space-y-2">
                      <Label>{{ t('settings.limitType') }}</Label>
                      <div class="grid gap-3 sm:grid-cols-2">
                        <label class="rounded-xl border p-4 cursor-pointer hover:bg-muted/30 transition-colors" :class="billingDraft.api_limit_type === 'token' ? 'border-primary bg-primary/5' : ''">
                          <div class="flex items-center gap-3">
                            <input v-model="billingDraft.api_limit_type" type="radio" value="token" />
                            <div>
                              <div class="font-semibold text-sm">{{ t('settings.limitByTokens') }}</div>
                              <p class="text-xs text-muted-foreground mt-1">{{ t('settings.limitByTokensDesc') }}</p>
                            </div>
                          </div>
                        </label>
                        <label class="rounded-xl border p-4 cursor-pointer hover:bg-muted/30 transition-colors" :class="billingDraft.api_limit_type === 'cost' ? 'border-primary bg-primary/5' : ''">
                          <div class="flex items-center gap-3">
                            <input v-model="billingDraft.api_limit_type" type="radio" value="cost" />
                            <div>
                              <div class="font-semibold text-sm">{{ t('settings.limitByCost') }}</div>
                              <p class="text-xs text-muted-foreground mt-1">{{ t('settings.limitByCostDesc') }}</p>
                            </div>
                          </div>
                        </label>
                      </div>
                    </div>

                    <div class="grid gap-4 sm:grid-cols-2">
                      <div class="space-y-2">
                        <Label>{{ t('settings.limitValue') }}</Label>
                        <Input v-model.number="billingDraft.api_limit_value" type="number" min="0" step="1" />
                        <p class="text-xs text-muted-foreground">{{ t('settings.zeroDisablesLimit') }}</p>
                      </div>
                      <div class="space-y-2">
                        <Label>{{ t('settings.primaryCurrency') }}</Label>
                        <select v-model="billingDraft.currency" class="w-full rounded-md border bg-background px-3 py-2 text-sm">
                          <option value="USD">USD</option>
                          <option value="CNY">CNY</option>
                          <option value="EUR">EUR</option>
                        </select>
                      </div>
                    </div>

                    <div class="rounded-xl border border-dashed bg-muted/20 p-4 text-xs text-muted-foreground leading-6">
                      {{ t('settings.billingHint') }}
                    </div>
                  </div>
                </div>
              </div>

              <div v-else-if="activeTab === 'data'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div>
                  <h3 class="text-2xl font-bold tracking-tight">{{ t('settings.dataHeading') }}</h3>
                  <p class="text-muted-foreground text-sm mt-1 text-balance">{{ t('settings.dataDesc') }}</p>
                </div>

                <div v-if="isLoadingData" class="flex justify-center items-center py-12">
                  <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
                </div>

                <div v-else-if="dataSources.length === 0" class="flex flex-col items-center justify-center py-20 text-muted-foreground border rounded-xl border-dashed">
                  <HardDrive class="w-12 h-12 opacity-20 mb-4" />
                  <p class="text-sm">{{ t('settings.noCachedData') }}</p>
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
                          {{ t('settings.cachedRecordsCount', { count: source.count }) }}
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
                      <span>{{ t('settings.clearData') }}</span>
                    </Button>
                  </div>
                </div>
              </div>

              <div v-else-if="activeTab === 'invites'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div class="flex items-center justify-between">
                  <div>
                    <h3 class="text-2xl font-bold tracking-tight">{{ t('settings.invitesHeading') }}</h3>
                    <p class="text-muted-foreground text-sm mt-1 text-balance">{{ t('settings.invitesDesc') }}</p>
                  </div>
                  <Button @click="handleCreateInvitation" :disabled="isCreatingInvitation">
                    <Loader2 v-if="isCreatingInvitation" class="w-4 h-4 mr-2 animate-spin" />
                    <MailPlus v-else class="w-4 h-4 mr-2" />
                    {{ t('settings.generateInvite') }}
                  </Button>
                </div>

                <div class="border rounded-xl overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-muted/40">
                      <tr class="text-left">
                        <th class="px-4 py-3 font-medium">{{ t('settings.inviteCodeColumn') }}</th>
                        <th class="px-4 py-3 font-medium">{{ t('settings.statusColumn') }}</th>
                        <th class="px-4 py-3 font-medium">{{ t('settings.usedByColumn') }}</th>
                        <th class="px-4 py-3 font-medium">{{ t('settings.actionsColumn') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="isLoadingInvitations">
                        <td colspan="4" class="px-4 py-8 text-center text-muted-foreground">
                          <Loader2 class="w-5 h-5 animate-spin inline mr-2" />
                          {{ t('settings.loadingInvites') }}
                        </td>
                      </tr>
                      <tr v-else-if="invitations.length === 0">
                        <td colspan="4" class="px-4 py-8 text-center text-muted-foreground">{{ t('settings.noInvitesYet') }}</td>
                      </tr>
                      <tr v-for="invitation in invitations" :key="invitation.id" class="border-t">
                        <td class="px-4 py-3 font-mono">{{ invitation.code }}</td>
                        <td class="px-4 py-3">
                          <span :class="invitation.is_used ? 'text-muted-foreground' : 'text-green-600'" class="font-medium">
                            {{ invitation.is_used ? t('settings.usedStatus') : t('settings.unusedStatus') }}
                          </span>
                        </td>
                        <td class="px-4 py-3">{{ invitation.used_by_username || '-' }}</td>
                        <td class="px-4 py-3">
                          <Button variant="ghost" size="sm" @click="copyInviteCode(invitation.code)">
                            <Copy class="w-4 h-4 mr-1" />
                            {{ t('common.copy') }}
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
                    <h3 class="text-2xl font-bold tracking-tight">{{ t('settings.tokensHeading') }}</h3>
                    <p class="text-muted-foreground text-sm mt-1 text-balance">{{ t('settings.tokensDesc') }}</p>
                  </div>
                </div>

                <div class="rounded-xl border bg-card p-5 space-y-4">
                  <div class="flex items-center gap-2 mb-2">
                    <Shield class="w-4 h-4 text-primary" />
                    <h4 class="font-semibold">{{ t('settings.createNewToken') }}</h4>
                  </div>
                  <div class="grid gap-4 md:grid-cols-[1fr_auto_auto]">
                    <Input v-model="newPatAlias" :placeholder="t('settings.tokenAliasPlaceholder')" />
                    <select v-model="newPatExpiry" class="rounded-md border bg-background px-3 py-2 text-sm min-w-[140px]">
                      <option :value="null">{{ t('settings.neverExpires') }}</option>
                      <option :value="30">{{ t('settings.daysOption', { count: 30 }) }}</option>
                      <option :value="90">{{ t('settings.daysOption', { count: 90 }) }}</option>
                      <option :value="180">{{ t('settings.daysOption', { count: 180 }) }}</option>
                      <option :value="365">{{ t('settings.daysOption', { count: 365 }) }}</option>
                    </select>
                    <Button @click="handleCreatePat" :disabled="isCreatingPat">
                      <Loader2 v-if="isCreatingPat" class="w-4 h-4 mr-2 animate-spin" />
                      <Plus v-else class="w-4 h-4 mr-2" />
                      {{ t('settings.createToken') }}
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
                      <div class="font-medium text-sm">{{ t('settings.adminToken') }}</div>
                      <p class="text-xs text-muted-foreground mt-1">{{ t('settings.adminTokenDesc') }}</p>
                    </div>
                  </label>
                </div>

                <div v-if="justCreatedToken" class="rounded-xl border-2 border-green-500/40 bg-green-500/5 p-5 space-y-3">
                  <div class="flex items-center gap-2">
                    <Shield class="w-4 h-4 text-green-500" />
                    <span class="font-semibold text-green-600 dark:text-green-400">{{ t('settings.tokenGeneratedNowCopy') }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <code class="flex-1 bg-background rounded-lg px-3 py-2 text-xs font-mono break-all border">{{ justCreatedToken }}</code>
                    <Button size="sm" variant="outline" @click="copyText(justCreatedToken!, t('settings.tokenLabel')); justCreatedToken = null">
                      <Copy class="w-4 h-4 mr-1" />
                      {{ t('settings.copyAndClose') }}
                    </Button>
                  </div>
                </div>

                <div v-if="isLoadingPats" class="flex justify-center items-center py-12">
                  <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
                </div>

                <div v-else-if="pats.length === 0" class="flex flex-col items-center justify-center py-16 text-muted-foreground border rounded-xl border-dashed">
                  <Shield class="w-12 h-12 opacity-20 mb-4" />
                  <p class="text-sm">{{ t('settings.noTokensYet') }}</p>
                </div>

                <div v-else class="border rounded-xl overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-muted/40">
                      <tr class="text-left">
                        <th class="px-4 py-3 font-medium">{{ t('settings.aliasColumn') }}</th>
                        <th class="px-4 py-3 font-medium">{{ t('settings.permissionsColumn') }}</th>
                        <th class="px-4 py-3 font-medium">{{ t('settings.lastUsedColumn') }}</th>
                        <th class="px-4 py-3 font-medium">{{ t('settings.expiryColumn') }}</th>
                        <th class="px-4 py-3 font-medium">{{ t('settings.createdAtColumn') }}</th>
                        <th class="px-4 py-3 font-medium">{{ t('settings.actionsColumn') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="pat in pats" :key="pat.id" class="border-t">
                        <td class="px-4 py-3">
                          <div class="font-medium">{{ pat.alias }}</div>
                          <div v-if="pat.is_admin" class="text-xs text-amber-600 mt-1">{{ t('settings.adminRoleLabel') }}</div>
                        </td>
                        <td class="px-4 py-3 text-muted-foreground">{{ formatPatScopes(pat.scopes) }}</td>
                        <td class="px-4 py-3 text-muted-foreground">{{ formatPatLastUsed(pat.last_used_at) }}</td>
                        <td class="px-4 py-3 text-muted-foreground">{{ formatPatExpiry(pat.expires_at) }}</td>
                        <td class="px-4 py-3 text-muted-foreground">{{ new Date(pat.created_at).toLocaleDateString(locale) }}</td>
                        <td class="px-4 py-3">
                          <div class="flex items-center gap-1">
                            <Button variant="ghost" size="sm" @click="copyText(pat.token, t('settings.tokenLabel'))">
                              <Copy class="w-4 h-4 mr-1" />
                              {{ t('common.copy') }}
                            </Button>
                            <Button variant="ghost" size="sm" class="text-destructive hover:text-destructive" @click="handleDeletePat(pat.id)">
                              <Trash2 class="w-4 h-4 mr-1" />
                              {{ t('common.delete') }}
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
                      <h3 class="text-2xl font-bold tracking-tight">{{ t('settings.mcpHeading') }}</h3>
                      <p class="text-muted-foreground text-sm mt-1 text-balance">{{ t('settings.mcpDesc') }}</p>
                    </div>

                    <div class="rounded-xl border bg-card p-5 space-y-4">
                      <div class="flex items-center gap-2">
                        <Server class="w-4 h-4 text-primary" />
                        <h4 class="font-semibold">{{ t('settings.connectionMethods') }}</h4>
                      </div>
                      <div class="grid gap-4 md:grid-cols-2">
                        <div class="rounded-lg border p-4 space-y-3">
                          <div>
                            <div class="text-sm font-semibold">{{ t('settings.streamableHttpRecommended') }}</div>
                            <p class="text-xs text-muted-foreground mt-1">{{ t('settings.streamableHttpDesc') }}</p>
                          </div>
                          <div class="rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs break-all">{{ mcpStreamableEndpoint }}</div>
                          <Button size="sm" variant="outline" @click="copyText(mcpStreamableEndpoint, t('settings.streamableHttpEndpointLabel'))">
                            <Copy class="w-4 h-4 mr-2" />
                            {{ t('settings.copyEndpoint') }}
                          </Button>
                        </div>

                        <div class="rounded-lg border p-4 space-y-3">
                          <div>
                            <div class="text-sm font-semibold">{{ t('settings.legacySseCompatible') }}</div>
                            <p class="text-xs text-muted-foreground mt-1">{{ t('settings.legacySseDesc') }}</p>
                          </div>
                          <div class="rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs break-all">{{ mcpLegacySseEndpoint }}</div>
                          <Button size="sm" variant="outline" @click="copyText(mcpLegacySseEndpoint, t('settings.legacySseEndpointLabel'))">
                            <Copy class="w-4 h-4 mr-2" />
                            {{ t('settings.copyEndpoint') }}
                          </Button>
                        </div>
                      </div>
                      <div class="rounded-lg border border-dashed bg-muted/20 p-4 text-xs text-muted-foreground leading-6">
                        {{ t('settings.mcpAuthorizationHint') }}
                      </div>
                    </div>

                    <div class="rounded-xl border bg-card p-5 space-y-4">
                      <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2">
                          <Shield class="w-4 h-4 text-primary" />
                          <h4 class="font-semibold">{{ t('settings.personalAccessToken') }}</h4>
                        </div>
                        <Button v-if="pats.length === 0" size="sm" @click="activeTab = 'tokens'">
                          <Plus class="w-4 h-4 mr-2" />
                          {{ t('settings.createToken') }}
                        </Button>
                      </div>
                      <p class="text-sm text-muted-foreground">{{ t('settings.mcpTokenDesc') }}</p>
                      <div v-if="pats.length > 0">
                        <select v-model="selectedMcpToken" class="w-full rounded-md border bg-background px-3 py-2 text-sm">
                          <option v-for="pat in pats" :key="pat.id" :value="pat.token">{{ pat.alias }} ({{ formatPatExpiry(pat.expires_at) }})</option>
                        </select>
                      </div>
                      <div v-else class="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
                        {{ t('settings.noAvailableTokens') }}
                      </div>
                    </div>

                    <div class="rounded-xl border bg-card p-5 space-y-4">
                      <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2">
                          <Server class="w-4 h-4 text-primary" />
                          <h4 class="font-semibold">{{ t('settings.legacySseJsonConfig') }}</h4>
                        </div>
                        <Button size="sm" variant="outline" @click="copyText(mcpJsonConfig, t('settings.mcpConfigLabel'))">
                          <Copy class="w-4 h-4 mr-2" />
                          {{ t('settings.copyJson') }}
                        </Button>
                      </div>
                      <p class="text-xs text-muted-foreground">{{ t('settings.legacySseJsonConfigDesc') }}</p>
                      <pre class="bg-muted/50 rounded-lg p-4 text-xs font-mono overflow-x-auto border"><code>{{ mcpJsonConfig }}</code></pre>
                    </div>

                    <div class="rounded-xl border bg-card p-5 space-y-4">
                      <div class="flex items-center gap-2">
                        <BrainCircuit class="w-4 h-4 text-primary" />
                        <h4 class="font-semibold">{{ t('settings.supportTools') }}</h4>
                      </div>
                      <div class="grid gap-3">
                        <div class="rounded-lg border p-4">
                          <div class="font-semibold text-sm">get_recent_items</div>
                          <p class="text-xs text-muted-foreground mt-1">{{ t('settings.mcpToolGetRecentItemsDesc') }}</p>
                        </div>
                        <div class="rounded-lg border p-4">
                          <div class="font-semibold text-sm">add_to_watch_later</div>
                          <p class="text-xs text-muted-foreground mt-1">{{ t('settings.mcpToolAddWatchLaterDesc') }}</p>
                        </div>
                        <div class="rounded-lg border p-4">
                          <div class="font-semibold text-sm">fetch_item_content</div>
                          <p class="text-xs text-muted-foreground mt-1">{{ t('settings.mcpToolFetchItemContentDesc') }}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </ScrollArea>
              </div>

              <div v-else-if="activeTab === 'account'" class="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
                <div>
                  <h3 class="text-2xl font-bold tracking-tight">{{ t('settings.accountHeading') }}</h3>
                  <p class="text-muted-foreground text-sm mt-1 text-balance">{{ t('settings.accountDesc') }}</p>
                </div>

                <div class="rounded-xl border p-5 space-y-3 bg-card">
                  <div>
                    <div class="text-sm text-muted-foreground">{{ t('auth.username') }}</div>
                    <div class="text-lg font-semibold">{{ currentUser.username }}</div>
                  </div>
                  <div>
                    <div class="text-sm text-muted-foreground">{{ t('settings.roleLabel') }}</div>
                    <div class="text-base font-medium">{{ currentUser.role }}</div>
                  </div>
                </div>

                <div class="rounded-xl border p-5 space-y-4 bg-card max-w-xl">
                  <div class="flex items-center gap-2">
                    <KeyRound class="w-4 h-4 text-primary" />
                    <h4 class="font-semibold">{{ t('settings.changePassword') }}</h4>
                  </div>

                  <div class="space-y-2">
                    <Label>{{ t('settings.currentPassword') }}</Label>
                    <Input v-model="currentPassword" type="password" />
                  </div>

                  <div class="space-y-2">
                    <Label>{{ t('settings.newPassword') }}</Label>
                    <Input v-model="newPassword" type="password" />
                  </div>

                  <div class="flex gap-3">
                    <Button @click="handleChangePassword" :disabled="isChangingPassword">
                      <Loader2 v-if="isChangingPassword" class="w-4 h-4 mr-2 animate-spin" />
                      <KeyRound v-else class="w-4 h-4 mr-2" />
                      {{ t('settings.updatePassword') }}
                    </Button>
                    <Button variant="destructive" @click="logout">
                      <LogOut class="w-4 h-4 mr-2" />
                      {{ t('common.logout') }}
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
        <AlertDialogTitle>{{ t('settings.clearConfirmTitle') }}</AlertDialogTitle>
        <AlertDialogDescription>
          {{ t('settings.clearConfirmDesc', { source: sourceNames[sourceToClear] || sourceToClear }) }}
        </AlertDialogDescription>
      </AlertDialogHeader>
      <div class="flex gap-3 justify-end mt-2">
        <AlertDialogCancel>{{ t('common.cancel') }}</AlertDialogCancel>
        <AlertDialogAction class="bg-destructive hover:bg-destructive/90 text-destructive-foreground" @click="confirmClearData">
          {{ t('settings.confirmClear') }}
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
