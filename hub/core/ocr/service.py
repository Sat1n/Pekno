from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import warnings
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader
import pypdfium2 as pdfium

from hub.core import model_settings
from shared.config import SYSTEM_CONFIG_USER_ID, ConfigManager

DEFAULT_OCR_PROVIDER = "paddleocr_v5_cpu"
DEFAULT_OCR_MODEL = "PP-OCRv5"
DEFAULT_OCR_CONFIG = {
    "enabled": "true",
    "lang": "ch",
    "max_workers": "1",
}

_ocr_engine: Any | None = None
_ocr_engine_signature: tuple[str, str] | None = None
_ocr_engine_lock = asyncio.Lock()
_ocr_semaphore: asyncio.Semaphore | None = None
_ocr_semaphore_size = 1

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("GLOG_minloglevel", "2")


class OCRConfigError(RuntimeError):
    pass


class OCRDisabledError(RuntimeError):
    pass


@contextlib.contextmanager
def _suppress_ocr_noise():
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r".*RequestsDependencyWarning.*")
        warnings.filterwarnings("ignore", message=r".*No ccache found.*")
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            yield


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _parse_positive_int(value: Any, default: int = 1) -> int:
    try:
        parsed = int(str(value).strip())
        return parsed if parsed > 0 else default
    except Exception:
        return default


async def _load_provider_config(provider_id: str) -> dict[str, Any]:
    raw_value = await ConfigManager.get_config(
        model_settings.MODEL_SETTINGS_NAMESPACE,
        f"provider_config::{provider_id}",
        default=None,
        user_id=SYSTEM_CONFIG_USER_ID,
    )
    if not raw_value:
        return dict(DEFAULT_OCR_CONFIG)
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return dict(DEFAULT_OCR_CONFIG)
    if not isinstance(parsed, dict):
        return dict(DEFAULT_OCR_CONFIG)
    merged = dict(DEFAULT_OCR_CONFIG)
    merged.update(parsed)
    return merged


async def _get_ocr_runtime() -> tuple[str, str, dict[str, Any]]:
    assignments = await model_settings.get_model_assignments()
    assignment = next((item for item in assignments if item["key"] == "ocr"), None)
    if not assignment:
        return DEFAULT_OCR_PROVIDER, DEFAULT_OCR_MODEL, dict(DEFAULT_OCR_CONFIG)

    provider_id = assignment.get("provider") or DEFAULT_OCR_PROVIDER
    model_name = assignment.get("model") or DEFAULT_OCR_MODEL
    if provider_id != DEFAULT_OCR_PROVIDER:
        raise OCRConfigError(f"当前 OCR 提供商 [{provider_id}] 不受支持，仅支持本地 PaddleOCR v5 CPU")

    config = await _load_provider_config(provider_id)
    return provider_id, model_name, config


async def _get_ocr_engine(lang: str, model_name: str, max_workers: int):
    global _ocr_engine, _ocr_engine_signature, _ocr_semaphore, _ocr_semaphore_size

    if _ocr_semaphore is None or _ocr_semaphore_size != max_workers:
        _ocr_semaphore = asyncio.Semaphore(max_workers)
        _ocr_semaphore_size = max_workers

    signature = (lang, model_name)
    if _ocr_engine is not None and _ocr_engine_signature == signature:
        return _ocr_engine

    async with _ocr_engine_lock:
        if _ocr_engine is not None and _ocr_engine_signature == signature:
            return _ocr_engine

        with _suppress_ocr_noise():
            from paddleocr import PaddleOCR

        base_kwargs = {
            "lang": lang,
            "device": "cpu",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
        attempts = [
            {**base_kwargs, "ocr_version": model_name},
            dict(base_kwargs),
            {
                "lang": lang,
                "ocr_version": model_name,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
            },
            {
                "lang": lang,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
            },
            {"lang": lang, "ocr_version": model_name},
            {"lang": lang},
        ]

        last_error: Exception | None = None
        for kwargs in attempts:
            try:
                with _suppress_ocr_noise():
                    _ocr_engine = PaddleOCR(**kwargs)
                _ocr_engine_signature = signature
                return _ocr_engine
            except Exception as exc:
                last_error = exc

        raise OCRConfigError(f"本地 PaddleOCR 初始化失败: {last_error}")


def _looks_like_points(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or not value:
        return False
    first = value[0]
    if isinstance(first, (list, tuple)) and len(first) >= 2:
        return True
    return len(value) == 4 and all(isinstance(item, (int, float)) for item in value)


def _bbox_to_norm(points: Any, width: int, height: int) -> dict[str, float] | None:
    if width <= 0 or height <= 0:
        return None
    try:
        if isinstance(points, (list, tuple)) and len(points) == 4 and all(isinstance(item, (int, float)) for item in points):
            x1, y1, x2, y2 = [float(item) for item in points]
            left, top = min(x1, x2), min(y1, y2)
            right, bottom = max(x1, x2), max(y1, y2)
        else:
            coords = [(float(point[0]), float(point[1])) for point in points if isinstance(point, (list, tuple)) and len(point) >= 2]
            if not coords:
                return None
            xs = [item[0] for item in coords]
            ys = [item[1] for item in coords]
            left, top = min(xs), min(ys)
            right, bottom = max(xs), max(ys)
        return {
            "x": max(0.0, min(1.0, left / width)),
            "y": max(0.0, min(1.0, top / height)),
            "width": max(0.0, min(1.0, (right - left) / width)),
            "height": max(0.0, min(1.0, (bottom - top) / height)),
        }
    except Exception:
        return None


def _normalize_ocr_output(raw_result: Any, width: int, height: int) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []

    def add_block(text: Any, score: Any, points: Any):
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return
        bbox_norm = _bbox_to_norm(points, width, height)
        if not bbox_norm:
            return
        try:
            score_value = float(score) if score is not None else 0.0
        except Exception:
            score_value = 0.0
        blocks.append(
            {
                "text": normalized_text,
                "score": score_value,
                "bbox_norm": bbox_norm,
            }
        )

    def consume(entry: Any):
        if isinstance(entry, dict):
            rec_texts = entry.get("rec_texts")
            rec_scores = entry.get("rec_scores")
            polys = entry.get("dt_polys") or entry.get("polys")
            if isinstance(rec_texts, list):
                for index, text in enumerate(rec_texts):
                    score = rec_scores[index] if isinstance(rec_scores, list) and index < len(rec_scores) else None
                    poly = polys[index] if isinstance(polys, list) and index < len(polys) else None
                    add_block(text, score, poly)
                return

            add_block(
                entry.get("text") or entry.get("rec_text"),
                entry.get("score") or entry.get("rec_score"),
                entry.get("bbox") or entry.get("poly") or entry.get("points") or entry.get("dt_poly"),
            )
            return

        if isinstance(entry, (list, tuple)):
            if len(entry) >= 2 and _looks_like_points(entry[0]):
                text_info = entry[1]
                if isinstance(text_info, (list, tuple)):
                    text = text_info[0] if len(text_info) > 0 else ""
                    score = text_info[1] if len(text_info) > 1 else None
                else:
                    text = text_info
                    score = entry[2] if len(entry) > 2 else None
                add_block(text, score, entry[0])
                return

            for child in entry:
                consume(child)

    consume(raw_result)

    full_text = "\n".join(block["text"] for block in blocks)
    return {
        "full_text": full_text.strip(),
        "blocks": blocks,
    }


def _run_ocr_sync(engine: Any, image_path: Path, width: int, height: int) -> dict[str, Any]:
    with _suppress_ocr_noise():
        if hasattr(engine, "predict"):
            raw_result = engine.predict(str(image_path))
        elif hasattr(engine, "ocr"):
            raw_result = engine.ocr(str(image_path))
        else:
            raise OCRConfigError("当前 PaddleOCR 实例不支持可识别的调用方式")
    return _normalize_ocr_output(raw_result, width, height)


async def run_image_ocr(image_path: str | Path) -> tuple[dict[str, Any], str, str]:
    provider_id, model_name, config = await _get_ocr_runtime()
    if not _parse_bool(config.get("enabled"), True):
        raise OCRDisabledError("OCR 已在设置中禁用")

    lang = str(config.get("lang") or "ch").strip() or "ch"
    max_workers = _parse_positive_int(config.get("max_workers"), 1)
    engine = await _get_ocr_engine(lang, model_name, max_workers)
    assert _ocr_semaphore is not None

    image_file = Path(image_path)
    with Image.open(image_file) as image:
        width, height = image.size

    async with _ocr_semaphore:
        result = await asyncio.to_thread(_run_ocr_sync, engine, image_file, width, height)

    return result, provider_id, model_name


def _extract_pdf_text_pages(pdf_path: Path) -> list[str]:
    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return []
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append((page.extract_text() or "").strip())
        except Exception:
            pages.append("")
    return pages


def _has_meaningful_text(text: str) -> bool:
    normalized = " ".join((text or "").split())
    return len(normalized) >= 20


async def run_pdf_ocr(pdf_path: str | Path) -> tuple[dict[str, Any], str, str]:
    provider_id, model_name, config = await _get_ocr_runtime()
    if not _parse_bool(config.get("enabled"), True):
        raise OCRDisabledError("OCR 已在设置中禁用")

    lang = str(config.get("lang") or "ch").strip() or "ch"
    max_workers = _parse_positive_int(config.get("max_workers"), 1)
    engine = await _get_ocr_engine(lang, model_name, max_workers)
    assert _ocr_semaphore is not None

    pdf_file = Path(pdf_path)
    extracted_pages = _extract_pdf_text_pages(pdf_file)
    document = pdfium.PdfDocument(str(pdf_file))

    page_results: list[dict[str, Any]] = []
    full_text_parts: list[str] = []
    ocr_page_count = 0

    try:
        for page_index in range(len(document)):
            extracted_text = extracted_pages[page_index] if page_index < len(extracted_pages) else ""
            if _has_meaningful_text(extracted_text):
                normalized_text = " ".join(extracted_text.split())
                page_results.append(
                    {
                        "page": page_index + 1,
                        "full_text": normalized_text,
                        "blocks": [],
                        "source": "text",
                    }
                )
                full_text_parts.append(normalized_text)
                continue

            page = document[page_index]
            bitmap = page.render(scale=2)
            pil_image = bitmap.to_pil()
            temp_image_path = pdf_file.parent / f".ocr-page-{page_index + 1}.png"
            pil_image.save(temp_image_path)
            try:
                async with _ocr_semaphore:
                    page_result = await asyncio.to_thread(
                        _run_ocr_sync,
                        engine,
                        temp_image_path,
                        pil_image.width,
                        pil_image.height,
                    )
            finally:
                temp_image_path.unlink(missing_ok=True)
                bitmap.close()
                page.close()

            page_full_text = page_result["full_text"].strip()
            page_results.append(
                {
                    "page": page_index + 1,
                    "full_text": page_full_text,
                    "blocks": page_result["blocks"],
                    "source": "ocr",
                }
            )
            if page_full_text:
                full_text_parts.append(page_full_text)
            ocr_page_count += 1
    finally:
        document.close()

    return (
        {
            "full_text": "\n\n".join(part for part in full_text_parts if part).strip(),
            "pages": page_results,
            "ocr_page_count": ocr_page_count,
        },
        provider_id,
        model_name,
    )
