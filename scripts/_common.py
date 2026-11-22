"""Shared helpers for the AI Content Studio scripts.

Standard library only, so every script works in any environment that has
Python 3.9+ (Kimi Code, Kimi Work, an agent sandbox on kimi.com, or a plain terminal).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
TEMPLATES_DIR = ASSETS_DIR / "templates"
BAKED_BRAND_DIR = SKILL_DIR / "brand"

FORMATS = ("reel", "story", "carousel", "email")
FORMAT_LABELS = {"reel": "Reel", "story": "Story", "carousel": "Carousel", "email": "Email"}
STATUSES = ("planned", "drafted", "ready", "published")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = {
    "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
    "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
}
PLATFORMS = ("instagram", "tiktok", "youtube_shorts", "email")
PLATFORM_LABELS = {
    "instagram": "Instagram", "tiktok": "TikTok",
    "youtube_shorts": "YouTube Shorts", "email": "Email",
}

MAX_PER_WEEK = 28
MAX_PER_DAY = 4

# --- language helpers (Chinese support) ---------------------------------------------------
CJK_CHARS = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
CJK_PUNCT = "\u3000-\u303f\uff00-\uff0f\uff1a-\uff20\uff3b-\uff40\uff5b-\uff65\u2018\u2019\u201c\u201d\u2026\u00b7"
_CJK_RE = re.compile(f"[{CJK_CHARS}]")


def has_cjk(text) -> bool:
    """True if the text contains Chinese/Japanese/Korean ideographs."""
    return bool(_CJK_RE.search(str(text or "")))


def cjk_ratio(text) -> float:
    """Share of non-space characters that are CJK ideographs (0..1)."""
    chars = [ch for ch in str(text or "") if not ch.isspace()]
    return sum(1 for ch in chars if _CJK_RE.match(ch)) / len(chars) if chars else 0.0


def is_zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


L10N_ZH = {
    "days": {"mon": "周一", "tue": "周二", "wed": "周三", "thu": "周四", "fri": "周五", "sat": "周六", "sun": "周日"},
    "formats": {"reel": "Reel", "story": "快拍", "carousel": "轮播图", "email": "邮件"},
    "statuses": {"planned": "已计划", "drafted": "已起草", "ready": "待发布", "published": "已发布"},
    "platforms": {"instagram": "Instagram", "tiktok": "TikTok", "youtube_shorts": "YouTube Shorts", "email": "邮件"},
}

# Weekly frequency presets: how many items of each format.
PRESETS = {
    "light": {"reel": 2, "carousel": 1, "story": 3, "email": 1},
    "balanced": {"reel": 3, "carousel": 2, "story": 7, "email": 1},
    "heavy": {"reel": 7, "carousel": 5, "story": 14, "email": 2},
}

# Neutral defaults. A brand kit only needs to override what it cares about;
# empty strings in a brand kit mean "not set" and fall back to these values.
DEFAULT_KIT: dict = {
    "schema": "ai-content-studio/brand-kit@1",
    "brand_name": "",
    "handle": "",
    "website": "",
    "language": "en",
    "timezone": "",
    "platforms": ["instagram", "tiktok", "youtube_shorts", "email"],
    "colors": {
        "primary": "#1F2A37",
        "secondary": "#F4EFE8",
        "accent": "#E26D5A",
        "background": "#FBF9F6",
        "text": "#1B1B1F",
        "muted": "#6B6F76",
    },
    "fonts": {
        "heading": {"family": "", "file": ""},
        "body": {"family": "", "file": ""},
        "cjk": {"family": "", "file": ""},
    },
    "logo": "",
    "carousel": {"size": "1080x1350", "show_handle": True, "show_slide_numbers": True},
    "reels": {
        "crosspost": ["tiktok", "youtube_shorts"],
        "subtitles": {
            "font_size": 74,
            "max_chars_per_line": 26,
            "max_chars_per_line_cjk": 16,
            "max_lines": 2,
            "color": "#FFFFFF",
            "outline_color": "#000000",
            "bottom_margin": 620,
        },
    },
    "schedule": {
        "frequency_preset": "balanced",
        "custom_mix": {},
        "preferred_days": {
            "reel": ["tue", "thu", "sat", "mon", "wed", "fri", "sun"],
            "carousel": ["mon", "wed", "fri", "tue", "thu", "sat", "sun"],
            "story": ["mon", "wed", "fri", "tue", "thu", "sat", "sun"],
            "email": ["thu", "mon", "tue", "wed", "fri", "sat", "sun"],
        },
        "default_times": {
            "reel": {"weekday": ["18:00", "12:00"], "weekend": ["11:00", "17:00"]},
            "carousel": {"weekday": ["12:00", "19:00"], "weekend": ["10:00", "16:00"]},
            "story": {"weekday": ["08:30", "20:00"], "weekend": ["10:00", "19:30"]},
            "email": {"weekday": ["08:00"], "weekend": ["09:00"]},
        },
        "platform_times": {"tiktok": "19:00", "youtube_shorts": "17:00"},
    },
}


def setup_stdio() -> None:
    """Force UTF-8 output so emoji and non-English text never crash a script."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(code)


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    path = Path(path)
    if not path.exists():
        die(f"File not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        die(f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}")
    return None  # unreachable


def save_json(path: Path, data: Any) -> Path:
    """Write JSON atomically so an interrupted write never corrupts a plan."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def deep_merge(base: Any, override: Any) -> Any:
    """Merge override into base. Empty strings / None in override keep the base value."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            if key.startswith("_"):
                continue
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            elif value not in ("", None):
                merged[key] = value
        return merged
    if override in ("", None):
        return base
    return override


def workspace_dir(explicit: Optional[str] = None) -> Path:
    """Where the user's brand memory and content library live.

    Priority: --workspace flag, $CONTENT_STUDIO_DIR, ./content-studio
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("CONTENT_STUDIO_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "content-studio").resolve()


def brand_file(name: str, workspace: Optional[Path]) -> Optional[Path]:
    """Find a brand file: workspace/brand first, then brand files baked into the skill."""
    candidates = []
    if workspace is not None:
        candidates.append(Path(workspace) / "brand" / name)
    candidates.append(BAKED_BRAND_DIR / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_brand_kit(workspace: Optional[Path] = None, explicit: Optional[str] = None) -> Tuple[dict, Optional[Path]]:
    """Return (merged brand kit, path it came from or None if only defaults)."""
    path = Path(explicit) if explicit else brand_file("brand-kit.json", workspace)
    if path is None or not path.exists():
        return json.loads(json.dumps(DEFAULT_KIT)), None
    raw = load_json(path)
    return deep_merge(DEFAULT_KIT, raw), path


def brand_kit_configured(path: Optional[Path]) -> bool:
    """True when a brand kit exists and has at least a brand name filled in."""
    if path is None or not Path(path).exists():
        return False
    raw = load_json(path)
    return bool(str(raw.get("brand_name", "")).strip()) and not raw.get("_placeholder", False)


def resolve_relative(path_str: str, *bases: Path) -> Optional[Path]:
    """Resolve a possibly relative path against several base folders."""
    if not path_str:
        return None
    p = Path(path_str).expanduser()
    if p.is_absolute():
        return p if p.exists() else None
    for base in bases:
        if base is None:
            continue
        candidate = Path(base) / p
        if candidate.exists():
            return candidate
    return p if p.exists() else None


WEEK_RE = re.compile(r"^(\d{4})-?W(\d{1,2})$", re.IGNORECASE)
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def monday_of(value: str) -> dt.date:
    """Accept '2026-W48', '2026W48' or any ISO date; return that week's Monday."""
    value = value.strip()
    match = WEEK_RE.match(value)
    if match:
        year, week = int(match.group(1)), int(match.group(2))
        return dt.date.fromisocalendar(year, week, 1)
    try:
        day = dt.date.fromisoformat(value)
    except ValueError:
        die(f"Could not read week/date '{value}'. Use 2026-W48 or 2026-11-23.")
    return day - dt.timedelta(days=day.weekday())


def week_label(monday: dt.date) -> str:
    year, week, _ = monday.isocalendar()
    return f"{year}-W{week:02d}"


def day_code(date: dt.date) -> str:
    return DAYS[date.weekday()]


def valid_time(value: str) -> bool:
    return bool(TIME_RE.match(str(value)))


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
