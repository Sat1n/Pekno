<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { SlidersHorizontal, X } from 'lucide-vue-next'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const { t } = useI18n()

export interface FilterState {
  author: string
  intent: string
  is_read: boolean | undefined
  date_from: string
  date_to: string
}

const props = defineProps<{
  modelValue: FilterState
}>()

const emit = defineEmits<{
  'update:modelValue': [value: FilterState]
  'apply': []
}>()

const isOpen = ref(false)

const localFilter = ref<FilterState>({ ...props.modelValue })

watch(() => props.modelValue, (newVal) => {
  localFilter.value = { ...newVal }
}, { deep: true })

const intentOptions = [
  { value: 'video', label: 'Video' },
  { value: 'article', label: 'Article' },
  { value: 'image', label: 'Image' },
  { value: 'code', label: 'Code' },
  { value: 'social_post', label: 'Social Post' },
  { value: 'dynamic', label: 'Dynamic' },
]

const hasActiveFilters = computed(() => {
  return (
    localFilter.value.author ||
    localFilter.value.intent ||
    localFilter.value.is_read !== undefined ||
    localFilter.value.date_from ||
    localFilter.value.date_to
  )
})

const activeFilterCount = computed(() => {
  let count = 0
  if (localFilter.value.author) count++
  if (localFilter.value.intent) count++
  if (localFilter.value.is_read !== undefined) count++
  if (localFilter.value.date_from || localFilter.value.date_to) count++
  return count
})

function applyFilters() {
  emit('update:modelValue', { ...localFilter.value })
  emit('apply')
  isOpen.value = false
}

function clearFilters() {
  localFilter.value = {
    author: '',
    intent: '',
    is_read: undefined,
    date_from: '',
    date_to: '',
  }
  emit('update:modelValue', { ...localFilter.value })
  emit('apply')
}
</script>

<template>
  <div class="flex items-center gap-2">
    <Popover v-model:open="isOpen">
      <PopoverTrigger as-child>
        <Button variant="outline" size="sm" class="relative">
          <SlidersHorizontal class="h-4 w-4 mr-1" />
          {{ t('filter.title') }}
          <Badge
            v-if="activeFilterCount > 0"
            variant="secondary"
            class="ml-1 h-5 w-5 rounded-full p-0 flex items-center justify-center text-xs"
          >
            {{ activeFilterCount }}
          </Badge>
        </Button>
      </PopoverTrigger>
      <PopoverContent class="w-80" align="end">
        <div class="grid gap-4">
          <div class="space-y-2">
            <h4 class="font-medium leading-none">{{ t('filter.title') }}</h4>
            <p class="text-sm text-muted-foreground">
              {{ t('filter.description') }}
            </p>
          </div>

          <!-- Author -->
          <div class="grid gap-2">
            <Label for="filter-author">{{ t('filter.author') }}</Label>
            <Input
              id="filter-author"
              v-model="localFilter.author"
              :placeholder="t('filter.authorPlaceholder')"
            />
          </div>

          <!-- Intent -->
          <div class="grid gap-2">
            <Label>{{ t('filter.intent') }}</Label>
            <Select v-model="localFilter.intent">
              <SelectTrigger>
                <SelectValue :placeholder="t('filter.allIntents')" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">{{ t('filter.allIntents') }}</SelectItem>
                <SelectItem
                  v-for="option in intentOptions"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <!-- Read Status -->
          <div class="grid gap-2">
            <Label>{{ t('filter.readStatus') }}</Label>
            <select
              v-model="localFilter.is_read"
              class="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option :value="undefined">{{ t('filter.all') }}</option>
              <option :value="true">{{ t('filter.read') }}</option>
              <option :value="false">{{ t('filter.unread') }}</option>
            </select>
          </div>

          <!-- Date Range -->
          <div class="grid gap-2">
            <Label>{{ t('filter.dateRange') }}</Label>
            <div class="grid grid-cols-2 gap-2">
              <Input
                v-model="localFilter.date_from"
                type="date"
                :placeholder="t('filter.from')"
              />
              <Input
                v-model="localFilter.date_to"
                type="date"
                :placeholder="t('filter.to')"
              />
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center justify-end pt-2 gap-2">
            <Button
              variant="ghost"
              size="sm"
              :disabled="!hasActiveFilters"
              @click="clearFilters"
            >
              <X class="h-4 w-4 mr-1" />
              {{ t('filter.clear') }}
            </Button>
            <Button size="sm" @click="applyFilters">
              {{ t('filter.apply') }}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>
