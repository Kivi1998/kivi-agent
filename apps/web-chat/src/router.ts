// Vue Router 配置：2 个 chat 路由 + 3 个 dashboard 路由（WT-G4） + 6 个新 dashboard 路由（WT-H4） + 1 个 memory dashboard 路由（WT-J4）

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import SessionListView from '@/views/SessionList.vue'
import ChatView from '@/views/ChatView.vue'
import Dashboard from '@/views/Dashboard.vue'
import DashboardRunDetail from '@/views/DashboardRunDetail.vue'
import DashboardCaseDetail from '@/views/DashboardCaseDetail.vue'
// Wave 5.2 WT-H4：T11 + T12 dashboard views
import TeamDashboard from '@/views/TeamDashboard.vue'
import TeamDashboardDetail from '@/views/TeamDashboardDetail.vue'
import TeamCaseDetail from '@/views/TeamCaseDetail.vue'
import CodingDashboard from '@/views/CodingDashboard.vue'
import CodingDashboardDetail from '@/views/CodingDashboardDetail.vue'
// Wave 6.1 WT-J4：前端记忆管理 UI
import MemoryDashboard from '@/views/MemoryDashboard.vue'

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
  },
  // --- Wave 5.2 WT-H4: T11 多 Agent 协作 dashboard 路由 ---
  {
    path: '/dashboard/team',
    name: 'team-dashboard',
    component: TeamDashboard
  },
  {
    path: '/dashboard/team/:teamId',
    name: 'team-dashboard-detail',
    component: TeamDashboardDetail,
    props: true
  },
  {
    path: '/dashboard/team/:teamId/cases/:caseId',
    name: 'team-case-detail',
    component: TeamCaseDetail,
    props: true
  },
  // --- Wave 5.2 WT-H4: T12 coding Agent dashboard 路由 ---
  {
    path: '/dashboard/coding',
    name: 'coding-dashboard',
    component: CodingDashboard
  },
  {
    path: '/dashboard/coding/:runId',
    name: 'coding-dashboard-detail',
    component: CodingDashboardDetail,
    props: true
  },
  // --- Wave 6.1 WT-J4: 记忆管理 dashboard 路由 ---
  {
    path: '/dashboard/memory',
    name: 'memory-dashboard',
    component: MemoryDashboard
  }
]

export const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
