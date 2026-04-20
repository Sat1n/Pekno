"""
加密工具类 - 用于安全存储敏感配置（如 Token）
使用 Fernet 对称加密算法
"""
import logging
from typing import Optional

from cryptography.fernet import Fernet

from shared.secret_store import load_or_create_secret

_log = logging.getLogger(__name__)

ENCRYPTION_KEY = load_or_create_secret(
    env_key="PEKNO_ENCRYPTION_KEY",
    filename="pekno_encryption_key",
    generator=lambda: Fernet.generate_key().decode(),
    announce_label="Pekno 配置加密密钥",
)


def get_fernet() -> Fernet:
    """获取 Fernet 实例"""
    # 确保密钥是 32 字节并经过 base64 编码
    key = ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY
    return Fernet(key)


def encrypt_value(value: str) -> str:
    """
    加密字符串值
    
    Args:
        value: 要加密的明文
        
    Returns:
        加密后的密文（base64 编码）
    """
    if not value:
        return ""
    
    f = get_fernet()
    encrypted = f.encrypt(value.encode())
    return encrypted.decode()


def decrypt_value(encrypted_value: str) -> Optional[str]:
    """
    解密字符串值
    
    Args:
        encrypted_value: 加密的密文
        
    Returns:
        解密后的明文，如果解密失败返回 None
    """
    if not encrypted_value:
        return None
    
    try:
        f = get_fernet()
        decrypted = f.decrypt(encrypted_value.encode())
        return decrypted.decode()
    except Exception:
        _log.warning("Decryption failed for a stored value (key may have changed).")
        return None


def generate_encryption_key() -> str:
    """
    生成一个新的加密密钥
    
    用于初始化时生成密钥，应该保存到环境变量中
    
    Returns:
        base64 编码的 32 字节密钥
    """
    return Fernet.generate_key().decode()


# 如果直接运行此文件，生成一个新的密钥
if __name__ == "__main__":
    new_key = generate_encryption_key()
    print(f"🔑 新生成的加密密钥: {new_key}")
    print("请将此密钥设置到环境变量 PEKNO_ENCRYPTION_KEY 中")
