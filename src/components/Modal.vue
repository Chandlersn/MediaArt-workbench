<template>
  <Teleport to="body">
    <div v-if="show" class="modal-overlay" @click.self="handleOverlayClick">
      <div class="modal-box" :class="sizeClass">
        <div class="modal-header">
          <h3 class="modal-title">{{ title }}</h3>
          <button class="modal-close" @click="close">✕</button>
        </div>
        <div class="modal-content">
          <slot></slot>
        </div>
        <div v-if="$slots.footer" class="modal-footer">
          <slot name="footer"></slot>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, watch } from 'vue'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: ''
  },
  size: {
    type: String,
    default: 'medium',
    validator: (v) => ['small', 'medium', 'large', 'xlarge'].includes(v)
  },
  closeOnOverlay: {
    type: Boolean,
    default: true
  },
  showFooter: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['close', 'update:show'])

const sizeClass = computed(() => `modal-${props.size}`)

const close = () => {
  emit('close')
  emit('update:show', false)
}

const handleOverlayClick = () => {
  if (props.closeOnOverlay) {
    close()
  }
}

watch(() => props.show, (newVal) => {
  if (newVal) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-box {
  background: var(--bg-primary, #fff);
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-small { width: 400px; }
.modal-medium { width: 560px; }
.modal-large { width: 720px; }
.modal-xlarge { width: 900px; }

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #eee);
}

.modal-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.modal-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--text-secondary, #666);
  padding: 4px;
  line-height: 1;
}

.modal-close:hover {
  color: var(--text-primary, #333);
}

.modal-content {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-color, #eee);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
