<script setup lang="ts">
import { cn } from '@/lib/utils'
import { computed } from 'vue'

const props = defineProps({
  class: {
    type: String,
    default: '',
  },
})

const descriptionClass = computed(() => {
  return cn(
    'text-sm text-muted-foreground',
    props.class
  )
})
</script>

<template>
  <p :class="descriptionClass">
    <slot />
  </p>
</template>