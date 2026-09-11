<template>
  <Teleport to="body">
    <div v-if="show" class="modal-overlay" :class="{ active: show }" @click.self="handleClose">
      <div class="modal login-modal">
        <div class="modal-header">
          <h3>{{ isChangePassword ? '修改密码' : '用户登录' }}</h3>
          <button v-if="!isChangePassword" class="modal-close" @click="handleClose">&times;</button>
        </div>
        <div class="modal-body">
          <form v-if="!isChangePassword" @submit.prevent="handleLogin">
            <div class="form-group">
              <label class="form-label">用户名 <span class="required">*</span></label>
              <input
                type="text"
                class="form-input"
                v-model="username"
                placeholder="请输入用户名"
                required
              />
            </div>
            <div class="form-group">
              <label class="form-label">密码 <span class="required">*</span></label>
              <input
                type="password"
                class="form-input"
                v-model="password"
                placeholder="请输入密码"
                autocomplete="current-password"
                required
              />
            </div>
            <div v-if="errorMessage" class="form-error">{{ errorMessage }}</div>
            <div class="form-actions">
              <button type="submit" class="btn-primary" :disabled="loading">
                {{ loading ? '登录中...' : '登录' }}
              </button>
            </div>
          </form>
          <form v-else @submit.prevent="handleChangePassword">
            <div class="change-password-notice">
              <span class="notice-icon">⚠️</span>
              <span>首次登录需要修改初始密码</span>
            </div>
            <div class="form-group">
              <label class="form-label">新密码 <span class="required">*</span></label>
              <input
                type="password"
                class="form-input"
                v-model="newPassword"
                placeholder="请输入新密码（至少6位）"
                autocomplete="new-password"
                required
              />
            </div>
            <div class="form-group">
              <label class="form-label">确认密码 <span class="required">*</span></label>
              <input
                type="password"
                class="form-input"
                v-model="confirmPassword"
                placeholder="请再次输入新密码"
                autocomplete="new-password"
                required
              />
            </div>
            <div v-if="errorMessage" class="form-error">{{ errorMessage }}</div>
            <div class="form-actions">
              <button type="submit" class="btn-primary" :disabled="loading">
                {{ loading ? '修改中...' : '确认修改' }}
              </button>
            </div>
          </form>
          <div v-if="!isChangePassword" class="login-tip">
            <p>首次使用时，系统会自动生成管理员账号和随机密码，请查看服务端日志获取初始密码。</p>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch } from 'vue'
import { login } from '../services/auth'
// 修复：下面调用了 post('/api/users/change-password')，但从未导入 post，
// 导致"首次登录强制改密"这条路一进就抛 ReferenceError
import { post } from '../services/http.js'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'login-success'])

const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMessage = ref('')
const isChangePassword = ref(false)
const newPassword = ref('')
const confirmPassword = ref('')
const currentUser = ref(null)

const show = ref(false)

watch(() => props.modelValue, (val) => {
  show.value = val
  if (!val) {
    resetForm()
  }
})

const handleClose = () => {
  emit('update:modelValue', false)
}

const resetForm = () => {
  username.value = ''
  password.value = ''
  errorMessage.value = ''
  loading.value = false
  isChangePassword.value = false
  newPassword.value = ''
  confirmPassword.value = ''
  currentUser.value = null
}

const handleLogin = async () => {
  if (!username.value || !password.value) {
    errorMessage.value = '请输入用户名和密码'
    return
  }

  errorMessage.value = ''
  loading.value = true

  try {
    const result = await login(username.value, password.value)
    if (result.success) {
      if (result.user && result.user.mustChangePassword) {
        isChangePassword.value = true
        currentUser.value = result.user
        errorMessage.value = ''
      } else {
        emit('login-success', result.user)
        handleClose()
      }
    } else {
      errorMessage.value = result.message || '登录失败'
    }
  } catch (error) {
    errorMessage.value = error.message || '登录失败，请检查网络连接'
  } finally {
    loading.value = false
  }
}

const handleChangePassword = async () => {
  if (!newPassword.value || newPassword.value.length < 6) {
    errorMessage.value = '密码长度至少6位'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }

  errorMessage.value = ''
  loading.value = true

  try {
    const data = await post('/api/users/change-password', {
      userId: currentUser.value?.id || currentUser.value?.user_id,
      newPassword: newPassword.value
    })
    if (data.success) {
      isChangePassword.value = false
      emit('login-success', { ...currentUser.value, mustChangePassword: false })
      handleClose()
    } else {
      errorMessage.value = data.message || '修改密码失败'
    }
  } catch (error) {
    errorMessage.value = error.message || '修改密码失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: none;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-overlay.active {
  display: flex;
}

.modal {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  max-width: 90vw;
  max-height: 90vh;
  overflow: auto;
}

.login-modal {
  width: 400px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-light);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-tertiary);
  padding: 0;
  line-height: 1;
}

.modal-close:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 24px;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.required {
  color: var(--danger);
}

.form-input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 14px;
  outline: none;
  transition: all var(--transition-fast);
  background-color: var(--surface);
}

.form-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-light);
}

.form-error {
  color: var(--danger);
  font-size: 13px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--danger-light);
  border-radius: var(--radius-sm);
}

.form-actions {
  margin-top: 20px;
}

.btn-primary {
  width: 100%;
  padding: 12px 24px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-tip {
  margin-top: 16px;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  font-size: 13px;
}

.login-tip p {
  margin: 0;
  color: var(--text-secondary);
}

.login-tip strong {
  color: var(--text-primary);
}

.change-password-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  margin-bottom: 16px;
  background: var(--warning-light, #fff8e1);
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--warning, #f57c00);
}

.notice-icon {
  font-size: 18px;
}
</style>
