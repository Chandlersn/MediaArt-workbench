<template>
  <Teleport to="body">
    <TransitionGroup name="message">
      <div v-for="msg in messages" :key="msg.id" :class="['message-box', `message-${msg.type}`]">
        <span class="message-icon">{{ getIcon(msg.type) }}</span>
        <span class="message-text">{{ msg.message }}</span>
      </div>
    </TransitionGroup>
  </Teleport>
</template>

<script setup>
import { useMessage } from '../composables/useMessage'

const { messages } = useMessage()

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
.message-box {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 16px 32px;
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  display: flex;
  align-items: center;
  gap: 12px;
  z-index: 9999;
  border: 2px solid;
}

.message-success {
  border-color: var(--success, #22c55e);
}

.message-error {
  border-color: var(--danger, #ef4444);
}

.message-warning {
  border-color: var(--warning, #f59e0b);
}

.message-info {
  border-color: var(--accent, #3b82f6);
}

.message-icon {
  font-size: 24px;
}

.message-text {
  font-size: 16px;
  color: var(--text-primary);
  font-weight: 500;
}

.message-enter-active,
.message-leave-active {
  transition: all 0.3s ease;
}

.message-enter-from {
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.8);
}

.message-leave-to {
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.8);
}
</style>
