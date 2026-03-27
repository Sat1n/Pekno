from shared.logger import hub_log
from hub.core.llm.ollama_manager import clear_vram_for_whisper
import os
from typing import Any

async def resolve_huggingface_env():
    """解析并注入 HuggingFace 环境设置：智能镜像探测与 Token 鉴权"""
    # 先清理可能残留的旧环境，避免多次任务执行时把错误配置一直带下去
    os.environ.pop("HF_ENDPOINT", None)
    os.environ.pop("HUGGINGFACE_HUB_ENDPOINT", None)

    # Hugging Face Hub 的 Xet 分发在部分网络环境下会出现“无报错卡住”。
    # 对 Whisper 首次拉取场景，优先禁用，回退到更稳定的常规下载链路。
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    try:
        from hub.core.model_settings import _load_json_config, _provider_config_key
        # 查询数据库中是否配置了 HuggingFace 设置
        hf_config = await _load_json_config(_provider_config_key("huggingface"), {})
        token = hf_config.get("api_key")
        endpoint = str(hf_config.get("endpoint") or "").strip()
        if token and str(token).strip():
            os.environ["HF_TOKEN"] = str(token).strip()
            hub_log.info("🔑 已读取并注入 HuggingFace Access Token！解锁网络限流...")
        if endpoint:
            os.environ["HF_ENDPOINT"] = endpoint
            os.environ["HUGGINGFACE_HUB_ENDPOINT"] = endpoint
            hub_log.info(f"🪞 已启用 HuggingFace 自定义 Endpoint: {endpoint}")
            return
    except Exception as e:
        hub_log.warning(f"⚠️ 读取 HuggingFace Token 失败: {e}")

    # 探测 HuggingFace 连通性
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.head("https://huggingface.co", follow_redirects=True)
            if resp.status_code == 200:
                hub_log.info("📶 HuggingFace 主站连接畅通，采用直连模式。")
                return
    except Exception:
        pass

    # 如果连通性自检失败，则注入国内镜像
    hub_log.warning("⚠️ HuggingFace 主站连接超时或被阻断，正自动切换至 hf-mirror.com 镜像加速！")
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    os.environ["HUGGINGFACE_HUB_ENDPOINT"] = "https://hf-mirror.com"


LOW_CONFIDENCE_LANGUAGE_THRESHOLD = 0.55


class TranscriberFactory:
    @staticmethod
    async def transcribe_audio(audio_path: str, provider: str = "local_whisper", model_name: str = "small"):
        """
        强防御语音转录工厂：负责调度不同底座的转录能力，返回格式化的 JSON 分段
        """
        if provider == "local_whisper":
            # 1. 强制清空 Ollama 显存，为 Whisper 释放空间
            await clear_vram_for_whisper()
            try:
                # 智能应用 HF 代理环境与鉴权
                await resolve_huggingface_env()
                
                from faster_whisper import WhisperModel
                import asyncio
                
                # 必须锁定 int8 量化，适配 6G 显存老盘
                # device="cuda" 如果 CUDA 环境炸了（比如 Docker 里没透传 --gpus all），会直接抛出异常
                hub_log.info(f"🔄 正在通过 CUDA 加载 Faster-Whisper ({model_name}) ...")
                hub_log.info(
                    "🧭 当前 HF 下载环境: "
                    f"endpoint={os.environ.get('HF_ENDPOINT', 'https://huggingface.co')} | "
                    f"disable_xet={os.environ.get('HF_HUB_DISABLE_XET', '0')}"
                )
                model = await asyncio.to_thread(WhisperModel, model_name, device="cuda", compute_type="int8")
                hub_log.info(f"✅ Faster-Whisper ({model_name}) 成功挂载至 GPU显存")
            except Exception as e:
                hub_log.error(f"❌ 严重警告: Whisper 无法使用 GPU 加载！原因: {str(e)}")
                hub_log.warning("⚠️ 正在降级到 CPU 运行，转录速度将极其缓慢！请检查 CUDA 环境！")
                # 优雅降级：如果 cuda 报错，转向 CPU 硬解
                hub_log.info(
                    "🧭 CPU 降级前 HF 下载环境: "
                    f"endpoint={os.environ.get('HF_ENDPOINT', 'https://huggingface.co')} | "
                    f"disable_xet={os.environ.get('HF_HUB_DISABLE_XET', '0')}"
                )
                model = await asyncio.to_thread(WhisperModel, model_name, device="cpu", compute_type="int8")

            hub_log.info(f"🎙️ 开始执行本地转录: {audio_path}")
            segments_generator, info = await asyncio.to_thread(model.transcribe, audio_path, beam_size=5)

            language = getattr(info, "language", None)
            language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
            if language:
                hub_log.info(
                    f"🧭 Whisper 语言判定: {language} (probability={language_probability:.2f})"
                )

            if language_probability < LOW_CONFIDENCE_LANGUAGE_THRESHOLD:
                hub_log.warning(
                    "⚠️ Whisper 语言置信度过低，判定本次内容可能为纯音乐/纯音效/不可稳定转写音频，"
                    f"已跳过转录分段生成 (threshold={LOW_CONFIDENCE_LANGUAGE_THRESHOLD:.2f})"
                )
                close_fn = getattr(segments_generator, "close", None)
                if callable(close_fn):
                    try:
                        close_fn()
                    except Exception:
                        pass
                return {
                    "segments": [],
                    "language": language,
                    "language_probability": language_probability,
                    "low_confidence": True,
                }
            
            # segments 是一个 generator，转录过程中逐步产出，转换成 list 返回
            # 根据用户要求，返回带时间戳的标准 JSON 数组
            result = []
            for s in await asyncio.to_thread(list, segments_generator):
                result.append({
                    "start": s.start,
                    "end": s.end,
                    "text": s.text.strip()
                })
            return {
                "segments": result,
                "language": language,
                "language_probability": language_probability,
                "low_confidence": False,
            }
        else:
            # 预留给 API 分支 (例如通义千问等 DashScope ASR)
            hub_log.info(f"API 转写路由尚未实装: {provider}. 请等待后续支持。")
            return {
                "segments": [],
                "language": None,
                "language_probability": 0.0,
                "low_confidence": False,
            }
