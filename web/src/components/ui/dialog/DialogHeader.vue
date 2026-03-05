<script setup lang="ts">
import { cn } from '@/lib/utils'
import { computed } from 'vue'

const props = defineProps({
  class: {
    type: String,
    default: '',
  },
})

const headerClass = computed(() => {
  return cn(
    'flex flex-col space-y-1.5 text-center sm:text-left',
    props.class
  )
})
</script>

<template>
  <div :class="headerClass">
    <slot />
  </div>
</template>