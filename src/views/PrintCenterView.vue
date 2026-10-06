<template>
  <div class="print-center">
    <div class="page-header">
      <h2>打印中心</h2>
      <div class="header-actions">
        <CustomSelect v-model="logType" style="width: 140px" @change="loadLogs">
          <option value="">全部类型</option>
          <option value="certificate">证书</option>
          <option value="roster">名单</option>
          <option value="report">报表</option>
        </CustomSelect>
        <button class="btn-secondary btn-sm" @click="loadLogs">刷新</button>
      </div>
    </div>

    <div class="panel-desc intro">
      这里是打印留痕：每次批量打印的时间、份数、操作人与归档件。
      可展开查看涉及证书、按原模板原名单一键重打，或删除不再需要的记录（连带清理归档件）；
      打印模板在「模板管理」维护。
    </div>

    <div v-if="logs.length === 0" class="empty-state">
      暂无打印记录。到「证书管理」勾选证书批量打印后，这里会自动留痕。
    </div>
    <div v-else class="cert-table-wrap">
      <table class="log-table">
        <thead>
          <tr>
            <th>时间</th><th>类型</th><th>标题</th><th>份数</th><th>操作人</th><th>归档件</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="l in logs" :key="l.id">
            <tr>
              <td class="mono">{{ l.printed_at }}</td>
              <td>{{ DOC_TYPE_LABELS[l.doc_type] || l.doc_type }}</td>
              <td>{{ l.title }}</td>
              <td>{{ l.item_count }}</td>
              <td>{{ l.printed_by || '—' }}</td>
              <td>
                <button v-if="l.snapshot_path" class="btn-text" @click="viewDoc(l)">查看</button>
                <span v-else class="muted">无</span>
              </td>
              <td class="row-ops">
                <button
                  v-if="refIdsOf(l).length"
                  class="btn-text"
                  @click="expanded = expanded === l.id ? '' : l.id"
                >涉及 {{ refIdsOf(l).length }} 份</button>
                <button
                  v-if="l.template_id && refIdsOf(l).length"
                  class="btn-text"
                  :disabled="!!reprinting"
                  @click="reprint(l)"
                >{{ reprinting === l.id ? '重打中…' : '重打' }}</button>
                <button
                  class="btn-text danger"
                  :disabled="!!deleting"
                  @click="removeLog(l)"
                >{{ deleting === l.id ? '删除中…' : '删除' }}</button>
              </td>
            </tr>
            <tr v-if="expanded === l.id">
              <td colspan="7" class="ref-row">
                <span class="muted">涉及证书：</span>
                <span v-for="r in refIdsOf(l)" :key="printReferenceKey(r)" class="pill mono"
                  :title="r.sessionId ? `批次：${r.sessionId}` : '批次未记录'"
                >{{ printReferenceNumber(r) }}</span>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import CustomSelect from '../components/CustomSelect.vue'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import {
  fetchPrintLogs, fetchPrintDoc, openHtmlWindow, generatePrint, archivePrint, deletePrintLog
} from '../services/print'
import { parsePrintReferences, printReferenceKey, printReferenceNumber } from '../utils/printReferences'

const { error: toastError, success, warning } = useToast()
const { confirm } = useConfirmDialog()

const DOC_TYPE_LABELS = { certificate: '证书', roster: '名单', report: '报表' }

const logs = ref([])
const logType = ref('')
const expanded = ref('')
const reprinting = ref('')
const deleting = ref('')

const refIdsOf = (l) => parsePrintReferences(l.ref_ids)

const loadLogs = async () => {
  try {
    const res = await fetchPrintLogs(logType.value)
    logs.value = (res.success && res.logs) || []
  } catch (e) { toastError('读取打印记录失败：' + (e.message || e)) }
}

const viewDoc = async (l) => {
  try {
    const res = await fetchPrintDoc(l.id)
    if (!res.success) throw new Error(res.message || '归档件读取失败')
    openHtmlWindow(res.html)
  } catch (err) {
    toastError('打开归档件失败：' + (err.message || err))
  }
}

// 一键重打：按原模板 + 原名单重新生成（数据以台账当前值为准），重新归档留痕
const reprint = async (l) => {
  const ids = refIdsOf(l)
  const ok = await confirm({
    title: '重新打印这一批',
    message: `将按模板重新生成「${l.title}」的 ${ids.length} 份打印件（取台账当前数据），并记一条新的打印留痕。继续吗？`,
    confirmText: '重打', cancelText: '取消', type: 'default'
  })
  if (!ok) return
  reprinting.value = l.id
  try {
    const res = await generatePrint({
      templateId: l.template_id,
      certNumbers: ids
    })
    if (!res.success) throw new Error(res.message || '生成失败')
    if ((res.warnings || []).length) {
      warning(`有 ${res.warnings.length} 个字段存在空值，已按当前数据生成`)
    }
    openHtmlWindow(res.html)
    try {
      await archivePrint({
        html: res.html,
        templateId: l.template_id,
        docType: l.doc_type || 'certificate',
        title: l.title,
        itemCount: res.itemCount,
        refIds: ids
      })
    } catch (e) { console.warn('重打留痕失败（不阻断）:', e) }
    success(`已重新生成 ${res.itemCount} 份，请在打印窗口确认后打印`)
    await loadLogs()
  } catch (err) {
    toastError('重打失败：' + (err.message || err))
  } finally {
    reprinting.value = ''
  }
}

// 删除一条留痕：不可逆，所以要明确告诉用户「连归档件一起删」
const removeLog = async (l) => {
  const hasArchive = !!l.snapshot_path
  const ok = await confirm({
    title: '删除这条打印记录',
    message: hasArchive
      ? `将删除「${l.title}」（${l.printed_at}）的打印记录，并一并删除它的归档件。此操作不可恢复，确认删除吗？`
      : `将删除「${l.title}」（${l.printed_at}）的打印记录。此操作不可恢复，确认删除吗？`,
    confirmText: '删除', cancelText: '取消', type: 'danger'
  })
  if (!ok) return
  deleting.value = l.id
  try {
    const res = await deletePrintLog(l.id)
    // 展开行若正指着这条，收起，避免留下指向已删记录的残留状态
    if (expanded.value === l.id) expanded.value = ''
    success(res.removedArchive ? '已删除记录与归档件' : '已删除记录')
    await loadLogs()
  } catch (err) {
    toastError('删除失败：' + (err.message || err))
  } finally {
    deleting.value = ''
  }
}

onMounted(loadLogs)
</script>

<style scoped>
.print-center { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.page-header h2 { margin: 0; font-size: 20px; color: var(--text-primary); }
.header-actions { display: flex; gap: 10px; align-items: center; }
.intro { margin-bottom: 16px; }
.panel-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.7; }
.muted { color: var(--text-secondary); font-size: 13px; }
.empty-state { padding: 60px 20px; text-align: center; color: var(--text-secondary); }

.cert-table-wrap { background: var(--bg-secondary); border-radius: 12px; padding: 8px 16px 16px; overflow-x: auto; }
.log-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.log-table th, .log-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }
.log-table th { color: var(--text-secondary); font-weight: 600; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.row-ops { white-space: nowrap; }
.row-ops .btn-text { margin-right: 12px; }
.ref-row { background: var(--bg-primary); }
.ref-row .pill { display: inline-block; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 2px 10px; margin: 2px 6px 2px 0; }

.btn-secondary { background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; cursor: pointer; font-size: 13px; }
.btn-text { background: none; border: none; color: var(--cinnabar, #b0392b); cursor: pointer; font-size: 13px; padding: 0; }
.btn-text:disabled { opacity: 0.5; cursor: default; }
.btn-text.danger { color: var(--danger, #d9534f); }
</style>
