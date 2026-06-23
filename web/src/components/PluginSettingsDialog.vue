<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Settings, Save, RefreshCw, Loader2, AlertCircle, Check, Trash2, ChevronsUpDown } from 'lucide-vue-next'

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { TagsInput, TagsInputInput, TagsInputItem, TagsInputItemDelete, TagsInputItemText } from '@/components/ui/tags-input'
import { Slider } from '@/components/ui/slider'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { useToast } from '@/components/ui/toast/use-toast'
import { getStoredAuthUser, getUserCredentials, resolveApiErrorMessage, uninstallPluginApi, saveCookie, type PluginCredentialState, type PluginSettingSchema, type UserCredentialItem } from '@/lib/api'
import { usePluginStore } from '@/store/usePluginStore'

const props = defineProps<{
  open: boolean
  pluginId: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { toast } = useToast()
const { t } = useI18n()
const pluginStore = usePluginStore()
const currentUser = computed(() => getStoredAuthUser())
const isAdmin = computed(() => ['admin', 'super_admin'].includes(currentUser.value.role || ''))

const isSaving = ref(false)
const isSyncing = ref(false)
const isUninstalling = ref(false)
const isUninstallDialogOpen = ref(false)
const formData = ref<Record<string, any>>({})
const userCredentials = ref<UserCredentialItem[]>([])
const applyGlobalCredentials = ref<Record<string, boolean>>({})
const globalCredentialInputs = ref<Record<string, string>>({})
const cookieInputs = ref<Record<string, string>>({})
const cookieSaving = ref<Record<string, boolean>>({})

const currentPlugin = computed(() => pluginStore.pluginsManifests.value.find((plugin) => plugin.manifest.id === props.pluginId))
const schema = computed<Record<string, PluginSettingSchema>>(() => currentPlugin.value?.manifest.settings_schema || {})
const visibleSchema = computed<Record<string, PluginSettingSchema>>(() => {
  const entries = Object.entries(schema.value).filter(([, fieldConfig]) => {
    if (isAdmin.value) return true
    return fieldConfig.scope !== 'system'
  })
  return Object.fromEntries(entries)
})
const requiredCredentials = computed(() => currentPlugin.value?.manifest.required_credentials || [])

function findUserCredential(platform: string) {
  return userCredentials.value.find((credential) => credential.platform === platform)
}

function resolveCredentialState(platform: string): PluginCredentialState | undefined {
  return currentPlugin.value?.credential_states?.find((state) => state.platform === platform)
}

function isCookieFilePlatform(platform: string): boolean {
  return resolveCredentialState(platform)?.credential_kind === 'cookie_file'
}

function credentialDotClass(platform: string) {
  const state = resolveCredentialState(platform)
  if (!state) return 'bg-slate-400'
  if (isCookieFilePlatform(platform)) {
    const hasFields = (state.cookie_fields?.length || 0) > 0
    if (state.status === 'applied' && hasFields) return 'bg-emerald-500'
    if (state.status === 'available' && hasFields) return 'bg-sky-500'
    return 'bg-slate-400'
  }
  const status = state.status
  if (status === 'applied') return 'bg-emerald-500'
  if (status === 'available') return 'bg-sky-500'
  return 'bg-slate-400'
}

function credentialStatusText(platform: string) {
  const state = resolveCredentialState(platform)
  if (isCookieFilePlatform(platform)) {
    if (!state?.has_global) return t('settings.cookieFields.noCookie')
    const count = state.cookie_fields?.length || 0
    if (count > 0) return t('settings.cookieFields.fieldsCount', { count })
    return t('settings.cookieFields.noCookie')
  }
  const status = state?.status
  if (status === 'applied') return t('settings.pluginCredentials.statusApplied')
  if (status === 'available') return t('settings.pluginCredentials.statusAvailable')
  return t('settings.pluginCredentials.statusMissing')
}

async function loadUserCredentials() {
  try {
    userCredentials.value = await getUserCredentials()
  } catch {
    userCredentials.value = []
  }
}

function initForm() {
  if (!currentPlugin.value) return
  const config = currentPlugin.value.config || {}

  formData.value = {}
  for (const key in visibleSchema.value) {
    const fieldConfig = visibleSchema.value[key]
    if (!fieldConfig) continue
    if (fieldConfig.secret) {
      formData.value[key] = ''
    } else {
      let defaultVal = config[key] ?? fieldConfig.default
      if (fieldConfig.type === 'array' && !defaultVal) {
        defaultVal = []
      }
      formData.value[key] = defaultVal
    }
  }

  applyGlobalCredentials.value = {}
  globalCredentialInputs.value = {}
  cookieInputs.value = {}
  cookieSaving.value = {}
  for (const platform of requiredCredentials.value) {
    applyGlobalCredentials.value[platform] = (currentPlugin.value.credential_bindings || []).includes(platform)
    globalCredentialInputs.value[platform] = ''
    cookieInputs.value[platform] = ''
    cookieSaving.value[platform] = false
  }
}

watch(() => props.open, async (newVal) => {
  if (newVal) {
    initForm()
    await loadUserCredentials()
  }
})

watch(() => props.pluginId, async () => {
  if (props.open) {
    initForm()
    await loadUserCredentials()
  }
})

function isRequired(field: PluginSettingSchema) {
  if (field.secret && currentPlugin.value?.has_token) {
    return false
  }
  return Boolean(field.required)
}

function applyExistingCredential(platform: string) {
  if (!findUserCredential(platform)) return
  applyGlobalCredentials.value[platform] = true
}

async function handleCookieSave(platform: string) {
  const value = (cookieInputs.value[platform] || '').trim()
  if (!value) {
    toast({
      title: t('settings.cookieFields.saveFailed'),
      description: t('settings.cookieFields.emptyInput'),
      variant: 'destructive',
    })
    return
  }

  cookieSaving.value[platform] = true
  try {
    await saveCookie(platform, value)
    await pluginStore.loadAllPlugins()
    await loadUserCredentials()
    cookieInputs.value[platform] = ''
    toast({
      title: t('settings.cookieFields.saveSuccess'),
      description: t('settings.cookieFields.saveSuccess'),
    })
  } catch (error: any) {
    toast({
      title: t('settings.cookieFields.saveFailed'),
      description: resolveApiErrorMessage(error),
      variant: 'destructive',
    })
  } finally {
    cookieSaving.value[platform] = false
  }
}

async function handleUninstall() {
  if (!currentPlugin.value) return

  isUninstalling.value = true
  try {
    await uninstallPluginApi(props.pluginId)
      toast({
        title: t('settings.pluginCredentials.uninstallSuccessTitle'),
        description: t('settings.pluginCredentials.uninstallSuccessDesc', { pluginName: currentPlugin.value.manifest.name }),
      })

      await pluginStore.loadAllPlugins()
      isUninstallDialogOpen.value = false
      emit('update:open', false)
    } catch (error: any) {
      toast({
        title: t('settings.pluginCredentials.uninstallFailedTitle'),
        description: resolveApiErrorMessage(error),
        variant: 'destructive',
      })
  } finally {
    isUninstalling.value = false
  }
}

async function handleSave() {
  if (!currentPlugin.value) return

  for (const key in visibleSchema.value) {
    const field = visibleSchema.value[key]
    if (!field) continue
    if (isRequired(field) && (formData.value[key] === undefined || formData.value[key] === null || formData.value[key] === '')) {
      toast({
        title: t('settings.pluginCredentials.validationFailedTitle'),
        description: t('settings.pluginCredentials.fieldRequired', { field: field.label || key }),
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
      const field = visibleSchema.value[key]
      if (!field) {
        savePayload[key] = val
        continue
      }
      if (field.secret && (val === '' || val === null || val === undefined)) {
        continue
      }
      savePayload[key] = val
    }

    const applyList = requiredCredentials.value.filter((platform) => {
      if (isCookieFilePlatform(platform)) return false
      return applyGlobalCredentials.value[platform]
    })
    const credentialPayload: Record<string, string> = {}
    for (const platform of requiredCredentials.value) {
      if (isCookieFilePlatform(platform)) continue
      const value = (globalCredentialInputs.value[platform] || '').trim()
      if (value) {
        credentialPayload[platform] = value
      }
    }
    if (applyList.length > 0) {
      savePayload.__apply_global_credentials = applyList
    }
    if (Object.keys(credentialPayload).length > 0) {
      savePayload.__global_credentials = credentialPayload
    }

    await pluginStore.savePluginConfig(props.pluginId, savePayload)
    await pluginStore.loadAllPlugins()
    await loadUserCredentials()
    initForm()

    toast({
      title: t('settings.pluginCredentials.saveSuccessTitle'),
      description: t('settings.pluginCredentials.saveSuccessDesc', { pluginName: currentPlugin.value.manifest.name }),
    })
  } catch (error: any) {
    toast({
      title: t('settings.pluginCredentials.saveFailedTitle'),
      description: resolveApiErrorMessage(error),
      variant: 'destructive',
    })
  } finally {
    isSaving.value = false
  }
}

async function handleSync() {
  if (!currentPlugin.value) return

  isSyncing.value = true
  try {
    await pluginStore.triggerPluginSync(props.pluginId)
    toast({
      title: t('settings.pluginCredentials.syncQueuedTitle'),
      description: t('settings.pluginCredentials.syncQueuedDesc', { pluginName: currentPlugin.value.manifest.name }),
    })
  } catch (error: any) {
    toast({
      title: t('settings.pluginCredentials.syncFailedTitle'),
      description: resolveApiErrorMessage(error),
      variant: 'destructive',
    })
  } finally {
    isSyncing.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="$emit('update:open', $event)">
    <DialogContent v-if="currentPlugin" class="sm:max-w-[560px] p-0 overflow-hidden bg-background border-none shadow-2xl">
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
                {{ currentPlugin.has_token ? t('settings.pluginCredentials.configured') : t('settings.pluginCredentials.notConfigured') }}
              </Badge>
            </DialogTitle>
            <DialogDescription>
              {{ currentPlugin.manifest.description || t('settings.pluginCredentials.defaultDescription') }}
            </DialogDescription>
          </div>
        </div>
      </DialogHeader>

      <Separator class="my-6" />

      <div class="px-6 space-y-6 max-h-[60vh] overflow-y-auto pb-6">
        <div
          v-for="platform in requiredCredentials"
          :key="`credential-${platform}`"
          class="space-y-3 rounded-lg border bg-card p-4"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <span class="inline-flex h-2.5 w-2.5 rounded-full" :class="credentialDotClass(platform)" />
                <Label class="text-base">{{ resolveCredentialState(platform)?.label || platform }}</Label>
              </div>
              <p class="text-xs text-muted-foreground">{{ credentialStatusText(platform) }}</p>
              <p v-if="!isCookieFilePlatform(platform) && findUserCredential(platform)" class="text-xs text-muted-foreground">
                {{ t('settings.pluginCredentials.currentGlobalCredential') }}
                <code class="bg-muted px-1.5 py-0.5 rounded text-[10px]">{{ findUserCredential(platform)?.masked_value }}</code>
              </p>
            </div>

            <Button
              v-if="!isCookieFilePlatform(platform) && resolveCredentialState(platform)?.status === 'available'"
              type="button"
              size="sm"
              variant="outline"
              @click="applyExistingCredential(platform)"
            >
              {{ t('settings.pluginCredentials.applyGlobalCredential') }}
            </Button>
          </div>

          <!-- Cookie input UI -->
          <div v-if="isCookieFilePlatform(platform)" class="space-y-3">
            <!-- Last updated time -->
            <div v-if="findUserCredential(platform)?.updated_at" class="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{{ t('settings.cookieFields.lastUpdated') }}:</span>
              <code class="bg-muted px-1.5 py-0.5 rounded text-[10px]">{{ new Date(findUserCredential(platform)!.updated_at).toLocaleString() }}</code>
            </div>

            <!-- Existing fields display -->
            <div v-if="resolveCredentialState(platform)?.cookie_fields?.length" class="space-y-2">
              <Label class="text-xs text-muted-foreground">{{ t('settings.cookieFields.storedFields') }}</Label>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="field in resolveCredentialState(platform)?.cookie_fields"
                  :key="field.name"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-mono bg-muted border"
                >
                  <span class="text-muted-foreground">{{ field.name }}=</span>
                  <span>{{ field.masked_value }}</span>
                </span>
              </div>
            </div>

            <!-- Paste area -->
            <div class="space-y-2">
              <Label class="text-xs text-muted-foreground">{{ t('settings.cookieFields.pasteHint') }}</Label>
              <Textarea
                v-model="cookieInputs[platform]"
                :placeholder="t('settings.cookieFields.placeholder')"
                :rows="3"
                class="text-xs font-mono"
              />
              <div class="flex justify-end">
                <Button
                  type="button"
                  size="sm"
                  :disabled="cookieSaving[platform] || !cookieInputs[platform]?.trim()"
                  @click="handleCookieSave(platform)"
                >
                  <Loader2 v-if="cookieSaving[platform]" class="w-4 h-4 mr-2 animate-spin" />
                  <Check v-else class="w-4 h-4 mr-2" />
                  {{ t('settings.cookieFields.saveCookie') }}
                </Button>
              </div>
            </div>
          </div>

          <!-- Token input UI (existing, for non-cookie platforms) -->
          <div v-else class="space-y-2">
            <Label>{{ t('settings.pluginCredentials.overrideGlobalCredential') }}</Label>
            <Input
              v-model="globalCredentialInputs[platform]"
              type="password"
              :placeholder="t('settings.pluginCredentials.enterNewCredential', { label: resolveCredentialState(platform)?.label || platform })"
            />
            <p class="text-xs text-muted-foreground">
              {{ t('settings.pluginCredentials.overrideHint') }}
            </p>
          </div>
        </div>

        <div v-for="(fieldConfig, fieldKey) in visibleSchema" :key="fieldKey" class="space-y-3">
          <div v-if="fieldConfig.type === 'boolean'" class="flex items-center justify-between p-4 rounded-lg border bg-card">
            <div class="space-y-0.5">
              <Label class="text-base">{{ fieldConfig.label || fieldKey }}</Label>
              <p v-if="fieldConfig.description" class="text-sm text-muted-foreground">{{ fieldConfig.description }}</p>
            </div>
            <Switch v-model="formData[fieldKey]" />
          </div>

          <div v-else-if="fieldConfig.type === 'string' && fieldConfig.secret" class="space-y-2">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <Input
              type="password"
              v-model="formData[fieldKey]"
              :placeholder="currentPlugin.has_token
                ? t('settings.pluginCredentials.secretAlreadySet')
                : t('settings.pluginCredentials.enterField', { field: fieldConfig.label || fieldKey })"
            />
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
            <p v-if="currentPlugin.token_preview" class="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <Check class="w-3 h-3 text-green-500" />
              {{ t('settings.pluginCredentials.currentValue') }}
              <code class="bg-muted px-1.5 py-0.5 rounded text-[10px]">{{ currentPlugin.token_preview }}</code>
            </p>
          </div>

          <div v-else-if="fieldConfig.type === 'string' && fieldConfig.format === 'textarea'" class="space-y-2">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <Textarea v-model="formData[fieldKey]" :rows="4" />
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>

          <div v-else-if="fieldConfig.type === 'string' && fieldConfig.format === 'radio' && fieldConfig.enum" class="space-y-3">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <RadioGroup v-model="formData[fieldKey]" class="flex flex-col space-y-1">
              <div v-for="option in fieldConfig.enum" :key="option" class="flex items-center space-x-2">
                <RadioGroupItem :value="option" :id="`${fieldKey}-${option}`" />
                <Label :for="`${fieldKey}-${option}`" class="font-normal cursor-pointer">{{ option }}</Label>
              </div>
            </RadioGroup>
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>

          <div v-else-if="fieldConfig.type === 'string' && fieldConfig.enum" class="space-y-2">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <Select v-model="formData[fieldKey]">
              <SelectTrigger>
                <SelectValue :placeholder="t('settings.pluginCredentials.selectPlaceholder')" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="option in fieldConfig.enum" :key="option" :value="option">
                  {{ option }}
                </SelectItem>
              </SelectContent>
            </Select>
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>

          <div v-else-if="fieldConfig.type === 'integer' && fieldConfig.format === 'slider'" class="space-y-4">
            <div class="flex justify-between items-center mb-2">
              <Label>{{ fieldConfig.label || fieldKey }}</Label>
              <span class="text-sm font-medium">{{ formData[fieldKey] }}</span>
            </div>
            <Slider
              :model-value="[formData[fieldKey]]"
              :min="fieldConfig.min || 0"
              :max="fieldConfig.max || 100"
              :step="1"
              @update:model-value="(val) => { formData[fieldKey] = val?.[0] ?? 0 }"
            />
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>

          <div v-else-if="fieldConfig.type === 'integer'" class="space-y-2">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <Input type="number" v-model.number="formData[fieldKey]" :min="fieldConfig.min" :max="fieldConfig.max" />
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>

          <div v-else-if="fieldConfig.type === 'array' && fieldConfig.format === 'multiselect' && fieldConfig.enum" class="space-y-2">
            <Label class="block">{{ fieldConfig.label || fieldKey }}</Label>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" class="w-full justify-between font-normal" role="combobox">
                  <span class="truncate">
                    {{ formData[fieldKey] && formData[fieldKey].length > 0 ? t('settings.pluginCredentials.selectedCount', { count: formData[fieldKey].length }) : t('settings.pluginCredentials.selectPlaceholder') }}
                  </span>
                  <ChevronsUpDown class="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent class="w-[300px] p-0" align="start">
                <Command>
                  <CommandInput :placeholder="t('settings.pluginCredentials.searchPlaceholder')" />
                  <CommandEmpty>{{ t('settings.pluginCredentials.noResults') }}</CommandEmpty>
                  <CommandList>
                    <CommandGroup>
                      <CommandItem
                        v-for="option in fieldConfig.enum"
                        :key="option"
                        :value="option"
                        @select="() => {
                          const arr = formData[fieldKey] || [];
                          const idx = arr.indexOf(option);
                          if (idx > -1) {
                            formData[fieldKey] = arr.filter((v: any) => v !== option);
                          } else {
                            formData[fieldKey] = [...arr, option];
                          }
                        }"
                      >
                        <div class="mr-2 flex h-4 w-4 items-center justify-center rounded-sm border border-primary" :class="[formData[fieldKey]?.includes(option) ? 'bg-primary text-primary-foreground' : 'opacity-50 [&_svg]:invisible']">
                          <Check class="h-4 w-4" />
                        </div>
                        {{ option }}
                      </CommandItem>
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>

          <div v-else-if="fieldConfig.type === 'array'" class="space-y-2">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <TagsInput v-model="formData[fieldKey]">
              <TagsInputItem v-for="item in formData[fieldKey]" :key="item" :value="item">
                <TagsInputItemText />
                <TagsInputItemDelete />
              </TagsInputItem>
              <TagsInputInput :placeholder="t('settings.pluginCredentials.addTag')" />
            </TagsInput>
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>

          <div v-else-if="fieldConfig.type === 'string' && !fieldConfig.secret" class="space-y-2">
            <Label>{{ fieldConfig.label || fieldKey }}</Label>
            <Input type="text" v-model="formData[fieldKey]" />
            <p v-if="fieldConfig.description" class="text-xs text-muted-foreground">{{ fieldConfig.description }}</p>
          </div>
        </div>
      </div>

      <div class="p-6 bg-muted/30 border-t flex justify-between items-center mt-auto">
        <div class="flex gap-2">
          <Button
            v-if="isAdmin && currentPlugin.manifest.id !== 'github_star'"
            variant="ghost"
            class="text-destructive hover:text-destructive hover:bg-destructive/10"
            @click="isUninstallDialogOpen = true"
          >
            <Trash2 class="w-4 h-4 mr-2" />
            {{ t('settings.pluginCredentials.uninstall') }}
          </Button>

          <Button variant="outline" @click="handleSync" :disabled="isSyncing || !currentPlugin.has_token">
            <Loader2 v-if="isSyncing" class="w-4 h-4 mr-2 animate-spin" />
            <RefreshCw v-else class="w-4 h-4 mr-2" />
            {{ t('settings.pluginCredentials.syncNow') }}
          </Button>
        </div>

        <div class="flex gap-2">
          <Button variant="ghost" @click="$emit('update:open', false)">{{ t('common.cancel') }}</Button>
          <Button @click="handleSave" :disabled="isSaving">
            <Loader2 v-if="isSaving" class="w-4 h-4 mr-2 animate-spin" />
            <Save v-else class="w-4 h-4 mr-2" />
            {{ t('settings.pluginCredentials.saveConfiguration') }}
          </Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>

  <AlertDialog :open="isUninstallDialogOpen" @update:open="isUninstallDialogOpen = $event">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ t('settings.pluginCredentials.uninstallConfirmTitle') }}</AlertDialogTitle>
        <AlertDialogDescription>
          {{ t('settings.pluginCredentials.uninstallConfirmDesc') }}
        </AlertDialogDescription>
      </AlertDialogHeader>
      <div class="flex gap-3 justify-end">
        <AlertDialogCancel>{{ t('common.cancel') }}</AlertDialogCancel>
        <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90" @click="handleUninstall">
          <Loader2 v-if="isUninstalling" class="w-4 h-4 mr-2 animate-spin" />
          {{ isUninstalling ? t('settings.pluginCredentials.uninstalling') : t('settings.pluginCredentials.confirmUninstall') }}
        </AlertDialogAction>
      </div>
    </AlertDialogContent>
  </AlertDialog>
</template>
