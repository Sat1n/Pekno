<script setup lang="ts">
import { ref, provide } from 'vue'
import { useToast as useToastComposable } from './use-toast'
import Toast from './Toast.vue'

const toasts = ref([])

const { addToast, removeToast } = useToastComposable(toasts)

provide('toast', {
  add: addToast,
  remove: removeToast,
})
</script>

<template>
  <div class="fixed inset-0 z-[100] flex items-end justify-center pointer-events-none">
    <div class="flex flex-col space-y-2 p-4">
      <Toast
        v-for="toast in toasts"
        :key="toast.id"
        :toast="toast"
        @close="removeToast(toast.id)"
        class="pointer-events-auto"
      />
    </div>
  </div>
</template>