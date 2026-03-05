import { ref, reactive } from 'vue'
import { getGitHubConfig, type GitHubConfig } from '@/lib/api'

// 创建全局状态
const githubConfig = ref<GitHubConfig>({
  has_token: false,
  sync_limit: 100,
  auto_sync: false,
})

const isLoading = ref(false)

// 加载GitHub配置
async function loadGitHubConfig() {
  isLoading.value = true
  try {
    const data = await getGitHubConfig()
    githubConfig.value = data
  } catch (error) {
    console.error('加载GitHub配置失败:', error)
  } finally {
    isLoading.value = false
  }
}

// 更新GitHub配置
function updateGitHubConfig(config: Partial<GitHubConfig>) {
  githubConfig.value = { ...githubConfig.value, ...config }
}

// 导出状态和方法
export function usePluginStore() {
  return {
    githubConfig,
    isLoading,
    loadGitHubConfig,
    updateGitHubConfig,
  }
}
