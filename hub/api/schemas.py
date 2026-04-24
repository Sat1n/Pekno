from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Any, Literal
from datetime import datetime
class ItemResponse(BaseModel):
    """用于列表和搜索结果展示的响应模型"""
    id: str
    title: str
    source_type: str
    raw_link: str
    content_text: Optional[str] = None
    summary: Optional[str] = None
    tags: List[str] = []
    intent: str
    created_at: datetime
    metadata_extra: dict = {}
    local_asset_url: Optional[str] = None
    vault_category_id: Optional[str] = None
    is_read: bool = False
    is_watch_later: bool = False
    is_favorited: bool = False
    # 注意：这里坚决不包含 embedding 字段，减少传输压力
    
    class Config:
        from_attributes = True # 允许从 SQLAlchemy 对象直接转换


class SearchResponse(ItemResponse):
    """带得分的搜索响应"""
    score: Optional[float] = None


class SyncRequest(BaseModel):
    """同步请求模型"""
    token: Optional[str] = None
    limit: Optional[int] = 10


class StatsResponse(BaseModel):
    """仪表盘统计数据"""
    total_count: int
    source_distribution: dict # {"github_star": 10, "bilibili": 5}


# 前端搜索响应 Schema
class FrontendSearchItem(BaseModel):
    """前端搜索接口返回的数据格式"""
    id: str  # 必须暴露数据库真实 ID 给前端
    title: str
    summary: Optional[str] = None
    long_summary: Optional[str] = None
    has_long_summary: bool = False
    cover_url: Optional[str] = None
    author: Optional[str] = None
    raw_link: Optional[str] = None
    local_asset_url: Optional[str] = None
    source_type: Optional[str] = None
    intent: Optional[str] = None
    metadata_extra: Optional[dict] = None
    score: Optional[float] = None
    source: str
    tags: List[str] = []
    time: str
    keyframes: Optional[List[str]] = None
    is_watch_later: bool = False
    is_favorited: bool = False
    
    class Config:
        from_attributes = True


class AuthStatusResponse(BaseModel):
    needs_initialization: bool


class AuthInitRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class AuthRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    invite_code: str = Field(min_length=6, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class ReadBatchRequest(BaseModel):
    item_ids: List[str] = Field(default_factory=list)


class ItemStateResponse(BaseModel):
    item_id: str
    is_read: bool
    is_watch_later: bool
    is_favorited: bool
    vault_category_id: Optional[str] = None


class VaultCategoryResponse(BaseModel):
    id: str
    name: str
    color: Optional[str] = None
    sort_order: int
    created_at: datetime


class AnnotationResponse(BaseModel):
    id: str
    item_id: str
    type: str
    content_raw: str
    anchor_data: dict = {}
    created_at: datetime


class AnnotationAssetResponse(BaseModel):
    asset_url: str
    content_type: str
    page: Optional[int] = None
    rect_norm: Optional[dict] = None


class InvitationCodeResponse(BaseModel):
    id: str
    code: str
    is_used: bool
    used_by_username: Optional[str] = None
    created_at: datetime


class InvitationCreateResponse(BaseModel):
    id: str
    code: str
    is_used: bool
    created_at: datetime


class NotificationResponse(BaseModel):
    id: str
    type: str
    category: str
    title: str
    description: str
    status: str
    related_item_id: Optional[str] = None
    related_plugin_id: Optional[str] = None
    created_at: datetime
    read_at: Optional[datetime] = None


class UserCredentialUpsertRequest(BaseModel):
    platform: str
    token_value: str = Field(min_length=1)


class UserCredentialResponse(BaseModel):
    id: str
    platform: str
    label: str
    masked_value: str
    created_at: datetime
    updated_at: datetime


class BillingSettingsRequest(BaseModel):
    api_limit_type: Literal["token", "cost"]
    api_limit_value: float = Field(ge=0)
    currency: Literal["USD", "CNY", "EUR"] = "USD"


class BillingSettingsResponse(BillingSettingsRequest):
    used_tokens: int
    used_cost: float
    limit_exceeded: bool


class PluginHealthResponse(BaseModel):
    plugin_id: str
    name: str
    last_successful_sync_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    sync_status: str = "idle"
    status: Literal["Healthy", "Stale", "Error"]
    auto_sync: bool = False
    auto_sync_interval: Optional[int] = None
    last_error: Optional[str] = None


class MonitorMetricsResponse(BaseModel):
    rag_backlog_count: int
    api_today_total_cost: float
    api_limit_type: Literal["token", "cost"]
    api_limit_value: float
    used_tokens: int
    used_cost: float
    limit_exceeded: bool
    billing_warning: bool = False
    warning_threshold_ratio: float = 0.9
    billing_currency: Literal["USD", "CNY", "EUR"]
    abnormal_plugin_count: int
    plugins: List[PluginHealthResponse]


class LogTailResponse(BaseModel):
    service: Literal["hub", "worker", "scheduler"]
    content: str
    lines: int


class UsageTrendPointResponse(BaseModel):
    date: str
    total_tokens: int
    total_cost: float


class UsageTrendResponse(BaseModel):
    api_limit_type: Literal["token", "cost"]
    api_limit_value: float
    currency: Literal["USD", "CNY", "EUR"]
    used_tokens: int
    used_cost: float
    limit_exceeded: bool
    billing_warning: bool = False
    warning_threshold_ratio: float = 0.9
    points: List[UsageTrendPointResponse]


class ForceProcessResponse(BaseModel):
    status: Literal["accepted"]
    requeued_count: int
    message: str
