import { ref } from 'vue'

const messages = ref([])
let messageId = 0

export function useMessage() {
  const showMessage = (options) => {
    const id = ++messageId
    const message = {
      id,
      type: options.type || 'info',
      message: options.message || '',
      duration: options.duration || 2000
    }

    messages.value.push(message)

    if (message.duration > 0) {
      setTimeout(() => {
        removeMessage(id)
      }, message.duration)
    }

    return id
  }

  const removeMessage = (id) => {
    const index = messages.value.findIndex(m => m.id === id)
    if (index !== -1) {
      messages.value.splice(index, 1)
    }
  }

  const success = (message, duration) => showMessage({ type: 'success', message, duration })
  const error = (message, duration) => showMessage({ type: 'error', message, duration })
  const warning = (message, duration) => showMessage({ type: 'warning', message, duration })
  const info = (message, duration) => showMessage({ type: 'info', message, duration })

  return {
    messages,
    showMessage,
    removeMessage,
    success,
    error,
    warning,
    info
  }
}
