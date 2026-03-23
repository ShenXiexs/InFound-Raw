<script lang="ts" setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInst, FormRules } from 'naive-ui'
import { useMessage } from 'naive-ui'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { rendererStore } from '@renderer/store/renderer-store'
import { resolveResourceAssetUrl } from '@renderer/utils/asset-url'
import { REGEX } from '@common/app-constants'
import { AppConfig } from '@common/app-config'

interface LoginForm {
  username: string
  password: string
}

const router = useRouter()
const message = useMessage()
const formRef = ref<FormInst | null>(null)
const isSubmitting = ref(false)
const showAlert = ref(false)
const alertMessage = ref('')
const signUpUrl = AppConfig.OFFICIAL_WEBSITE_BASE_URL + '/signup'

const formValue = ref<LoginForm>({
  username: '',
  password: ''
})
const onlyAllowNumber = (value: string): boolean => !value || REGEX.NUMBER.test(value)
const rules = computed<FormRules>(() => ({
  username: [
    {
      required: true,
      len: 11,
      message: '请输入正确的手机号',
      validator: () => {
        const username = formValue.value.username.trim()
        if (!username) return new Error('请输入手机号')
        if (!REGEX.PHONE.test(username)) return new Error('请输入正确的手机号')
        return true
      },
      trigger: ['input', 'blur']
    }
  ],
  password: [
    {
      required: true,
      message: '请输入密码',
      validator: () => {
        // 密码长度范围 8 ~ 16，字母、数字、特殊符号 三选二，不允许中间有空格
        const password = formValue.value.password.trim()
        if (!password) return new Error('请输入密码')
        // 明确检查长度范围
        if (password.length < 8 || password.length > 16) {
          return new Error('密码长度必须在 8 到 16 位之间')
        }
        //if (!REGEX.PASSWORD.test(password)) return new Error('密码长度范围 8 ~ 16，字母、数字、特殊符号 三选二，不允许中间有空格')
        return true
      },
      trigger: ['input', 'blur']
    }
  ]
}))

const canSubmit = computed(() => {
  return formValue.value.username.trim().length > 0 && formValue.value.password.length > 0
})

const logo = computed(() => {
  return resolveResourceAssetUrl(rendererStore.currentState.appSetting.resourcesPath, 'logo.png')
})

const onSubmit = async (): Promise<void> => {
  if (!canSubmit.value || isSubmitting.value) return

  try {
    showAlert.value = false
    alertMessage.value = ''
    await formRef.value?.validate()
  } catch {
    return
  }

  isSubmitting.value = true
  const username = formValue.value.username.trim()
  const password = formValue.value.password.trim()

  try {
    const result = await window.ipc.invoke(IPC_CHANNELS.API_AUTH_LOGIN, username, password)
    if (!result.success) {
      showAlert.value = true
      alertMessage.value = result.error || '登录失败，请稍后重试'
      return
    }

    const stateResult = await window.ipc.invoke(IPC_CHANNELS.APP_GLOBAL_STATE_GET_ALL)
    if (stateResult.success) {
      rendererStore.currentState.currentUser = stateResult.data.currentUser ?? undefined
      rendererStore.currentState.isLogin = Boolean(stateResult.data.isLogin)
      rendererStore.currentState.enableDebug = Boolean(stateResult.data.enableDebug)
    }

    const token = rendererStore.currentState.currentUser?.tokenValue?.trim()
    if (!rendererStore.currentState.isLogin || !token) {
      showAlert.value = true
      alertMessage.value = '登录状态同步失败，请重试'
      return
    }

    message.success('登录成功，正在跳转')
    await router.replace('/')
  } catch (error) {
    window.logger.error('登录失败', error)
    showAlert.value = true
    alertMessage.value = '登录失败，请稍后重试'
  } finally {
    isSubmitting.value = false
  }
}

const onSignup = (): void => {
  window.ipc.send(IPC_CHANNELS.APP_OPEN_EXTERNAL_LINK, signUpUrl)
}

/*onMounted(() => {
  if (route.query.needLogin === '1') {
    message.warning('请先登录')
  }
})*/
</script>

<template>
  <div class="login-page">
    <n-card :bordered="false" class="login-card">
      <template #header>
        <div class="header-block">
          <img :src="logo" alt="Xunda" class="brand-logo" />
        </div>
      </template>

      <n-form ref="formRef" :model="formValue" :rules="rules" class="auth-form">
        <n-form-item :show-label="false" path="username">
          <div class="input-shell">
            <div class="prefix">中国大陆 +86</div>
            <n-input v-model:value="formValue.username" :allow-input="onlyAllowNumber" :bordered="false" class="input-core" placeholder="请输入您的手机号" />
          </div>
        </n-form-item>

        <n-form-item :show-label="false" path="password">
          <div class="input-shell">
            <n-input
              v-model:value="formValue.password"
              :bordered="false"
              class="input-core"
              placeholder="请输入账号密码"
              show-password-on="click"
              type="password"
              @keydown.enter="onSubmit"
            />
          </div>
        </n-form-item>
        <n-space :size="[0, 20]" vertical>
          <n-alert v-if="showAlert" type="warning">{{ alertMessage }}</n-alert>
          <n-button :disabled="!canSubmit || isSubmitting" :loading="isSubmitting" block size="large" type="primary" @click="onSubmit">立即登录</n-button>
        </n-space>
      </n-form>

      <template #footer>
        <div class="footer-tip">
          <span>还没有账号？</span>
          <n-button text type="primary" @click="onSignup"> 点击注册 </n-button>
        </div>
      </template>
    </n-card>
  </div>
</template>

<style lang="scss" scoped>
.login-page {
  min-height: calc(100vh - 45px);
  display: grid;
  place-items: center;
  padding: 24px;
  box-sizing: border-box;
  background:
    radial-gradient(circle at 15% 10%, #eaf5ff 0, #eaf5ff 24%, transparent 45%), radial-gradient(circle at 85% 90%, #f3f6ff 0, #f3f6ff 20%, transparent 44%),
    linear-gradient(135deg, #f8fbff 0%, #ffffff 42%, #f5f8ff 100%);
}

.login-card {
  width: min(440px, 92vw);
  height: 600px;
  border-radius: 16px;
  box-shadow: 0 14px 36px rgba(14, 34, 70, 0.08);
}

.header-block {
  margin: 0;
  padding: 0;
  text-align: center;
}

.brand-logo {
  width: clamp(176px, 40vw, 240px);
  height: auto;
  aspect-ratio: 1 / 1;
  object-fit: contain;
  display: block;
  margin: 0 auto;
  padding: 0;
}

.auth-form {
  width: min(340px, 100%);
  margin: 8px auto 0;
}

.auth-form :deep(.n-form-item) {
  width: 100%;
}

.input-shell {
  width: 100%;
  height: 48px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  display: flex;
  align-items: stretch;
  overflow: hidden;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.input-shell:focus-within {
  border-color: #8142f6;
  box-shadow: 0 0 0 2px rgba(129, 66, 246, 0.18);
}

.prefix {
  display: inline-flex;
  align-items: center;
  height: 100%;
  background: #f3f4f6;
  color: #4b5563;
  font-size: 13px;
  padding: 0 12px;
  border-right: 1px solid #e5e7eb;
  white-space: nowrap;
}

.input-core {
  flex: 1;
}

.input-core :deep(.n-input) {
  height: 100%;
  --n-border: 0px;
  --n-border-hover: 0px;
  --n-border-focus: 0px;
  --n-box-shadow-focus: none;
}

.input-core :deep(.n-input-wrapper) {
  height: 100%;
  padding-left: 12px;
  padding-right: 12px;
}

.input-core :deep(.n-input__input-el) {
  height: 100%;
  line-height: 48px;
  padding-top: 0;
  padding-bottom: 0;
}

.auth-form :deep(.n-form-item.n-form-item--error .input-shell) {
  border-color: #d03050;
  box-shadow: 0 0 0 2px rgba(208, 48, 80, 0.12);
}

.auth-form :deep(.n-form-item.n-form-item--error .prefix) {
  border-right-color: #d03050;
}

.footer-tip {
  color: #6b7280;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}
</style>
