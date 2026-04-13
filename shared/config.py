"""
Configuration management helpers for reading and persisting user settings.
Sensitive values are stored in encrypted form.
"""
from typing import Optional
from shared.database import AsyncSessionLocal
from shared.models import ConfigORM
from shared.crypto import encrypt_value, decrypt_value
from shared.logger import worker_log
from sqlalchemy import select


class ConfigKeys:
    TOKEN = "token"
    COOKIE = "cookie"
    SYNC_LIMIT = "sync_limit"
    AUTO_SYNC = "auto_sync"
    AUTO_SYNC_INTERVAL = "auto_sync_interval"
    LAST_SYNC_TIME = "last_sync_time"
    LAST_SUCCESSFUL_SYNC_TIME = "last_successful_sync_time"
    LAST_SYNC_RESULT = "last_sync_result"
    LAST_SYNC_ERROR = "last_sync_error"
    SYNC_STATUS = "sync_status"
    AUTO_SHORT_SUMMARY = "auto_short_summary"
    RETENTION_HOURS = "retention_hours"

    @staticmethod
    def credential_binding(platform: str) -> str:
        return f"credential_binding:{platform}"


SYSTEM_CONFIG_USER_ID = "system"
SYSTEM_SCOPED_CONFIG_KEYS = {
    ConfigKeys.SYNC_LIMIT,
    ConfigKeys.AUTO_SYNC,
    ConfigKeys.AUTO_SYNC_INTERVAL,
    ConfigKeys.LAST_SUCCESSFUL_SYNC_TIME,
    ConfigKeys.LAST_SYNC_RESULT,
    ConfigKeys.LAST_SYNC_ERROR,
    ConfigKeys.AUTO_SHORT_SUMMARY,
    ConfigKeys.RETENTION_HOURS,
}


class ConfigManager:
    """Configuration manager."""

    @staticmethod
    def resolve_user_scope(key: str, user_id: Optional[str] = None) -> str:
        if key in SYSTEM_SCOPED_CONFIG_KEYS:
            return SYSTEM_CONFIG_USER_ID
        return user_id or SYSTEM_CONFIG_USER_ID
    
    @staticmethod
    async def get_config(
        plugin_id: str,
        key: str,
        default: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Retrieve a configuration value.
        
        Args:
            plugin_id: Plugin namespace identifier
            key: Configuration key
            default: Default value
            
        Returns:
            Decrypted configuration value, or the default if it does not exist.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ConfigORM).where(
                    (ConfigORM.plugin_id == plugin_id)
                    & (ConfigORM.key == key)
                    & (ConfigORM.user_id == ConfigManager.resolve_user_scope(key, user_id))
                )
            )
            config = result.scalar_one_or_none()

            if config is None and user_id is None and key not in SYSTEM_SCOPED_CONFIG_KEYS:
                fallback_result = await session.execute(
                    select(ConfigORM)
                    .where(
                        (ConfigORM.plugin_id == plugin_id)
                        & (ConfigORM.key == key)
                        & (ConfigORM.user_id != SYSTEM_CONFIG_USER_ID)
                    )
                    .order_by(ConfigORM.updated_at.desc())
                    .limit(1)
                )
                config = fallback_result.scalar_one_or_none()
            
            if not config or not config.value:
                return default
            
            # Decrypt stored value
            decrypted = decrypt_value(config.value)
            return decrypted if decrypted is not None else default
    
    @staticmethod
    async def set_config(
        plugin_id: str,
        key: str,
        value: str,
        description: str = "",
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Persist a configuration value.
        
        Args:
            plugin_id: Plugin namespace identifier
            key: Configuration key
            value: Configuration value, which will be encrypted
            description: Human-readable description
            
        Returns:
            Whether the operation succeeded
        """
        try:
            # Encrypt the value before persisting it
            encrypted_value = encrypt_value(value)
            
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    from sqlalchemy.dialects.postgresql import insert
                    
                    stmt = insert(ConfigORM).values(
                        plugin_id=plugin_id,
                        user_id=ConfigManager.resolve_user_scope(key, user_id),
                        key=key,
                        value=encrypted_value,
                        description=description
                    ).on_conflict_do_update(
                        index_elements=['plugin_id', 'user_id', 'key'],
                        set_={
                            'value': encrypted_value,
                            'description': description
                        }
                    )
                    
                    await session.execute(stmt)
                
                worker_log.info(f"✅ Configuration saved [{plugin_id}]: {key}")
                return True
                
        except Exception as e:
            worker_log.error(f"❌ Failed to save configuration [{plugin_id}] {key}: {e}")
            return False
    
    @staticmethod
    async def delete_config(plugin_id: str, key: str, user_id: Optional[str] = None) -> bool:
        """
        Delete a configuration value.
        
        Args:
            plugin_id: Plugin namespace identifier
            key: Configuration key
            
        Returns:
            Whether the delete operation succeeded
        """
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    from sqlalchemy import delete
                    stmt = delete(ConfigORM).where(
                        (ConfigORM.plugin_id == plugin_id)
                        & (ConfigORM.key == key)
                        & (ConfigORM.user_id == ConfigManager.resolve_user_scope(key, user_id))
                    )
                    result = await session.execute(stmt)
                    if result.rowcount > 0:
                        worker_log.info(f"🗑️ Configuration deleted [{plugin_id}]: {key}")
                        return True
                    return False
        except Exception as e:
            worker_log.error(f"❌ Failed to delete configuration [{plugin_id}] {key}: {e}")
            return False
