from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

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

class ItemRetention(str, Enum):
    PERMANENT = "permanent"
    TRANSIENT = "transient" # 临时

class UniversalItem(BaseModel):
    """
    Pekno 万能信息实体类 - Iris 的核心数据结构
    直接对应 schemas/item_schema.json
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    source_type: str
    created_at: datetime = Field(default_factory=datetime.now)
    raw_link: HttpUrl
    intent: ItemIntent
    cover_url: Optional[str] = None 
    retention_days: int = -1 # -1 代表永久，正整数代表保留天数
    capabilities: List[str] = Field(default_factory=list)
    content_text: Optional[str] = None
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.inbox
    metadata_extra: Dict[str, Any] = Field(default_factory=dict)
    auto_ai_processing: bool = True
