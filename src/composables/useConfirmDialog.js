import { ref } from 'vue'

const dialogs = ref([])
let dialogId = 0

export function useConfirmDialog() {
  const confirm = (options) => {
    return new Promise((resolve) => {
      const id = ++dialogId
      const dialog = {
        id,
        title: options.title || '确认',
        message: options.message || '确定要执行此操作吗？',
        confirmText: options.confirmText || '确定',
        cancelText: options.cancelText || '取消',
        type: options.type || 'warning',
        onConfirm: () => {
          resolve(true)
          removeDialog(id)
        },
        onCancel: () => {
          resolve(false)
          removeDialog(id)
        }
      }

      dialogs.value.push(dialog)
    })
  }

  const removeDialog = (id) => {
    const index = dialogs.value.findIndex(d => d.id === id)
    if (index !== -1) {
      dialogs.value.splice(index, 1)
    }
  }

  const alert = (options) => {
    return new Promise((resolve) => {
      const id = ++dialogId
      const dialog = {
        id,
        title: options.title || '提示',
        message: options.message || '',
        confirmText: options.confirmText || '确定',
        cancelText: null,
        type: options.type || 'info',
        onConfirm: () => {
          resolve(true)
          removeDialog(id)
        },
        onCancel: null
      }

      dialogs.value.push(dialog)
    })
  }

  /**
   * 带输入框的提示（替代原生 prompt）：
   * 确认时 resolve 输入值（空则 null），取消时 resolve(null)。
   */
  const prompt = (options = {}) => {
    return new Promise((resolve) => {
      const id = ++dialogId
      const dialog = {
        id,
        title: options.title || '请输入',
        message: options.message || '',
        confirmText: options.confirmText || '确定',
        cancelText: options.cancelText || '取消',
        type: options.type || 'info',
        input: true,
        inputValue: options.defaultValue != null ? String(options.defaultValue) : '',
        inputPlaceholder: options.placeholder || '',
        onConfirm: () => {
          const val = (dialog.inputValue || '').trim()
          resolve(val === '' ? null : val)
          removeDialog(id)
        },
        onCancel: () => {
          resolve(null)
          removeDialog(id)
        }
      }

      dialogs.value.push(dialog)
    })
  }

  return {
    dialogs,
    confirm,
    alert,
    prompt,
    removeDialog
  }
}
