<script setup lang="ts">
import { useToast } from './use-toast'
import Toast from './Toast.vue'

const { toasts } = useToast()
</script>

<template>
  <div class="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
    <Toast
      v-for="toast in toasts"
      :key="toast.id"
      :toast="toast"
      @close="toasts.splice(toasts.indexOf(toast), 1)"
    />
  </div>
</template>
