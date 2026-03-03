from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl

class ItemIntent(str, Enum):
    video = "video"
    article = "article"
    code = "code"
    image = "image"
    social_post = "social_post"

class ItemStatus(str, Enum):
    inbox = "inbox"
    watch_later = "watch_later"
    archived = "archived"

class UniversalItem(BaseModel):
    """
    Pekno 万能信息实体类 - Iris 的核心数据结构
    直接对应 schemas/item_schema.json
    """
    id: str = Field(..., description="唯一ID")
    title: str = Field(..., min_length=1)
    source_type: str = Field(..., description="来源插件名")
    created_at: datetime = Field(default_factory=datetime.now)
    raw_link: HttpUrl
    intent: ItemIntent
    
    # 可选字段
    capabilities: List[str] = Field(default_factory=list)
    content_text: Optional[str] = None
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.inbox
    
    # 插件私有数据
    metadata_extra: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        # 允许从字典或 JSON 字符串中加载
        from_attributes = True