"""
加密工具类 - 用于安全存储敏感配置（如 Token）
使用 Fernet 对称加密算法
"""
from cryptography.fernet import Fernet
import os
import base64
from typing import Optional

# 从环境变量获取加密密钥，如果不存在则生成一个（仅开发环境）
# 生产环境必须在环境变量中设置固定的密钥
ENCRYPTION_KEY = os.getenv("IRIS_ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    # 开发环境：生成一个临时密钥（每次重启会变化，仅用于测试）
    # 警告：生产环境不要使用这种方式！
    ENCRYPTION_KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()
    print(f"⚠️ 警告：使用临时加密密钥（开发环境），密钥: {ENCRYPTION_KEY[:20]}...")


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
    except Exception as e:
        print(f"❌ 解密失败: {e}")
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
    print("请将此密钥设置到环境变量 IRIS_ENCRYPTION_KEY 中")
