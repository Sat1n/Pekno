"""
配置管理模块 - 用于读取和保存用户配置
支持加密存储敏感信息
"""
from typing import Optional
from shared.database import AsyncSessionLocal
from shared.models import ConfigORM
from shared.crypto import encrypt_value, decrypt_value
from shared.logger import worker_log


class ConfigKeys:
    TOKEN = "token"
    SYNC_LIMIT = "sync_limit"
    AUTO_SYNC = "auto_sync"
    AUTO_SYNC_INTERVAL = "auto_sync_interval"
    LAST_SYNC_TIME = "last_sync_time"
    SYNC_STATUS = "sync_status"


class ConfigManager:
    """配置管理器"""
    
    @staticmethod
    async def get_config(plugin_id: str, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        获取配置值
        
        Args:
            plugin_id: 插件命名空间标识
            key: 配置键
            default: 默认值
            
        Returns:
            配置值（已解密），如果不存在返回默认值
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                ConfigORM.__table__.select().where(
                    (ConfigORM.plugin_id == plugin_id) & (ConfigORM.key == key)
                )
            )
            config = result.fetchone()
            
            if not config or not config.value:
                return default
            
            # 解密值
            decrypted = decrypt_value(config.value)
            return decrypted if decrypted is not None else default
    
    @staticmethod
    async def set_config(plugin_id: str, key: str, value: str, description: str = "") -> bool:
        """
        设置配置值
        
        Args:
            plugin_id: 插件命名空间标识
            key: 配置键
            value: 配置值（会被加密）
            description: 配置描述
            
        Returns:
            是否设置成功
        """
        try:
            # 加密值
            encrypted_value = encrypt_value(value)
            
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    from sqlalchemy.dialects.postgresql import insert
                    
                    stmt = insert(ConfigORM).values(
                        plugin_id=plugin_id,
                        key=key,
                        value=encrypted_value,
                        description=description
                    ).on_conflict_do_update(
                        index_elements=['plugin_id', 'key'],
                        set_={
                            'value': encrypted_value,
                            'description': description
                        }
                    )
                    
                    await session.execute(stmt)
                
                worker_log.info(f"✅ 配置已保存 [{plugin_id}]: {key}")
                return True
                
        except Exception as e:
            worker_log.error(f"❌ 保存配置失败 [{plugin_id}] {key}: {e}")
            return False
    
    @staticmethod
    async def delete_config(plugin_id: str, key: str) -> bool:
        """
        删除配置
        
        Args:
            plugin_id: 插件命名空间标识
            key: 配置键
            
        Returns:
            是否删除成功
        """
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    from sqlalchemy import delete
                    stmt = delete(ConfigORM).where(
                        (ConfigORM.plugin_id == plugin_id) & (ConfigORM.key == key)
                    )
                    result = await session.execute(stmt)
                    if result.rowcount > 0:
                        worker_log.info(f"🗑️ 配置已删除 [{plugin_id}]: {key}")
                        return True
                    return False
        except Exception as e:
            worker_log.error(f"❌ 删除配置失败 [{plugin_id}] {key}: {e}")
            return False
