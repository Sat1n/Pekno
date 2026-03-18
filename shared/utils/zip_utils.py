import os
import zipfile
from pathlib import Path

def safe_extract_zip(zip_path: str, extract_to: str):
    """
    安全解压 ZIP 文件，防止 Zip Slip 攻击
    """
    extract_path = Path(extract_to).resolve()
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.infolist():
            # 获取成员的规范化路径
            member_path = (extract_path / member.filename).resolve()
            
            # 检查成员路径是否在解压目录下
            if not str(member_path).startswith(str(extract_path)):
                raise Exception(f"Zip Slip attack detected: {member.filename}")
                
            # 解压
            zip_ref.extract(member, extract_path)
