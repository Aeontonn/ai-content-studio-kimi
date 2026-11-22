#!/usr/bin/env python3
"""AI Content Studio - transcript tools (no ffmpeg needed).

Reads transcripts from SRT, WebVTT, Whisper/faster-whisper JSON, or plain text
(with or without [mm:ss] timestamps), and turns them into:
  * a normalized JSON transcript (segments, optional word timings)
  * an analysis: filler words, long pauses, possible retakes, speaking rate
  * vertical-video subtitles (.srt or styled .ass), optionally re-timed to an
    edited cut list so captions match the edited Reel

Commands
  parse     FILE [--out transcript.json]
  analyze   FILE [--lang en|sv|auto] [--pause 0.6] [--out analysis.json]
  text      FILE                      plain text, for repurposing / carousels
  subtitles FILE [--cutlist cutlist.json] [--format srt|ass] [--out subs.srt]

Where do transcripts come from?  Instagram/TikTok/CapCut auto-captions export,
Descript, Premiere/DaVinci transcription, YouTube Studio (.vtt/.srt), or
video_tools.py transcribe (needs faster-whisper or openai-whisper installed).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TRANSCRIPT_SCHEMA = "ai-content-studio/transcript@1"

# Hard fillers are safe to cut automatically. Soft fillers depend on context
# ("I like this" vs "it was, like, huge"), so they are only flagged for review.
HARD_FILLERS = {
    "en": {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "ahh", "hmm", "mm", "mhm"},
    "sv": {"eh", "ehm", "öh", "öhm", "ööh", "äh", "äöh", "hmm", "mm", "mhm", "eeh"},
    "zh": {"嗯", "呃", "额", "唔", "嗯嗯", "呃呃", "额额"},
}
SOFT_FILLERS = {
    "en": {"like", "so", "basically", "actually", "literally", "right", "okay", "ok", "well",
           "you know", "i mean", "kind of", "sort of", "you see"},
    "sv": {"liksom", "typ", "alltså", "asså", "ba", "bara", "så här", "du vet", "eller hur", "va", "ju", "nämligen"},
    "zh": {"那个", "就是", "就是说", "然后", "这个", "对吧", "其实", "反正", "怎么说呢", "你知道", "啊"},
}

TS_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?")
CUE_RE = re.compile(r"((?:\d+:)?\d{1,2}:\d{1,2}(?:[.,]\d{1,3})?)\s*-->\s*((?:\d+:)?\d{1,2}:\d{1,2}(?:[.,]\d{1,3})?)")
TXT_TS_RE = re.compile(r"^\s*[\[(]?((?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)[\])]?\s*[-–:]?\s*(.*)$")
TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]*\}")


def ts_to_seconds(value: str) -> float:
    match = TS_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Bad timestamp '{value}'")
    hours, minutes, seconds, frac = match.groups()
    total = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
    if frac:
        total += int(frac.ljust(3, "0")[:3]) / 1000
    return round(total, 3)


def seconds_to_srt(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def seconds_to_ass(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def clean(text: str) -> str:
    return " ".join(TAG_RE.sub("", text).split())


# --------------------------------------------------------------------------- parsing

def parse_cues(text: str) -> List[dict]:
    """SRT and WebVTT share the 'start --> end' cue structure."""
    segments = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    for block in blocks:
        lines = [ln for ln in block.strip().split("\n") if ln.strip()]
        for i, line in enumerate(lines):
            match = CUE_RE.search(line)
            if match:
                body = clean(" ".join(lines[i + 1:]))
                if body:
                    segments.append({"start": ts_to_seconds(match.group(1)), "end": ts_to_seconds(match.group(2)), "text": body})
                break
    return segments


def parse_whisper_json(data) -> Tuple[List[dict], Optional[str]]:
    if isinstance(data, dict) and data.get("schema") == TRANSCRIPT_SCHEMA:
        return data["segments"], data.get("language")
    raw = data.get("segments", []) if isinstance(data, dict) else data
    segments = []
    for seg in raw:
        words = []
        for w in seg.get("words") or []:
            token = (w.get("word") or w.get("text") or "").strip()
            if token and w.get("start") is not None and w.get("end") is not None:
                words.append({"word": token, "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)})
        entry = {"start": round(float(seg["start"]), 3), "end": round(float(seg["end"]), 3), "text": clean(seg.get("text", ""))}
        if words:
            entry["words"] = words
        segments.append(entry)
    language = data.get("language") if isinstance(data, dict) else None
    return segments, language


def parse_plain(text: str) -> List[dict]:
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    stamped = []
    for line in lines:
        match = TXT_TS_RE.match(line)
        if match and match.group(2):
            try:
                stamped.append((ts_to_seconds(match.group(1)), clean(match.group(2))))
                continue
            except ValueError:
                pass
        if stamped:
            stamped[-1] = (stamped[-1][0], stamped[-1][1] + " " + clean(line))
        else:
            stamped.append((None, clean(line)))
    if stamped and all(start is not None for start, _ in stamped):
        segments = []
        for i, (start, body) in enumerate(stamped):
            end = stamped[i + 1][0] if i + 1 < len(stamped) else start + max(1.5, len(body.split()) / 2.6)
            segments.append({"start": start, "end": round(end, 3), "text": body})
        return segments
    return [{"start": None, "end": None, "text": " ".join(body for _, body in stamped)}]


def load_transcript(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        C.die(f"Transcript not found: {p}")
    raw = p.read_text(encoding="utf-8-sig", errors="replace")
    language = None
    suffix = p.suffix.lower()
    if suffix == ".json":
        segments, language = parse_whisper_json(json.loads(raw))
        kind = "json"
    elif suffix in (".srt", ".vtt") or CUE_RE.search(raw):
        segments, kind = parse_cues(raw), ("vtt" if raw.lstrip().startswith("WEBVTT") or suffix == ".vtt" else "srt")
    else:
        segments, kind = parse_plain(raw), "text"
    for i, seg in enumerate(segments, 1):
        seg["id"] = i
    timed = bool(segments) and all(seg.get("start") is not None for seg in segments)
    return {
        "schema": TRANSCRIPT_SCHEMA,
        "source": p.name,
        "source_kind": kind,
        "language": language,
        "has_timing": timed,
        "word_level": timed and all(seg.get("words") for seg in segments),
        "duration": max((seg["end"] for seg in segments), default=None) if timed else None,
        "segments": segments,
    }


def full_text(transcript: dict) -> str:
    return " ".join(seg["text"] for seg in transcript["segments"]).strip()


# --------------------------------------------------------------------------- words

WORD_RE = re.compile(r"\S+")
TOKEN_RE = re.compile(f"[{C.CJK_CHARS}]|[{C.CJK_PUNCT}]|[^\\s{C.CJK_CHARS}{C.CJK_PUNCT}]+")
PUNCT_ONLY = re.compile(r"^[\W_]+$")


def tokenize(text: str) -> List[str]:
    """Words for languages with spaces; single characters for Chinese (written without spaces)."""
    return TOKEN_RE.findall(text)


def norm_word(token: str) -> str:
    return re.sub(r"[^\wåäöéü'-]", "", token.lower())


def words_of(transcript: dict) -> List[dict]:
    """Word list with timings. Segment-level transcripts get proportional (approximate) timings."""
    words: List[dict] = []
    for seg in transcript["segments"]:
        if seg.get("words"):
            for w in seg["words"]:
                words.append({"word": w["word"], "start": w["start"], "end": w["end"], "approx": False, "seg": seg["id"]})
            continue
        tokens = tokenize(seg["text"])
        if not tokens or seg.get("start") is None:
            continue
        span = max(0.01, seg["end"] - seg["start"])
        weights = [3 if C.has_cjk(t) else (0.3 if PUNCT_ONLY.match(t) else len(t) + 1) for t in tokens]
        total = sum(weights)
        cursor = seg["start"]
        for token, weight in zip(tokens, weights):
            duration = span * weight / total
            words.append({"word": token, "start": round(cursor, 3), "end": round(cursor + duration, 3), "approx": True, "seg": seg["id"]})
            cursor += duration
    return words


def detect_language(text: str) -> str:
    if C.cjk_ratio(text) > 0.2:
        return "zh"
    lowered = f" {text.lower()} "
    swedish = sum(lowered.count(f" {w} ") for w in ("och", "att", "det", "är", "jag", "som", "inte", "på", "med", "för"))
    english = sum(lowered.count(f" {w} ") for w in ("the", "and", "to", "is", "you", "that", "it", "of", "for", "with"))
    return "sv" if swedish > english else "en"


def filler_sets(lang: str) -> Tuple[set, set]:
    langs = ["en", "sv", "zh"] if lang == "auto" else [str(lang).split("-")[0].lower()]
    hard = set().union(*(HARD_FILLERS.get(code, set()) for code in langs))
    soft = set().union(*(SOFT_FILLERS.get(code, set()) for code in langs))
    return hard, soft


def find_fillers(words: List[dict], lang: str) -> List[dict]:
    """Fillers in a word list. Works on words (English, Swedish) and on characters (Chinese):
    a filler matches one token, or several consecutive tokens ("you know", 那 + 个)."""
    hard, soft = filler_sets(lang)
    keys = {}
    for kind, group in (("soft", soft), ("hard", hard)):
        for phrase in group:
            keys[phrase.replace(" ", "")] = (kind, " " in phrase or C.has_cjk(phrase))
    longest = max((len(k) for k in keys), default=0)
    normalized = [norm_word(w["word"]) for w in words]
    found: List[dict] = []
    i = 0
    while i < len(words):
        if not normalized[i]:
            i += 1
            continue
        acc, best = "", None
        for j in range(i, min(i + 6, len(words))):
            acc += normalized[j]
            if len(acc) > longest:
                break
            if acc in keys and (j == i or keys[acc][1]):
                best = (j, keys[acc][0])
        if best is None:
            i += 1
            continue
        j, kind = best
        span = words[i:j + 1]
        approx = any(w["approx"] for w in span)
        joiner = "" if C.has_cjk(normalized[i]) else " "
        action = "review" if kind == "soft" else ("review (timing approximate)" if approx else "cut")
        found.append({"text": joiner.join(w["word"].strip() for w in span), "start": span[0]["start"],
                      "end": span[-1]["end"], "kind": kind, "approx": approx, "action": action})
        i = j + 1
    return found

def find_pauses(transcript: dict, words: List[dict], threshold: float) -> List[dict]:
    pauses = []
    timeline = words if transcript.get("word_level") else [
        {"start": s["start"], "end": s["end"]} for s in transcript["segments"] if s.get("start") is not None]
    if not timeline:
        return pauses
    if timeline[0]["start"] > 0.3:
        pauses.append({"start": 0.0, "end": timeline[0]["start"], "duration": round(timeline[0]["start"], 3), "where": "before first word"})
    for prev, nxt in zip(timeline, timeline[1:]):
        gap = nxt["start"] - prev["end"]
        if gap >= threshold:
            pauses.append({"start": prev["end"], "end": nxt["start"], "duration": round(gap, 3), "where": "between words"})
    return pauses


def find_retakes(transcript: dict) -> List[dict]:
    """Segments that restart the same sentence: usually the later take is the keeper."""
    retakes = []
    segs = [s for s in transcript["segments"] if s.get("start") is not None]
    hard_zh = "".join(sorted(HARD_FILLERS["zh"]))
    for prev, nxt in zip(segs, segs[1:]):
        if C.has_cjk(prev["text"]):  # compare the first 5 characters, ignoring 嗯/呃
            a = "".join(norm_word(t) for t in tokenize(prev["text"]) if t not in hard_zh)[:5]
            b = "".join(norm_word(t) for t in tokenize(nxt["text"]) if t not in hard_zh)[:5]
            same = len(a) >= 4 and a == b
        else:
            a = [norm_word(t) for t in prev["text"].split()][:4]
            b = [norm_word(t) for t in nxt["text"].split()][:4]
            same = len(a) >= 3 and a[:3] == b[:3]
        if same:
            retakes.append({"start": prev["start"], "end": prev["end"], "text": prev["text"],
                            "reason": "next segment restarts the same sentence; keep the better take (usually the later one)",
                            "next_take_start": nxt["start"]})
    # immediate word repetitions: "I think I think", "the the"
    words = words_of(transcript)
    for i in range(len(words) - 1):
        for n in (3, 2, 1):
            if i + 2 * n <= len(words):
                first = [norm_word(w["word"]) for w in words[i:i + n]]
                second = [norm_word(w["word"]) for w in words[i + n:i + 2 * n]]
                # Chinese doubles words on purpose (一个一个, 慢慢, 看看): only flag 3+ character repeats
                if first == second and all(first) and (n > 1 or len(first[0]) > 2) and not (C.has_cjk(first[0]) and n < 3):
                    retakes.append({"start": words[i]["start"], "end": words[i + n - 1]["end"],
                                    "text": ("" if C.has_cjk(words[i]["word"]) else " ").join(w["word"] for w in words[i:i + 2 * n]),
                                    "reason": f"repeated {'word' if n == 1 else 'phrase'}; cut the first copy",
                                    "approx": words[i]["approx"]})
                    break
    return retakes


def analyze(transcript: dict, lang: str = "auto", pause: float = 0.6) -> dict:
    text = full_text(transcript)
    if lang == "auto":
        lang = transcript.get("language") or detect_language(text)
    words = words_of(transcript)
    fillers = find_fillers(words, lang) if words else []
    pauses = find_pauses(transcript, words, pause) if transcript["has_timing"] else []
    retakes = find_retakes(transcript) if transcript["has_timing"] else []
    duration = transcript.get("duration") or 0
    word_count = sum(1 for ch in text if C.has_cjk(ch)) if lang == "zh" else len(text.split())
    speech = sum(seg["end"] - seg["start"] for seg in transcript["segments"] if seg.get("start") is not None)
    report = {
        "language": lang,
        "has_timing": transcript["has_timing"],
        "word_level_timing": transcript["word_level"],
        "timing_note": ("exact word timings" if transcript["word_level"] else
                        "segment timings only: filler/pause times are approximate (+/- 0.3 s); verify before cutting"
                        if transcript["has_timing"] else "no timings: only text analysis is possible"),
        "stats": {
            "duration_s": round(duration, 2) if duration else None,
            "words": word_count,
            "rate_unit": "characters per minute" if lang == "zh" else "words per minute",
            "words_per_minute": round(word_count / (duration / 60), 1) if duration else None,
            "speech_ratio": round(speech / duration, 2) if duration else None,
            "hard_fillers": sum(1 for f in fillers if f["kind"] == "hard"),
            "soft_fillers": sum(1 for f in fillers if f["kind"] == "soft"),
            "long_pauses": len(pauses),
            "pause_time_s": round(sum(p["duration"] for p in pauses), 2),
            "possible_retakes": len(retakes),
        },
        "fillers": fillers,
        "pauses": pauses,
        "retakes": retakes,
    }
    wpm = report["stats"]["words_per_minute"]
    if wpm:
        report["pacing_hint"] = ("slow for short-form: tighten pauses and cut setup" if wpm < (170 if lang == "zh" else 130) else
                                 "fast: keep pauses after key points so captions stay readable" if wpm > (300 if lang == "zh" else 190) else
                                 "natural short-form pace")
    return report


# --------------------------------------------------------------------------- subtitles

def map_time(t: float, keeps: List[dict]) -> Optional[float]:
    """Source time -> edited-timeline time, or None if t falls in a removed part."""
    offset = 0.0
    for seg in keeps:
        if seg["start"] <= t <= seg["end"]:
            return round(offset + (t - seg["start"]), 3)
        offset += seg["end"] - seg["start"]
    return None


def retime_words(words: List[dict], keeps: List[dict]) -> List[dict]:
    mapped = []
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        if map_time(mid, keeps) is None:
            continue
        start = map_time(max(w["start"], next((k["start"] for k in keeps if k["start"] <= mid <= k["end"]), w["start"])), keeps)
        end = map_time(min(w["end"], next((k["end"] for k in keeps if k["start"] <= mid <= k["end"]), w["end"])), keeps)
        if start is None or end is None:
            continue
        mapped.append(dict(w, start=start, end=max(end, start + 0.05)))
    return mapped


def display_width(text: str) -> float:
    """Line width in Chinese-character units: CJK and full-width characters = 1, Latin = about 0.55."""
    return sum(1.0 if ord(ch) >= 0x2E80 else 0.55 for ch in text)


def join_token(line: str, token: str) -> str:
    if not line:
        return token
    if PUNCT_ONLY.match(token) or (ord(line[-1]) >= 0x2E80 and ord(token[0]) >= 0x2E80):
        return line + token
    return line + " " + token


SOFT_BREAKS = set("，、；：,;:")


def build_cues(words: List[dict], max_chars: int = 26, max_lines: int = 2, max_duration: float = 2.8,
               drop: Optional[set] = None, cjk_mode: bool = False) -> List[dict]:
    """Group words (or Chinese characters) into short caption cues for vertical video.

    Each line keeps its tokens with their times, so when a Chinese line overflows it can break
    after the nearest comma instead of mid-phrase, and the moved text keeps its exact timing.
    """
    cues: List[dict] = []
    lines: List[list] = [[]]  # each line: [(token, start, end), ...]
    skip_punct = False
    width = display_width if cjk_mode else len
    if cjk_mode:  # 16 Chinese characters take about 3.7 s to say; 2.8 s would cut phrases in half
        max_duration = max(max_duration, 4.2)

    def split_after_comma(line) -> list:
        """Cut the line after its last comma if at most 6 characters follow; return the cut-off tail."""
        for k in range(len(line) - 2, max(-1, len(line) - 8), -1):
            if line[k][0] in SOFT_BREAKS:
                tail = line[k + 1:]
                del line[k + 1:]
                return tail
        return []

    def text(line) -> str:
        out = ""
        for token, _, _ in line:
            out = join_token(out, token)
        return out

    def first_start():
        return next((line[0][1] for line in lines if line), None)

    def last_end():
        return next((line[-1][2] for line in reversed(lines) if line), None)

    def flush():
        nonlocal lines
        body = "\n".join(t for t in (text(line) for line in lines) if t)
        if body:
            cues.append({"start": first_start(), "end": last_end(), "text": body})
        lines = [[]]

    for w in words:
        token = w["word"].strip()
        if not token:
            continue
        if drop and norm_word(token) in drop:
            skip_punct = True  # also drop the comma that follows a removed "嗯，" / "um,"
            continue
        is_punct = bool(PUNCT_ONLY.match(token))
        started = first_start() is not None
        if is_punct and (skip_punct or not started):
            continue
        skip_punct = False
        if started and (w["start"] - last_end() > 0.6 or w["end"] - first_start() > max_duration):
            pause = w["start"] - last_end() > 0.6
            carry = split_after_comma(lines[-1]) if (cjk_mode and not pause) else []
            flush()
            if is_punct:
                continue
            lines[-1] = carry
        entry = (token, w["start"], w["end"])
        current = lines[-1]
        if current and not is_punct and width(text(current + [entry])) > max_chars:
            tail = split_after_comma(current) if cjk_mode else []
            if len(lines) >= max_lines:
                flush()
                lines[-1] = tail + [entry]
            else:
                lines.append(tail + [entry])
        else:
            current.append(entry)
        if token.endswith((".", "!", "?", "。", "！", "？")):
            flush()
    flush()
    for prev, nxt in zip(cues, cues[1:]):  # no overlaps, small hold for readability
        prev["end"] = min(max(prev["end"], prev["start"] + 0.7), nxt["start"])
    if cues:
        cues[-1]["end"] = max(cues[-1]["end"], cues[-1]["start"] + 0.7)
    return cues

def to_srt(cues: List[dict]) -> str:
    return "\n".join(f"{i}\n{seconds_to_srt(c['start'])} --> {seconds_to_srt(c['end'])}\n{c['text']}\n"
                     for i, c in enumerate(cues, 1))


def hex_to_ass(color: str, alpha: str = "00") -> str:
    color = color.lstrip("#")
    if len(color) != 6:
        color = "FFFFFF"
    r, g, b = color[0:2], color[2:4], color[4:6]
    return f"&H{alpha}{b}{g}{r}".upper()


def default_cjk_font() -> str:
    """A Chinese-capable font family name for burned-in subtitles on this platform."""
    if sys.platform.startswith("win"):
        return "Microsoft YaHei"
    if sys.platform == "darwin":
        return "PingFang SC"
    return "Noto Sans CJK SC"


def to_ass(cues: List[dict], style: dict, width: int = 1080, height: int = 1920) -> str:
    font = style.get("font") or "Arial"
    size = int(style.get("font_size", 74))
    primary = hex_to_ass(style.get("color", "#FFFFFF"))
    outline = hex_to_ass(style.get("outline_color", "#000000"))
    margin_v = int(style.get("bottom_margin", 620))
    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Reel,{font},{size},{primary},{primary},{outline},&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,90,90,{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = [f"Dialogue: 0,{seconds_to_ass(c['start'])},{seconds_to_ass(c['end'])},Reel,,0,0,0,,{c['text'].replace(chr(10), chr(92) + 'N')}"
              for c in cues]
    return header + "\n".join(events) + "\n"


def make_subtitles(transcript: dict, keeps: Optional[List[dict]], fmt: str, style: dict, lang: str = "auto") -> Tuple[str, int, bool]:
    words = words_of(transcript)
    if not words:
        C.die("This transcript has no timings, so subtitles cannot be timed. Use an .srt/.vtt or word-level JSON.")
    if keeps:
        words = retime_words(words, keeps)
    hard, _ = filler_sets(lang if lang != "auto" else (transcript.get("language") or detect_language(full_text(transcript))))
    cjk = C.cjk_ratio(full_text(transcript)) > 0.3
    max_chars = int(style.get("max_chars_per_line_cjk", 16)) if cjk else int(style.get("max_chars_per_line", 26))
    if cjk and fmt == "ass" and not style.get("font"):
        style = dict(style, font=default_cjk_font())
    cues = build_cues(words, max_chars, int(style.get("max_lines", 2)), drop=hard, cjk_mode=cjk)
    text = to_ass(cues, style) if fmt == "ass" else to_srt(cues)
    approx = any(w.get("approx") for w in words)
    return text, len(cues), approx


# --------------------------------------------------------------------------- CLI

def cmd_parse(args) -> None:
    transcript = load_transcript(args.file)
    if args.out:
        C.save_json(Path(args.out), transcript)
        C.print_json({"saved": args.out, "segments": len(transcript["segments"]), "has_timing": transcript["has_timing"],
                      "word_level": transcript["word_level"], "duration": transcript["duration"]})
    else:
        C.print_json(transcript)


def cmd_analyze(args) -> None:
    report = analyze(load_transcript(args.file), args.lang, args.pause)
    if args.out:
        C.save_json(Path(args.out), report)
        C.print_json({"saved": args.out, **report["stats"], "timing_note": report["timing_note"]})
    else:
        C.print_json(report)


def cmd_text(args) -> None:
    print(full_text(load_transcript(args.file)))


def cmd_subtitles(args) -> None:
    transcript = load_transcript(args.file)
    kit, _ = C.load_brand_kit(C.workspace_dir(args.workspace))
    style = dict(kit.get("reels", {}).get("subtitles", {}))
    if args.font:
        style["font"] = args.font
    keeps = None
    if args.cutlist:
        keeps = C.load_json(Path(args.cutlist)).get("keep")
    fmt = args.format or (Path(args.out).suffix.lstrip(".") if args.out else "srt")
    if fmt not in ("srt", "ass"):
        C.die("--format must be srt or ass")
    text, count, approx = make_subtitles(transcript, keeps, fmt, style, args.lang)
    out = Path(args.out) if args.out else Path(args.file).with_suffix(f".captions.{fmt}")
    out.write_text(text, encoding="utf-8")
    C.print_json({"subtitles": str(out), "cues": count, "format": fmt, "retimed_to_cutlist": bool(keeps),
                  "timing": "approximate (segment-level source)" if approx else "word-level"})


def main() -> None:
    C.setup_stdio()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse")
    p.add_argument("file")
    p.add_argument("--out")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("analyze")
    p.add_argument("file")
    p.add_argument("--lang", default="auto", choices=["auto", "en", "sv", "zh"])
    p.add_argument("--pause", type=float, default=0.6, help="Pause length (s) worth flagging")
    p.add_argument("--out")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("text")
    p.add_argument("file")
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("subtitles")
    p.add_argument("file")
    p.add_argument("--cutlist", help="Re-time captions to this edited cut list")
    p.add_argument("--format", choices=["srt", "ass"])
    p.add_argument("--font", help="Font family for .ass subtitles")
    p.add_argument("--lang", default="auto", choices=["auto", "en", "sv", "zh"])
    p.add_argument("--workspace")
    p.add_argument("--out")
    p.set_defaults(func=cmd_subtitles)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
