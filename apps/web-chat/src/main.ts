import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

// 单 SPA 入口；路由 / Pinia / 全局 store 由 WT-E2 在主控集成期补齐
const app = createApp(App)
app.mount('#app')
