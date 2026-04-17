import shutil
import os
from shared.logger import hub_log

def check_media_dependencies():
    """
    Runtime dependency check for backend multimedia processing.
    """
    env = os.getenv("APP_ENV", "prod")
    missing_deps = []
    
    if not shutil.which("ffmpeg"): 
        missing_deps.append("ffmpeg")
        
    if missing_deps:
        if env == "dev":
            hub_log.warning(
                "Missing multimedia runtime dependencies: %s. Please install them before running media processing tasks.",
                ", ".join(missing_deps),
            )
        else:
            hub_log.error(
                "Missing required multimedia runtime dependencies: %s. Please verify the runtime image.",
                ", ".join(missing_deps),
            )
    else:
        hub_log.info("Multimedia runtime dependency check passed (ffmpeg).")
