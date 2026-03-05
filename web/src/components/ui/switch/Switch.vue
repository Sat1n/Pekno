<script setup lang="ts">
import { cn } from '@/lib/utils'
import { computed } from 'vue'

const props = defineProps({
  checked: {
    type: Boolean,
    default: false,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  class: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:checked', 'change'])

const handleChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  const checked = target.checked
  emit('update:checked', checked)
  emit('change', checked)
}

const switchClass = computed(() => {
  return cn(
    'peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-input',
    props.class
  )
})

const thumbClass = computed(() => {
  return cn(
    'pointer-events-none block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0'
  )
})
</script>

<template>
  <div :class="switchClass" :data-state="checked ? 'checked' : 'unchecked'">
    <input
      type="checkbox"
      :checked="checked"
      :disabled="disabled"
      @change="handleChange"
      class="peer sr-only"
    />
    <span :class="thumbClass"></span>
  </div>
</template>