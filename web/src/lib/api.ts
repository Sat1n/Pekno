import axios from 'axios'
import i18n from '@/i18n'

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

  const payloadText = decodeBase64Url(parts[1] as string)
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

export const API_BASE_URL = String(apiClient.defaults.baseURL || '').replace(/\/$/, '')

export function buildAuthorizedHeaders(): Record<string, string> | undefined {
  const token = getStoredToken()
  if (!token) return undefined
  return {
    Authorization: `Bearer ${token}`,
  }
}

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
  local_asset_url?: string | null
  source_type?: string
  intent?: string
  metadata_extra?: Record<string, any>
  score: number
  source: string
  tags: string[]
  time: string
  is_read?: boolean
  is_watch_later?: boolean
  is_favorited?: boolean
  is_starred?: boolean
}

export interface RawItem {
  id: string
  title: string
  source_type: string
  raw_link: string
  local_asset_url?: string | null
  summary?: string | null
  content_text?: string | null
  tags: string[]
  intent: string
  created_at: string
  metadata_extra?: Record<string, any> | null
  vault_category_id?: string | null
  is_read: boolean
  is_watch_later: boolean
  is_favorited: boolean
  is_starred?: boolean
}

export interface AcceptedTaskResponse {
  status: string
  task_id: string
  message: string
}

export interface AnnotationItem {
  id: string
  item_id: string
  type: string
  content_raw: string
  anchor_data: Record<string, any>
  created_at: string
}

export interface AnnotationAssetUploadResult {
  asset_url: string
  content_type: string
  page?: number | null
  rect_norm?: Record<string, number> | null
}

export interface VaultCategory {
  id: string
  name: string
  color?: string | null
  sort_order: number
  created_at: string
}

export interface NotificationItem {
  id: string
  type: 'success' | 'error' | 'info' | 'warning'
  category: 'summary' | 'upload_processing' | 'plugin_sync' | 'vault_processing' | string
  title: string
  description: string
  status: 'unread' | 'read' | string
  related_item_id?: string | null
  related_plugin_id?: string | null
  created_at: string
  read_at?: string | null
}

export interface UploadDedupResponse {
  message: string
  item_id: string
  deduplicated: boolean
  item: RawItem
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
  task_type: 'llm' | 'embedding' | 'speech' | 'vision' | 'video' | 'ocr'
  default_provider: string
  default_model: string
  provider: string
  model: string
}

export interface SystemBillingSettings {
  api_limit_type: 'token' | 'cost'
  api_limit_value: number
  currency: 'USD' | 'CNY' | 'EUR'
  used_tokens: number
  used_cost: number
  limit_exceeded: boolean
}

export interface PluginHealthItem {
  plugin_id: string
  name: string
  last_successful_sync_at?: string | null
  last_sync_at?: string | null
  sync_status: string
  status: 'Healthy' | 'Stale' | 'Error'
  auto_sync: boolean
  auto_sync_interval?: number | null
  last_error?: string | null
}

export interface AdminMetricsResponse {
  rag_backlog_count: number
  api_today_total_cost: number
  api_limit_type: 'token' | 'cost'
  api_limit_value: number
  used_tokens: number
  used_cost: number
  limit_exceeded: boolean
  billing_warning: boolean
  warning_threshold_ratio: number
  billing_currency: 'USD' | 'CNY' | 'EUR'
  abnormal_plugin_count: number
  plugins: PluginHealthItem[]
}

export interface UsageTrendPoint {
  date: string
  total_tokens: number
  total_cost: number
}

export interface AdminUsageTrendResponse {
  api_limit_type: 'token' | 'cost'
  api_limit_value: number
  currency: 'USD' | 'CNY' | 'EUR'
  used_tokens: number
  used_cost: number
  limit_exceeded: boolean
  billing_warning: boolean
  warning_threshold_ratio: number
  points: UsageTrendPoint[]
}

export interface AdminLogTailResponse {
  service: 'hub' | 'worker' | 'scheduler'
  content: string
  lines: number
}

export interface ForceProcessResponse {
  status: 'accepted'
  requeued_count: number
  message: string
}

export interface ApiErrorPayload {
  error_code?: string
  detail?: string
}

export function getApiErrorPayload(error: any): ApiErrorPayload {
  const payload = error?.response?.data
  if (payload && typeof payload === 'object') {
    return {
      error_code: typeof payload.error_code === 'string' ? payload.error_code : undefined,
      detail: typeof payload.detail === 'string' ? payload.detail : undefined,
    }
  }
  return {}
}

export function resolveApiErrorMessage(error: any, fallbackKey: string = 'errors.fallback'): string {
  const payload = getApiErrorPayload(error)
  if (payload.error_code) {
    const key = `errors.${payload.error_code}`
    if (i18n.global.te(key)) {
      return String(i18n.global.t(key))
    }
  }
  if (payload.detail) {
    return payload.detail
  }
  return String(i18n.global.t(fallbackKey))
}

// 搜索参数接口
export interface SearchParams {
  q?: string
  limit?: number
  source_type?: string
  favorited_only?: boolean
}

/**
 * 全局混合搜索（语义 + 关键词）
 * @param params 搜索参数
 * @returns 搜索结果列表
 */
export async function search(params: SearchParams = {}): Promise<SearchResult[]> {
  const queryParams: Record<string, any> = { q: params.q || '' }
  if (params.source_type && params.source_type !== 'all') {
    queryParams.source_type = params.source_type
  }
  if (params.favorited_only) {
    queryParams.favorited_only = true
  }
  const response = await apiClient.get<SearchResult[]>('/api/search', {
    params: queryParams,
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
  options: { watchLaterOnly?: boolean; favoritedOnly?: boolean; starredOnly?: boolean; source_type?: string } = {}
): Promise<RawItem[]> {
  const params: Record<string, number | boolean | string> = { offset }
  if (typeof limit === 'number') {
    params.limit = limit
  }
  if (options.watchLaterOnly || options.starredOnly) {
    params.watch_later_only = true
  }
  if (options.favoritedOnly) {
    params.favorited_only = true
  }
  if (options.source_type) {
    params.source_type = options.source_type
  }

  const response = await apiClient.get<RawItem[]>('/api/items', {
    params,
  })
  return response.data
}

export async function uploadItem(
  file: File,
  payload: { title?: string; summary?: string; retention_days?: number; auto_favorite?: boolean } = {}
): Promise<RawItem> {
  const formData = new FormData()
  formData.append('file', file)
  if (payload.title) {
    formData.append('title', payload.title)
  }
  if (payload.summary) {
    formData.append('summary', payload.summary)
  }
  if (typeof payload.retention_days === 'number') {
    formData.append('retention_days', String(payload.retention_days))
  }
  if (payload.auto_favorite) {
    formData.append('auto_favorite', 'true')
  }
  const response = await apiClient.post<RawItem>('/api/items/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

export async function parseItemUrl(pluginName: string, url: string, retention_days: number = -1): Promise<AcceptedTaskResponse> {
  const response = await apiClient.post<AcceptedTaskResponse>('/api/items/parse', {
    plugin_name: pluginName,
    url,
    retention_days,
  })
  return response.data
}

export async function toggleItemWatchLater(itemId: string): Promise<{ item_id: string; is_read: boolean; is_watch_later: boolean; is_favorited: boolean; vault_category_id?: string | null }> {
  const response = await apiClient.post(`/api/items/${itemId}/watch_later`)
  return response.data
}

export async function toggleItemFavorite(itemId: string): Promise<{ item_id: string; is_read: boolean; is_watch_later: boolean; is_favorited: boolean; vault_category_id?: string | null }> {
  const response = await apiClient.post(`/api/items/${itemId}/favorite`)
  return response.data
}

export async function toggleItemStar(itemId: string): Promise<{ item_id: string; is_read: boolean; is_starred: boolean }> {
  const response = await apiClient.post(`/api/items/${itemId}/watch_later`)
  // Map the backend field to the frontend's simplified schema
  return { item_id: response.data.item_id, is_read: response.data.is_read, is_starred: response.data.is_watch_later }
}

export async function getAnnotations(itemId: string): Promise<AnnotationItem[]> {
  const response = await apiClient.get<AnnotationItem[]>(`/api/items/${itemId}/annotations`)
  return response.data
}

export async function createAnnotation(
  itemId: string,
  payload: { content_raw: string; type?: string; anchor_data?: Record<string, any> }
): Promise<AnnotationItem> {
  const response = await apiClient.post<AnnotationItem>(`/api/items/${itemId}/annotations`, {
    type: payload.type ?? 'general',
    content_raw: payload.content_raw,
    anchor_data: payload.anchor_data ?? {},
  })
  return response.data
}

export async function getNotifications(limit: number = 30): Promise<NotificationItem[]> {
  const response = await apiClient.get<NotificationItem[]>('/api/notifications', {
    params: { limit },
  })
  return response.data
}

export async function markNotificationRead(notificationId: string): Promise<NotificationItem> {
  const response = await apiClient.post<NotificationItem>(`/api/notifications/${notificationId}/read`)
  return response.data
}

export async function markAllNotificationsRead(): Promise<void> {
  await apiClient.post('/api/notifications/read-all')
}

export async function clearNotifications(): Promise<void> {
  await apiClient.delete('/api/notifications')
}

export async function uploadAnnotationAsset(
  itemId: string,
  file: Blob,
  payload: { filename?: string; page?: number; rect_norm?: Record<string, number> } = {},
): Promise<AnnotationAssetUploadResult> {
  const formData = new FormData()
  formData.append('file', file, payload.filename || 'annotation-capture.png')
  if (typeof payload.page === 'number') {
    formData.append('page', String(payload.page))
  }
  if (payload.rect_norm) {
    formData.append('rect_norm', JSON.stringify(payload.rect_norm))
  }

  const response = await apiClient.post<AnnotationAssetUploadResult>(
    `/api/items/${itemId}/annotation-assets`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
    },
  )
  return response.data
}

export async function getVaultCategories(): Promise<VaultCategory[]> {
  const response = await apiClient.get<VaultCategory[]>('/api/vault/categories')
  return response.data
}

export async function createVaultCategory(payload: { name: string; color?: string }): Promise<VaultCategory> {
  const response = await apiClient.post<VaultCategory>('/api/vault/categories', payload)
  return response.data
}

export async function updateVaultCategory(categoryId: string, payload: { name?: string; color?: string | null }): Promise<VaultCategory> {
  const response = await apiClient.patch<VaultCategory>(`/api/vault/categories/${categoryId}`, payload)
  return response.data
}

export async function deleteVaultCategory(categoryId: string): Promise<{ status: string }> {
  const response = await apiClient.delete<{ status: string }>(`/api/vault/categories/${categoryId}`)
  return response.data
}

export async function assignItemVaultCategory(itemId: string, vaultCategoryId?: string | null): Promise<{ item_id: string; is_read: boolean; is_watch_later: boolean; is_favorited: boolean; vault_category_id?: string | null }> {
  const response = await apiClient.patch(`/api/items/${itemId}/vault-category`, {
    vault_category_id: vaultCategoryId ?? null,
  })
  return response.data
}

export async function ensureVaultAsset(itemId: string): Promise<RawItem> {
  const response = await apiClient.post<RawItem>(`/api/items/${itemId}/ensure_vault_asset`)
  return response.data
}

// ========== SDUI Hover API ==========
export interface HoverBlockBase {
  block_type: string
}
export interface KVBlock extends HoverBlockBase {
  block_type: 'kv'
  kv_data: Record<string, string | number | boolean>
}
export interface QuoteBlock extends HoverBlockBase {
  block_type: 'quote'
  author: string
  avatar_url: string
  content: string
  date?: string
}
export interface MarkdownBlock extends HoverBlockBase {
  block_type: 'markdown'
  text: string
}
export interface ProgressItem {
  label: string
  value: number
  color?: string
}
export interface ProgressBlock extends HoverBlockBase {
  block_type: 'progress'
  items: ProgressItem[]
}
export type HoverResponse = Array<KVBlock | QuoteBlock | MarkdownBlock | ProgressBlock>

export async function getHoverBlocks(itemId: string): Promise<HoverResponse> {
  const response = await apiClient.get<HoverResponse>(`/api/items/${itemId}/hover`)
  return response.data
}
// ===================================


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

export async function getSystemBillingSettings(): Promise<SystemBillingSettings> {
  const response = await apiClient.get<SystemBillingSettings>('/api/admin/system/billing')
  return response.data
}

export async function saveSystemBillingSettings(payload: Pick<SystemBillingSettings, 'api_limit_type' | 'api_limit_value' | 'currency'>): Promise<SystemBillingSettings> {
  const response = await apiClient.put<SystemBillingSettings>('/api/admin/system/billing', payload)
  return response.data
}

export async function getAdminMetrics(): Promise<AdminMetricsResponse> {
  const response = await apiClient.get<AdminMetricsResponse>('/api/admin/metrics')
  return response.data
}

export async function getAdminUsageTrend(): Promise<AdminUsageTrendResponse> {
  const response = await apiClient.get<AdminUsageTrendResponse>('/api/admin/metrics/usage-trend')
  return response.data
}

export async function getAdminLogTail(service: 'hub' | 'worker' | 'scheduler'): Promise<AdminLogTailResponse> {
  const response = await apiClient.get<AdminLogTailResponse>(`/api/admin/logs/${service}`)
  return response.data
}

export async function forceProcessQueue(): Promise<ForceProcessResponse> {
  const response = await apiClient.post<ForceProcessResponse>('/api/admin/queue/force-process')
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

export interface ActivePlugin {
  id: string
  name: string
  source_type: string
}

export async function getActivePlugins(): Promise<ActivePlugin[]> {
  const response = await apiClient.get<ActivePlugin[]>('/api/plugins/active')
  return response.data
}

export async function getParsePlugins(): Promise<ActivePlugin[]> {
  const response = await apiClient.get<ActivePlugin[]>('/api/items/parse/plugins')
  return response.data
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

// PAT Types
export interface PATItem {
  id: string
  alias: string
  token: string
  is_admin: boolean
  scopes: string[]
  created_at: string
  last_used_at: string | null
  expires_at: string | null
}

export interface PATCreateResponse {
  token: string
  pat: PATItem
}

export async function getPATs(): Promise<PATItem[]> {
  const res = await apiClient.get('/api/auth/pat')
  return res.data
}

export async function createPAT(
  alias: string,
  expires_days: number | null,
  options: { is_admin?: boolean; scopes?: string[] } = {}
): Promise<PATCreateResponse> {
  const res = await apiClient.post('/api/auth/pat', {
    alias,
    expires_days,
    is_admin: options.is_admin ?? false,
    scopes: options.scopes ?? ['read:knowledge', 'write:star'],
  })
  return res.data
}

export async function deletePAT(id: string): Promise<void> {
  await apiClient.delete(`/api/auth/pat/${id}`)
}
