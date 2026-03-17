from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Any
from datetime import datetime
from shared.entities import ItemIntent


class ItemResponse(BaseModel):
    """用于列表和搜索结果展示的响应模型"""
    id: str
    title: str
    source_type: str
    raw_link: str
    summary: Optional[str] = None
    tags: List[str] = []
    intent: ItemIntent
    created_at: datetime
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
    score: float
    source: str
    tags: List[str] = []
    time: str
    
    class Config:
        from_attributes = True