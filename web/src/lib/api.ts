import axios from 'axios'

const TOKEN_KEY = 'pekno-access-token'

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setStoredToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearStoredToken() {
  localStorage.removeItem(TOKEN_KEY)
}

function decodeBase64Url(value: string): string | null {
  try {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized + '='.repeat((4 - (normalized.length % 4 || 4)) % 4)
    return decodeURIComponent(
      atob(padded)
        .split('')
        .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, '0')}`)
        .join('')
    )
  } catch {
    return null
  }
}

export interface StoredAuthUser {
  id: string | null
  username: string | null
  role: string | null
}

export function getStoredAuthUser(): StoredAuthUser {
  const token = getStoredToken()
  if (!token) {
    return { id: null, username: null, role: null }
  }

  const parts = token.split('.')
  if (parts.length < 2) {
    return { id: null, username: null, role: null }
  }

  const payloadText = decodeBase64Url(parts[1])
  if (!payloadText) {
    return { id: null, username: null, role: null }
  }

  try {
    const payload = JSON.parse(payloadText) as { sub?: string; role?: string; uid?: string }
    return {
      id: payload.uid ?? null,
      username: payload.sub ?? null,
      role: payload.role ?? null,
    }
  } catch {
    return { id: null, username: null, role: null }
  }
}

// API 客户端配置
export const apiClient = axios.create({
  baseURL: 'http://localhost:8001', // FastAPI 后端地址
  timeout: 10000, // 10 秒超时
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      clearStoredToken()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// 搜索结果的接口定义
export interface SearchResult {
  id: string
  title: string
  summary: string
  long_summary?: string
  has_long_summary: boolean
  cover_url?: string
  author?: string
  raw_link?: string
  score: number
  source: string
  tags: string[]
  time: string
  is_read?: boolean
  is_starred?: boolean
}

export interface RawItem {
  id: string
  title: string
  source_type: string
  raw_link: string
  summary?: string | null
  content_text?: string | null
  tags: string[]
  intent: string
  created_at: string
  metadata_extra?: Record<string, any> | null
  is_read: boolean
  is_starred: boolean
}

export interface AuthStatus {
  needs_initialization: boolean
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
  role: string
}

export interface InvitationCodeInfo {
  id: string
  code: string
  is_used: boolean
  used_by_username?: string | null
  created_at: string
}

export interface ModelProviderField {
  key: string
  label: string
  type: 'string'
  secret?: boolean
  default?: string
}

export interface ModelProviderInfo {
  id: string
  name: string
  description: string
  badge?: string
  capabilities: string[]
  config_fields: ModelProviderField[]
  config: Record<string, string>
  is_configured: boolean
  secret_preview?: string | null
}

export interface ModelAssignmentInfo {
  key: string
  label: string
  description: string
  group: string
  status: 'active' | 'planned'
  task_type: 'llm' | 'embedding' | 'speech' | 'vision' | 'video'
  default_provider: string
  default_model: string
  provider: string
  model: string
}

// 搜索参数接口
export interface SearchParams {
  q?: string
  limit?: number
}

/**
 * 全局混合搜索（语义 + 关键词）
 * @param params 搜索参数
 * @returns 搜索结果列表
 */
export async function search(params: SearchParams = {}): Promise<SearchResult[]> {
  const response = await apiClient.get<SearchResult[]>('/api/search', {
    params: {
      q: params.q || '',
    },
  })
  return response.data
}

/**
 * 搜索 GitHub 项目（仅 GitHub 数据）
 * @param params 搜索参数
 * @returns 搜索结果列表
 */
export async function searchGitHub(params: SearchParams = {}): Promise<SearchResult[]> {
  const response = await apiClient.get<SearchResult[]>('/api/search/github', {
    params: {
      q: params.q || '',
      limit: params.limit || 20,
    },
  })
  return response.data
}

/**
 * 获取所有条目
 * @param limit 返回数量限制
 * @param offset 偏移量
 * @returns 条目列表
 */
export async function getItems(
  limit?: number,
  offset: number = 0,
  options: { starredOnly?: boolean } = {}
): Promise<RawItem[]> {
  const params: Record<string, number | boolean> = { offset }
  if (typeof limit === 'number') {
    params.limit = limit
  }
  if (options.starredOnly) {
    params.starred_only = true
  }

  const response = await apiClient.get<RawItem[]>('/api/items', {
    params,
  })
  return response.data
}

export async function toggleItemStar(itemId: string): Promise<{ item_id: string; is_read: boolean; is_starred: boolean }> {
  const response = await apiClient.post(`/api/items/${itemId}/star`)
  return response.data
}

export async function markItemsReadBatch(itemIds: string[]): Promise<{ status: string; updated_count: number }> {
  const response = await apiClient.post('/api/items/read_batch', {
    item_ids: itemIds,
  })
  return response.data
}

export async function getAuthStatus(): Promise<AuthStatus> {
  const response = await apiClient.get<AuthStatus>('/api/auth/status')
  return response.data
}

export async function initializeAuth(payload: { username: string; password: string }): Promise<AuthTokenResponse> {
  const response = await apiClient.post<AuthTokenResponse>('/api/auth/init', payload)
  return response.data
}

export async function login(payload: { username: string; password: string }): Promise<AuthTokenResponse> {
  const response = await apiClient.post<AuthTokenResponse>('/api/auth/login', payload)
  return response.data
}

export async function register(payload: { username: string; password: string; invite_code: string }): Promise<AuthTokenResponse> {
  const response = await apiClient.post<AuthTokenResponse>('/api/auth/register', payload)
  return response.data
}

export async function changePassword(payload: { current_password: string; new_password: string }): Promise<{ status: string; message: string }> {
  const response = await apiClient.post('/api/auth/change_password', payload)
  return response.data
}

export async function createInvitationCode(): Promise<InvitationCodeInfo> {
  const response = await apiClient.post<InvitationCodeInfo>('/api/admin/invitations')
  return response.data
}

export async function getInvitationCodes(): Promise<InvitationCodeInfo[]> {
  const response = await apiClient.get<InvitationCodeInfo[]>('/api/admin/invitations')
  return response.data
}

export async function getModelProviders(): Promise<{ providers: ModelProviderInfo[]; assignments: ModelAssignmentInfo[] }> {
  const response = await apiClient.get('/api/admin/models/providers')
  return response.data
}

export async function saveModelProvider(providerId: string, payload: Record<string, string>): Promise<{ providers: ModelProviderInfo[]; assignments: ModelAssignmentInfo[] }> {
  const response = await apiClient.put(`/api/admin/models/providers/${providerId}`, payload)
  return response.data
}

export async function getModelAssignments(): Promise<{ assignments: ModelAssignmentInfo[] }> {
  const response = await apiClient.get('/api/admin/models/assignments')
  return response.data
}

export async function saveModelAssignments(assignments: ModelAssignmentInfo[]): Promise<{ assignments: ModelAssignmentInfo[] }> {
  const response = await apiClient.put('/api/admin/models/assignments', {
    assignments,
  })
  return response.data
}

/**
 * 触发 AI 总结任务
 * @param itemId 项目 ID
 * @returns 任务信息
 */
export async function summarizeItem(itemId: string): Promise<{
  status: string
  task_id: string
  message: string
}> {
  const response = await apiClient.post(`/api/items/${itemId}/summarize`)
  return response.data
}

// AI 总结状态接口
export interface SummaryStatus {
  item_id: string
  status: 'pending' | 'completed' | 'not_found'
  summary?: string
}

/**
 * 查询某条目的 AI 总结完成状态
 * @param itemId 项目 ID
 * @returns 总结状态（pending / completed）
 */
export async function getItemSummaryStatus(itemId: string): Promise<SummaryStatus> {
  const response = await apiClient.get<SummaryStatus>(`/api/items/${itemId}/summary_status`)
  return response.data
}

// ========== 动态插件 API ==========

export interface PluginSettingSchema {
  type: 'string' | 'boolean' | 'integer' | 'select'
  label: string
  scope?: 'system' | 'user'
  description?: string
  default?: any
  secret?: boolean
  required?: boolean
  min?: number
  max?: number
  options?: { label: string; value: string }[]
}

export interface PluginManifestData {
  id: string
  name: string
  description: string
  version: string
  author: string
  settings_schema: Record<string, PluginSettingSchema>
}

export interface PluginInfo {
  manifest: PluginManifestData
  config: Record<string, any>
  has_token: boolean
  token_preview: string | null
}

/**
 * 获取所有插件清单和当前配置
 */
export async function getAllPlugins(): Promise<PluginInfo[]> {
  const response = await apiClient.get<PluginInfo[]>('/api/plugins')
  return response.data
}

/**
 * 动态保存插件配置
 */
export async function savePluginConfigApi(pluginId: string, config: Record<string, any>): Promise<{ status: string; message: string }> {
  const response = await apiClient.post(`/api/plugins/${pluginId}/config`, config)
  return response.data
}

/**
 * 触发插件同步
 */
export async function triggerPluginSyncApi(pluginId: string): Promise<{ status: string; task_id?: string; message: string }> {
  const response = await apiClient.post(`/api/plugins/${pluginId}/sync`)
  return response.data
}

/**
 * 预检插件 (上传 ZIP)
 */
export async function uploadPluginPreviewApi(file: File): Promise<{ temp_token: string; manifest: any; source_code: string; file_structure: string[] }> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await apiClient.post('/api/plugins/upload_preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return response.data
}

/**
 * 确认安装插件
 */
export async function confirmInstallPluginApi(token: string): Promise<{ status: string; message: string }> {
  const response = await apiClient.post(`/api/plugins/confirm_install`, null, {
    params: { token }
  })
  return response.data
}

/**
 * 卸载插件
 */
export async function uninstallPluginApi(pluginId: string): Promise<{ status: string; message: string }> {
  const response = await apiClient.delete(`/api/plugins/${pluginId}`)
  return response.data
}

// ----------------------------------------------------------------------------
// 全局数据管理相关接口
// ----------------------------------------------------------------------------

export interface DataSourceStat {
  source_type: string
  count: number
}

/**
 * 获取所有数据源的统计信息
 */
export async function getDataSources(): Promise<DataSourceStat[]> {
  const response = await apiClient.get<DataSourceStat[]>('/api/data/sources')
  return response.data
}

/**
 * 清除特定数据源的所有数据
 * @param sourceType 数据源标识，例如 github_star
 */
export async function clearDataSource(sourceType: string): Promise<{ status: string; message: string; deleted_count: number }> {
  const response = await apiClient.delete(`/api/data/sources/${sourceType}`)
  return response.data
}

/**
 * 获取 GitHub 同步状态
 * @returns 状态
 */
export async function getGitHubSyncStatus(): Promise<{ status: 'idle' | 'running'; last_sync_time?: string }> {
  const response = await apiClient.get('/api/config/github/status')
  return response.data
}
