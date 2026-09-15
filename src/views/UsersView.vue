<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import { useUserStore } from '../stores'
import { get } from '../services/http'
import { useToast } from '../composables/useToast'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'
import CustomSelect from '../components/CustomSelect.vue'

const userStore = useUserStore()
const { success, error } = useToast()

const searchKeyword = ref('')
const filterRole = ref('all')
const showAddModal = ref(false)
const showEditModal = ref(false)
const showDeleteModal = ref(false)
const deleteId = ref(null)

const newUser = ref({ realName: '', username: '', password: '', email: '', role: 'viewer' })
const editingUser = ref(null)
// 创建成功后展示一次性下发的初始密码（后端自动生成时才有）
const initialPasswordNotice = ref(null)

// 与后端 ROLE_PERMISSIONS 保持一致：admin / editor / viewer
const roles = [
  { value: 'all', label: '全部角色' },
  { value: 'admin', label: '管理员' },
  { value: 'editor', label: '编辑者' },
  { value: 'viewer', label: '查看者' }
]

const filteredUsers = computed(() => {
  let result = userStore.users

  if (filterRole.value !== 'all') {
    result = result.filter(u => u.role === filterRole.value)
  }

  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    result = result.filter(u =>
      u.realName?.toLowerCase().includes(kw) ||
      u.username?.toLowerCase().includes(kw) ||
      u.email?.toLowerCase().includes(kw)
    )
  }

  return result.sort((a, b) => new Date(b.createdAt || b.created_at || 0) - new Date(a.createdAt || a.created_at || 0))
})

const getRoleBadgeClass = (role) => {
  const classes = {
    admin: 'role-admin',
    editor: 'role-manager',
    viewer: 'role-user'
  }
  return classes[role] || 'role-user'
}

const getRoleLabel = (role) => {
  const labels = {
    admin: '管理员',
    editor: '编辑者',
    viewer: '查看者'
  }
  return labels[role] || role
}

const getStatusLabel = (status) => {
  return status === 'active' ? '活跃' : '停用'
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

// ============ 标签页：用户列表 / 角色权限 ============
const activeTab = ref('users')

// 权限矩阵（角色 × 模块 × 动作）
const matrix = ref(null)          // 当前编辑中的矩阵 { role: { module: [actions] } }
const matrixMeta = ref(null)      // 模块/动作定义与中文标签
const matrixLoading = ref(false)
const matrixSaving = ref(false)
const matrixError = ref('')
const matrixDirty = ref(false)

const canManageUsers = computed(() => userStore.can('users', 'edit'))

const loadMatrix = async () => {
  matrixLoading.value = true
  matrixError.value = ''
  try {
    const [rolesRes, meRes] = await Promise.all([
      get('/api/permissions/roles'),
      get('/api/permissions/me')
    ])
    if (rolesRes.success) {
      matrixMeta.value = {
        modules: rolesRes.modules,
        actions: rolesRes.actions,
        moduleLabels: rolesRes.module_labels,
        actionLabels: rolesRes.action_labels,
        roleLabels: rolesRes.role_labels
      }
      // 深拷贝，避免直接改动响应式缓存
      matrix.value = JSON.parse(JSON.stringify(rolesRes.roles))
      matrixDirty.value = false
    } else {
      matrixError.value = rolesRes.message || '加载权限矩阵失败'
    }
  } catch (e) {
    matrixError.value = e.message || '加载权限矩阵失败'
  } finally {
    matrixLoading.value = false
  }
}

const switchTab = (tab) => {
  activeTab.value = tab
  if (tab === 'permissions' && canManageUsers.value && !matrix.value) {
    loadMatrix()
  }
}

const hasAction = (role, module, action) => {
  const acts = matrix.value?.[role]?.[module] || []
  return acts.includes(action)
}

const toggleAction = (role, module, action) => {
  if (!matrix.value) return
  const acts = matrix.value[role][module] || []
  const idx = acts.indexOf(action)
  if (idx >= 0) {
    acts.splice(idx, 1)
  } else {
    acts.push(action)
  }
  matrixDirty.value = true
}

const saveMatrix = async () => {
  matrixSaving.value = true
  matrixError.value = ''
  try {
    await userStore.savePermissions(matrix.value)
    success('权限矩阵已保存')
    matrixDirty.value = false
    // 刷新当前用户自身权限（避免管理员把自己锁死后界面错乱）
    await userStore.loadPermissions()
  } catch (e) {
    matrixError.value = e.message || '保存失败'
    error(matrixError.value)
  } finally {
    matrixSaving.value = false
  }
}

const handleAdd = () => {
  newUser.value = { realName: '', username: '', password: '', email: '', role: 'viewer' }
  showAddModal.value = true
}

const submitAdd = async () => {
  if (!newUser.value.realName.trim()) return
  try {
    const result = await userStore.addUser({ ...newUser.value })
    showAddModal.value = false
    // 后端在未指定密码时会随机生成一个初始密码，仅此一次返回
    if (result?.initialPassword) {
      initialPasswordNotice.value = {
        username: result.user?.username || '',
        password: result.initialPassword
      }
    }
  } catch (e) {
    console.error('添加用户失败:', e)
  }
}

const handleEdit = (user) => {
  editingUser.value = { ...user }
  showEditModal.value = true
}

const submitEdit = async () => {
  if (!editingUser.value) return
  try {
    await userStore.updateUser(editingUser.value.id, {
      realName: editingUser.value.realName,
      email: editingUser.value.email,
      role: editingUser.value.role
    })
    showEditModal.value = false
    editingUser.value = null
  } catch (e) {
    console.error('编辑用户失败:', e)
  }
}

const handleToggleStatus = async (user) => {
  try {
    await userStore.toggleUserStatus(user.id)
  } catch (e) {
    console.error('切换状态失败:', e)
  }
}

const handleDelete = (id) => {
  deleteId.value = id
  showDeleteModal.value = true
}

const confirmDelete = async () => {
  if (!deleteId.value) return
  try {
    await userStore.deleteUser(deleteId.value)
    showDeleteModal.value = false
    deleteId.value = null
  } catch (e) {
    console.error('删除用户失败:', e)
  }
}

onMounted(() => {
  userStore.loadUsers()
  userStore.loadPermissions()
})

onActivated(() => {
  userStore.loadUsers()
  userStore.loadPermissions()
})
</script>

<template>
  <div class="users-view">
    <PageHeader
      title="用户管理"
      description="管理系统用户账号和权限"
    >
      <template #actions>
        <button class="btn btn-primary" @click="handleAdd">
          <span class="btn-icon">+</span>
          新增用户
        </button>
      </template>
    </PageHeader>

    <div class="tab-nav">
      <button class="tab-btn" :class="{ active: activeTab === 'users' }" @click="switchTab('users')">用户列表</button>
      <button class="tab-btn" :class="{ active: activeTab === 'permissions' }" :disabled="!canManageUsers" @click="switchTab('permissions')">角色权限</button>
    </div>

    <div v-if="activeTab === 'users'">
    <div class="filter-bar">
      <div class="filter-group">
        <CustomSelect v-model="filterRole">
          <option v-for="r in roles" :key="r.value" :value="r.value">{{ r.label }}</option>
        </CustomSelect>
      </div>
      <input
        v-model="searchKeyword"
        type="text"
        class="search-input"
        placeholder="搜索姓名、登录名或邮箱..."
      />
    </div>

    <div v-if="initialPasswordNotice" class="notice-bar">
      <span class="notice-text">
        用户「{{ initialPasswordNotice.username }}」已创建，初始密码：
        <strong class="notice-password">{{ initialPasswordNotice.password }}</strong>
        （仅显示一次，请转交本人并尽快修改）
      </span>
      <button class="notice-close" @click="initialPasswordNotice = null">知道了</button>
    </div>

    <div v-if="userStore.loading" class="loading-state">
      <span class="loading-icon">⏳</span>
      <span>加载中...</span>
    </div>

    <div v-else class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <th>姓名</th>
            <th>登录名</th>
            <th>邮箱</th>
            <th>角色</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="filteredUsers.length === 0">
            <td colspan="7" class="empty-cell">
              <div class="empty-state">
                <span class="empty-icon">👤</span>
                <span>暂无用户</span>
              </div>
            </td>
          </tr>
          <tr v-for="user in filteredUsers" :key="user.id">
            <td>
              <div class="user-cell">
                <span class="user-avatar">{{ (user.realName || user.username)?.charAt(0) }}</span>
                <span class="user-name">{{ user.realName || user.username }}</span>
              </div>
            </td>
            <td>{{ user.username || '-' }}</td>
            <td>{{ user.email || '-' }}</td>
            <td>
              <span class="role-badge" :class="getRoleBadgeClass(user.role)">
                {{ getRoleLabel(user.role) }}
              </span>
            </td>
            <td>
              <span class="status-badge" :class="user.isActive === 0 ? 'inactive' : 'active'">
                {{ user.isActive === 0 ? '停用' : '启用' }}
              </span>
            </td>
            <td>{{ formatDate(user.createdAt || user.created_at) }}</td>
            <td class="actions-cell">
              <button class="btn-icon-text" @click="handleEdit(user)">编辑</button>
              <button
                class="btn-icon-text"
                :class="{ 'text-warning': user.isActive !== 0 }"
                @click="handleToggleStatus(user)"
              >
                {{ user.isActive !== 0 ? '停用' : '启用' }}
              </button>
              <button class="btn-icon-text danger" @click="handleDelete(user.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    </div>

    <!-- ============ 角色权限矩阵 ============ -->
    <div v-else-if="activeTab === 'permissions'" class="permissions-view">
      <p class="section-desc matrix-desc">按模块配置每个角色可执行的动作（查看 / 编辑 / 删除）。修改后点击保存即时生效，并持久化到服务端。</p>
      <div v-if="!canManageUsers" class="notice-bar">
        <span class="notice-text">当前账号无「用户管理」权限，无法查看或修改权限矩阵。</span>
      </div>
      <div v-else-if="matrixLoading" class="loading-state">
        <span class="loading-icon">⏳</span>
        <span>加载中...</span>
      </div>
      <div v-else-if="matrixError" class="notice-bar">
        <span class="notice-text">{{ matrixError }}</span>
      </div>
      <template v-else-if="matrix && matrixMeta">
        <h3 class="section-title matrix-title">角色权限矩阵</h3>
        <div class="matrix-wrap">
          <table class="matrix-table">
            <thead>
              <tr>
                <th class="matrix-mod">模块</th>
                <th v-for="r in ['admin', 'editor', 'viewer']" :key="r" class="matrix-role">
                  {{ matrixMeta.roleLabels[r] || r }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in matrixMeta.modules" :key="m">
                <td class="matrix-mod">{{ matrixMeta.moduleLabels[m] || m }}</td>
                <td v-for="r in ['admin', 'editor', 'viewer']" :key="r" class="matrix-cell">
                  <label v-for="a in matrixMeta.actions" :key="a" class="matrix-check" :class="{ disabled: r === 'admin' }">
                    <input
                      type="checkbox"
                      :checked="hasAction(r, m, a)"
                      :disabled="r === 'admin'"
                      @change="toggleAction(r, m, a)"
                    />
                    <span>{{ matrixMeta.actionLabels[a] || a }}</span>
                  </label>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="matrix-foot">
          <span class="matrix-hint">管理员（admin）恒拥有全部权限，不可取消。查看=只读；编辑=新增/修改；删除=移除。</span>
          <div class="settings-actions">
            <button class="btn btn-secondary" :disabled="matrixLoading || !matrixDirty" @click="loadMatrix">重置</button>
            <button class="btn btn-primary" :disabled="matrixSaving || !matrixDirty" @click="saveMatrix">
              {{ matrixSaving ? '保存中...' : '保存权限矩阵' }}
            </button>
          </div>
        </div>
      </template>
    </div>

    <Modal
      :show="showAddModal"
      :title="newUser.role === 'admin' ? '新增管理员' : '新增用户'"
      size="medium"
      @close="showAddModal = false"
    >
      <div class="form-group">
        <label class="form-label">姓名 <span class="required">*</span></label>
        <input type="text" v-model="newUser.realName" class="form-input" placeholder="请输入姓名" />
      </div>
      <div class="form-group">
        <label class="form-label">登录名</label>
        <input type="text" v-model="newUser.username" class="form-input" placeholder="留空则按邮箱前缀自动生成" />
      </div>
      <div class="form-group">
        <label class="form-label">初始密码</label>
        <input type="text" v-model="newUser.password" class="form-input" placeholder="留空则自动生成并在此提示一次" />
      </div>
      <div class="form-group">
        <label class="form-label">邮箱</label>
        <input type="email" v-model="newUser.email" class="form-input" placeholder="请输入邮箱" />
      </div>
      <div class="form-group">
        <label class="form-label">角色</label>
        <CustomSelect v-model="newUser.role" style="width:100%">
          <option value="viewer">查看者（只读）</option>
          <option value="editor">编辑者（增改）</option>
          <option value="admin">管理员（全部权限）</option>
        </CustomSelect>
      </div>
      <template #footer>
        <button class="btn btn-secondary" @click="showAddModal = false">取消</button>
        <button class="btn btn-primary" @click="submitAdd" :disabled="!newUser.realName.trim()">创建</button>
      </template>
    </Modal>

    <Modal
      :show="showEditModal"
      title="编辑用户"
      size="medium"
      @close="showEditModal = false"
    >
      <template v-if="editingUser">
        <div class="form-group">
          <label class="form-label">姓名 <span class="required">*</span></label>
          <input type="text" v-model="editingUser.realName" class="form-input" />
        </div>
        <div class="form-group">
          <label class="form-label">邮箱</label>
          <input type="email" v-model="editingUser.email" class="form-input" />
        </div>
        <div class="form-group">
          <label class="form-label">角色</label>
          <CustomSelect v-model="editingUser.role" style="width:100%">
            <option value="viewer">查看者（只读）</option>
            <option value="editor">编辑者（增改）</option>
            <option value="admin">管理员（全部权限）</option>
          </CustomSelect>
        </div>
      </template>
      <template #footer>
        <button class="btn btn-secondary" @click="showEditModal = false">取消</button>
        <button class="btn btn-primary" @click="submitEdit" :disabled="!editingUser?.realName?.trim()">保存</button>
      </template>
    </Modal>

    <Modal
      :show="showDeleteModal"
      title="确认删除"
      size="small"
      @close="showDeleteModal = false"
    >
      <p>确定要删除这个用户吗？此操作不可撤销。</p>
      <template #footer>
        <button class="btn btn-secondary" @click="showDeleteModal = false">取消</button>
        <button class="btn btn-danger" @click="confirmDelete">确认删除</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.users-view {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  gap: 12px;
}

.search-input {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  flex: 1;
  min-width: 160px;
  width: auto;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.notice-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--accent);
  border-left-width: 4px;
  border-radius: 8px;
  flex-wrap: wrap;
}

.notice-text {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
}

.notice-password {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 15px;
  letter-spacing: 1px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--accent);
}

.notice-close {
  padding: 6px 14px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}

.notice-close:hover {
  background: var(--bg-hover);
}

.loading-icon {
  font-size: 24px;
}

.table-container {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.data-table th {
  background: var(--bg-tertiary);
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary);
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: white;
  font-weight: 600;
  border-radius: 50%;
  font-size: 14px;
}

.user-name {
  font-weight: 500;
}

.role-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.role-admin {
  background: var(--accent-light);
  color: var(--accent);
}

.role-manager {
  background: var(--success-light);
  color: var(--success);
}

.role-user {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.status-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.status-badge.active {
  background: var(--success-light);
  color: var(--success-color);
}

.status-badge.inactive {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.actions-cell {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.btn-icon-text {
  padding: 4px 8px;
  background: none;
  border: none;
  color: var(--primary-color);
  cursor: pointer;
  font-size: 13px;
  border-radius: 4px;
}

.btn-icon-text:hover {
  background: var(--bg-hover);
}

.btn-icon-text.danger {
  color: var(--danger-color);
}

.btn-icon-text.text-warning {
  color: var(--warning-color);
}

.empty-cell {
  text-align: center;
  padding: 60px 20px !important;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 48px;
  opacity: 0.5;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--text-primary);
}

.required {
  color: var(--danger-color);
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--primary-color);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-light);
}

.btn-danger {
  background: var(--danger-color);
  color: white;
}

.btn-icon {
  font-size: 16px;
}

/* ============ 角色权限矩阵（对齐系统卡片/表格规范） ============ */
.matrix-desc {
  margin-bottom: 20px;
}

.matrix-title {
  margin-bottom: 16px;
}

.matrix-wrap {
  background: var(--surface);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow-x: auto;
}

.matrix-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 560px;
}

.matrix-table th,
.matrix-table td {
  padding: 14px 18px;
  text-align: left;
  border-bottom: 1px solid var(--border-light);
  vertical-align: top;
}

.matrix-table thead th {
  background: var(--bg-secondary);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
}

.matrix-table tbody tr:last-child td {
  border-bottom: none;
}

.matrix-table tbody tr:hover td {
  background: var(--bg-hover);
}

.matrix-mod {
  font-weight: 500;
  color: var(--text-primary);
  background: var(--bg-secondary);
  white-space: nowrap;
}

.matrix-role {
  text-align: center;
}

.matrix-cell {
  min-width: 140px;
}

.matrix-check {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.matrix-check input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
  cursor: pointer;
  flex-shrink: 0;
}

.matrix-check.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.matrix-check:not(.disabled):hover {
  color: var(--text-primary);
}

.matrix-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 20px;
  flex-wrap: wrap;
}

.matrix-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.6;
  flex: 1;
  min-width: 220px;
}

[data-theme="dark"] .matrix-wrap {
  background: var(--surface);
  border-color: var(--border);
}

[data-theme="dark"] .matrix-table thead th {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

[data-theme="dark"] .matrix-table th,
[data-theme="dark"] .matrix-table td {
  border-color: var(--border);
}

[data-theme="dark"] .matrix-mod {
  background: var(--bg-secondary);
}
</style>
