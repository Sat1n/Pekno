<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useColorMode } from '@vueuse/core'
import { Search, Activity, Clock, Settings, Sun, Moon, Monitor, LayoutList, LayoutGrid, Rows3, Bell, Plus, Archive } from 'lucide-vue-next'
import { Sidebar, SidebarContent, SidebarGroup, SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import SettingsDialog from '@/components/SettingsDialog.vue'
import PluginSettingsDialog from '@/components/PluginSettingsDialog.vue'
import {
  clearNotifications,
  clearStoredToken,
  getNotifications,
  getStoredAuthUser,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationItem,
} from '@/lib/api'

const props = withDefaults(defineProps<{
  searchPlaceholder?: string
}>(), {
  searchPlaceholder: '搜索 GitHub 项目...',
})

defineEmits<{
  search: []
  addContent: []
}>()

const notifications = ref<NotificationItem[]>([])
const isLoadingNotifications = ref(false)
const unreadCount = computed(() => notifications.value.filter((notification) => notification.status !== 'read').length)
let notificationPollTimer: number | undefined

function addNotification(notification: NotificationItem) {
  const exists = notifications.value.some((existing) => existing.id === notification.id)
  if (exists) return
  notifications.value.unshift(notification)
}

async function loadNotifications() {
  if (isLoadingNotifications.value) return
  isLoadingNotifications.value = true
  try {
    notifications.value = await getNotifications(30)
  } catch (error) {
    console.error('加载通知失败:', error)
  } finally {
    isLoadingNotifications.value = false
  }
}

async function markAsRead(id: string) {
  const notification = notifications.value.find((entry) => entry.id === id)
  if (!notification || notification.status === 'read') return

  try {
    const updated = await markNotificationRead(id)
    notifications.value = notifications.value.map((entry) => (entry.id === id ? updated : entry))
  } catch (error) {
    console.error('标记通知已读失败:', error)
  }
}

async function markAllAsRead() {
  if (!notifications.value.length) return
  try {
    await markAllNotificationsRead()
    notifications.value = notifications.value.map((notification) => ({
      ...notification,
      status: 'read',
      read_at: notification.read_at || new Date().toISOString(),
    }))
  } catch (error) {
    console.error('全部标记已读失败:', error)
  }
}

async function clearAll() {
  try {
    await clearNotifications()
    notifications.value = []
  } catch (error) {
    console.error('清空通知失败:', error)
  }
}

function formatTime(value: string): string {
  const date = new Date(value)
  const now = Date.now()
  const diff = now - date.getTime()
  const minutes = Math.floor(diff / 60000)
  
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}小时前`
  return `${Math.floor(minutes / 1440)}天前`
}

const mode = useColorMode()
const router = useRouter()
const route = useRoute()
const currentUser = computed(() => getStoredAuthUser())
const usernameLabel = computed(() => currentUser.value.username || 'Guest')
const userInitials = computed(() => usernameLabel.value.slice(0, 2).toUpperCase())

// 布局模式 v-model
const layoutMode = defineModel<'list' | 'grid' | 'compact'>('layout', { default: 'list' })

// 搜索关键词 v-model
const searchQuery = defineModel<string>('searchQuery', { default: '' })

const SIDEBAR_STATE_KEY = 'pekno-sidebar-open'

// 系统设置弹窗状态
const isSettingsOpen = ref(false)
const settingsTab = ref('plugins')
const sidebarOpen = ref(true)

// 插件设置弹窗状态
const isPluginSettingsOpen = ref(false)
const activePluginId = ref('')

function openPluginSettings(pluginId: string) {
  activePluginId.value = pluginId
  isPluginSettingsOpen.value = true
}

defineExpose({
  addNotification,
})

const navMain = computed(() => {
  const items: Array<{ title: string; icon: any; to: string; disabled?: boolean }> = [
    { title: '探索 (Explore)', icon: Search, to: '/' },
    { title: '稍后再看', icon: Clock, to: '/watch-later' },
    { title: '收藏库 / Vault', icon: Archive, to: '/vault' },
  ]
  if (currentUser.value.role === 'super_admin') {
    items.push({ title: '动态 (Activity) [开发中]', icon: Activity, to: '/activity', disabled: true })
  }
  return items
})

async function logout() {
  clearStoredToken()
  await router.replace('/login')
}

async function navigateTo(path: string, disabled?: boolean) {
  if (disabled || route.path === path) {
    return
  }
  await router.push(path)
}

onMounted(() => {
  const savedSidebarState = window.localStorage.getItem(SIDEBAR_STATE_KEY)
  if (savedSidebarState === 'false') {
    sidebarOpen.value = false
  }

  void loadNotifications()
  notificationPollTimer = window.setInterval(() => {
    void loadNotifications()
  }, 45000)
  window.addEventListener('focus', handleWindowFocus)

  if (route.query.openSettings === 'models') {
    settingsTab.value = 'models'
    isSettingsOpen.value = true
    router.replace({ path: route.path })
  }
  if (route.query.openSettings === 'plugins') {
    settingsTab.value = 'plugins'
    isSettingsOpen.value = true
  }
  if (typeof route.query.pluginId === 'string' && route.query.pluginId) {
    openPluginSettings(route.query.pluginId)
  }
})

watch(sidebarOpen, (value) => {
  window.localStorage.setItem(SIDEBAR_STATE_KEY, String(value))
})

watch(
  () => route.query,
  (query) => {
    if (query.openSettings === 'plugins') {
      settingsTab.value = 'plugins'
      isSettingsOpen.value = true
    }
    if (typeof query.pluginId === 'string' && query.pluginId) {
      openPluginSettings(query.pluginId)
    }
  }
)

onBeforeUnmount(() => {
  if (notificationPollTimer !== undefined) {
    window.clearInterval(notificationPollTimer)
  }
  window.removeEventListener('focus', handleWindowFocus)
})

function handleWindowFocus() {
  void loadNotifications()
}

async function handleNotificationClick(notification: NotificationItem) {
  await markAsRead(notification.id)

  if (notification.related_plugin_id) {
    await router.push({
      path: route.path,
      query: {
        ...route.query,
        openSettings: 'plugins',
        pluginId: notification.related_plugin_id,
      },
    })
    return
  }

  if (!notification.related_item_id) {
    return
  }

  const targetPath = notification.category === 'vault_processing' ? '/vault' : route.path === '/vault' ? '/vault' : '/'
  await router.push({
    path: targetPath,
    query: {
      item: notification.related_item_id,
    },
  })
}
</script>

<template>
  <SidebarProvider :open="sidebarOpen" @update:open="sidebarOpen = $event">
    <div class="flex flex-col h-screen w-full bg-background transition-colors duration-300">
      
      <header class="h-14 border-b border-border flex items-center justify-between px-4 sticky top-0 z-50 bg-background/80 backdrop-blur-md">
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2 px-2">
            <div class="w-7 h-7 bg-primary rounded flex items-center justify-center">
              <span class="text-primary-foreground font-bold text-lg">I</span>
            </div>
            <span class="font-bold text-lg tracking-tight hidden md:block">Iris Hub</span>
          </div>
          <SidebarTrigger />
        </div>

        <div class="flex-1 max-w-xl relative group mx-4">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input 
            v-model="searchQuery"
            :placeholder="props.searchPlaceholder" 
            class="w-full pl-9 bg-muted/50 border-transparent focus:bg-background rounded-md h-9 transition-all"
            @keyup.enter="$emit('search')"
          />
        </div>

        <div class="flex items-center gap-2">
          <Button variant="default" size="sm" class="hidden md:inline-flex gap-2 mr-2" @click="$emit('addContent')">
            <Plus class="w-4 h-4" />
            添加内容
          </Button>

          <!-- 布局切换按钮 -->
          <div class="flex items-center gap-1 bg-muted/50 p-1 rounded-md mr-2">
            <Button
              variant="ghost" size="sm" class="h-8 w-8 p-0"
              :class="{ 'bg-background shadow-sm': layoutMode === 'list' }"
              @click="layoutMode = 'list'"
            >
              <LayoutList class="h-4 w-4" />
            </Button>
            <Button
              variant="ghost" size="sm" class="h-8 w-8 p-0"
              :class="{ 'bg-background shadow-sm': layoutMode === 'grid' }"
              @click="layoutMode = 'grid'"
            >
              <LayoutGrid class="h-4 w-4" />
            </Button>
            <Button
              variant="ghost" size="sm" class="h-8 w-8 p-0"
              :class="{ 'bg-background shadow-sm': layoutMode === 'compact' }"
              @click="layoutMode = 'compact'"
            >
              <Rows3 class="h-4 w-4" />
            </Button>
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger as-child>
            <Button variant="ghost" size="icon" class="h-9 w-9">
                <Sun class="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
                <Moon class="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem @click="mode = 'light'"><Sun class="mr-2 h-4 w-4"/>亮色</DropdownMenuItem>
              <DropdownMenuItem @click="mode = 'dark'"><Moon class="mr-2 h-4 w-4"/>暗色</DropdownMenuItem>
              <DropdownMenuItem @click="mode = 'auto'"><Monitor class="mr-2 h-4 w-4"/>跟随系统</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <!-- 通知铃铛 -->
          <Button variant="ghost" size="icon" class="h-9 w-9 md:hidden" @click="$emit('addContent')">
            <Plus class="h-4 w-4" />
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button variant="ghost" size="icon" class="h-9 w-9 relative">
                <Bell class="h-4 w-4" />
                <span 
                  v-if="unreadCount > 0" 
                  class="absolute -top-1 -right-1 h-4 w-4 bg-destructive text-destructive-foreground text-[10px] font-bold rounded-full flex items-center justify-center"
                >
                  {{ unreadCount > 9 ? '9+' : unreadCount }}
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="w-80">
              <div class="flex items-center justify-between px-3 py-2 border-b">
                <span class="font-semibold">通知</span>
                <div class="flex gap-1">
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    class="h-6 text-xs"
                    @click="markAllAsRead"
                  >
                    全部已读
                  </Button>
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    class="h-6 text-xs text-muted-foreground"
                    @click="clearAll"
                  >
                    清除
                  </Button>
                </div>
              </div>
              
              <!-- 通知列表 -->
              <div class="max-h-80 overflow-y-auto">
                <div v-if="notifications.length === 0" class="p-4 text-center text-muted-foreground text-sm">
                  暂无通知
                </div>
                <div 
                  v-for="notification in notifications" 
                  :key="notification.id"
                  class="px-3 py-2 border-b last:border-0 hover:bg-muted/50 cursor-pointer transition-colors"
                  :class="{ 'bg-muted/30': notification.status !== 'read' }"
                  @click="handleNotificationClick(notification)"
                >
                  <div class="flex gap-2">
                    <div 
                      class="w-2 h-2 rounded-full mt-2 flex-shrink-0"
                      :class="{
                        'bg-green-500': notification.type === 'success',
                        'bg-red-500': notification.type === 'error',
                        'bg-blue-500': notification.type === 'info',
                        'bg-yellow-500': notification.type === 'warning',
                      }"
                    ></div>
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center justify-between">
                        <span class="font-medium text-sm truncate">{{ notification.title }}</span>
                        <span class="text-xs text-muted-foreground ml-2">{{ formatTime(notification.created_at) }}</span>
                      </div>
                      <p class="text-xs text-muted-foreground truncate">{{ notification.description }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button variant="ghost" class="h-10 px-2 gap-2">
                <Avatar class="h-8 w-8 cursor-pointer border">
                  <AvatarFallback>{{ userInitials }}</AvatarFallback>
                </Avatar>
                <div class="hidden md:flex flex-col items-start leading-none">
                  <span class="text-sm font-medium">{{ usernameLabel }}</span>
                  <span class="text-[11px] text-muted-foreground">{{ currentUser.role || 'admin' }}</span>
                </div>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="w-48">
              <DropdownMenuItem disabled>
                {{ usernameLabel }}
              </DropdownMenuItem>
              <DropdownMenuItem @click="logout">
                退出登录
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <div class="flex min-h-0 flex-1 overflow-hidden">
        <Sidebar class="top-14 h-[calc(100vh-3.5rem)] border-r bg-muted/30">
          <SidebarContent>
            <SidebarGroup>
              <SidebarMenu>
                <SidebarMenuItem v-for="item in navMain" :key="item.title">
                  <SidebarMenuButton
                    class="py-5"
                    :class="{ 'bg-background text-foreground shadow-sm': route.path === item.to }"
                    :disabled="item.disabled"
                    @click="navigateTo(item.to, item.disabled)"
                  >
                    <component :is="item.icon" class="w-4 h-4 mr-2" />
                    <span>{{ item.title }}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroup>
          </SidebarContent>
          <div class="mt-auto p-4 border-t border-border space-y-2">
            <SidebarMenuButton 
              class="w-full justify-start hover:bg-muted/50"
              @click="isSettingsOpen = true; settingsTab = 'plugins'"
            >
              <Settings class="w-4 h-4 mr-2" />
              <span>系统设置</span>
            </SidebarMenuButton>
          </div>
        </Sidebar>

        <main class="min-h-0 min-w-0 flex-1 overflow-y-auto bg-background px-8 py-6 lg:px-12 xl:px-16 custom-scrollbar">
          <div class="mx-auto w-full min-w-0 max-w-[1920px]">
            <slot />
          </div>
        </main>
      </div>
    </div>

    <!-- 系统设置弹窗 -->
    <SettingsDialog 
      :open="isSettingsOpen" 
      :initial-tab="settingsTab"
      @close="isSettingsOpen = false"
      @open-plugin-settings="openPluginSettings"
    />
    
    <!-- 插件设置弹窗 -->
    <PluginSettingsDialog 
      v-model:open="isPluginSettingsOpen" 
      :plugin-id="activePluginId"
    />
  </SidebarProvider>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background-color: #27272a; border-radius: 10px; }
:deep(.group[data-collapsible=icon]) {
  height: 100%;
}
</style>
