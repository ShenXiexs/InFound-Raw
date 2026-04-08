<script lang="ts" setup>
import { onMounted, ref } from 'vue'
import { createDiscreteApi, NInput } from 'naive-ui'
import { changePassword, fetchCurrentUser } from '../api/user.api'

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const isSubmitting = ref(false)

const displayUserName = ref('—')

const { message } = createDiscreteApi(['message'])

const loadUsername = async (): Promise<void> => {
  const u = await fetchCurrentUser()
  if (u?.username?.trim()) {
    displayUserName.value = u.username.trim()
  }
}

const goBackSettings = (): void => {
  window.location.hash = '#/settings?tab=profile'
}

const handleSubmit = async (): Promise<void> => {
  const oldPasswordValue = oldPassword.value.trim()
  const newPasswordValue = newPassword.value.trim()
  const confirmPasswordValue = confirmPassword.value.trim()

  if (!oldPasswordValue) {
    message.warning('请输入原密码')
    return
  }
  if (!newPasswordValue) {
    message.warning('请输入新密码')
    return
  }
  if (!confirmPasswordValue) {
    message.warning('请输入确认新密码')
    return
  }
  if (newPasswordValue !== confirmPasswordValue) {
    message.error('两次输入的新密码不一致')
    return
  }
  if (isSubmitting.value) return

  isSubmitting.value = true
  try {
    await changePassword({
      oldPassword: oldPasswordValue,
      newPassword: newPasswordValue,
      confirmPassword: confirmPasswordValue
    })
    message.success('密码修改成功')
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (error: any) {
    const backendMessage = error?.response?.data?.msg
    message.error(backendMessage || error?.message || '密码修改失败')
  } finally {
    isSubmitting.value = false
  }
}

onMounted(() => {
  void loadUsername()
})
</script>

<template>
  <div class="change-password-page">
    <div class="header-row">
      <h1 class="page-title">修改密码</h1>
      <button class="back-link" type="button" @click="goBackSettings">返回设置</button>
    </div>
    <div class="title-rule" />

    <div class="form-wrap">
      <div class="form-row">
        <span class="row-label">用户名：</span>
        <span class="row-static">{{ displayUserName }}</span>
      </div>
      <div class="form-row">
        <span class="row-label">原密码：</span>
        <n-input
          v-model:value="oldPassword"
          class="row-input"
          type="password"
          show-password-on="click"
          placeholder="请输入原密码"
        />
      </div>
      <div class="form-row">
        <span class="row-label">新密码：</span>
        <n-input
          v-model:value="newPassword"
          class="row-input"
          type="password"
          show-password-on="click"
          placeholder="请输入新密码"
        />
      </div>
      <div class="form-row">
        <span class="row-label">确认新密码：</span>
        <n-input
          v-model:value="confirmPassword"
          class="row-input"
          type="password"
          show-password-on="click"
          placeholder="请再输入一遍新密码"
        />
      </div>

      <div class="action-row">
        <button class="submit-btn" :disabled="isSubmitting" type="button" @click="handleSubmit">
          {{ isSubmitting ? '提交中...' : '确认修改' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.change-password-page {
  padding: 20px 28px 40px;
  width: 100%;
  background: #ffffff;
  min-height: 100vh;
  box-sizing: border-box;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.back-link {
  display: inline-block;
  margin-bottom: 0;
  padding: 0;
  border: none;
  background: none;
  font-size: 13px;
  color: #0f67ff;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.title-rule {
  height: 1px;
  background: #111827;
  margin: 12px 0 28px;
  max-width: 100%;
}

.form-wrap {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.action-row {
  display: flex;
  padding-left: 136px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 14px;
}

.row-label {
  width: 120px;
  flex-shrink: 0;
  text-align: right;
  color: #374151;
}

.row-static {
  color: #111827;
}

.row-input {
  flex: 1;
  max-width: 360px;
}

.submit-btn {
  min-width: 120px;
  height: 38px;
  border: 0;
  border-radius: 8px;
  background: #0f67ff;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

:deep(.row-input.n-input) {
  border-radius: 6px;
}

@media (max-width: 560px) {
  .header-row,
  .form-row {
    flex-direction: column;
    align-items: stretch;
  }

  .row-label {
    width: auto;
    text-align: left;
  }

  .row-input {
    max-width: none;
  }

  .action-row {
    padding-left: 0;
  }
}
</style>
