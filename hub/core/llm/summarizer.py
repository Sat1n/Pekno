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
    keyframe_timestamps: list[int]  # 推荐截取画面的整数秒数列表（1-3个）


def _repair_video_summary_json(raw_output: str, locale: str) -> VideoSummaryResult | None:
    """
    尝试修复 LLM 返回的格式不正确的 JSON。
    常见错误: keyframe_timestamps 被写成嵌套数组 [[1,2,3]], 或多了额外字段。
    """
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError:
        # JSON 本身不合法, 跳过后面的摘要提取
        return _extract_summary_by_regex(raw_output, locale)

    # 修复 keyframe_timestamps: 拍平嵌套数组 [[1,2,3]] -> [1,2,3]
    if isinstance(data, dict):
        timestamps = data.get("keyframe_timestamps")
        if isinstance(timestamps, list):
            while len(timestamps) == 1 and isinstance(timestamps[0], list):
                timestamps = timestamps[0]
            data["keyframe_timestamps"] = [int(v) for v in timestamps if isinstance(v, (int, float))]

        # 先尝试用修复后的 data 重新构建
        try:
            return VideoSummaryResult(
                summary=data.get("summary", ""),
                keyframe_timestamps=data["keyframe_timestamps"],
            )
        except Exception:
            pass

    return _extract_summary_by_regex(raw_output, locale)


def _extract_summary_by_regex(raw_output: str, locale: str) -> VideoSummaryResult | None:
    """层 2: 用正则从原始输出中提取 summary 字段的文本内容 (兼容非法 JSON)。"""
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

async def summarize_video_transcript(item: Any, transcript: str, preferred_locale: str | None = None) -> VideoSummaryResult:
    """
    AI 导演总结引擎 - 防幻觉机制与复合约束注入
    将语音识别输出作为输入交给大模型，通过约束提示指令强制输出带有关键画面时间轴节点的标准结构体。
    """
    normalized_locale = normalize_preferred_locale(preferred_locale)
    prompt = f"""你是一个专业视频分析师。请根据以下信息总结：

    【高信度参考资料】（利用此处的语境纠正转录错误）：
    标题={item.title}
    简介={item.summary}

    【AI 语音转录文本】（每段前面的 [mm:ss] / [hh:mm:ss] 是时间锚点，可能存在同音字，请自动纠正）：
    {transcript}

    任务：
    1. 输出适合前端直接渲染的深度总结，使用 Markdown。
    2. 总结必须尽量写成分点结构，避免大段连续正文。
    3. 每个重点尽量带一个时间标记，推荐写成 `- [mm:ss] 重点内容`。
    4. 挑选 1-3 个最具代表性的高光画面时间戳（整数秒）。
    5. {build_output_language_instruction(normalized_locale)}

    输出要求：
    1. `summary` 字段必须是符合语言要求的 Markdown。
    2. `summary` 开头先给一段约 50 字的总览，尽量完整交代主题、核心结论与讨论方向。
    3. 然后给出 3-6 条要点列表。
    4. 如果能从转录中定位时间，就在对应要点前标注时间；如果某条无法确定精确时间，可以不标，但整体至少尽量覆盖 2 条带时间的要点。
    5. 不要编造转录中没有出现的细节。

    请仅输出合法的 JSON 格式内容，禁止包含多余废话或 Markdown 代码块标记（无需 ```json）。JSON 的键必须精确为以下两个：
    "summary": 你的深度总结文本内容（字符串）
    "keyframe_timestamps": [时间点数字数组，如 [15, 60, 120]]
    """

    provider, _ = await _build_llm_provider("long_summary")
    
    if isinstance(provider, OpenAIProvider):
        # 兼容高级大模型：启用显式 JSON 格式
        response = await provider.client.chat.completions.create(
            model=provider.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        raw_output = response.choices[0].message.content
    else:
        # 向下兼容普通开源大模型 (Ollama)
        response = await provider.client.chat.completions.create(
            model=getattr(provider, "model_name", getattr(provider, "model", "")),
            messages=[{"role": "user", "content": prompt}],
        )
        raw_output = response.choices[0].message.content or ""
        
    try:
        raw_output = re.sub(r'```json\s*', '', raw_output.strip())
        raw_output = re.sub(r'```\s*', '', raw_output)
        data = json.loads(raw_output)
        return VideoSummaryResult(**data)
    except Exception as e:
        hub_log.warning(f"⚠️ Director summary engine returned malformed JSON, attempting repair: {e}")

        # 层 1: 尝试修复常见 JSON 错误
        repaired = _repair_video_summary_json(raw_output, normalized_locale)
        if repaired:
            return repaired

        hub_log.error(f"❌ Director summary engine repair failed, raw_output={raw_output}")
        fallback_summary = (
            "Failed to parse the structured multimedia summary output."
            if normalized_locale == "en"
            else "无法解析结构化多媒体总结输出。"
        )
        return VideoSummaryResult(
            summary=fallback_summary,
            keyframe_timestamps=[]
        )
