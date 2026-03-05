import { ref } from 'vue'

export type ToastVariant = 'default' | 'destructive'

export interface Toast {
  id: string
  title?: string
  description?: string
  variant?: ToastVariant
  duration?: number
}

function createToastManager(toastsRef) {
  const toasts = toastsRef || ref([])

  const addToast = (toast: Omit<Toast, 'id'>) => {
    const id = crypto.randomUUID()
    const newToast = {
      id,
      ...toast,
      duration: toast.duration || 3000,
    }
    toasts.value.push(newToast)
    return id
  }

  const removeToast = (id: string) => {
    toasts.value = toasts.value.filter((toast) => toast.id !== id)
  }

  return {
    toasts,
    addToast,
    removeToast,
  }
}

export function useToast() {
  const toasts = ref([])
  return createToastManager(toasts)
}