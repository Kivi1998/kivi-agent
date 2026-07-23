// Vue Router 配置：2 个 chat 路由 + 3 个 dashboard 路由（WT-G4）

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import SessionListView from '@/views/SessionList.vue'
import ChatView from '@/views/ChatView.vue'
import Dashboard from '@/views/Dashboard.vue'
import DashboardRunDetail from '@/views/DashboardRunDetail.vue'
import DashboardCaseDetail from '@/views/DashboardCaseDetail.vue'

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
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: Dashboard
  },
  {
    path: '/dashboard/runs/:runId',
    name: 'dashboard-run-detail',
    component: DashboardRunDetail,
    props: true
  },
  {
    path: '/dashboard/runs/:runId/cases/:caseId',
    name: 'dashboard-case-detail',
    component: DashboardCaseDetail,
    props: true
  }
]

export const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
