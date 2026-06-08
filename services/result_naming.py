"""결과 파일명 생성 — 요청·컬럼·차트 종류 등 맥락을 파일명에 반영."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from services.file_manager import RESULT_DIR

_SLUG_CLEAN = re.compile(r"[^\w가-힣+-]+", re.UNICODE)
_PROMPT_TRIM_SUFFIXES = (
    "해 주세요", "해주세요", "해 줘", "해줘",
    "보여 주세요", "보여주세요", "보여 줘", "보여줘",
    "만들어 주세요", "만들어주세요", "만들어 줘", "만들어줘",
    "알려 주세요", "알려주세요", "알려 줘", "알려줘",
    "출력해줘", "출력해 줘", "저장해줘", "저장해 줘",
)


def slugify(text: str, max_len: int = 40) -> str:
    """파일명에 쓸 수 있는 짧은 slug."""
    s = _SLUG_CLEAN.sub("_", str(text).strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return "결과"
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s or "결과"


def prompt_slug(prompt: str, max_len: int = 28) -> str:
    """사용자 질문에서 파일명 힌트 추출."""
    text = str(prompt).strip()
    for suffix in _PROMPT_TRIM_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    return slugify(text, max_len=max_len)


def build_filename(prefix: str, *parts: str, ext: str, max_stem_len: int = 96) -> str:
    """타임스탬프 포함 고유 파일명 생성."""
    if not ext.startswith("."):
        ext = f".{ext}"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    segments = [prefix]
    for part in parts:
        s = slugify(part)
        if s and s not in segments:
            segments.append(s)
    segments.append(ts)

    stem = "_".join(segments)
    if len(stem) > max_stem_len:
        stem = stem[:max_stem_len].rstrip("_")

    name = f"{stem}{ext}"
    if not (RESULT_DIR / name).exists():
        return name

    for i in range(2, 100):
        alt = f"{stem}_{i}{ext}"
        if not (RESULT_DIR / alt).exists():
            return alt
    return name


def chart_filename(chart_type: str, title: str, prompt: str = "") -> str:
    """차트 PNG 파일명 — 예: chart_bar_비목분류_계획예산_20260608_144530.png"""
    title_part = (
        str(title)
        .replace(" × ", "_")
        .replace("·", "_")
        .replace(" vs ", "_")
    )
    return build_filename(f"chart_{chart_type}", title_part, ext=".png")


def result_filename(
    prompt: str = "",
    label: str = "",
    intent: str = "",
) -> str:
    """DataFrame 결과 xlsx — 예: result_filter_계획예산1000만이상_20260608_144530.xlsx"""
    parts: list[str] = []
    if intent:
        parts.append(intent)
    if prompt:
        parts.append(prompt_slug(prompt))
    elif label:
        parts.append(slugify(label.replace("—", "_").replace("**", ""), max_len=36))
    return build_filename("result", *parts, ext=".xlsx")


def export_filename(prompt: str = "", label: str = "") -> str:
    """export 도구 저장명 — 예: export_병합결과_20260608_144530.xlsx"""
    hint = prompt_slug(prompt) if prompt else slugify(label, max_len=28) if label else "데이터"
    return build_filename("export", hint, ext=".xlsx")


def code_chart_filename(prompt: str = "") -> str:
    """LLM 코드로 생성된 차트 PNG."""
    hint = prompt_slug(prompt) if prompt else "생성"
    return build_filename("chart", hint, ext=".png")


_TS_SUFFIX = re.compile(r"_\d{8}_\d{6}(?:_\d+)?$")


def download_label(filename: str) -> str:
    """채팅 다운로드 버튼용 짧은 표시명 (타임스탬프·확장자 제거)."""
    stem = Path(filename).stem
    stem = _TS_SUFFIX.sub("", stem)
    return stem.replace("_", " ")


def saved_files_hint(saved: list[str]) -> str:
    """채팅 답변에 붙일 다운로드 안내 문구."""
    if not saved:
        return ""
    if len(saved) == 1:
        return f"\n\n💾 **{download_label(saved[0])}** — 아래 버튼으로 다운로드하세요."
    items = "\n".join(f"- **{download_label(f)}**" for f in saved)
    return f"\n\n💾 저장된 파일:\n{items}\n\n아래 버튼으로 다운로드하세요."
