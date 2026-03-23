import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { rendererStore } from '@renderer/store/renderer-store'
// 通用字体
import 'vfonts/Lato.css'
// 等宽字体
import 'vfonts/FiraCode.css'

import App from './App.vue'
import router from '@renderer/pages/portal/router'

const app = createApp(App)

app.use(createPinia())

await rendererStore.init()

app.use(router)

await router.isReady()
app.mount('#app')
