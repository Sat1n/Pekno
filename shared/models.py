from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, JSON, Text, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector # 处理向量的核心
from datetime import datetime, timedelta
from typing import List, Optional
from shared.time_utils import now_in_app_timezone_naive
import uuid

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)
    raw_link: Mapped[str] = mapped_column(String)
    intent: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive, onupdate=now_in_app_timezone_naive)

    # 保留策略：-1 代表永久，正整数按“小时”解释（沿用旧列名避免额外迁移）
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
    __table_args__ = (
        UniqueConstraint("plugin_id", "user_id", "key", name="uq_config_plugin_user_key"),
    )

    # 插件标识，如 "github_stars"
    plugin_id: Mapped[str] = mapped_column(String)

    # 配置所属用户，system 代表系统级配置
    user_id: Mapped[str] = mapped_column(String, default="system")
    
    # 配置键，如 "token", "sync_limit" 等
    key: Mapped[str] = mapped_column(String)
    
    # 加密后的值
    value: Mapped[str] = mapped_column(Text)
    
    # 配置描述
    description: Mapped[Optional[str]] = mapped_column(Text, default="")
    
    # 创建和更新时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive, onupdate=now_in_app_timezone_naive)
    
    # 是否启用
    is_enabled: Mapped[bool] = mapped_column(default=True)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

class PluginRegistryORM(Base):
    """插件物理注册表"""
    __tablename__ = "plugins"

    # 插件标识，如 "github_stars"
    plugin_id: Mapped[str] = mapped_column(String, primary_key=True)

    # 插件展示名
    name: Mapped[str] = mapped_column(String)

    # 核心字段：模块路径，如 "worker.plugins.github.plugin"
    module_path: Mapped[str] = mapped_column(String)

    # 是否启用
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 版本
    version: Mapped[str] = mapped_column(String, default="1.0.0")

    # 安装时间
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)


class UserORM(Base):
    """Hub 身份认证用户表"""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="admin")


class UserItemStateORM(Base):
    """用户与内容之间的个性化状态表"""
    __tablename__ = "user_item_states"
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_user_item_state_user_item"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String, ForeignKey("items.id", ondelete="CASCADE"), index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_in_app_timezone_naive,
        onupdate=now_in_app_timezone_naive,
    )


class InvitationCodeORM(Base):
    """邀请码追踪表"""
    __tablename__ = "invitation_codes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_by_user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)
