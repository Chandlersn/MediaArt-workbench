<template>
  <div class="settings-page">
    <div class="page-header">
      <h2>设置</h2>
    </div>

    <div class="settings-content">
      <div class="settings-container">
      <div class="settings-section">
        <h3>系统状态</h3>
        <div class="system-status-grid" v-if="systemStatus">
          <div class="status-card">
            <div class="status-icon uptime-icon">⏱</div>
            <div class="status-detail">
              <div class="status-value">{{ systemStatus.uptime }}</div>
              <div class="status-label">服务运行时间</div>
            </div>
          </div>
          <div class="status-card">
            <div class="status-icon data-icon">📊</div>
            <div class="status-detail">
              <div class="status-value">{{ formatDataSize(systemStatus.data_size) }}</div>
              <div class="status-label">数据文件大小</div>
            </div>
          </div>
          <div class="status-card">
            <div class="status-icon platform-icon">💻</div>
            <div class="status-detail">
              <div class="status-value">{{ systemStatus.system?.platform || '-' }}</div>
              <div class="status-label">运行平台</div>
            </div>
          </div>
          <div class="status-card">
            <div class="status-icon python-icon">🐍</div>
            <div class="status-detail">
              <div class="status-value">Python {{ systemStatus.system?.python_version || '-' }}</div>
              <div class="status-label">运行环境</div>
            </div>
          </div>
        </div>
        <div v-else class="status-loading">加载中...</div>
        <div class="settings-actions" style="margin-top: 12px;">
          <button class="btn-secondary" @click="loadSystemStatus">刷新状态</button>
        </div>
      </div>

      <div class="settings-section">
        <h3>数据管理</h3>
        <div class="data-stats">
          <div class="data-stat-item">
            <span class="data-stat-label">项目总数</span>
            <span class="data-stat-value">{{ stats.projects }}</span>
          </div>
          <div class="data-stat-item">
            <span class="data-stat-label">机构总数</span>
            <span class="data-stat-value">{{ stats.organizations }}</span>
          </div>
          <div class="data-stat-item">
            <span class="data-stat-label">人员总数</span>
            <span class="data-stat-value">{{ stats.players }}</span>
          </div>
          <div class="data-stat-item">
            <span class="data-stat-label">知识条目</span>
            <span class="data-stat-value">{{ stats.knowledge }}</span>
          </div>
        </div>
        <div class="settings-actions">
          <button class="btn-secondary" @click="showExportModal">导出数据</button>
          <button class="btn-secondary" @click="importData">导入数据</button>
          <button class="btn-secondary" @click="showBackupModal">备份管理</button>
        </div>
      </div>

      <div class="settings-section">
        <h3>数据同步</h3>
        <p class="section-desc">管理 JSON 数据文件与 SQLite 数据库之间的数据迁移</p>
        <div v-if="syncStatus" class="sync-info">
          <div class="sync-status-row">
            <div class="sync-item" :class="{ active: syncStatus.json_exists }">
              <div class="sync-item-icon">📄</div>
              <div class="sync-item-detail">
                <div class="sync-item-title">JSON 文件</div>
                <div class="sync-item-desc">{{ syncStatus.json_exists ? `${syncStatus.json_records} 条记录` : '不存在' }}</div>
              </div>
            </div>
            <div class="sync-arrow">⇄</div>
            <div class="sync-item" :class="{ active: syncStatus.db_exists }">
              <div class="sync-item-icon">🗄</div>
              <div class="sync-item-detail">
                <div class="sync-item-title">SQLite 数据库</div>
                <div class="sync-item-desc">{{ syncStatus.db_exists ? `${syncStatus.db_records} 条记录` : '不存在' }}</div>
              </div>
            </div>
          </div>
          <div v-if="syncStatus.recommendation" class="sync-recommendation" :class="{ warning: syncStatus.needs_migration }">
            {{ syncStatus.recommendation }}
          </div>
        </div>
        <div v-else class="status-loading">加载中...</div>
        <div class="settings-actions" style="margin-top: 12px;">
          <button class="btn-secondary" :disabled="syncing" @click="syncJsonToDb">
            {{ syncing ? '迁移中...' : 'JSON → SQLite' }}
          </button>
          <button class="btn-secondary" :disabled="syncing" @click="syncDbToJson">
            {{ syncing ? '导出中...' : 'SQLite → JSON' }}
          </button>
          <button class="btn-secondary" @click="loadSyncStatus">刷新状态</button>
        </div>
      </div>

      <div class="settings-section">
        <h3>临时文件清理</h3>
        <p class="section-desc">assets 目录存放上传的临时文件，定期清理可释放磁盘空间</p>
        <div class="cleanup-options">
          <div class="cleanup-stats-row">
            <div class="cleanup-stat-card">
              <div class="cleanup-stat-value">{{ tempFilesSize }}</div>
              <div class="cleanup-stat-label">临时文件占用</div>
            </div>
            <div class="cleanup-stat-card">
              <div class="cleanup-stat-value">{{ tempFileCount }}</div>
              <div class="cleanup-stat-label">文件总数</div>
            </div>
            <div class="cleanup-stat-card" :class="{ 'has-warning': oldFiles.length > 0 }">
              <div class="cleanup-stat-value">{{ oldFiles.length }}</div>
              <div class="cleanup-stat-label">超过30天的旧文件</div>
            </div>
          </div>

          <div class="cleanup-config">
            <label>自动清理周期：</label>
            <CustomSelect v-model="cleanupPeriod" style="width: auto;" @change="saveCleanupConfig">
              <option value="never">不自动清理</option>
              <option value="30">1个月</option>
              <option value="90">3个月</option>
              <option value="180">6个月</option>
            </CustomSelect>
          </div>

          <div class="cleanup-config" style="margin-top: 12px;">
            <label>清理范围：</label>
            <CustomSelect v-model="cleanupDays" style="width: auto;">
              <option :value="7">7天前的文件</option>
              <option :value="14">14天前的文件</option>
              <option :value="30">30天前的文件</option>
              <option :value="60">60天前的文件</option>
              <option :value="90">90天前的文件</option>
            </CustomSelect>
          </div>

          <div class="settings-actions" style="margin-top: 16px;">
            <button class="btn-secondary" :disabled="scanning" @click="scanTempFiles">
              {{ scanning ? '扫描中...' : '扫描临时文件' }}
            </button>
            <button class="btn-secondary btn-danger" :disabled="cleaning" @click="cleanupTempFiles">
              {{ cleaning ? '清理中...' : '立即清理' }}
            </button>
          </div>

          <div v-if="oldFiles.length > 0" class="old-files-list">
            <div class="old-files-header">
              <span>旧文件列表（前20个）</span>
              <span class="old-files-size">共 {{ CleanupUI.formatSize(oldFilesSize) }}</span>
            </div>
            <div class="old-files-items">
              <div v-for="file in oldFiles.slice(0, 20)" :key="file.path" class="old-file-item">
                <div class="old-file-info">
                  <span class="old-file-name">{{ file.path }}</span>
                  <span class="old-file-meta">{{ file.age_days }}天前 · {{ file.modified }}</span>
                </div>
                <span class="old-file-size">{{ CleanupUI.formatSize(file.size) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <h3>归档目录配置</h3>
        <p class="section-desc">配置档案归档的根目录，用于存储项目档案、选手档案等</p>
        <div class="archive-path-config">
          <div class="path-input-group">
            <input type="text" v-model="archivePath" placeholder="请选择或输入归档目录路径" readonly>
            <button class="btn-secondary" @click="selectArchivePath">选择目录</button>
          </div>
          <div class="path-info">
            <span class="path-status" :class="{ configured: archivePath }">{{ archivePathStatus }}</span>
          </div>
        </div>
        <div class="settings-actions" style="margin-top: 12px;">
          <button class="btn-primary" @click="saveArchivePath">保存配置</button>
          <button class="btn-secondary" @click="resetArchivePath">恢复默认</button>
          <button class="btn-secondary" @click="openArchiveFolder">打开目录</button>
        </div>
      </div>

      <!-- 资源中心：存储目录 + 文件分类合并为一个功能区 -->
      <div class="settings-section">
        <h3>资源中心配置</h3>
        <p class="section-desc">资源中心的存储根目录，以及各文件分类对应的文件夹</p>

        <div class="config-subblock">
          <div class="subblock-title">存储目录</div>
          <div class="archive-path-config">
            <div class="path-input-group">
              <input type="text" v-model="resourcePath" placeholder="请选择或输入资源目录路径" readonly>
              <button class="btn-secondary" @click="selectResourcePath">选择目录</button>
            </div>
            <div class="path-info">
              <span class="path-status" :class="{ configured: resourcePath }">{{ resourcePathStatus }}</span>
            </div>
          </div>
          <div class="settings-actions" style="margin-top: 12px;">
            <button class="btn-primary" @click="saveResourcePath">保存配置</button>
            <button class="btn-secondary" @click="resetResourcePath">恢复默认</button>
            <button class="btn-secondary" @click="openResourceFolder">打开目录</button>
          </div>
        </div>

        <div class="config-subblock">
          <div class="subblock-title">
            <span>文件分类</span>
            <button class="btn-secondary btn-sm" @click="showAddCategoryModal">+ 添加分类</button>
          </div>
          <div class="resource-category-config">
            <div v-if="resourceCategories.length === 0" class="empty-hint">
              暂无分类，点击右上角「添加分类」
            </div>
            <div v-for="(cat, index) in resourceCategories" :key="index" class="category-item">
              <div class="category-main">
                <span class="category-name">{{ cat.name }}</span>
                <span class="category-arrow">→</span>
                <span class="category-folder">{{ cat.folder }}</span>
              </div>
              <div class="category-actions">
                <button class="btn-icon-text" title="编辑" @click="editCategory(index)">✏</button>
                <button class="btn-icon-text btn-icon-danger" title="删除" @click="removeCategory(index)">✕</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <h3>导入模板下载</h3>
        <p class="section-desc">下载标准模板，按格式填写后导入</p>
        <div class="template-downloads">
          <a href="templates/选手导入模板.csv" download class="btn-secondary btn-sm">选手导入模板</a>
          <a href="templates/机构导入模板.csv" download class="btn-secondary btn-sm">机构导入模板</a>
        </div>
      </div>

      <div class="settings-section">
        <h3>关于</h3>
        <div class="about-info">
          <div class="about-header">
            <div class="about-title">
              <strong>媒体艺术智能工作台</strong>
              <span class="about-version">v{{ appVersion }}</span>
            </div>
          </div>
          <p class="about-desc">用于媒体艺术展览项目的全生命周期管理</p>
          <div class="about-details">
            <div class="about-detail-item">
              <span class="about-detail-label">开源协议</span>
              <span class="about-detail-value">MIT License</span>
            </div>
            <div class="about-detail-item">
              <span class="about-detail-label">技术栈</span>
              <span class="about-detail-value">Vue 3 + Python + Electron</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Folder Picker Modal -->
    <div v-if="showFolderPicker" class="modal-overlay" @click.self="showFolderPicker = false">
      <div class="modal-content modal-lg">
        <div class="modal-header">
          <h3>选择目录</h3>
          <button class="modal-close" @click="showFolderPicker = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="folder-picker-path">
            <button class="btn-secondary btn-sm" @click="goBrowseParent" :disabled="!browsePath && browseParentPath === null">↑ 上级</button>
            <span class="folder-current-path">{{ browsePath || '我的电脑' }}</span>
          </div>
          <div class="folder-picker-list" v-if="!browseLoading">
            <div v-if="browseDirs.length === 0" class="empty-hint" style="padding: 16px;">
              此目录下没有可访问的子文件夹
            </div>
            <div
              v-for="dir in browseDirs"
              :key="dir"
              class="folder-picker-item"
              @click="selectBrowseDir(dir)"
            >
              <span class="folder-picker-icon">📁</span>
              <span class="folder-picker-name">{{ dir }}</span>
            </div>
          </div>
          <div v-else class="status-loading">加载中...</div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showFolderPicker = false">取消</button>
          <button class="btn-primary" @click="confirmBrowseDir" :disabled="!browsePath">选择此目录</button>
        </div>
      </div>
    </div>

    <!-- Backup Modal -->
    <div v-if="showBackup" class="modal-overlay" @click.self="showBackup = false">
      <div class="modal-content modal-lg">
        <div class="modal-header">
          <h3>备份管理</h3>
          <button class="modal-close" @click="showBackup = false">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="backupLoading" class="status-loading">加载备份列表中...</div>
          <div v-else-if="backups.length === 0" class="empty-hint">
            暂无服务端备份，点击"创建备份"生成第一份备份
          </div>
          <div v-else class="backup-list">
            <div v-for="backup in backups" :key="backup.name" class="backup-item">
              <div class="backup-info">
                <span class="backup-name">{{ backup.date }}</span>
                <span class="backup-time" v-if="backup.time">{{ backup.time }}</span>
                <span class="backup-badge" v-if="backup.has_data">完整</span>
                <span class="backup-badge badge-warning" v-else>数据缺失</span>
              </div>
              <div class="backup-actions">
                <button class="btn-secondary btn-sm" :disabled="!backup.has_data || restoring" @click="restoreBackup(backup)">
                  {{ restoring && restoreTarget === backup.name ? '恢复中...' : '恢复' }}
                </button>
                <button class="btn-icon-text btn-icon-danger" @click="deleteBackupConfirm(backup)">✕</button>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-primary" :disabled="creatingBackup" @click="createBackup">
            {{ creatingBackup ? '创建中...' : '创建备份' }}
          </button>
          <button class="btn-secondary" @click="showBackup = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- Add/Edit Category Modal -->
    <div v-if="showCategoryModal" class="modal-overlay" @click.self="showCategoryModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>{{ editingCategoryIndex >= 0 ? '编辑分类' : '添加分类' }}</h3>
          <button class="modal-close" @click="showCategoryModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>分类名称</label>
            <input type="text" v-model="newCategory.name" class="form-input" placeholder="如：图片素材">
          </div>
          <div class="form-group">
            <label>对应文件夹</label>
            <input type="text" v-model="newCategory.folder" class="form-input" placeholder="如：images">
            <span class="form-hint">文件夹名称，用于在资源目录下创建对应的子目录</span>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-primary" @click="saveCategory">{{ editingCategoryIndex >= 0 ? '保存' : '添加' }}</button>
          <button class="btn-secondary" @click="showCategoryModal = false">取消</button>
        </div>
      </div>
    </div>

    <!-- Export Config Modal -->
    <div v-if="showExport" class="modal-overlay" @click.self="showExport = false">
      <div class="modal-content modal-lg">
        <div class="modal-header">
          <h3>导出数据配置</h3>
          <button class="modal-close" @click="showExport = false">&times;</button>
        </div>
        <div class="modal-body export-config-content">
          <div class="config-section">
            <h4>选择数据层级</h4>
            <div class="checkbox-group">
              <label class="checkbox-item">
                <input type="checkbox" v-model="exportOptions.projects">
                <span>项目数据</span>
              </label>
              <label class="checkbox-item">
                <input type="checkbox" v-model="exportOptions.organizations">
                <span>机构数据</span>
              </label>
              <label class="checkbox-item">
                <input type="checkbox" v-model="exportOptions.players">
                <span>选手数据</span>
              </label>
              <label class="checkbox-item">
                <input type="checkbox" v-model="exportOptions.finances">
                <span>财务数据</span>
              </label>
              <label class="checkbox-item">
                <input type="checkbox" v-model="exportOptions.knowledge">
                <span>知识库数据</span>
              </label>
            </div>
          </div>

          <div class="config-section" v-if="exportOptions.projects">
            <h4>项目字段 <label class="select-all"><input type="checkbox" @change="toggleAllFields('projects', $event)" :checked="allFieldsSelected('projects')"> 全选</label></h4>
            <div class="checkbox-group fields-group">
              <label v-for="field in projectFields" :key="field.key" class="checkbox-item">
                <input type="checkbox" v-model="exportOptions.projectFields" :value="field.key">
                <span>{{ field.label }}</span>
              </label>
            </div>
          </div>

          <div class="config-section" v-if="exportOptions.organizations">
            <h4>机构字段 <label class="select-all"><input type="checkbox" @change="toggleAllFields('organizations', $event)" :checked="allFieldsSelected('organizations')"> 全选</label></h4>
            <div class="checkbox-group fields-group">
              <label v-for="field in orgFields" :key="field.key" class="checkbox-item">
                <input type="checkbox" v-model="exportOptions.orgFields" :value="field.key">
                <span>{{ field.label }}</span>
              </label>
            </div>
          </div>

          <div class="config-section" v-if="exportOptions.players">
            <h4>选手字段 <label class="select-all"><input type="checkbox" @change="toggleAllFields('players', $event)" :checked="allFieldsSelected('players')"> 全选</label></h4>
            <div class="checkbox-group fields-group">
              <label v-for="field in playerFields" :key="field.key" class="checkbox-item">
                <input type="checkbox" v-model="exportOptions.playerFields" :value="field.key">
                <span>{{ field.label }}</span>
              </label>
            </div>
          </div>

          <div class="config-section">
            <h4>导出格式</h4>
            <div class="radio-group">
              <label class="radio-item">
                <input type="radio" v-model="exportOptions.format" value="csv">
                <span>Excel (CSV格式)</span>
              </label>
              <label class="radio-item">
                <input type="radio" v-model="exportOptions.format" value="json">
                <span>JSON (完整数据备份)</span>
              </label>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showExport = false">取消</button>
          <button class="btn-primary" @click="executeExport">确认导出</button>
        </div>
      </div>
    </div>
  </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { CleanupUI } from '../services/cleanup'
import { useToast } from '../composables/useToast'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import { get, post } from '../services/http'
import * as dataService from '../services/dataService.js'
import CustomSelect from '../components/CustomSelect.vue'

const { success, error, warning } = useToast()
const { confirm, alert } = useConfirmDialog()

const appVersion = __APP_VERSION__

const stats = ref({
  projects: 0,
  organizations: 0,
  players: 0,
  knowledge: 0
})

const systemStatus = ref(null)
const syncStatus = ref(null)
const syncing = ref(false)

const cleanupPeriod = ref('never')
const tempFilesSize = ref('计算中...')
const tempFileCount = ref(0)
const oldFiles = ref([])
const oldFilesSize = ref(0)
const cleanupDays = ref(30)
const scanning = ref(false)
const cleaning = ref(false)
const archivePath = ref('')
const archivePathStatus = ref('')
const resourcePath = ref('')
const resourcePathStatus = ref('')
const resourceCategories = ref([])
const showBackup = ref(false)
const backups = ref([])
const backupLoading = ref(false)
const creatingBackup = ref(false)
const restoring = ref(false)
const restoreTarget = ref('')
const showCategoryModal = ref(false)
const newCategory = ref({ name: '', folder: '' })
const editingCategoryIndex = ref(-1)

const defaultArchivePath = ref('')
const defaultResourcePath = ref('')

onMounted(async () => {
  await Promise.all([
    loadStats(),
    loadSystemStatus(),
    loadSyncStatus(),
    loadArchivePath(),
    loadResourcePath(),
    loadResourceCategories()
  ])
  loadCleanupConfig()
  scanTempFiles()
})

onActivated(async () => {
  await Promise.all([
    loadStats(),
    loadSystemStatus(),
    loadSyncStatus(),
    loadArchivePath(),
    loadResourcePath(),
    loadResourceCategories()
  ])
  loadCleanupConfig()
  scanTempFiles()
})

const formatDataSize = (bytes) => {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

const loadSystemStatus = async () => {
  try {
    const data = await get('/api/status')
    systemStatus.value = data
  } catch (e) {
    console.error('加载系统状态失败:', e)
  }
}

const loadSyncStatus = async () => {
  try {
    const data = await get('/api/data/sync/status')
    if (data.success) {
      syncStatus.value = data.status
    }
  } catch (e) {
    console.error('加载同步状态失败:', e)
  }
}

const syncJsonToDb = async () => {
  const confirmed = await confirm({
    title: '数据迁移确认',
    message: '将 JSON 文件中的数据导入到 SQLite 数据库，已有数据将被覆盖。确定继续吗？',
    type: 'warning'
  })
  if (!confirmed) return

  syncing.value = true
  try {
    const data = await post('/api/data/sync/import')
    if (data.success) {
      success(`迁移成功！已导入 ${Object.values(data.records || {}).reduce((a, b) => a + b, 0)} 条记录`)
      await loadSyncStatus()
    } else {
      error(data.message || '迁移失败')
    }
  } catch (e) {
    error(`迁移失败：${e.message}`)
  } finally {
    syncing.value = false
  }
}

const syncDbToJson = async () => {
  const confirmed = await confirm({
    title: '数据导出确认',
    message: '将 SQLite 数据库中的数据导出到 JSON 文件，已有 JSON 文件将被覆盖。确定继续吗？',
    type: 'warning'
  })
  if (!confirmed) return

  syncing.value = true
  try {
    const data = await post('/api/data/sync/export')
    if (data.success) {
      success('导出成功！数据已写入 JSON 文件')
      await loadSyncStatus()
    } else {
      error(data.message || '导出失败')
    }
  } catch (e) {
    error(`导出失败：${e.message}`)
  } finally {
    syncing.value = false
  }
}

const loadStats = async () => {
  try {
    await dataService.load()
    const data = {
      projects: dataService.getData('projects'),
      organizations: dataService.getData('organizations'),
      players: dataService.getData('players'),
      knowledge: dataService.getData('knowledge')
    }
    stats.value.projects = Array.isArray(data.projects) ? data.projects.length : 0
    stats.value.organizations = Array.isArray(data.organizations) ? data.organizations.length : 0
    stats.value.players = Array.isArray(data.players) ? data.players.length : 0
    stats.value.knowledge =
      (data.knowledge?.solutions?.length || 0) +
      (data.knowledge?.practices?.length || 0) +
      (data.knowledge?.training?.length || 0)
  } catch (e) {
    console.error('加载统计数据失败:', e)
  }
}

const loadCleanupConfig = () => {
  const config = CleanupUI.loadConfig()
  if (config && config.period) {
    cleanupPeriod.value = config.period
  }
}

const saveCleanupConfig = () => {
  CleanupUI.saveConfig(cleanupPeriod.value)
  success('清理配置已保存')
}

const scanTempFiles = async () => {
  scanning.value = true
  tempFilesSize.value = '扫描中...'
  try {
    const result = await CleanupUI.scanTempFiles()
    if (result.success) {
      tempFilesSize.value = CleanupUI.formatSize(result.totalSize)
      tempFileCount.value = result.fileCount
      oldFiles.value = result.oldFiles || []
      oldFilesSize.value = result.oldFilesSize || 0
    } else {
      tempFilesSize.value = '扫描失败'
    }
  } catch (e) {
    console.error('扫描失败:', e)
    tempFilesSize.value = '扫描失败'
    error(`扫描失败：${e.message}`)
  } finally {
    scanning.value = false
  }
}

const cleanupTempFiles = async () => {
  const days = cleanupDays.value
  const confirmed = await confirm({
    title: '清理确认',
    message: `确定要清理 ${days} 天前的临时文件吗？此操作不可撤销。${oldFiles.value.length > 0 ? `\n\n将清理 ${oldFiles.value.length} 个旧文件，释放 ${CleanupUI.formatSize(oldFilesSize.value)} 空间。` : ''}`,
    type: 'warning'
  })
  if (!confirmed) return

  cleaning.value = true
  try {
    const result = await CleanupUI.executeCleanup(days)
    if (result.success) {
      success(`清理完成！已删除 ${result.deletedCount} 个文件，释放 ${CleanupUI.formatSize(result.deletedSize)} 空间`)
      scanTempFiles()
    } else {
      error(`清理失败：${result.message}`)
    }
  } catch (e) {
    console.error('清理失败:', e)
    error(`清理失败：${e.message}`)
  } finally {
    cleaning.value = false
  }
}

const loadArchivePath = async () => {
  try {
    const data = await get('/api/config/archive-path')
    if (data.path) {
      archivePath.value = data.path
    }
    if (data.defaultPath) {
      defaultArchivePath.value = data.defaultPath
    }
    updateArchivePathStatus()
  } catch (e) {
    try {
      await dataService.load()
      const settings = dataService.getData('settings') || {}
      archivePath.value = settings.archivePath || ''
      updateArchivePathStatus()
    } catch (e2) {
      console.error('加载归档路径失败:', e2)
    }
  }
}

const showFolderPicker = ref(false)
const folderPickerTarget = ref('')
const browsePath = ref('')
const browseParentPath = ref(null)
const browseDirs = ref([])
const browseLoading = ref(false)

const browseDirectory = async (path) => {
  browseLoading.value = true
  try {
    const url = path
      ? `/api/browse-dirs?path=${encodeURIComponent(path)}`
      : '/api/browse-dirs'
    const data = await get(url)
    if (data.success) {
      browsePath.value = data.currentPath
      browseParentPath.value = data.parentPath
      browseDirs.value = data.directories || []
    } else {
      error(data.message || '浏览目录失败')
    }
  } catch (e) {
    console.error('浏览目录失败:', e)
    error('浏览目录失败')
  } finally {
    browseLoading.value = false
  }
}

const openFolderPicker = (target) => {
  folderPickerTarget.value = target
  browseDirectory('')
  showFolderPicker.value = true
}

const selectBrowseDir = (dir) => {
  let newPath
  if (browsePath.value) {
    const sep = browsePath.value.includes('/') ? '/' : '\\'
    newPath = browsePath.value.replace(/[\\/]+$/, '') + sep + dir
  } else {
    newPath = dir
  }
  browseDirectory(newPath)
}

const goBrowseParent = () => {
  if (browseParentPath.value !== null) {
    browseDirectory(browseParentPath.value)
  } else {
    browseDirectory('')
  }
}

const confirmBrowseDir = () => {
  if (browsePath.value && folderPickerTarget.value) {
    if (folderPickerTarget.value === 'archive') {
      archivePath.value = browsePath.value
      updateArchivePathStatus()
    } else if (folderPickerTarget.value === 'resource') {
      resourcePath.value = browsePath.value
      updateResourcePathStatus()
    }
  }
  showFolderPicker.value = false
}

const selectArchivePath = async () => {
  if (window.electronAPI && window.electronAPI.selectFolder) {
    try {
      const result = await window.electronAPI.selectFolder()
      if (!result.canceled && result.filePaths && result.filePaths.length > 0) {
        archivePath.value = result.filePaths[0]
        updateArchivePathStatus()
        return
      }
    } catch (err) {
      console.error('Electron 目录选择失败:', err)
    }
  }
  openFolderPicker('archive')
}

const updateArchivePathStatus = () => {
  if (archivePath.value) {
    archivePathStatus.value = '已配置'
  } else {
    archivePathStatus.value = '未配置'
  }
}

const saveArchivePath = async () => {
  try {
    const result = await post('/api/config/archive-path', { path: archivePath.value })

    if (result.success) {
      try {
        await dataService.load()
        let settings = dataService.getData('settings') || {}
        settings = { ...settings, archivePath: archivePath.value }
        dataService.setData('settings', settings)
        await dataService.save()
      } catch (e) {
        console.error('保存归档路径到dataService失败:', e)
      }
      success('归档路径已保存，刷新页面后生效')
    } else {
      error(result.message || '保存失败')
    }
  } catch (e) {
    console.error('保存归档路径失败:', e)
    error(`保存失败: ${e.message}`)
  }
}

const resetArchivePath = () => {
  archivePath.value = defaultArchivePath.value || ''
  updateArchivePathStatus()
}

const openArchiveFolder = async () => {
  if (!archivePath.value) {
    warning('请先配置归档目录路径')
    return
  }
  try {
    const result = await get(`/api/open-file?path=${encodeURIComponent(archivePath.value)}`)
    if (!result.success) {
      error('无法打开目录')
    }
  } catch (e) {
    console.error('打开目录失败:', e)
    error('打开目录失败')
  }
}

const loadResourcePath = async () => {
  try {
    const data = await get('/api/config/resources-path')
    if (data.path) {
      resourcePath.value = data.path
    }
    if (data.defaultPath) {
      defaultResourcePath.value = data.defaultPath
    }
    updateResourcePathStatus()
  } catch (e) {
    try {
      await dataService.load()
      const settings = dataService.getData('settings') || {}
      resourcePath.value = settings.resourcePath || ''
      updateResourcePathStatus()
    } catch (e2) {
      console.error('加载资源路径失败:', e2)
    }
  }
}

const selectResourcePath = async () => {
  if (window.electronAPI && window.electronAPI.selectFolder) {
    try {
      const result = await window.electronAPI.selectFolder()
      if (!result.canceled && result.filePaths && result.filePaths.length > 0) {
        resourcePath.value = result.filePaths[0]
        updateResourcePathStatus()
        return
      }
    } catch (err) {
      console.error('Electron 目录选择失败:', err)
    }
  }
  openFolderPicker('resource')
}

const updateResourcePathStatus = () => {
  if (resourcePath.value) {
    resourcePathStatus.value = '已配置'
  } else {
    resourcePathStatus.value = '未配置'
  }
}

const saveResourcePath = async () => {
  try {
    const result = await post('/api/config/resources-path', { path: resourcePath.value })

    if (result.success) {
      try {
        await dataService.load()
        let settings = dataService.getData('settings') || {}
        settings = { ...settings, resourcePath: resourcePath.value }
        dataService.setData('settings', settings)
        await dataService.save()
      } catch (e) {
        console.error('保存资源路径到dataService失败:', e)
      }
      success('资源路径已保存，刷新页面后生效')
    } else {
      error(result.message || '保存失败')
    }
  } catch (e) {
    console.error('保存资源路径失败:', e)
    error(`保存失败: ${e.message}`)
  }
}

const resetResourcePath = () => {
  resourcePath.value = defaultResourcePath.value || ''
  updateResourcePathStatus()
}

const openResourceFolder = async () => {
  if (!resourcePath.value) {
    warning('请先配置资源目录路径')
    return
  }
  try {
    const result = await get(`/api/open-file?path=${encodeURIComponent(resourcePath.value)}`)
    if (!result.success) {
      error('无法打开目录')
    }
  } catch (e) {
    console.error('打开目录失败:', e)
    error('打开目录失败')
  }
}

const loadResourceCategories = async () => {
  try {
    await dataService.load()
    let settings = dataService.getData('settings') || {}
    // 归档管理专属分类（项目/选手/机构）不出现在资源中心，这里一并过滤掉
    const reserved = ['project', 'player', 'organization']
    let cats = (settings.resourceCategories || []).filter(c => !reserved.includes(c.id))
    if (cats.length !== (settings.resourceCategories || []).length) {
      settings = { ...settings, resourceCategories: cats }
      dataService.setData('settings', settings)
      await dataService.save()
    }
    resourceCategories.value = cats
  } catch (e) {
    console.error('加载资源分类失败:', e)
  }
}

const showAddCategoryModal = () => {
  newCategory.value = { name: '', folder: '' }
  editingCategoryIndex.value = -1
  showCategoryModal.value = true
}

const editCategory = (index) => {
  newCategory.value = { ...resourceCategories.value[index] }
  editingCategoryIndex.value = index
  showCategoryModal.value = true
}

const saveCategory = () => {
  if (newCategory.value.name && newCategory.value.folder) {
    if (editingCategoryIndex.value >= 0) {
      resourceCategories.value[editingCategoryIndex.value] = { ...newCategory.value }
    } else {
      resourceCategories.value.push({ ...newCategory.value })
    }
    saveResourceCategories()
    showCategoryModal.value = false
  }
}

const removeCategory = (index) => {
  resourceCategories.value.splice(index, 1)
  saveResourceCategories()
}

const saveResourceCategories = async () => {
  try {
    await dataService.load()
    let settings = dataService.getData('settings') || {}
    settings = { ...settings, resourceCategories: resourceCategories.value }
    dataService.setData('settings', settings)
    await dataService.save()
  } catch (e) {
    console.error('保存资源分类失败:', e)
  }
}

const importData = () => {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async (e) => {
    const file = e.target.files[0]
    if (!file) return

    const confirmed = await confirm({
      title: '导入确认',
      message: '导入数据将覆盖现有数据，是否继续？',
      type: 'warning'
    })
    if (!confirmed) return

    try {
      const text = await file.text()
      const data = JSON.parse(text)

      await dataService.load()
      if (data.projects) dataService.setData('projects', data.projects)
      if (data.organizations) dataService.setData('organizations', data.organizations)
      if (data.players) dataService.setData('players', data.players)
      if (data.finances) dataService.setData('finances', data.finances)
      if (data.knowledge) dataService.setData('knowledge', data.knowledge)
      if (data.settings) dataService.setData('settings', data.settings)

      await dataService.save()
      success('数据导入成功！')
      loadStats()
    } catch (err) {
      error(`导入失败：${err.message}`)
    }
  }
  input.click()
}

const showBackupModal = () => {
  showBackup.value = true
  loadBackups()
}

const loadBackups = async () => {
  backupLoading.value = true
  try {
    const data = await get('/api/data/list-backups')
    if (data.success) {
      backups.value = data.backups || []
    } else {
      backups.value = []
    }
  } catch (e) {
    console.error('加载备份列表失败:', e)
    backups.value = []
  } finally {
    backupLoading.value = false
  }
}

const createBackup = async () => {
  creatingBackup.value = true
  try {
    await dataService.load()
    const data = dataService.getData()
    const result = await post('/api/data/backup', data)
    if (result.success) {
      success(`备份创建成功：${result.backup_name}`)
      await loadBackups()
    } else {
      error(result.message || '创建备份失败')
    }
  } catch (e) {
    console.error('创建备份失败:', e)
    error(`创建备份失败: ${e.message}`)
  } finally {
    creatingBackup.value = false
  }
}

const restoreBackup = async (backup) => {
  const confirmed = await confirm({
    title: '恢复备份确认',
    message: `确定要恢复备份 "${backup.name}" 吗？当前数据将被覆盖，此操作不可撤销。`,
    type: 'warning'
  })
  if (!confirmed) return

  restoring.value = true
  restoreTarget.value = backup.name
  try {
    const result = await post('/api/data/restore', { backup_name: backup.name })
    if (result.success && result.data) {
      const data = result.data
      await dataService.load()
      if (data.projects) dataService.setData('projects', data.projects)
      if (data.organizations) dataService.setData('organizations', data.organizations)
      if (data.players) dataService.setData('players', data.players)
      if (data.finances) dataService.setData('finances', data.finances)
      if (data.knowledge) dataService.setData('knowledge', data.knowledge)
      if (data.settings) dataService.setData('settings', data.settings)
      await dataService.save()
      success('备份恢复成功！')
      await loadStats()
      showBackup.value = false
    } else {
      error(result.message || '恢复备份失败')
    }
  } catch (e) {
    console.error('恢复备份失败:', e)
    error(`恢复备份失败: ${e.message}`)
  } finally {
    restoring.value = false
    restoreTarget.value = ''
  }
}

const deleteBackupConfirm = async (backup) => {
  const confirmed = await confirm({
    title: '删除备份确认',
    message: `确定要删除备份 "${backup.name}" 吗？此操作不可撤销。`,
    type: 'warning'
  })
  if (!confirmed) return
  warning(`暂不支持在界面删除服务端备份，请手动删除 data/backup/${backup.name} 目录`)
}

const showExport = ref(false)
const exportOptions = ref({
  projects: true,
  organizations: true,
  players: true,
  finances: false,
  knowledge: false,
  projectFields: [],
  orgFields: [],
  playerFields: [],
  format: 'csv'
})

// 字段中文名映射（未收录的字段回退显示原始键名，保证新字段不会被静默漏掉）
const PROJECT_FIELD_LABELS = {
  name: '项目名称', type: '项目类型', status: '项目状态', manager: '负责人',
  startDate: '开始日期', endDate: '结束日期', description: '描述', orgIds: '关联机构',
  id: 'ID'
}
const ORG_FIELD_LABELS = {
  name: '机构名称', type: '机构类型', level: '合作等级', contact: '联系人',
  phone: '联系电话', address: '机构地址', note: '备注', id: 'ID'
}
const PLAYER_FIELD_LABELS = {
  name: '姓名', gender: '性别', category: '艺术类别', level: '专业等级',
  phone: '联系电话', idCard: '身份证号', orgId: '所属机构', projectId: '所属项目',
  stage: '赛段', stageHistory: '赛段历史', note: '备注', customFields: '自定义字段',
  id: 'ID'
}

// ⚠️ 字段清单由「实际数据」推导，而非硬编码：历史上硬编码过 level/budget/location/email
// 等并不存在的列（导出恒为空），同时漏掉了 orgIds/idCard 等真实字段。动态推导可杜绝漂移。
const projectFields = ref([])
const orgFields = ref([])
const playerFields = ref([])
const INTERNAL_FIELDS = ['createdAt', 'updatedAt']

const buildFields = (records, labels) => {
  const keys = new Set()
  ;(records || []).forEach(r => {
    if (r && typeof r === 'object') Object.keys(r).forEach(k => keys.add(k))
  })
  const out = []
  // 先按标签映射的既定顺序，再追加映射外的字段（按字母序）
  Object.keys(labels).forEach(k => {
    if (keys.has(k)) { out.push({ key: k, label: labels[k] }); keys.delete(k) }
  })
  ;[...keys].filter(k => !INTERNAL_FIELDS.includes(k)).sort()
    .forEach(k => out.push({ key: k, label: k }))
  return out
}

const showExportModal = async () => {
  try {
    await dataService.load()
  } catch (e) {
    console.error('导出前加载数据失败:', e)
  }
  const data = dataService.getData()
  projectFields.value = buildFields(data.projects, PROJECT_FIELD_LABELS)
  orgFields.value = buildFields(data.organizations, ORG_FIELD_LABELS)
  playerFields.value = buildFields(data.players, PLAYER_FIELD_LABELS)
  exportOptions.value = {
    projects: true,
    organizations: true,
    players: true,
    finances: false,
    knowledge: false,
    projectFields: projectFields.value.map(f => f.key),
    orgFields: orgFields.value.map(f => f.key),
    playerFields: playerFields.value.map(f => f.key),
    format: 'csv'
  }
  showExport.value = true
}

const allFieldsSelected = (type) => {
  if (type === 'projects') {
    return projectFields.value.every(f => exportOptions.value.projectFields.includes(f.key))
  } else if (type === 'organizations') {
    return orgFields.value.every(f => exportOptions.value.orgFields.includes(f.key))
  } else if (type === 'players') {
    return playerFields.value.every(f => exportOptions.value.playerFields.includes(f.key))
  }
  return false
}

const toggleAllFields = (type, event) => {
  const checked = event.target.checked
  if (type === 'projects') {
    exportOptions.value.projectFields = checked ? projectFields.value.map(f => f.key) : []
  } else if (type === 'organizations') {
    exportOptions.value.orgFields = checked ? orgFields.value.map(f => f.key) : []
  } else if (type === 'players') {
    exportOptions.value.playerFields = checked ? playerFields.value.map(f => f.key) : []
  }
}

const executeExport = () => {
  if (exportOptions.value.format === 'json') {
    exportDataJSON()
  } else {
    exportDataCSV()
  }
  showExport.value = false
}

const exportDataJSON = async () => {
  try {
    await dataService.load()
    const data = dataService.getData()
    const exportPayload = {
      projects: data.projects || [],
      organizations: data.organizations || [],
      players: data.players || [],
      finances: data.finances || [],
      knowledge: data.knowledge || {},
      settings: data.settings || {},
      exportDate: new Date().toISOString()
    }

    const jsonStr = JSON.stringify(exportPayload, null, 2)
    const blob = new Blob([jsonStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)

    const link = document.createElement('a')
    link.href = url
    link.download = `工作台数据备份_${new Date().toISOString().split('T')[0]}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('导出JSON失败:', e)
    error(`导出JSON失败: ${e.message}`)
  }
}

const exportDataCSV = async () => {
  try {
    await dataService.load()
  } catch (e) {
    console.error('加载数据失败:', e)
    alert({ title: '提示', message: '数据加载失败', type: 'warning' })
    return
  }
  const data = dataService.getData()
  if (!data) {
    alert({ title: '提示', message: '数据加载失败', type: 'warning' })
    return
  }

  let csvContent = '\uFEFF'
  let hasData = false

  const getFieldValue = (obj, key) => {
    const keys = key.split('.')
    let value = obj
    for (const k of keys) {
      value = value?.[k]
    }
    return value ?? ''
  }

  const escapeCSV = (value) => {
    const str = String(value)
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`
    }
    return str
  }

  if (exportOptions.value.projects && data.projects?.length > 0 && exportOptions.value.projectFields.length > 0) {
    hasData = true
    csvContent += '=== 项目数据 ===\n'
    csvContent += `${exportOptions.value.projectFields.map(f => {
      const field = projectFields.value.find(pf => pf.key === f)
      return field?.label || f
    }).join(',')}\n`

    data.projects.forEach(p => {
      csvContent += `${exportOptions.value.projectFields.map(f => escapeCSV(getFieldValue(p, f))).join(',')}\n`
    })
    csvContent += '\n'
  }

  if (exportOptions.value.organizations && data.organizations?.length > 0 && exportOptions.value.orgFields.length > 0) {
    hasData = true
    csvContent += '=== 机构数据 ===\n'
    csvContent += `${exportOptions.value.orgFields.map(f => {
      const field = orgFields.value.find(of => of.key === f)
      return field?.label || f
    }).join(',')}\n`

    data.organizations.forEach(o => {
      csvContent += `${exportOptions.value.orgFields.map(f => escapeCSV(getFieldValue(o, f))).join(',')}\n`
    })
    csvContent += '\n'
  }

  if (exportOptions.value.players && data.players?.length > 0 && exportOptions.value.playerFields.length > 0) {
    hasData = true
    csvContent += '=== 选手数据 ===\n'
    csvContent += `${exportOptions.value.playerFields.map(f => {
      const field = playerFields.value.find(pf => pf.key === f)
      return field?.label || f
    }).join(',')}\n`

    data.players.forEach(p => {
      csvContent += `${exportOptions.value.playerFields.map(f => escapeCSV(getFieldValue(p, f))).join(',')}\n`
    })
    csvContent += '\n'
  }

  if (exportOptions.value.finances && data.finances?.length > 0) {
    hasData = true
    csvContent += '=== 财务数据 ===\n'
    csvContent += 'ID,类型,分类,金额,日期,关联机构,关联项目,摘要,备注\n'

    data.finances.forEach(f => {
      const org = data.organizations?.find(o => o.id === f.orgId)
      const project = data.projects?.find(p => p.id === f.projectId)
      csvContent += `${[
        f.id,
        f.type,
        f.category,
        f.amount,
        f.date,
        escapeCSV(org?.name || ''),
        escapeCSV(project?.name || ''),
        escapeCSV(f.title || ''),
        escapeCSV(f.note || '')
      ].join(',')}\n`
    })
    csvContent += '\n'
  }

  if (!hasData) {
    warning('请至少选择一项要导出的数据')
    return
  }

  const blob = new Blob([csvContent], { type: 'application/vnd.ms-excel;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `工作台数据导出_${new Date().toISOString().split('T')[0]}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.settings-page {
  padding: 24px;
}

.settings-content {
  max-width: 800px;
  width: 100%;
  margin: 0;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.settings-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.settings-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 20px;
}

.settings-section h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-primary);
}

.section-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

/* 同一功能区内的子块（如「资源中心配置」下的存储目录 / 文件分类） */
.config-subblock + .config-subblock {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}
.subblock-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.system-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.status-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: 8px;
}

.status-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.status-detail {
  min-width: 0;
}

.status-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.status-loading {
  text-align: center;
  padding: 20px;
  color: var(--text-secondary);
  font-size: 14px;
}

.data-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.data-stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.data-stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.data-stat-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.settings-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.sync-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sync-status-row {
  display: flex;
  align-items: center;
  gap: 16px;
  justify-content: center;
}

.sync-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  flex: 1;
  max-width: 240px;
  transition: border-color 0.2s;
}

.sync-item.active {
  border-color: var(--accent);
}

.sync-item-icon {
  font-size: 24px;
}

.sync-item-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.sync-item-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.sync-arrow {
  font-size: 20px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.sync-recommendation {
  padding: 10px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.sync-recommendation.warning {
  border-color: var(--warning, #f59e0b);
  background: var(--warning-light, #fffbeb);
  color: var(--warning, #f59e0b);
}

.cleanup-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cleanup-stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.cleanup-stat-card {
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  text-align: center;
  border: 1px solid var(--border-light);
}

.cleanup-stat-card.has-warning {
  border-color: var(--warning, #f59e0b);
  background: var(--warning-light, #fffbeb);
}

.cleanup-stat-card .cleanup-stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.cleanup-stat-card.has-warning .cleanup-stat-value {
  color: var(--warning, #f59e0b);
}

.cleanup-stat-card .cleanup-stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.cleanup-config {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.cleanup-config label {
  font-size: 14px;
  color: var(--text-secondary);
}

.old-files-list {
  margin-top: 16px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  overflow: hidden;
}

.old-files-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: var(--bg-secondary);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.old-files-size {
  font-weight: 500;
  color: var(--text-secondary);
}

.old-files-items {
  max-height: 300px;
  overflow-y: auto;
}

.old-file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-top: 1px solid var(--border-light);
  transition: background 0.1s;
}

.old-file-item:hover {
  background: var(--bg-secondary);
}

.old-file-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.old-file-name {
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.old-file-meta {
  font-size: 11px;
  color: var(--text-tertiary);
}

.old-file-size {
  font-size: 13px;
  color: var(--text-secondary);
  flex-shrink: 0;
  margin-left: 12px;
}

.archive-path-config {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.path-input-group {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.path-input-group input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
}

.path-info {
  font-size: 13px;
}

.path-status {
  color: var(--text-secondary);
}

.path-status.configured {
  color: var(--success, #10b981);
}

.resource-category-config {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.category-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  transition: border-color 0.2s;
}

.category-item:hover {
  border-color: var(--accent);
}

.category-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.category-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.category-arrow {
  font-size: 13px;
  color: var(--text-tertiary);
}

.category-folder {
  font-size: 13px;
  color: var(--text-secondary);
  font-family: monospace;
  background: var(--bg-secondary);
  padding: 2px 8px;
  border-radius: 4px;
}

.category-actions {
  display: flex;
  gap: 4px;
}

.empty-hint {
  text-align: center;
  padding: 24px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.template-downloads {
  display: flex;
  gap: 12px;
}

.about-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.about-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.about-logo {
  font-size: 32px;
}

.about-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.about-title strong {
  font-size: 16px;
  color: var(--text-primary);
}

.about-version {
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-light);
}

.about-desc {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.about-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-light);
}

.about-detail-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.about-detail-label {
  font-size: 13px;
  color: var(--text-tertiary);
  min-width: 80px;
}

.about-detail-value {
  font-size: 13px;
  color: var(--text-secondary);
}

.btn-primary {
  background: var(--accent);
  color: white;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: var(--accent-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  padding: 8px 16px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-light);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-danger {
  background: #ef4444;
  color: white;
}

.btn-danger:hover {
  background: #dc2626;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
}

.btn-icon-text {
  padding: 4px 8px;
  background: transparent;
  color: var(--text-secondary);
  border: none;
  cursor: pointer;
  font-size: 13px;
  border-radius: 4px;
  transition: all 0.15s;
}

.btn-icon-text:hover {
  color: var(--text-primary);
  background: var(--bg-secondary);
}

.btn-icon-danger:hover {
  color: #ef4444;
  background: #fef2f2;
}

[data-theme="dark"] .btn-icon-danger:hover {
  background: rgba(239, 68, 68, 0.15);
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  color: var(--text-primary);
}

.form-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-secondary);
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-color);
}

.backup-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.backup-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
}

.backup-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.backup-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.backup-time {
  font-size: 13px;
  color: var(--text-secondary);
}

.backup-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--success-light, #ecfdf5);
  color: var(--success, #10b981);
}

.backup-badge.badge-warning {
  background: var(--warning-light, #fffbeb);
  color: var(--warning, #f59e0b);
}

.backup-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.modal-lg {
  max-width: 600px;
}

.export-config-content {
  max-height: 60vh;
  overflow-y: auto;
}

.config-section {
  margin-bottom: 20px;
}

.config-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.select-all {
  font-weight: normal;
  font-size: 13px;
  color: var(--text-secondary);
  margin-left: 8px;
}

.checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-primary);
}

.checkbox-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.folder-picker-path {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  margin-bottom: 12px;
}

.folder-current-path {
  font-size: 13px;
  color: var(--text-secondary);
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.folder-picker-list {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

.folder-picker-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.1s;
  border-bottom: 1px solid var(--border-light);
}

.folder-picker-item:last-child {
  border-bottom: none;
}

.folder-picker-item:hover {
  background: var(--accent-light, #eff6ff);
}

[data-theme="dark"] .folder-picker-item:hover {
  background: rgba(59, 130, 246, 0.1);
}

.folder-picker-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.folder-picker-name {
  font-size: 14px;
  color: var(--text-primary);
}

.radio-item {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-primary);
}

.radio-item input[type="radio"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.fields-group {
  background: var(--bg-primary);
  padding: 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
}

[data-theme="dark"] .btn-danger { background: var(--danger); }
[data-theme="dark"] .btn-danger:hover { background: #b91c1c; }
[data-theme="dark"] .sync-recommendation.warning { background: rgba(245, 158, 11, 0.1); }
[data-theme="dark"] .backup-badge { background: rgba(16, 185, 129, 0.15); }
[data-theme="dark"] .backup-badge.badge-warning { background: rgba(245, 158, 11, 0.15); }
</style>
