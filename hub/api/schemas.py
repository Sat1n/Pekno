from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Any
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
    is_read: bool = False
    is_starred: bool = False
    # 注意：这里坚决不包含 embedding 字段，减少传输压力
    
    class Config:
        from_attributes = True # 允许从 SQLAlchemy 对象直接转换


class SearchResponse(ItemResponse):
    """带得分的搜索响应"""
    score: float


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
    source_type: Optional[str] = None
    intent: Optional[str] = None
    metadata_extra: Optional[dict] = None
    score: float
    source: str
    tags: List[str] = []
    time: str
    keyframes: Optional[List[str]] = None
    
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
    is_starred: bool


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
