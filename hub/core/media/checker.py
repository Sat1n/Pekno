import shutil
import os
from shared.logger import hub_log

def check_media_dependencies():
    """
    Runtime dependency check for system-level multimedia engines (ffmpeg, node.js).
    """
    env = os.getenv("APP_ENV", "prod")
    missing_deps = []
    
    if not shutil.which("ffmpeg"): 
        missing_deps.append("ffmpeg")
    if not shutil.which("node"): 
        missing_deps.append("node.js")
        
    if missing_deps:
        if env == "dev":
            # Warn only in development. Never auto-install dependencies.
            hub_log.warning(
                f"⚠️ [Dev Warning] Missing multimedia runtime dependencies: {', '.join(missing_deps)}. "
                "Please install them manually on the host machine to unlock full media processing."
            )
        else:
            # In production or Docker, treat this as a fatal infrastructure issue.
            hub_log.error(
                f"❌ [Prod Error] Missing required container dependencies: {', '.join(missing_deps)}. "
                "Please verify the Dockerfile or runtime image."
            )
    else:
        hub_log.info("✅ Multimedia runtime dependency check passed (ffmpeg, node).")
