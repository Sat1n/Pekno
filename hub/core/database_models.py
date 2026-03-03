from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector # 处理向量的核心
from datetime import datetime
from typing import List, Optional

class Base(DeclarativeBase):
    pass

class ItemORM(Base):
    """这是 Iris 的物理存储结构"""
    __tablename__ = "items"

    # 基础字段
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    raw_link: Mapped[str] = mapped_column(String)
    intent: Mapped[str] = mapped_column(String)
    
    # 扩展字段
    content_text: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=[])
    
    # 核心：向量字段 (假设我们使用 1536 维的 Embedding，如 OpenAI 或 Ollama)
    # 暂时设为 nullable，因为还没接 Embedding 模型
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(1536))
    
    # 插件私有数据
    metadata_extra: Mapped[dict] = mapped_column(JSON, default={})