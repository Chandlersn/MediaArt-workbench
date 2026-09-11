import { ref } from 'vue'

const toasts = ref([])
let toastId = 0

export function useToast() {
  const addToast = (options) => {
    const id = ++toastId
    const toast = {
      id,
      type: options.type || 'info',
      message: options.message || '',
      duration: options.duration || 3000
    }

    toasts.value.push(toast)

    if (toast.duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, toast.duration)
    }

    return id
  }

  const removeToast = (id) => {
    const index = toasts.value.findIndex(t => t.id === id)
    if (index !== -1) {
      toasts.value.splice(index, 1)
    }
  }

  const success = (message, duration) => addToast({ type: 'success', message, duration })
  const error = (message, duration) => addToast({ type: 'error', message, duration })
  const warning = (message, duration) => addToast({ type: 'warning', message, duration })
  const info = (message, duration) => addToast({ type: 'info', message, duration })

  return {
    toasts,
    addToast,
    removeToast,
    success,
    error,
    warning,
    info
  }
}
