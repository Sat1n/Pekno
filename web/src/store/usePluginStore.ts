import { ref } from 'vue'
import { getAllPlugins, savePluginConfigApi, triggerPluginSyncApi, type PluginInfo } from '@/lib/api'

// 创建全局状态
const pluginsManifests = ref<PluginInfo[]>([])
const isLoading = ref(false)

// 加载所有插件配置
async function loadAllPlugins() {
  isLoading.value = true
  try {
    const data = await getAllPlugins()
    pluginsManifests.value = data
  } catch (error) {
    console.error('加载插件配置失败:', error)
  } finally {
    isLoading.value = false
  }
}

// 保存插件配置
async function savePluginConfig(pluginId: string, configData: Record<string, any>) {
  try {
    await savePluginConfigApi(pluginId, configData)
  } catch (error) {
    console.error(`保存插件 ${pluginId} 配置失败:`, error)
    throw error
  }
}

// 触发插件同步
async function triggerPluginSync(pluginId: string) {
  try {
    await triggerPluginSyncApi(pluginId)
  } catch (error) {
    console.error(`触发插件 ${pluginId} 同步失败:`, error)
    throw error
  }
}

// 导出状态和方法
export function usePluginStore() {
  return {
    pluginsManifests,
    isLoading,
    loadAllPlugins,
    savePluginConfig,
    triggerPluginSync,
  }
}
