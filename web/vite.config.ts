import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite' // 引入插件

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(), // 注册插件
  ],
})