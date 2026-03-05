<script setup lang="ts">
import { cn } from '@/lib/utils'
import { computed, onMounted } from 'vue'

const props = defineProps({
  toast: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['close'])

const toastClass = computed(() => {
  return cn(
    'relative flex w-full items-center justify-between rounded-md border p-4 shadow-lg',
    props.toast.variant === 'destructive' ? 'bg-destructive text-destructive-foreground' : 'bg-background',
    'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom'
  )
})

onMounted(() => {
  if (props.toast.duration !== 0) {
    setTimeout(() => {
      emit('close')
    }, props.toast.duration || 3000)
  }
})
</script>

<template>
  <div :class="toastClass" data-state="open">
    <div class="flex items-center">
      <slot>
        <div v-if="toast.title" class="text-sm font-medium">
          {{ toast.title }}
        </div>
        <div v-if="toast.description" class="text-sm">
          {{ toast.description }}
        </div>
      </slot>
    </div>
    <button
      @click="emit('close')"
      class="ml-4 rounded-md p-1 text-muted-foreground hover:bg-muted"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
      </svg>
    </button>
  </div>
</template>