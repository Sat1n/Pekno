from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, JSON, Text, Integer
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector # 处理向量的核心
from datetime import datetime, timedelta
from typing import List, Optional

class Base(DeclarativeBase):
    pass

class ItemORM(Base):
    """这是 Iris 的物理存储结构"""
    __tablename__ = "items"

    # 基础字段
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(768))
    source_type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    raw_link: Mapped[str] = mapped_column(String)
    intent: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 保留策略：-1 代表永久，正整数代表保留天数
    retention_days: Mapped[int] = mapped_column(Integer, default=-1) 
    
    # 标记：是否已"收藏" (如果收藏了，即便过了天数也不删)
    is_pinned: Mapped[bool] = mapped_column(default=False)
    
    # 扩展字段
    content_text: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=[])
    
    # 插件私有数据
    metadata_extra: Mapped[dict] = mapped_column(JSON, default={})


class ConfigORM(Base):
    """用户配置存储表（加密存储敏感信息）"""
    __tablename__ = "configs"

    # 配置键，如 "github_token", "sync_limit" 等
    key: Mapped[str] = mapped_column(String, primary_key=True)
    
    # 加密后的值
    value: Mapped[str] = mapped_column(Text)
    
    # 配置描述
    description: Mapped[Optional[str]] = mapped_column(Text, default="")
    
    # 创建和更新时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 是否启用
    is_enabled: Mapped[bool] = mapped_column(default=True)
