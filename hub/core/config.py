"""
配置管理模块 - 用于读取和保存用户配置
支持加密存储敏感信息
"""
from typing import Optional
from hub.core.database import AsyncSessionLocal
from hub.core.database_models import ConfigORM
from hub.core.crypto import encrypt_value, decrypt_value
from hub.core.logger import worker_log


class ConfigManager:
    """配置管理器"""
    
    @staticmethod
    async def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值（已解密），如果不存在返回默认值
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                ConfigORM.__table__.select().where(ConfigORM.key == key)
            )
            config = result.fetchone()
            
            if not config or not config.value:
                return default
            
            # 解密值
            decrypted = decrypt_value(config.value)
            return decrypted if decrypted is not None else default
    
    @staticmethod
    async def set_config(key: str, value: str, description: str = "") -> bool:
        """
        设置配置值
        
        Args:
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
                        key=key,
                        value=encrypted_value,
                        description=description
                    ).on_conflict_do_update(
                        index_elements=['key'],
                        set_={
                            'value': encrypted_value,
                            'description': description
                        }
                    )
                    
                    await session.execute(stmt)
                
                worker_log.info(f"✅ 配置已保存: {key}")
                return True
                
        except Exception as e:
            worker_log.error(f"❌ 保存配置失败 {key}: {e}")
            return False
    
    @staticmethod
    async def delete_config(key: str) -> bool:
        """
        删除配置
        
        Args:
            key: 配置键
            
        Returns:
            是否删除成功
        """
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    from sqlalchemy import delete
                    await session.execute(
                        delete(ConfigORM).where(ConfigORM.key == key)
                    )
                
                worker_log.info(f"✅ 配置已删除: {key}")
                return True
                
        except Exception as e:
            worker_log.error(f"❌ 删除配置失败 {key}: {e}")
            return False


# 预定义的配置键
class ConfigKeys:
    """配置键常量"""
    GITHUB_TOKEN = "github_token"
    GITHUB_SYNC_LIMIT = "github_sync_limit"
    GITHUB_AUTO_SYNC = "github_auto_sync"
    GITHUB_AUTO_SYNC_INTERVAL = "github_auto_sync_interval"
    GITHUB_AUTO_SUMMARIZE = "github_auto_summarize"
    GITHUB_SYNC_STATUS = "github_sync_status"
    GITHUB_LAST_SYNC_TIME = "github_last_sync_time"
