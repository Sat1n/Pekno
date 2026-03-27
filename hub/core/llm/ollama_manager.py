import httpx
from shared.logger import hub_log

async def clear_vram_for_whisper(base_url="http://localhost:11434"):
    """
    极客级显存清道夫：为了确保 6GB 显存的老显卡能跑通复杂的音视频 AI 工作流，
    在启动本地 Whisper 之前通过 Ollama /api/ps 检测常驻模型，
    并通过 keep_alive=0 强制它们卸载腾出 VRAM 空间。
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{base_url}/api/ps")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                cleared_any = False
                for m in models:
                    model_name = m.get("name")
                    if model_name:
                        # 强制发送卸载信号
                        await client.post(f"{base_url}/api/generate", json={"model": model_name, "keep_alive": 0})
                        hub_log.info(f"🧹 已向 Ollama 发送内存强制回收信号: {model_name}")
                        cleared_any = True
                
                if cleared_any:
                    hub_log.info("🧹 已强制清空 Ollama 显存，为 Whisper 腾出计算空间")
                else:
                    hub_log.debug("✨ Ollama 当前未占用常驻显存")
    except Exception as e:
        hub_log.warning(f"⚠️ 无法连接 Ollama 清理显存: {e}")
