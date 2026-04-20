from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, JSON, Text, Integer, Boolean, ForeignKey, UniqueConstraint, Float
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector # 处理向量的核心
from datetime import datetime, timedelta
from typing import List, Optional
from shared.time_utils import now_in_app_timezone_naive
import uuid

class Base(DeclarativeBase):
    pass

class ItemORM(Base):
    """这是 Pekno 的物理存储结构"""
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
    file_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    local_asset_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # 保留策略：-1 代表永久，正整数按“小时”解释（沿用旧列名避免额外迁移）
    retention_days: Mapped[int] = mapped_column(Integer, default=-1) 
    
    # 条目级保留标记：用于系统级永久保留，不等同于用户收藏
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


class PersonalAccessTokenORM(Base):
    """个人访问令牌表 (PAT)"""
    __tablename__ = "personal_access_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String)
    token: Mapped[str] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    scopes: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UserItemStateORM(Base):
    """用户与内容之间的个性化状态表"""
    __tablename__ = "user_item_states"
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_user_item_state_user_item"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String, ForeignKey("items.id", ondelete="CASCADE"), index=True)
    vault_category_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("vault_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_watch_later: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorited: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_in_app_timezone_naive,
        onupdate=now_in_app_timezone_naive,
    )


class UserAnnotationsORM(Base):
    """用户对条目的轻量批注/内化记录"""
    __tablename__ = "user_annotations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String, ForeignKey("items.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String, default="general")
    content_raw: Mapped[str] = mapped_column(Text)
    anchor_data: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)


class VaultCategoryORM(Base):
    """用户的 Vault 自定义分类"""
    __tablename__ = "vault_categories"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_vault_category_user_name"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    color: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive, onupdate=now_in_app_timezone_naive)


class UserNotificationORM(Base):
    """用户异步任务通知"""
    __tablename__ = "user_notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String, default="info")
    category: Mapped[str] = mapped_column(String, default="summary")
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="unread")
    related_item_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    related_plugin_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UserCredentialORM(Base):
    """User-scoped reusable credentials for approved platforms."""
    __tablename__ = "user_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_user_credentials_user_platform"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String, index=True)
    token_value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_in_app_timezone_naive,
        onupdate=now_in_app_timezone_naive,
    )


class ApiUsageORM(Base):
    """大模型与本地智能引擎调用账本"""
    __tablename__ = "api_usage"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    model_name: Mapped[str] = mapped_column(String)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)


class SystemConfigORM(Base):
    """管理员全局系统配置"""
    __tablename__ = "system_configs"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_in_app_timezone_naive)
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
