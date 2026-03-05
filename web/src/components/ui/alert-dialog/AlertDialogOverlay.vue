<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { AlertDialogOverlay, type AlertDialogOverlayProps } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<AlertDialogOverlayProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <AlertDialogOverlay
    v-bind="delegatedProps"
    :class="cn(
      'fixed inset-0 z-[199] bg-black/80 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
      props.class,
    )"
  />
</template>