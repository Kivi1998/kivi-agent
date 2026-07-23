// Vue Router 配置：2 个路由（SessionList / ChatView）

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import SessionListView from '@/views/SessionList.vue'
import ChatView from '@/views/ChatView.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'session-list',
    component: SessionListView
  },
  {
    path: '/chat/:sessionId',
    name: 'chat',
    component: ChatView,
    props: true
  }
]

export const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
