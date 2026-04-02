import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '@renderer/pages/portal/views/Home.vue'
import LoginView from '@renderer/pages/portal/views/Login.vue'
import { AppState } from '@infound/desktop-base'
import { rendererStore } from '@renderer/store/renderer-store'

const router = createRouter({
  // history: createWebHistory(import.meta.env.BASE_URL),
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { requiresAuth: true }
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView
    }
  ]
})

const PLACEHOLDER_USER_ID = '00000000-0000-0000-0000-000000000001'

const hasValidSession = (globalState: AppState): boolean => {
  const currentUser = globalState.currentUser
  const userId = currentUser?.userId?.trim()
  const username = currentUser?.username?.trim()
  const tokenName = currentUser?.tokenName?.trim()
  const tokenValue = currentUser?.tokenValue?.trim()
  return Boolean(
    globalState.isLogin &&
      userId &&
      userId !== PLACEHOLDER_USER_ID &&
      username &&
      tokenName &&
      tokenValue
  )
}

// 登录验证
router.beforeEach((to, _from, next) => {
  const globalState: AppState = rendererStore.currentState
  const isLoggedIn = hasValidSession(globalState)

  if (to.path === '/login') {
    if (isLoggedIn) {
      return next({ path: '/' })
    }
    return next()
  }

  if (to.meta.requiresAuth) {
    // 需要登录权限进入的路由
    if (!isLoggedIn) {
      return next({
        path: '/login',
        query: { needLogin: '1' }
      })
    }
    return next()
  } else {
    // 不需要权限登录的直接进行下一步
    return next()
  }
})

export default router
