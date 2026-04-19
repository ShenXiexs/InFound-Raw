import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { createPinia } from 'pinia'
import { rendererStore } from './store/renderer-store.ts'

const app = createApp(App)

app.use(createPinia())

await rendererStore.init()

app.mount('#app')
