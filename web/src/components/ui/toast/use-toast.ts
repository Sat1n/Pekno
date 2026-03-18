import { ref, type Ref } from 'vue'

export type ToastVariant = 'default' | 'destructive'

export interface Toast {
  id: string
  title?: string
  description?: string
  variant?: ToastVariant
  duration?: number
}

const globalToasts = ref<Toast[]>([])

function createToastManager(toastsRef?: Ref<Toast[]>) {
  const toasts = toastsRef || globalToasts

  const addToast = (toast: Omit<Toast, 'id'>) => {
    const id = crypto.randomUUID()
    const newToast = {
      id,
      ...toast,
      duration: toast.duration || 3000,
    }
    toasts.value.push(newToast)

    // Auto remove after duration
    if (newToast.duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, newToast.duration)
    }

    return id
  }

  const removeToast = (id: string) => {
    toasts.value = toasts.value.filter((toast: Toast) => toast.id !== id)
  }

  return {
    toasts,
    addToast,
    removeToast,
    toast: addToast, // alias for addToast
  }
}

export function useToast() {
  return createToastManager(globalToasts)
}

export function createScopedToastManager(toastsRef: Ref<Toast[]>) {
  return createToastManager(toastsRef)
}
