// 应用入口：创建 app + pinia + router + 注入 session API
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { createSessionApi } from './api/session'
import { useSessionStore } from './stores/session'
import './style.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// 注入 session API 客户端到 store（默认用 /api 前缀走 Vite 代理）
const sessionApi = createSessionApi()
const sessionStore = useSessionStore()
sessionStore.setApi(sessionApi)

app.mount('#app')
