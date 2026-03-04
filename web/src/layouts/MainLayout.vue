<script setup lang="ts">
import { useColorMode } from '@vueuse/core'
import { Search, Activity, Clock, Github, Tv, Settings, Sun, Moon, Monitor, LayoutList, LayoutGrid, Rows3 } from 'lucide-vue-next'
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupLabel, SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

const mode = useColorMode()

// 布局模式 v-model
const layoutMode = defineModel<'list' | 'grid' | 'compact'>('layout', { default: 'list' })

const navMain = [
  { title: '探索 (Explore)', icon: Search },
  { title: '动态 (Activity)', icon: Activity },
  { title: '稍后再看', icon: Clock },
]

const plugins = [
  { name: 'GitHub Stars', icon: Github },
  { name: 'Bilibili', icon: Tv },
]
</script>

<template>
  <SidebarProvider>
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
            placeholder="搜索..." 
            class="w-full pl-9 bg-muted/50 border-transparent focus:bg-background rounded-md h-9 transition-all"
          />
        </div>

        <div class="flex items-center gap-2">
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

          <Avatar class="h-8 w-8 cursor-pointer border">
            <AvatarImage src="https://github.com/shadcn.png" />
            <AvatarFallback>NT</AvatarFallback>
          </Avatar>
        </div>
      </header>

      <div class="flex flex-1 overflow-hidden">
        <Sidebar class="top-14 h-[calc(100vh-3.5rem)] border-r bg-muted/30">
          <SidebarContent>
            <SidebarGroup>
              <SidebarMenu>
                <SidebarMenuItem v-for="item in navMain" :key="item.title">
                  <SidebarMenuButton class="py-5">
                    <component :is="item.icon" class="w-4 h-4 mr-2" />
                    <span>{{ item.title }}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroup>
          </SidebarContent>
          <div class="mt-auto p-4 border-t border-border">
            <SidebarMenuButton class="w-full justify-start hover:bg-muted/50">
              <Settings class="w-4 h-4 mr-2" />
              <span>系统设置</span>
            </SidebarMenuButton>
          </div>
        </Sidebar>

        <main class="flex-1 overflow-y-auto bg-background py-6 px-8 lg:px-12 xl:px-16 custom-scrollbar">
          <div class="w-full max-w-[1920px] mx-auto">
            <slot />
          </div>
        </main>
      </div>
    </div>
  </SidebarProvider>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background-color: #27272a; border-radius: 10px; }
:deep(.group[data-collapsible=icon]) {
  height: 100%;
}
</style>