from __future__ import annotations

SUPPORTED_APP_LOCALES = {"zh-CN", "en"}


def normalize_preferred_locale(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw == "zh" or raw.startswith("zh-cn") or raw.startswith("zh-hans"):
        return "zh-CN"
    if raw.startswith("en"):
        return "en"
    return "en"


def get_locale_display_name(locale: str | None) -> str:
    normalized = normalize_preferred_locale(locale)
    if normalized == "zh-CN":
        return "Simplified Chinese"
    return "English"


def build_output_language_instruction(locale: str | None, *, style: str = "text") -> str:
    language_name = get_locale_display_name(locale)
    if style == "tags":
        return f"Output language requirement: return the tags in {language_name}."
    if style == "json":
        return (
            f"Output language requirement: keep the JSON structure unchanged, "
            f"and write all natural-language field values in {language_name}."
        )
    return f"Output language requirement: write the final answer in {language_name}."
