import shutil
import os
from shared.logger import hub_log

def check_media_dependencies():
    """
    运行环境安全巡检：检查系统底层多媒体引擎 (ffmpeg, nodejs)
    """
    env = os.getenv("APP_ENV", "prod")
    missing_deps = []
    
    if not shutil.which("ffmpeg"): 
        missing_deps.append("ffmpeg")
    if not shutil.which("node"): 
        missing_deps.append("node.js")
        
    if missing_deps:
        if env == "dev":
            # 仅告警，绝对不执行自动安装
            hub_log.warning(f"⚠️ [Dev 环境警告] 缺失多媒体底层依赖: {', '.join(missing_deps)}。请在宿主机手动安装以解锁完整的多媒体处理能力。")
        else:
            # 生产/Docker 环境直接抛出致命错误级别的日志
            hub_log.error(f"❌ [Prod 环境错误] 容器内缺失致命依赖: {', '.join(missing_deps)}。请检查 Dockerfile。")
    else:
        hub_log.info("✅ 系统层多媒体底层服务 (ffmpeg, node) 集群探测正常。")
