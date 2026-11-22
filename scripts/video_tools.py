#!/usr/bin/env python3
"""AI Content Studio - Reel editing tools.

Honesty contract: `render` only reports success after it has re-opened the
output file and verified its duration and resolution. Every command that
needs ffmpeg says so plainly (exit code 2) when ffmpeg is missing, and never
pretends to have produced a file.

Commands                                                         needs ffmpeg?
  probe          VIDEO                      duration, size, fps, audio    yes
  contact-sheet  VIDEO --count 12           grid of frames to look at     yes (+Pillow)
  thumbnail      VIDEO --at 3.2             cover frame for calendar/post yes
  silences       VIDEO                      silence intervals (pauses)    yes
  transcribe     VIDEO                      word-level transcript JSON    faster-whisper or whisper
  cutlist        --transcript T [--silences S] [--video V]  editable cut list + CSV + EDL   no
  edit           CUTLIST --remove 1.2-1.9 --zoom 30=1.15     hand-tune cuts, zoom, reframing no
  edl            CUTLIST                    CMX3600 EDL for Premiere/Resolve            no
  render         VIDEO --cutlist C [--subs captions.ass]  1080x1920 MP4, verified      yes

ffmpeg is found on PATH, or through the imageio-ffmpeg Python package
(pip install imageio-ffmpeg), which bundles a static ffmpeg binary.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402
import transcript as T  # noqa: E402

CUTLIST_SCHEMA = "ai-content-studio/cutlist@1"
EXIT_MISSING_TOOL = 2
EXIT_UNVERIFIED = 3


# --------------------------------------------------------------------------- tool discovery

def find_ffmpeg() -> Optional[str]:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def find_ffprobe() -> Optional[str]:
    path = shutil.which("ffprobe")
    if path:
        return path
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        candidate = Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix)
        if candidate.exists():
            return str(candidate)
    return None


def require_ffmpeg() -> str:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print(json.dumps({
            "ok": False,
            "rendered": False,
            "reason": "ffmpeg is not available in this environment, so no video was processed or created.",
            "fix": ["Install ffmpeg (winget install Gyan.FFmpeg / brew install ffmpeg / apt install ffmpeg)",
                    "or: pip install imageio-ffmpeg",
                    "or: use the cut list (cutlist / edl commands) in CapCut, Premiere Pro, DaVinci Resolve"],
        }, indent=2))
        sys.exit(EXIT_MISSING_TOOL)
    return ffmpeg


def run(cmd: List[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def ffmpeg_has(ffmpeg: str, kind: str, name: str) -> bool:
    result = run([ffmpeg, "-hide_banner", f"-{kind}"])
    return re.search(rf"\s{re.escape(name)}\s", result.stdout) is not None


# --------------------------------------------------------------------------- probe

def probe(video: str) -> dict:
    path = Path(video)
    if not path.exists():
        C.die(f"Video not found: {path}")
    ffprobe = find_ffprobe()
    info = {"path": str(path), "size_bytes": path.stat().st_size}
    if ffprobe:
        result = run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
        if result.returncode != 0:
            C.die(f"ffprobe could not read {path}: {result.stderr.strip()[:300]}")
        data = json.loads(result.stdout)
        video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
        audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
        info["duration"] = float(data.get("format", {}).get("duration") or 0)
        if video_streams:
            vs = video_streams[0]
            width, height = int(vs.get("width", 0)), int(vs.get("height", 0))
            rotation = 0
            for side in vs.get("side_data_list", []) or []:
                if "rotation" in side:
                    rotation = int(side["rotation"])
            rotation = rotation or int((vs.get("tags") or {}).get("rotate", 0) or 0)
            if abs(rotation) in (90, 270):
                width, height = height, width
            num, _, den = (vs.get("avg_frame_rate") or "0/1").partition("/")
            fps = float(num) / float(den or 1) if float(den or 1) else 0
            info.update({"width": width, "height": height, "fps": round(fps, 3), "video_codec": vs.get("codec_name"),
                         "rotation": rotation})
        info["has_audio"] = bool(audio_streams)
    else:
        ffmpeg = require_ffmpeg()
        result = run([ffmpeg, "-hide_banner", "-i", str(path)])
        text = result.stderr
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        info["duration"] = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3)) if match else 0
        vmatch = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
        fmatch = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
        rot = re.search(r"rotat\w*\s*[:=]?\s*(-?\d+)", text)
        width, height = (int(vmatch.group(1)), int(vmatch.group(2))) if vmatch else (0, 0)
        if rot and abs(int(rot.group(1))) in (90, 270):
            width, height = height, width
        info.update({"width": width, "height": height, "fps": float(fmatch.group(1)) if fmatch else 0,
                     "has_audio": "Audio:" in text, "rotation": int(rot.group(1)) if rot else 0})
    if info.get("width") and info.get("height"):
        ratio = info["width"] / info["height"]
        info["orientation"] = "vertical" if ratio < 0.8 else "horizontal" if ratio > 1.2 else "square-ish"
    return info


def cmd_probe(args) -> None:
    C.print_json(probe(args.video))


# --------------------------------------------------------------------------- frames

def extract_frame(ffmpeg: str, video: str, at: float, out: Path, width: int = 0) -> bool:
    vf = ["-vf", f"scale={width}:-2"] if width else []
    result = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at:.3f}", "-i", video,
                  "-frames:v", "1", *vf, "-q:v", "3", str(out)])
    return result.returncode == 0 and out.exists() and out.stat().st_size > 0


def cmd_contact_sheet(args) -> None:
    ffmpeg = require_ffmpeg()
    info = probe(args.video)
    duration = info.get("duration") or 0
    if duration <= 0:
        C.die("Could not read the video duration")
    count = max(1, min(args.count, 36))
    times = [duration * (i + 0.5) / count for i in range(count)]
    out = Path(args.out or Path(args.video).with_suffix(".contact.jpg"))
    with tempfile.TemporaryDirectory() as tmp:
        frames = []
        for i, t in enumerate(times):
            frame = Path(tmp) / f"f{i:02d}.jpg"
            if extract_frame(ffmpeg, args.video, t, frame, 320):
                frames.append((t, frame))
        if not frames:
            C.die("No frames could be extracted")
        try:
            from PIL import Image, ImageDraw  # type: ignore
        except ImportError:
            folder = out.with_suffix("")
            folder.mkdir(parents=True, exist_ok=True)
            for t, frame in frames:
                shutil.copyfile(frame, folder / f"frame_{t:07.2f}s.jpg")
            C.print_json({"frames_dir": str(folder), "frames": len(frames), "note": "Pillow missing: saved separate frames"})
            return
        images = [Image.open(f).convert("RGB") for _, f in frames]
        tile_w = 320
        tile_h = max(img.height for img in images)
        cols = 6 if len(images) > 12 else 4
        rows = (len(images) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tile_w + (cols + 1) * 8, rows * (tile_h + 34) + 8), (24, 24, 28))
        draw = ImageDraw.Draw(sheet)
        for i, ((t, _), img) in enumerate(zip(frames, images)):
            x = 8 + (i % cols) * (tile_w + 8)
            y = 8 + (i // cols) * (tile_h + 34)
            sheet.paste(img, (x, y))
            draw.text((x + 4, y + img.height + 6), f"{int(t // 60):02d}:{t % 60:05.2f}", fill=(235, 235, 240))
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out, quality=88)
    C.print_json({"contact_sheet": str(out), "frames": len(frames), "duration": round(duration, 2),
                  "timestamps": [round(t, 2) for t, _ in frames]})


def cmd_thumbnail(args) -> None:
    ffmpeg = require_ffmpeg()
    out = Path(args.out or Path(args.video).with_suffix(".thumb.jpg"))
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.vertical:
        crop = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{args.at:.3f}", "-i", args.video,
               "-frames:v", "1", "-vf", crop, "-q:v", "2", str(out)]
        ok = run(cmd).returncode == 0 and out.exists()
    else:
        ok = extract_frame(ffmpeg, args.video, args.at, out)
    if not ok:
        C.die("Thumbnail could not be extracted", EXIT_UNVERIFIED)
    C.print_json({"thumbnail": str(out), "at": args.at, "bytes": out.stat().st_size})


# --------------------------------------------------------------------------- silences

def detect_silences(video: str, noise_db: float, min_duration: float) -> List[dict]:
    ffmpeg = require_ffmpeg()
    result = run([ffmpeg, "-hide_banner", "-nostats", "-i", video, "-vn", "-af",
                  f"silencedetect=noise={noise_db}dB:d={min_duration}", "-f", "null", "-"])
    silences, start = [], None
    for line in result.stderr.splitlines():
        m_start = re.search(r"silence_start:\s*(-?\d+(?:\.\d+)?)", line)
        m_end = re.search(r"silence_end:\s*(\d+(?:\.\d+)?)", line)
        if m_start:
            start = max(0.0, float(m_start.group(1)))
        elif m_end and start is not None:
            end = float(m_end.group(1))
            silences.append({"start": round(start, 3), "end": round(end, 3), "duration": round(end - start, 3)})
            start = None
    if start is not None:
        info = probe(video)
        silences.append({"start": round(start, 3), "end": round(info["duration"], 3),
                         "duration": round(info["duration"] - start, 3)})
    return silences


def cmd_silences(args) -> None:
    silences = detect_silences(args.video, args.noise, args.min)
    payload = {"video": args.video, "noise_db": args.noise, "min_duration": args.min, "silences": silences,
               "total_silence_s": round(sum(s["duration"] for s in silences), 2)}
    if args.out:
        C.save_json(Path(args.out), payload)
        C.print_json({"saved": args.out, "silences": len(silences), "total_silence_s": payload["total_silence_s"]})
    else:
        C.print_json(payload)


# --------------------------------------------------------------------------- transcription

def decode_audio_16k(media: str):
    """Decode any audio/video file to 16 kHz mono float32 samples with ffmpeg.

    Handing Whisper raw samples avoids its own PyAV-based file loader, which breaks
    whenever PyAV changes its API (faster-whisper 1.2.1 + PyAV 19 is one such pair).
    Returns None when ffmpeg is unavailable so the caller can fall back to the path.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        import numpy as np  # installed with faster-whisper / openai-whisper
    except ImportError:
        return None
    proc = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", media, "-vn",
                           "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return None
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def zh_prompt(language):
    """Nudges Whisper to write Simplified Chinese with punctuation (it can drift into Traditional)."""
    return "以下是普通话的句子，使用简体中文和标点符号。" if str(language or "").lower().startswith("zh") else None


def cmd_transcribe(args) -> None:
    out = Path(args.out or Path(args.video).with_suffix(".transcript.json"))
    segments, language, engine = None, None, None
    try:
        from faster_whisper import WhisperModel  # type: ignore
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
        audio = decode_audio_16k(args.video)
        result, info = model.transcribe(audio if audio is not None else args.video, word_timestamps=True,
                                        language=args.language, initial_prompt=zh_prompt(args.language))
        segments = [{"start": s.start, "end": s.end, "text": s.text,
                     "words": [{"word": w.word, "start": w.start, "end": w.end} for w in (s.words or [])]} for s in result]
        language, engine = info.language, "faster-whisper"
    except ImportError:
        try:
            import whisper  # type: ignore
            require_ffmpeg()  # openai-whisper decodes audio with ffmpeg
            model = whisper.load_model(args.model)
            result = model.transcribe(args.video, word_timestamps=True, language=args.language,
                                      initial_prompt=zh_prompt(args.language))
            segments, language, engine = result["segments"], result.get("language"), "openai-whisper"
        except ImportError:
            print(json.dumps({
                "ok": False,
                "transcribed": False,
                "reason": "No speech-to-text engine is installed here, so the audio was not transcribed.",
                "fix": ["pip install faster-whisper   (downloads a model on first use; needs internet once)",
                        "or export captions from CapCut / Instagram / TikTok / Descript / Premiere as .srt and use that file"],
            }, indent=2))
            sys.exit(EXIT_MISSING_TOOL)
    except Exception as exc:  # model download blocked, unreadable file, etc.
        print(json.dumps({"ok": False, "transcribed": False, "reason": f"Transcription failed: {exc}"}, indent=2))
        sys.exit(EXIT_UNVERIFIED)
    parsed, _ = T.parse_whisper_json({"segments": segments, "language": language})
    for i, seg in enumerate(parsed, 1):
        seg["id"] = i
    transcript = {"schema": T.TRANSCRIPT_SCHEMA, "source": Path(args.video).name, "source_kind": engine,
                  "language": language, "has_timing": True, "word_level": all(s.get("words") for s in parsed),
                  "duration": max((s["end"] for s in parsed), default=0), "segments": parsed}
    C.save_json(out, transcript)
    C.print_json({"ok": True, "transcript": str(out), "engine": engine, "language": language, "segments": len(parsed)})


# --------------------------------------------------------------------------- cut list

def merge_intervals(intervals: List[List[float]], gap: float = 0.0) -> List[List[float]]:
    merged: List[List[float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def build_cutlist(transcript: Optional[dict], silences: Optional[List[dict]], duration: float, source: str,
                  keep_pause: float, max_pause: float, pad: float, cut_soft: bool, punch_in: float,
                  lang: str, fps: float, cut_retakes: bool = False) -> dict:
    removed: List[dict] = []
    suggestions: List[dict] = []
    notes: List[str] = []
    words = T.words_of(transcript) if transcript and transcript.get("has_timing") else []
    exact = bool(transcript and transcript.get("word_level"))

    if words:
        first, last = words[0]["start"], words[-1]["end"]
        if first - pad > 0.05:
            removed.append({"start": 0.0, "end": round(first - pad, 3), "reason": "dead air before first word"})
        if duration - (last + pad) > 0.05:
            removed.append({"start": round(last + pad, 3), "end": round(duration, 3), "reason": "dead air after last word"})
    elif silences:
        if silences[0]["start"] <= 0.05:
            removed.append({"start": 0.0, "end": max(0.0, silences[0]["end"] - pad), "reason": "silence at start"})
        if silences[-1]["end"] >= duration - 0.05:
            removed.append({"start": silences[-1]["start"] + pad, "end": duration, "reason": "silence at end"})

    gaps = []
    if silences:
        gaps = [(s["start"], s["end"]) for s in silences]
        if not exact and words:
            notes.append("Pauses come from audio silence detection (precise); fillers from a segment-level transcript are only flagged.")
    elif words:
        gaps = [(a["end"], b["start"]) for a, b in zip(words, words[1:])]
        if not exact:
            notes.append("Pause cuts are estimated from segment timings. Check them by ear, or run `silences` for precise audio pauses.")
    for start, end in gaps:
        if end - start > max_pause:
            half = keep_pause / 2
            removed.append({"start": round(start + half, 3), "end": round(end - half, 3), "reason": f"pause {end - start:.1f}s shortened to {keep_pause:.2f}s"})

    if words:
        for filler in T.find_fillers(words, lang):
            if filler["kind"] == "hard" and exact:
                removed.append({"start": round(max(0, filler["start"] - 0.03), 3), "end": round(filler["end"] + 0.03, 3),
                                "reason": f"filler '{filler['text']}'"})
            elif filler["kind"] == "soft" and cut_soft and exact:
                removed.append({"start": round(filler["start"] - 0.02, 3), "end": round(filler["end"] + 0.02, 3),
                                "reason": f"soft filler '{filler['text']}'"})
            else:
                suggestions.append({"start": filler["start"], "end": filler["end"], "reason": f"{filler['kind']} filler '{filler['text']}'"
                                    + (" (approximate timing)" if filler["approx"] else ""), "action": "review"})
        for retake in T.find_retakes(transcript):
            if cut_retakes and retake.get("next_take_start") is not None:
                removed.append({"start": round(max(0.0, retake["start"] - 0.05), 3),
                                "end": round(retake["next_take_start"] - keep_pause / 2, 3),
                                "reason": f"retake removed: '{retake['text'][:50]}'"})
            else:
                suggestions.append({"start": retake["start"], "end": retake["end"], "reason": retake["reason"],
                                    "text": retake["text"], "action": "review"})

    cuts = merge_intervals([[max(0.0, r["start"]), min(duration, r["end"])] for r in removed if r["end"] - r["start"] > 0.06])
    keep, cursor = [], 0.0
    for start, end in cuts:
        if start - cursor >= 0.15:
            keep.append({"start": round(cursor, 3), "end": round(start, 3)})
        cursor = max(cursor, end)
    if duration - cursor >= 0.15:
        keep.append({"start": round(cursor, 3), "end": round(duration, 3)})
    for i, seg in enumerate(keep):
        seg.update({"zoom": 1.0, "focus_x": 0.5, "label": ""})
        if punch_in > 1.0 and i % 2 == 1 and seg["end"] - seg["start"] >= 1.5:
            seg["zoom"] = punch_in
    if keep:
        keep[0]["label"] = "hook"
    edited = sum(k["end"] - k["start"] for k in keep)
    return {
        "schema": CUTLIST_SCHEMA,
        "source": source,
        "source_duration": round(duration, 3),
        "fps": fps,
        "output": {"width": 1080, "height": 1920, "fps": 30, "fit": "cover"},
        "keep": keep,
        "removed": sorted(removed, key=lambda r: r["start"]),
        "suggestions": suggestions,
        "edited_duration": round(edited, 3),
        "time_saved": round(duration - edited, 3),
        "notes": notes,
    }


def tc(seconds: float, fps: int) -> str:
    frames = int(round(seconds * fps))
    f = frames % fps
    s = (frames // fps) % 60
    m = (frames // (fps * 60)) % 60
    h = frames // (fps * 3600)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def write_edl(cutlist: dict, out: Path, fps_override: Optional[float] = None) -> Path:
    fps = int(round(fps_override or cutlist.get("fps") or 30))
    lines = [f"TITLE: {Path(cutlist['source']).stem}_edit", "FCM: NON-DROP FRAME", ""]
    record = 3600.0
    for i, seg in enumerate(cutlist["keep"], 1):
        length = seg["end"] - seg["start"]
        lines.append(f"{i:03d}  AX       AA/V  C        {tc(seg['start'], fps)} {tc(seg['end'], fps)} {tc(record, fps)} {tc(record + length, fps)}")
        lines.append(f"* FROM CLIP NAME: {Path(cutlist['source']).name}")
        if seg.get("zoom", 1.0) != 1.0:
            lines.append(f"* COMMENT: punch-in zoom {seg['zoom']}x")
        lines.append("")
        record += length
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def write_csv(cutlist: dict, out: Path) -> Path:
    with open(out, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["#", "action", "source_start", "source_end", "length_s", "timeline_start", "zoom", "reason"])
        rows, timeline = [], 0.0
        for seg in cutlist["keep"]:
            rows.append((seg["start"], "KEEP", seg["end"], seg.get("zoom", 1.0), seg.get("label", ""), timeline))
            timeline += seg["end"] - seg["start"]
        for rem in cutlist["removed"]:
            rows.append((rem["start"], "CUT", rem["end"], "", rem["reason"], None))
        for i, (start, action, end, zoom, reason, tl) in enumerate(sorted(rows), 1):
            writer.writerow([i, action, T.seconds_to_srt(start), T.seconds_to_srt(end), round(end - start, 2),
                             T.seconds_to_srt(tl) if tl is not None else "", zoom, reason])
    return out


def cmd_cutlist(args) -> None:
    transcript = T.load_transcript(args.transcript) if args.transcript else None
    silences = C.load_json(Path(args.silences)).get("silences") if args.silences else None
    if not transcript and not silences:
        C.die("Pass --transcript and/or --silences")
    duration, fps, source = args.duration, args.fps, args.source
    if args.video:
        info = probe(args.video)
        duration = duration or info.get("duration")
        fps = fps or info.get("fps")
        source = source or Path(args.video).name
    duration = duration or (transcript.get("duration") if transcript else None) or max(s["end"] for s in silences)
    source = source or (transcript.get("source") if transcript else "source.mp4")
    lang = args.lang if args.lang != "auto" else (transcript.get("language") if transcript and transcript.get("language")
                                                    else T.detect_language(T.full_text(transcript)) if transcript else "en")
    cutlist = build_cutlist(transcript, silences, float(duration), source, args.keep_pause, args.max_pause, args.pad,
                            args.cut_soft_fillers, args.punch_in, lang, float(fps or 30), args.cut_retakes)
    save_cutlist(Path(args.out or "cutlist.json"), cutlist)


def save_cutlist(out: Path, cutlist: dict) -> None:
    """Write cutlist.json plus the CSV and EDL that always travel with it."""
    cutlist["edited_duration"] = round(sum(k["end"] - k["start"] for k in cutlist["keep"]), 3)
    cutlist["time_saved"] = round(cutlist["source_duration"] - cutlist["edited_duration"], 3)
    C.save_json(out, cutlist)
    edl = write_edl(cutlist, out.with_suffix(".edl"))
    table = write_csv(cutlist, out.with_suffix(".csv"))
    C.print_json({"cutlist": str(out), "edl": str(edl), "csv": str(table), "keep_segments": len(cutlist["keep"]),
                  "cuts": len(cutlist["removed"]), "review_suggestions": len(cutlist.get("suggestions", [])),
                  "source_duration": cutlist["source_duration"], "edited_duration": cutlist["edited_duration"],
                  "time_saved": cutlist["time_saved"], "notes": cutlist.get("notes", [])})


def parse_range(text: str):
    match = re.fullmatch(r"\s*([\d:.,]+)\s*-\s*([\d:.,]+)\s*", text)
    if not match:
        C.die(f"Range '{text}' should look like 12.4-13.1 or 00:12.4-00:13.1")
    to_s = lambda v: T.ts_to_seconds(v) if ":" in v else float(v.replace(",", "."))  # noqa: E731
    start, end = to_s(match.group(1)), to_s(match.group(2))
    if end <= start:
        C.die(f"Range '{text}' ends before it starts")
    return start, end


def cmd_edit(args) -> None:
    """Hand edits: cut extra ranges, restore ranges, set zoom / reframing on the segment at a time."""
    path = Path(args.cutlist)
    cutlist = C.load_json(path)
    keep = cutlist["keep"]
    for text in args.remove or []:
        start, end = parse_range(text)
        new_keep = []
        for seg in keep:
            if end <= seg["start"] or start >= seg["end"]:
                new_keep.append(seg)
                continue
            if start - seg["start"] >= 0.15:
                new_keep.append(dict(seg, end=round(start, 3)))
            if seg["end"] - end >= 0.15:
                new_keep.append(dict(seg, start=round(end, 3), label=""))
        keep = new_keep
        cutlist["removed"].append({"start": start, "end": end, "reason": args.reason or "manual cut"})
    for text in args.restore or []:
        start, end = parse_range(text)
        keep.append({"start": start, "end": end, "zoom": 1.0, "focus_x": 0.5, "label": "restored"})
        merged = merge_intervals([[k["start"], k["end"]] for k in keep])
        by_start = {k["start"]: k for k in keep}
        keep = [dict(by_start.get(a, {"zoom": 1.0, "focus_x": 0.5, "label": ""}), start=round(a, 3), end=round(b, 3)) for a, b in merged]
        cutlist["removed"] = [r for r in cutlist["removed"] if r["end"] <= start or r["start"] >= end]
    for text in args.zoom or []:
        at, _, value = text.partition("=")
        t = float(at)
        for seg in keep:
            if seg["start"] <= t <= seg["end"]:
                seg["zoom"] = float(value or 1.0)
    for text in args.focus or []:
        at, _, value = text.partition("=")
        t = float(at)
        for seg in keep:
            if seg["start"] <= t <= seg["end"]:
                seg["focus_x"] = min(1.0, max(0.0, float(value or 0.5)))
    keep.sort(key=lambda k: k["start"])
    cutlist["keep"] = keep
    cutlist["removed"].sort(key=lambda r: r["start"])
    save_cutlist(path, cutlist)


def cmd_edl(args) -> None:
    cutlist = C.load_json(Path(args.cutlist))
    out = write_edl(cutlist, Path(args.out or Path(args.cutlist).with_suffix(".edl")), args.fps)
    C.print_json({"edl": str(out), "events": len(cutlist["keep"])})


# --------------------------------------------------------------------------- render

def build_filtergraph(cutlist: dict, info: dict, fit: str, width: int, height: int, fps: int,
                      subs_name: Optional[str], fontsdir: Optional[str], loudnorm: bool) -> str:
    src_w, src_h = int(info["width"]), int(info["height"])
    has_audio = info.get("has_audio", False)
    parts, labels = [], []
    focus_global = float(cutlist.get("output", {}).get("focus_x", 0.5))
    for i, seg in enumerate(cutlist["keep"]):
        start, end = float(seg["start"]), float(seg["end"])
        zoom = float(seg.get("zoom", 1.0) or 1.0)
        fx = min(1.0, max(0.0, float(seg.get("focus_x", focus_global))))
        chain = f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS"
        if zoom > 1.001:
            cw, ch = int(src_w / zoom) // 2 * 2, int(src_h / zoom) // 2 * 2
            chain += f",crop={cw}:{ch}:{(src_w - cw) * fx:.0f}:{(src_h - ch) / 2:.0f},scale={src_w}:{src_h}"
        chain += f",setsar=1[v{i}]"
        parts.append(chain)
        if has_audio:
            length = end - start
            fade = min(0.012, length / 4)
            parts.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:st=0:d={fade:.3f},afade=t=out:st={max(0.0, length - fade):.3f}:d={fade:.3f}[a{i}]")
            labels.append(f"[v{i}][a{i}]")
        else:
            labels.append(f"[v{i}]")
    n = len(cutlist["keep"])
    parts.append("".join(labels) + f"concat=n={n}:v=1:a={1 if has_audio else 0}" + ("[vc][ac]" if has_audio else "[vc]"))
    if fit == "blur":
        parts.append(f"[vc]split[bgs][fgs];[bgs]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
                     f"boxblur=luma_radius=40:luma_power=2[bg];[fgs]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
                     f"[bg][fg]overlay=(W-w)/2:(H-h)/2[vf]")
    elif fit == "pad":
        parts.append(f"[vc]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black[vf]")
    else:  # cover: fill the frame, crop the sides (horizontal sources keep the focus_x area)
        parts.append(f"[vc]scale={width}:{height}:force_original_aspect_ratio=increase,"
                     f"crop={width}:{height}:(iw-{width})*{focus_global:.3f}:(ih-{height})/2[vf]")
    tail = f"[vf]fps={fps},format=yuv420p"
    if subs_name:
        filt = "ass" if subs_name.lower().endswith(".ass") else "subtitles"
        tail += f",{filt}={subs_name}" + (f":fontsdir={fontsdir}" if fontsdir else "")
    parts.append(tail + "[vout]")
    if has_audio and loudnorm:
        parts.append("[ac]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    elif has_audio:
        parts.append("[ac]anull[aout]")
    return ";".join(parts)


def verify_output(path: Path, expected_duration: float, width: int, height: int) -> dict:
    problems = []
    if not path.exists() or path.stat().st_size == 0:
        return {"verified": False, "problems": ["output file was not created"]}
    info = probe(str(path))
    if (info.get("width"), info.get("height")) != (width, height):
        problems.append(f"resolution is {info.get('width')}x{info.get('height')}, expected {width}x{height}")
    if abs((info.get("duration") or 0) - expected_duration) > max(0.6, expected_duration * 0.03):
        problems.append(f"duration is {info.get('duration'):.2f}s, expected about {expected_duration:.2f}s")
    return {"verified": not problems, "problems": problems, "probe": info}


def cmd_render(args) -> None:
    ffmpeg = require_ffmpeg()
    video = Path(args.video).resolve()
    cutlist = C.load_json(Path(args.cutlist))
    if not cutlist.get("keep"):
        C.die("The cut list has no keep segments")
    info = probe(str(video))
    if not info.get("width"):
        C.die("Could not read the video stream")
    output = cutlist.get("output", {})
    width, height = (args.width or output.get("width", 1080)), (args.height or output.get("height", 1920))
    fps = int(args.fps or output.get("fps", 30))
    fit = args.fit or output.get("fit", "cover")
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cwd, subs_name, fontsdir = None, None, None
    if args.subs:
        subs = Path(args.subs).resolve()
        if not subs.exists():
            C.die(f"Subtitle file not found: {subs}")
        filt = "ass" if subs.suffix.lower() == ".ass" else "subtitles"
        if not ffmpeg_has(ffmpeg, "filters", filt):
            C.die(f"This ffmpeg build has no '{filt}' filter (libass), so captions cannot be burned in. "
                  f"Render without --subs and upload {subs.name} as captions instead.", EXIT_MISSING_TOOL)
        cwd, subs_name = str(subs.parent), subs.name  # avoids Windows path escaping inside the filter
        if args.fontsdir:
            fontsdir = str(Path(args.fontsdir).resolve()).replace("\\", "/").replace(":", "\\:")
    encoder = "libx264" if ffmpeg_has(ffmpeg, "encoders", "libx264") else "libopenh264" if ffmpeg_has(ffmpeg, "encoders", "libopenh264") else "mpeg4"
    graph = build_filtergraph(cutlist, info, fit, width, height, fps, subs_name, fontsdir, args.loudnorm)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    script = None
    if len(graph) > 25000:
        script = Path(tempfile.mkstemp(suffix=".txt")[1])
        script.write_text(graph, encoding="utf-8")
        cmd += ["-filter_complex_script", str(script)]
    else:
        cmd += ["-filter_complex", graph]
    cmd += ["-map", "[vout]"]
    if info.get("has_audio"):
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    cmd += ["-c:v", encoder]
    if encoder == "libx264":
        cmd += ["-preset", args.preset, "-crf", str(args.crf), "-profile:v", "high"]
    else:
        cmd += ["-b:v", "8M"]
    cmd += ["-r", str(fps), "-movflags", "+faststart", str(out)]
    result = run(cmd, cwd=cwd)
    if script:
        script.unlink(missing_ok=True)
    expected = sum(float(k["end"]) - float(k["start"]) for k in cutlist["keep"])
    if result.returncode != 0:
        print(json.dumps({"ok": False, "rendered": False, "verified": False, "reason": "ffmpeg failed",
                          "ffmpeg_error": result.stderr.strip()[-1500:]}, indent=2))
        sys.exit(EXIT_UNVERIFIED)
    check = verify_output(out, expected, width, height)
    payload = {"ok": check["verified"], "rendered": out.exists(), "verified": check["verified"], "output": str(out),
               "expected_duration": round(expected, 2), "encoder": encoder, "subtitles_burned": bool(subs_name),
               "problems": check["problems"]}
    if check.get("probe"):
        payload.update({"duration": round(check["probe"].get("duration", 0), 2),
                        "resolution": f"{check['probe'].get('width')}x{check['probe'].get('height')}",
                        "size": C.human_size(out.stat().st_size)})
    C.print_json(payload)
    sys.exit(0 if check["verified"] else EXIT_UNVERIFIED)


# --------------------------------------------------------------------------- CLI

def main() -> None:
    C.setup_stdio()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("probe")
    p.add_argument("video")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("contact-sheet")
    p.add_argument("video")
    p.add_argument("--count", type=int, default=12)
    p.add_argument("--out")
    p.set_defaults(func=cmd_contact_sheet)

    p = sub.add_parser("thumbnail")
    p.add_argument("video")
    p.add_argument("--at", type=float, default=1.0)
    p.add_argument("--vertical", action="store_true", help="Crop to 1080x1920")
    p.add_argument("--out")
    p.set_defaults(func=cmd_thumbnail)

    p = sub.add_parser("silences")
    p.add_argument("video")
    p.add_argument("--noise", type=float, default=-32.0, help="Silence threshold in dB (try -28 for noisy rooms)")
    p.add_argument("--min", type=float, default=0.45, help="Minimum silence length in seconds")
    p.add_argument("--out")
    p.set_defaults(func=cmd_silences)

    p = sub.add_parser("transcribe")
    p.add_argument("video")
    p.add_argument("--model", default="small", help="tiny, base, small, medium, large-v3")
    p.add_argument("--language", help="en, zh, sv, ... (default: auto-detect; use zh for Chinese speech)")
    p.add_argument("--out")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("cutlist")
    p.add_argument("--transcript", help=".srt / .vtt / transcript JSON")
    p.add_argument("--silences", help="JSON from the silences command")
    p.add_argument("--video", help="Source video (reads duration and fps)")
    p.add_argument("--duration", type=float)
    p.add_argument("--fps", type=float)
    p.add_argument("--source", help="Source file name to record in the cut list")
    p.add_argument("--max-pause", type=float, default=0.55, help="Pauses longer than this are shortened")
    p.add_argument("--keep-pause", type=float, default=0.25, help="How much of a long pause to keep (breathing room)")
    p.add_argument("--pad", type=float, default=0.12, help="Padding before the first / after the last word")
    p.add_argument("--cut-soft-fillers", action="store_true", help="Also cut 'like', 'basically', 'liksom'... (word-level only)")
    p.add_argument("--punch-in", type=float, default=1.0, help="Zoom every other segment, e.g. 1.12 for a two-camera feel")
    p.add_argument("--cut-retakes", action="store_true", help="Remove the first take when a sentence is restarted")
    p.add_argument("--lang", default="auto", choices=["auto", "en", "sv", "zh"])
    p.add_argument("--out", help="cutlist.json path (CSV and EDL are written next to it)")
    p.set_defaults(func=cmd_cutlist)

    p = sub.add_parser("edit", help="Hand-edit a cut list (CSV and EDL are rewritten)")
    p.add_argument("cutlist")
    p.add_argument("--remove", action="append", help="Cut a source range, e.g. 1.28-1.95 (repeatable)")
    p.add_argument("--restore", action="append", help="Put a source range back, e.g. 20.5-22.4")
    p.add_argument("--zoom", action="append", help="TIME=ZOOM for the segment containing TIME, e.g. 30.2=1.15")
    p.add_argument("--focus", action="append", help="TIME=X (0..1) horizontal subject position for 9:16 crops, e.g. 30.2=0.35")
    p.add_argument("--reason", help="Why (kept in the cut list)")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("edl")
    p.add_argument("cutlist")
    p.add_argument("--fps", type=float)
    p.add_argument("--out")
    p.set_defaults(func=cmd_edl)

    p = sub.add_parser("render")
    p.add_argument("video")
    p.add_argument("--cutlist", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--subs", help=".ass (styled) or .srt captions to burn in")
    p.add_argument("--fontsdir", help="Folder with brand fonts for burned captions")
    p.add_argument("--fit", choices=["cover", "blur", "pad"], help="How to fit non-vertical footage into 9:16")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--fps", type=int)
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--preset", default="medium")
    p.add_argument("--loudnorm", action="store_true", help="Normalize loudness to -14 LUFS (social media standard)")
    p.set_defaults(func=cmd_render)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
