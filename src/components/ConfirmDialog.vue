<template>
  <Teleport to="body">
    <div v-for="dialog in dialogs" :key="dialog.id" class="confirm-dialog-overlay" @click.self="dialog.onCancel && dialog.onCancel()">
      <div class="confirm-dialog" :class="`confirm-dialog-${dialog.type}`">
        <div class="confirm-dialog-header">
          <span class="confirm-dialog-icon">{{ getIcon(dialog.type) }}</span>
          <h3 class="confirm-dialog-title">{{ dialog.title }}</h3>
        </div>
        <div class="confirm-dialog-body">
          <p>{{ dialog.message }}</p>
        </div>
        <div class="confirm-dialog-footer">
          <button
            v-if="dialog.cancelText"
            class="btn-secondary"
            @click="dialog.onCancel"
          >
            {{ dialog.cancelText }}
          </button>
          <button
            class="btn-primary"
            :class="{ 'btn-danger': dialog.type === 'danger' || dialog.type === 'warning' }"
            @click="dialog.onConfirm"
          >
            {{ dialog.confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { useConfirmDialog } from '../composables/useConfirmDialog'

const { dialogs } = useConfirmDialog()

const getIcon = (type) => {
  const icons = {
    warning: '⚠️',
    danger: '❌',
    info: 'ℹ️',
    success: '✅'
  }
  return icons[type] || icons.info
}
</script>

<style scoped>
.confirm-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9998;
}

.confirm-dialog {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 400px;
  max-width: 90vw;
  overflow: hidden;
}

.confirm-dialog-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-light);
}

.confirm-dialog-icon {
  font-size: 24px;
}

.confirm-dialog-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.confirm-dialog-body {
  padding: 24px;
}

.confirm-dialog-body p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.confirm-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  background: var(--bg-secondary);
}

.btn-primary {
  padding: 10px 20px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary:hover {
  background: var(--accent-hover);
}

.btn-primary.btn-danger {
  background: var(--danger);
}

.btn-primary.btn-danger:hover {
  background: #dc2626;
}

.btn-secondary {
  padding: 10px 20px;
  background: var(--surface);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-secondary:hover {
  background: var(--bg-secondary);
}
</style>
