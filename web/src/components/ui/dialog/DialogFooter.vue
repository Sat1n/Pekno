<script setup lang="ts">
import { cn } from '@/lib/utils'
import { computed } from 'vue'

const props = defineProps({
  class: {
    type: String,
    default: '',
  },
})

const footerClass = computed(() => {
  return cn(
    'flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2',
    props.class
  )
})
</script>

<template>
  <div :class="footerClass">
    <slot />
  </div>
</template>