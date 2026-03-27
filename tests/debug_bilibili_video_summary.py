import asyncio
import json
import os
import shutil
import tempfile
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hub.core.llm.summarizer import summarize_video_transcript
from hub.core.media.downloader import YTDlpService
from hub.core.media.transcriber import TranscriberFactory
from hub.core.model_settings import get_model_assignments

# BV1s6XnBcE72 long
# BV1cbXWBKEMd short
BV_ID = "BV1cbXWBKEMd"
VIDEO_URL = f"https://www.bilibili.com/video/{BV_ID}"
OUTPUT_DIR = Path("tests") / "output"
CACHE_ROOT = Path("data") / "cache" / "media_tests"


@dataclass
class DebugContext:
    title: str
    summary: str


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
    return sorted(random.sample(candidates, sample_size))


def _safe_text(value: str | None) -> str:
    return (value or "").strip()


def _markdown_code_block(title: str, content: str, lang: str = "text") -> str:
    return f"## {title}\n\n```{lang}\n{content.rstrip()}\n```\n"


async def _extract_keyframes(
    item_id: str,
    video_path: str,
    timestamps: list[int],
) -> tuple[list[Path], list[str]]:
    keyframe_dir = OUTPUT_DIR / "keyframes"
    keyframe_dir.mkdir(parents=True, exist_ok=True)

    logs: list[str] = []
    generated: list[Path] = []

    if not timestamps:
        logs.append("没有可用的时间戳，跳过关键帧抽取。")
        return generated, logs

    if not video_path:
        logs.append("未提供本地视频路径，跳过关键帧抽取。")
        return generated, logs

    for idx, ts in enumerate(timestamps):
        output_path = keyframe_dir / f"{item_id}_{idx}_{ts}.jpg"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(ts),
            "-i",
            video_path,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        logs.append(
            "\n".join(
                [
                    f"[timestamp={ts}] returncode={proc.returncode}",
                    stdout.decode("utf-8", errors="ignore").strip(),
                    stderr.decode("utf-8", errors="ignore").strip(),
                ]
            ).strip()
        )

        if proc.returncode == 0 and output_path.exists():
            generated.append(output_path)

    return generated, logs


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    report_path = OUTPUT_DIR / f"video_summary_{BV_ID}.md"
    task_cache_dir = Path(tempfile.mkdtemp(prefix=f"{BV_ID}_", dir=str(CACHE_ROOT)))
    requested_audio_path = task_cache_dir / "audio.mp3"

    audio_path = ""
    video_path = ""
    transcript_segments: list[dict] = []
    transcript_text = ""
    provider = "local_whisper"
    model_name = "small"
    transcript_meta: dict = {}
    keyframes: list[Path] = []
    keyframe_logs: list[str] = []
    summary_result = None
    stream_info = {}

    try:
        stream_info = await asyncio.to_thread(YTDlpService.extract_info, VIDEO_URL, {})
        title = _safe_text(stream_info.get("title")) or BV_ID
        description = _safe_text(stream_info.get("description")) or "暂无简介"
        context = DebugContext(title=title, summary=description)

        audio_path = await asyncio.to_thread(
            YTDlpService.download_audio,
            VIDEO_URL,
            str(requested_audio_path),
        )

        assignments = await get_model_assignments()
        speech_cfg = next((a for a in assignments if a["key"] == "speech_to_text"), None)
        provider = speech_cfg["provider"] if speech_cfg else "local_whisper"
        model_name = speech_cfg["model"] if speech_cfg else "small"

        transcript_result = await TranscriberFactory.transcribe_audio(audio_path, provider, model_name)
        transcript_segments = transcript_result.get("segments", [])
        transcript_meta = transcript_result
        transcript_text = " ".join([segment["text"] for segment in transcript_segments]).strip()
        timed_transcript = _build_timed_transcript(transcript_segments)

        if transcript_result.get("low_confidence"):
            fallback_summary = (
                "转译失败，可能为纯音频、背景音乐或难以稳定识别的内容，因此未生成新的 AI 长总结。\n\n"
                "作为兜底，下面保留原始简介或短摘要供参考：\n\n"
                f"{description}"
            )

            class FallbackSummaryResult:
                def __init__(self, summary: str, keyframe_timestamps: list[int]):
                    self.summary = summary
                    self.keyframe_timestamps = keyframe_timestamps

            summary_result = FallbackSummaryResult(
                fallback_summary,
                _pick_random_keyframe_timestamps(stream_info.get("duration"), count=5),
            )
        else:
            summary_result = await summarize_video_transcript(context, timed_transcript)
        video_path = await asyncio.to_thread(
            YTDlpService.download_video_1080p,
            VIDEO_URL,
            str(task_cache_dir / "video.mp4"),
        )
        keyframes, keyframe_logs = await _extract_keyframes(
            BV_ID,
            video_path,
            summary_result.keyframe_timestamps,
        )

        lines: list[str] = [
            f"# Bilibili 视频 AI 总结调试报告",
            "",
            f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
            f"- BV: `{BV_ID}`",
            f"- URL: {VIDEO_URL}",
            f"- 标题: {title}",
            f"- Whisper 提供商: `{provider}`",
            f"- Whisper 模型: `{model_name}`",
            f"- 音频路径: `{audio_path}`",
            f"- 视频路径: `{video_path}`",
            f"- 语言识别: `{transcript_meta.get('language')}`",
            f"- 语言置信度: `{transcript_meta.get('language_probability')}`",
            f"- 是否低置信度降级: `{bool(transcript_meta.get('low_confidence'))}`",
            f"- 转录片段数: `{len(transcript_segments)}`",
            f"- 提取到的时间戳: `{summary_result.keyframe_timestamps}`",
            f"- 成功生成关键帧数: `{len(keyframes)}`",
            "",
            "## 视频简介",
            "",
            description,
            "",
            "## AI 深度总结",
            "",
            summary_result.summary,
            "",
        ]

        if keyframes:
            lines.extend(
                [
                    "## 关键帧文件",
                    "",
                    *[f"- `{path.as_posix()}`" for path in keyframes],
                    "",
                ]
            )

        lines.append(_markdown_code_block("关键帧抽取日志", "\n\n".join(keyframe_logs) or "无"))
        lines.append(_markdown_code_block("视频元数据摘要", json.dumps({
            "title": stream_info.get("title"),
            "duration": stream_info.get("duration"),
            "uploader": stream_info.get("uploader"),
            "http_headers": stream_info.get("http_headers"),
        }, ensure_ascii=False, indent=2), "json"))
        lines.append(_markdown_code_block("转录 JSON", json.dumps(transcript_segments, ensure_ascii=False, indent=2), "json"))
        lines.append(_markdown_code_block("完整转录文本", transcript_text or "无"))

        report_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Markdown 报告已生成: {report_path}")

    finally:
        if task_cache_dir.exists():
            shutil.rmtree(task_cache_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
