#!/usr/bin/env python3
"""AI Content Studio - capability check.

Run this before promising any file output. It reports which features can
really run here, so the assistant never offers (or claims) an export the
environment cannot produce.

  python check_env.py          human-readable table
  python check_env.py --json   machine-readable
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> None:
    C.setup_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--workspace")
    args = parser.parse_args()

    import video_tools  # local import: keeps this script fast when only --help is used

    ffmpeg = video_tools.find_ffmpeg()
    ffprobe = video_tools.find_ffprobe()
    libass = bool(ffmpeg) and video_tools.ffmpeg_has(ffmpeg, "filters", "ass")
    x264 = bool(ffmpeg) and video_tools.ffmpeg_has(ffmpeg, "encoders", "libx264")
    pillow = has_module("PIL")
    pptx = has_module("pptx")
    whisper_engine = "faster-whisper" if has_module("faster_whisper") else "openai-whisper" if has_module("whisper") else None
    workspace = C.workspace_dir(args.workspace)
    outputs_dir = os.environ.get("ACS_OUTPUT_DIR") or str(workspace / "exports")
    import carousel  # noqa: E402  (font lookup only; does not need Pillow)
    cjk_font = carousel.find_font_file(carousel.CJK_FONTS["regular"])
    skill_writable = os.access(C.SKILL_DIR, os.W_OK)

    def feature(name, ok, detail, needs=""):
        return {"feature": name, "status": "ready" if ok else "unavailable", "detail": detail, "needs": "" if ok else needs}

    features = [
        feature("Weekly planning + plan JSON", True, "standard library only"),
        feature("Visual HTML calendar", True, "self-contained .html file"),
        feature("Exports: Markdown, CSV, .ics calendar", True, "standard library only"),
        feature("Brand memory + content library", True, f"workspace: {workspace}"),
        feature("Transcript analysis (fillers, pauses, retakes)", True, "from .srt/.vtt/.json/.txt"),
        feature("Subtitle files (.srt / styled .ass)", True, "timed from transcript"),
        feature("Cut list + CSV + EDL for editors", True, "Premiere Pro / DaVinci Resolve / manual in CapCut"),
        feature("Carousel PNG slides", pillow, "Pillow " + (_version("PIL") or ""), "pip install pillow"),
        feature("Carousel editable PPTX (PowerPoint / Keynote / Google Slides / Canva import)", pptx and pillow,
                "python-pptx " + (_version("pptx") or ""), "pip install python-pptx"),
        feature("Video probe, frames, contact sheets, thumbnails", bool(ffmpeg), ffmpeg or "",
                "ffmpeg (winget install Gyan.FFmpeg / brew install ffmpeg / pip install imageio-ffmpeg)"),
        feature("Silence (pause) detection from audio", bool(ffmpeg), "ffmpeg silencedetect", "ffmpeg"),
        feature("Render edited 1080x1920 MP4 (verified)", bool(ffmpeg), "encoder: " + ("libx264" if x264 else "fallback"), "ffmpeg"),
        feature("Burn styled captions into video", libass, "ffmpeg built with libass", "an ffmpeg build with libass (most full builds)"),
        feature("Chinese text in carousel slides", pillow and bool(cjk_font), str(cjk_font or ""),
                "a Chinese font: built in on Windows (Microsoft YaHei) and macOS (PingFang); on Linux install "
                "fonts-noto-cjk, or put a .ttf/.otf in brand/fonts and set fonts.cjk.file"),
        feature("Speech-to-text transcription", bool(whisper_engine), whisper_engine or "",
                "pip install faster-whisper (downloads a model once; needs internet) - or supply an .srt"),
    ]
    report = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "environment": platform.system() or "unknown",
        "outputs_dir": outputs_dir,
        "skill_dir": str(C.SKILL_DIR),
        "skill_dir_writable": skill_writable,
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "features": features,
    }
    if args.json:
        C.print_json(report)
        return
    print(f"AI Content Studio capability check | Python {report['python']} | {report['environment']}")
    print(f"Save user-facing files to: {report['outputs_dir']}")
    print()
    width = max(len(f["feature"]) for f in features)
    for f in features:
        mark = "OK " if f["status"] == "ready" else "-- "
        line = f"{mark}{f['feature']:<{width}}  {f['detail'] if f['status'] == 'ready' else 'needs: ' + f['needs']}"
        print(line)
    missing = [f for f in features if f["status"] != "ready"]
    print()
    print("All features available." if not missing else
          f"{len(missing)} feature(s) unavailable here. Offer the fallback (cut list / EDL / plan) instead of claiming a file.")


def _version(module: str):
    try:
        mod = __import__(module)
        return getattr(mod, "__version__", "")
    except Exception:
        return None


if __name__ == "__main__":
    main()
