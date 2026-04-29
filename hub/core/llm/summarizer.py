import json
import re
from pydantic import BaseModel
from typing import Any
from hub.core.model_settings import _build_llm_provider
from hub.core.llm.providers.openai_adapter import OpenAIProvider
from shared.logger import hub_log
from shared.locale import build_output_language_instruction, normalize_preferred_locale

class VideoSummaryResult(BaseModel):
    summary: str
    keyframe_timestamps: list[int]

TIMESTAMP_FALLBACK: list[int] = []


def _repair_video_summary_json(raw_output: str, locale: str) -> VideoSummaryResult | None:
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError:
        return _extract_summary_by_regex(raw_output, locale)

    if isinstance(data, dict):
        timestamps = data.get("keyframe_timestamps")
        if isinstance(timestamps, list):
            while len(timestamps) == 1 and isinstance(timestamps[0], list):
                timestamps = timestamps[0]
            data["keyframe_timestamps"] = [int(v) for v in timestamps if isinstance(v, (int, float))]

        try:
            return VideoSummaryResult(
                summary=data.get("summary", ""),
                keyframe_timestamps=data["keyframe_timestamps"],
            )
        except Exception:
            pass

    return _extract_summary_by_regex(raw_output, locale)


def _extract_summary_by_regex(raw_output: str, locale: str) -> VideoSummaryResult | None:
    match = re.search(r'"summary"\s*:\s*"', raw_output)
    if not match:
        return None

    start = match.end()
    content_chars = []
    i = start
    while i < len(raw_output):
        ch = raw_output[i]
        if ch == "\\" and i + 1 < len(raw_output):
            content_chars.append(raw_output[i + 1])
            i += 2
        elif ch == '"':
            break
        else:
            content_chars.append(ch)
            i += 1

    summary_text = "".join(content_chars)
    if not summary_text.strip():
        return None

    hub_log.info(f"🔧 Extracted summary via regex ({len(summary_text)} chars), keyframe_timestamps empty.")
    return VideoSummaryResult(summary=summary_text, keyframe_timestamps=[])


async def _call_llm(provider, prompt: str) -> str:
    if isinstance(provider, OpenAIProvider):
        response = await provider.client.chat.completions.create(
            model=provider.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    else:
        response = await provider.client.chat.completions.create(
            model=getattr(provider, "model_name", getattr(provider, "model", "")),
            messages=[{"role": "user", "content": prompt}],
        )
    return response.choices[0].message.content or ""


def _parse_keyframe_timestamps(raw_output: str) -> list[int]:
    raw = re.sub(r'```json\s*', '', raw_output.strip())
    raw = re.sub(r'```\s*', '', raw)

    # 尝试 JSON 解析
    try:
        data = json.loads(raw)
        ts = data if isinstance(data, list) else data.get("keyframe_timestamps", [])
        if isinstance(ts, list):
            while len(ts) == 1 and isinstance(ts[0], list):
                ts = ts[0]
            return [int(v) for v in ts if isinstance(v, (int, float))]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # 正则降级: 匹配文本中的整数
    numbers = re.findall(r'\b\d{2,5}\b', raw)
    parsed = []
    for n in numbers:
        val = int(n)
        if 0 <= val <= 7200:
            parsed.append(val)
    return sorted(set(parsed))[:5]


async def _extract_keyframe_timestamps(provider, item: Any, transcript: str, locale: str) -> list[int]:
    lang_instr = build_output_language_instruction(locale)

    prompt = f"""你是一个视频画面分析助手。请从以下视频转录中找出 2-4 个最具代表性的高光画面时间戳。

【参考资料】
标题={item.title}
简介={item.summary}

【转录文本】（每段前面的 [mm:ss] / [hh:mm:ss] 是时间锚点）：
{transcript}

任务：
1. 挑选 2-4 个最关键的时刻，它们在视频中最有代表性（比如转折点、核心论点、精彩场景）。
2. 只输出时间戳对应的秒数（整数），不要输出任何解释文字。
3. 严格输出一个 JSON 数组，例如 [145, 320, 580]。
4. {lang_instr}

请仅输出 JSON 数组，不要包裹在 markdown 代码块中。"""

    hub_log.info("🎬 Step 1/2: Extracting keyframe timestamps...")
    raw = await _call_llm(provider, prompt)

    try:
        timestamps = _parse_keyframe_timestamps(raw)
        if timestamps:
            hub_log.info(f"📸 Keyframe timestamps extracted: {timestamps}")
            return timestamps
    except Exception:
        pass

    hub_log.warning(f"⚠️ Failed to extract keyframe timestamps, raw_output={raw[:200]}")
    return TIMESTAMP_FALLBACK


async def _generate_summary(provider, item: Any, transcript: str, timestamps: list[int], locale: str) -> str:
    lang_instr = build_output_language_instruction(locale)

    timestamp_hint = ""
    if timestamps:
        timestamp_hint = (
            f"\n【已识别的关键时间戳（整数秒）】：{timestamps}\n"
            "请在总结中重点围绕这些时间点的内容展开。"
        )

    prompt = f"""你是一个专业视频分析师。请根据以下信息写一份深度总结。

【高信度参考资料】（利用此处的语境纠正转录错误）：
标题={item.title}
简介={item.summary}
{timestamp_hint}
【AI 语音转录文本】（每段前面的 [mm:ss] / [hh:mm:ss] 是时间锚点，可能存在同音字，请自动纠正）：
{transcript}

任务：
1. 输出适合前端直接渲染的深度总结，使用 Markdown。
2. 总结必须尽量写成分点结构，避免大段连续正文。
3. 每个重点尽量带一个时间标记，推荐写成 `- [mm:ss] 重点内容`。
4. {lang_instr}

输出要求：
1. 开头先给一段约 50 字的总览，尽量完整交代主题、核心结论与讨论方向。
2. 然后给出 3-6 条要点列表。
3. 如果能从转录中定位时间，就在对应要点前标注时间；如果某条无法确定精确时间，可以不标，但整体至少尽量覆盖 2 条带时间的要点。
4. 不要编造转录中没有出现的细节。
5. 仅输出 Markdown 文本，不要包裹在 JSON 或代码块中。"""

    hub_log.info("📝 Step 2/2: Generating long-form summary...")
    raw = await _call_llm(provider, prompt)
    return raw.strip()


async def summarize_video_transcript(item: Any, transcript: str, preferred_locale: str | None = None) -> VideoSummaryResult:
    """
    AI 导演总结引擎 - 两步式流水线。

    第一步: 从转录中提取关键帧时间戳 (短 prompt, 适合小模型)。
    第二步: 将时间戳作为上下文, 生成深度 Markdown 总结。
    """
    normalized_locale = normalize_preferred_locale(preferred_locale)

    provider, _ = await _build_llm_provider("long_summary")

    # Step 1: Extract keyframe timestamps
    timestamps = await _extract_keyframe_timestamps(provider, item, transcript, normalized_locale)

    # Step 2: Generate summary
    summary_text = await _generate_summary(provider, item, transcript, timestamps, normalized_locale)

    if not summary_text:
        fallback = (
            "Failed to generate the multimedia summary."
            if normalized_locale == "en"
            else "无法生成多媒体总结。"
        )
        return VideoSummaryResult(summary=fallback, keyframe_timestamps=timestamps)

    return VideoSummaryResult(summary=summary_text, keyframe_timestamps=timestamps)
