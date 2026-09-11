<template>
  <Teleport to="body">
    <div class="toast-container" v-if="toasts.length > 0">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="['toast', `toast-${toast.type}`]"
        >
          <span class="toast-icon">{{ getIcon(toast.type) }}</span>
          <span class="toast-message">{{ toast.message }}</span>
          <button class="toast-close" @click="removeToast(toast.id)">&times;</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { useToast } from '../composables/useToast'

const { toasts, removeToast } = useToast()

const getIcon = (type) => {
  const icons = {
    success: '✅',
    error: '❌',
    warning: '⚠️',
    info: 'ℹ️'
  }
  return icons[type] || icons.info
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 400px;
}

.toast {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  background: var(--surface);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  border-left: 4px solid;
  animation: slideIn 0.3s ease;
}

.toast-success {
  border-left-color: var(--success, #22c55e);
}

.toast-error {
  border-left-color: var(--danger, #ef4444);
}

.toast-warning {
  border-left-color: var(--warning, #f59e0b);
}

.toast-info {
  border-left-color: var(--accent, #3b82f6);
}

.toast-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.toast-message {
  flex: 1;
  font-size: 14px;
  color: var(--text-primary);
}

.toast-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--text-tertiary);
  padding: 0;
  line-height: 1;
  flex-shrink: 0;
}

.toast-close:hover {
  color: var(--text-primary);
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>
