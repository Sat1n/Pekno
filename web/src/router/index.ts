import { createRouter, createWebHistory } from 'vue-router'

import Home from '@/views/Home.vue'
import Init from '@/views/Init.vue'
import Login from '@/views/Login.vue'
import { getAuthStatus, getStoredToken } from '@/lib/api'

let authStatusCache: { needs_initialization: boolean } | null = null

export async function resolveAuthStatus(force = false) {
  if (!force && authStatusCache) {
    return authStatusCache
  }

  authStatusCache = await getAuthStatus()
  return authStatusCache
}

export function clearAuthStatusCache() {
  authStatusCache = null
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: Home,
      meta: { requiresAuth: true },
    },
    {
      path: '/init',
      name: 'init',
      component: Init,
      meta: { public: true },
    },
    {
      path: '/login',
      name: 'login',
      component: Login,
      meta: { public: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const status = await resolveAuthStatus()

  if (status.needs_initialization) {
    if (to.path !== '/init') {
      return { path: '/init' }
    }
    return true
  }

  if (to.path === '/init') {
    return { path: getStoredToken() ? '/' : '/login' }
  }

  const requiresAuth = to.meta.requiresAuth !== false
  if (requiresAuth && !getStoredToken()) {
    if (to.path !== '/login') {
      return {
        path: '/login',
        query: to.fullPath !== '/' ? { redirect: to.fullPath } : {},
      }
    }
  }

  if (to.path === '/login' && getStoredToken()) {
    return { path: '/' }
  }

  return true
})

export default router
