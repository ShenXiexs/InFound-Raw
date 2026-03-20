import { createRouter, createWebHashHistory } from 'vue-router'
import LoadingView from './loading/Index.vue'
import ErrorView from './error/Index.vue'

const router = createRouter({
  // history: createWebHistory(import.meta.env.BASE_URL),
  history: createWebHashHistory(),
  routes: [
    {
      path: '/loading',
      name: 'loading',
      component: LoadingView
    },
    {
      path: '/error',
      name: 'error',
      component: ErrorView
    }
  ]
})

export default router
