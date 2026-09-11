<script setup>
import { computed } from 'vue'
import CustomSelect from './CustomSelect.vue'

const props = defineProps({
  totalItems: { type: Number, required: true },
  pageSize: { type: Number, default: 20 },
  currentPage: { type: Number, default: 1 }
})

const emit = defineEmits(['page-change', 'page-size-change'])

const totalPages = computed(() => Math.ceil(props.totalItems / props.pageSize) || 1)

const pageNumbers = computed(() => {
  const pages = []
  const total = totalPages.value
  const current = props.currentPage

  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages.push(i)
  } else {
    pages.push(1)
    if (current > 3) pages.push('...')

    const start = Math.max(2, current - 1)
    const end = Math.min(total - 1, current + 1)
    for (let i = start; i <= end; i++) pages.push(i)

    if (current < total - 2) pages.push('...')
    pages.push(total)
  }

  return pages
})

const handlePageChange = (page) => {
  if (page < 1 || page > totalPages.value || page === props.currentPage) return
  emit('page-change', page)
}

const handlePageSizeChange = (size) => {
  emit('page-size-change', Number(size))
}
</script>

<template>
  <div class="pagination" v-if="totalPages > 1">
    <div class="pagination-info">
      共 {{ totalItems }} 条记录，每页
      <CustomSelect :model-value="pageSize" @change="handlePageSizeChange">
        <option :value="10">10</option>
        <option :value="20">20</option>
        <option :value="50">50</option>
      </CustomSelect>
      条
    </div>
    <div class="pagination-controls">
      <button
        class="page-btn"
        :disabled="currentPage === 1"
        @click="handlePageChange(currentPage - 1)"
      >
        ‹
      </button>
      <template v-for="page in pageNumbers" :key="page">
        <span v-if="page === '...'" class="page-ellipsis">...</span>
        <button
          v-else
          class="page-btn"
          :class="{ active: page === currentPage }"
          @click="handlePageChange(page)"
        >
          {{ page }}
        </button>
      </template>
      <button
        class="page-btn"
        :disabled="currentPage === totalPages"
        @click="handlePageChange(currentPage + 1)"
      >
        ›
      </button>
    </div>
  </div>
</template>

<style scoped>
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0;
  margin-top: 8px;
}

.pagination-info {
  font-size: 13px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}

.pagination-info .filter-select {
  min-width: auto;
  height: 32px;
  padding: 4px 30px 4px 10px;
  font-size: 13px;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

.page-btn {
  min-width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.page-btn:hover:not(:disabled):not(.active) {
  border-color: var(--accent);
  color: var(--accent);
}

.page-btn.active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-ellipsis {
  padding: 0 4px;
  color: var(--text-secondary);
}
</style>
