<template>
  <div class="page-header">
    <div class="page-header-left">
      <h2 class="page-title">{{ title }}</h2>
      <p v-if="description" class="page-desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header-right">
      <slot name="actions"></slot>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    default: ''
  }
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color, #eee);
}

.page-header-left {
  flex: 1;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.page-desc {
  margin: 8px 0 0;
  font-size: 14px;
  color: var(--text-secondary, #666);
}

.page-header-right {
  display: flex;
  gap: 12px;
  align-items: center;
}
</style>
