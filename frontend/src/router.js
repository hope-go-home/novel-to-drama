import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Home', component: () => import('./pages/Home.vue') },
  { path: '/create', name: 'Create', component: () => import('./pages/Create.vue') },
  { path: '/project/:id', name: 'Project', component: () => import('./pages/Project.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
