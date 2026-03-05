<script setup lang="ts">
import { cn } from '@/lib/utils'
import { computed } from 'vue'

const props = defineProps({
  class: {
    type: String,
    default: '',
  },
})

const titleClass = computed(() => {
  return cn(
    'text-lg font-semibold leading-none tracking-tight',
    props.class
  )
})
</script>

<template>
  <h2 :class="titleClass">
    <slot />
  </h2>
</template>