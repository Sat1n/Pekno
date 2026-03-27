from worker.broker import broker
from shared.logger import worker_log
from shared.database import AsyncSessionLocal
from shared.models import ItemORM
from hub.core.media.downloader import YTDlpService
from hub.core.media.transcriber import TranscriberFactory
from hub.core.llm.summarizer import summarize_video_transcript
from hub.core.model_settings import get_model_assignments
import os
import json
import asyncio
import shutil
import tempfile
import random
from pathlib import Path


def _format_seconds_for_summary(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _build_timed_transcript(segments: list[dict]) -> str:
    lines: list[str] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = float(segment.get("start", 0))
        lines.append(f"[{_format_seconds_for_summary(start)}] {text}")
    return "\n".join(lines)


def _fallback_long_summary(item_ctx, reason: str) -> str:
    base_text = (item_ctx.summary or "").strip()
    if not base_text:
        base_text = "原始简介为空，暂无可回退的文本说明。"
    return (
        f"转译失败，可能为纯音频、背景音乐或难以稳定识别的内容，因此未生成新的 AI 长总结。\n\n"
        f"作为兜底，下面保留原始简介或短摘要供参考：\n\n"
        f"{base_text}"
    )


def _pick_random_keyframe_timestamps(duration_seconds: float | int | None, count: int = 5) -> list[int]:
    if not duration_seconds or duration_seconds <= 0:
        return []

    max_second = max(1, int(duration_seconds))
    start = 3 if max_second > 6 else 0
    end = max(start, max_second - 3)

    if end <= start:
        return [start]

    candidates = list(range(start, end + 1))
    sample_size = min(count, len(candidates))
    if sample_size <= 0:
        return []

    return sorted(random.sample(candidates, sample_size))


@broker.task(task_name="process_multimedia")
async def process_multimedia_task(item_id: str, url: str):
    """
    终端多媒体 Worker 流水线：
    YTDlp 剥离音轨 -> Whisper 识别 JSON 阵列 -> AI 导演对峙转录偏差生成报告 -> 数据库双写合并
    """
    worker_log.info(f"🎬 多媒体主引擎介入执行: {item_id} | 路径: {url}")
    
    # 获取 ItemORM 记录供参考
    async with AsyncSessionLocal() as session:
        result = await session.execute(ItemORM.__table__.select().where(ItemORM.id == item_id))
        item_data = result.fetchone()
        if not item_data:
            worker_log.error(f"❌ 查无此入库任务: {item_id}")
            return
            
        class TranscribeContext:
            _data = item_data
            @property
            def title(self): return self._data.title
            @property
            def summary(self): return self._data.content_text or self._data.summary
            
        item_ctx = TranscribeContext()
    
    cache_root = Path("data") / "cache" / "media"
    cache_root.mkdir(parents=True, exist_ok=True)
    task_cache_dir = Path(tempfile.mkdtemp(prefix=f"{item_id}_", dir=str(cache_root)))
    requested_audio_path = task_cache_dir / "audio.mp3"
    requested_video_path = task_cache_dir / "video.mp4"
    
    try:
        stream_info = await asyncio.to_thread(YTDlpService.extract_info, url, {})
        duration_seconds = stream_info.get("duration")

        worker_log.info(f"📥 核心层: YTDlp 剥离最高音质流媒体并实施本地化... 缓存目录={task_cache_dir}")
        # 这里的耗时阻断将转为守护线程执行
        audio_path = await asyncio.to_thread(YTDlpService.download_audio, url, str(requested_audio_path))
        worker_log.info(f"🎧 音轨已落盘: {audio_path}")
            
        # 定位底层 Whisper 挂载型号
        assignments = await get_model_assignments()
        speech_cfg = next((a for a in assignments if a["key"] == "speech_to_text"), None)
        provider = speech_cfg["provider"] if speech_cfg else "local_whisper"
        model_name = speech_cfg["model"] if speech_cfg else "small"
        
        worker_log.info(f"🎙️ 推理层: 注入 {provider}/{model_name}...")
        transcript_result = await TranscriberFactory.transcribe_audio(audio_path, provider, model_name)
        segments = transcript_result.get("segments", [])
        low_confidence = bool(transcript_result.get("low_confidence"))
        language_probability = float(transcript_result.get("language_probability", 0.0) or 0.0)
        
        if not segments and not low_confidence:
            worker_log.warning("⚠️ 沉默的流媒体: 未能捕捉有效语义切片。")
            return

        raw_transcript_json = json.dumps(segments, ensure_ascii=False)

        if low_confidence:
            worker_log.warning(
                "⚠️ 本次音频语言置信度过低，已跳过长总结生成，改用失败提示 + 原始简介兜底。"
            )

            class FallbackSummaryResult:
                def __init__(self, summary: str, keyframe_timestamps: list[int]):
                    self.summary = summary
                    self.keyframe_timestamps = keyframe_timestamps

            summary_result = FallbackSummaryResult(
                summary=_fallback_long_summary(
                    item_ctx,
                    reason=f"language_probability={language_probability:.2f}",
                ),
                keyframe_timestamps=_pick_random_keyframe_timestamps(duration_seconds, count=5),
            )
        else:
            timed_transcript_text = _build_timed_transcript(segments)
            worker_log.info("🧠 导演层: 大语言模型接入交叉融合语义纠偏...")
            summary_result = await summarize_video_transcript(item_ctx, timed_transcript_text)
        
        worker_log.info(f"📝 提炼的关键帧锚点: {summary_result.keyframe_timestamps}")
        
        # 4. FFmpeg 截帧落地
        keyframes_urls = []
        if summary_result.keyframe_timestamps:
            worker_log.info("📸 开始通过 FFmpeg 切取高光关键帧快照...")
            os.makedirs(os.path.join("data", "static", "keyframes"), exist_ok=True)
            try:
                worker_log.info("📹 正在下载本地视频缓存用于关键帧抽取...")
                video_path = await asyncio.to_thread(
                    YTDlpService.download_video_1080p,
                    url,
                    str(requested_video_path),
                )
                worker_log.info(f"🎞️ 视频已落盘: {video_path}")

                for idx, ts in enumerate(summary_result.keyframe_timestamps):
                    filename = f"{item_id}_{idx}_{ts}.jpg"
                    filepath = os.path.join("data", "static", "keyframes", filename)

                    cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(ts),
                        "-i", video_path,
                        "-frames:v", "1",
                        "-q:v", "2",
                        filepath
                    ]

                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE
                    )
                    _, stderr = await proc.communicate()

                    if proc.returncode == 0 and os.path.exists(filepath):
                        keyframes_urls.append(f"/api/static/keyframes/{filename}")
                    else:
                        err_text = stderr.decode("utf-8", errors="ignore").strip()
                        worker_log.warning(
                            f"⚠️ 关键帧抽取失败 [timestamp={ts}] returncode={proc.returncode}: {err_text[:500]}"
                        )

                worker_log.info(f"✅ 成功生成 {len(keyframes_urls)} 张关键帧图片")
            except Exception as e:
                worker_log.warning(f"⚠️ 关键帧流抽取中断: {e}")
        
        worker_log.info("💾 落地层: 将源数据与总结写入 Postgre 内核...")
        async with AsyncSessionLocal() as session:
            meta = dict(item_data.metadata_extra) if item_data.metadata_extra else {}
            meta["raw_transcript"] = raw_transcript_json
            meta["keyframes"] = keyframes_urls
            meta["keyframe_timestamps"] = summary_result.keyframe_timestamps
            meta["has_long_summary"] = True
            meta["long_summary"] = summary_result.summary
            if low_confidence:
                meta["summary_fallback_reason"] = "transcription_low_confidence"
                meta["transcription_language_probability"] = language_probability
            
            await session.execute(
                ItemORM.__table__.update()
                .where(ItemORM.id == item_id)
                .values(
                    metadata_extra=meta
                )
            )
            await session.commit()
            worker_log.info("🎯 多媒体终极流水线完美收官！")
            
    except Exception as e:
        worker_log.error(f"❌ 多媒体任务核心链崩塌: {e}")
    finally:
        if task_cache_dir.exists():
            shutil.rmtree(task_cache_dir, ignore_errors=True)
            worker_log.info(f"🧹 已清理本次多媒体缓存目录: {task_cache_dir}")
