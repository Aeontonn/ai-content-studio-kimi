# Reel editing assistant

Turn raw footage into a tight, captioned 9:16 Reel, or into a precise edit plan when
rendering isn't possible here.

## Contents
1. What works where
2. Step-by-step
3. Editing decisions
4. Captions, on-screen text, graphics, transitions
5. Rendering and verification
6. Handing off to editing apps
7. Deliverable format

---

## 1. What works where (check with `check_env.py`)

| Capability | Needs | Fallback |
|---|---|---|
| Read duration / size / fps | ffmpeg | ask the user, or work from the transcript |
| Look at the footage | ffmpeg + Pillow (contact sheet) | ask for screenshots or a description |
| Transcribe speech | faster-whisper or openai-whisper (model download needs internet once) | user exports captions (.srt/.vtt) from CapCut, Instagram, TikTok, Descript, Premiere, YouTube Studio |
| Find pauses precisely | ffmpeg | pause estimates from transcript timings |
| Render the edit | ffmpeg (libx264) | cut list CSV + EDL + captions for an editing app |
| Burn in captions | ffmpeg with libass | upload the .srt as captions, or import into the editing app |

Chat uploads are usually limited in size. For longer or 4K footage, work locally in
Kimi Code or Kimi Work, or have the user send a compressed preview (720p) for analysis
and apply the cut list to the original in their editor.

## 2. Step-by-step

```bash
V=raw.mp4; OUT=<ws>/exports/<name>
python scripts/video_tools.py probe $V
python scripts/video_tools.py contact-sheet $V --count 12 --out $OUT/contact.jpg      # then LOOK at it
python scripts/video_tools.py transcribe $V --out $OUT/transcript.json                # or use the user's .srt
python scripts/transcript.py analyze $OUT/transcript.json --out $OUT/analysis.json
python scripts/video_tools.py silences $V --out $OUT/silences.json
python scripts/video_tools.py cutlist --transcript $OUT/transcript.json --silences $OUT/silences.json \
       --video $V --cut-retakes --out $OUT/cutlist.json
# review cutlist.json "suggestions", then hand-tune:
python scripts/video_tools.py edit $OUT/cutlist.json --remove 1.28-1.95 --reason "filler before hook"
python scripts/transcript.py subtitles $OUT/transcript.json --cutlist $OUT/cutlist.json --format ass --out $OUT/captions.ass
python scripts/transcript.py subtitles $OUT/transcript.json --cutlist $OUT/cutlist.json --out $OUT/captions.srt
python scripts/video_tools.py render $V --cutlist $OUT/cutlist.json --subs $OUT/captions.ass --loudnorm --out $OUT/reel.mp4
python scripts/video_tools.py contact-sheet $OUT/reel.mp4 --count 8 --out $OUT/reel-check.jpg   # LOOK at the result
```

Without a transcript, `cutlist --silences ... --video ...` still removes dead air and long pauses.

For Chinese speech pass `--language zh` to `transcribe`: it also nudges Whisper to write Simplified
Chinese. Chinese captions wrap at about 16 characters per line, and the styled `.ass` file uses a
Chinese system font (Microsoft YaHei, PingFang SC or Noto Sans CJK SC).

## 3. Editing decisions

**The hook decides everything.** The first spoken or shown line must land within ~1 s.
Cut any warm-up ("Hi guys, so today..."), "um", breath or fumbling before it. If the
strongest line comes later in the footage, suggest opening with it (a cold open): give the
timestamp range to move, since the renderer only removes, it does not reorder (an editing
app can reorder using the cut list).

**Pauses:** shorten pauses longer than ~0.55 s down to ~0.25 s. Keep a beat after punchlines,
questions and before a reveal. Natural speech needs breathing room. Do not
cut every gap to zero: it sounds robotic and makes captions flash.

**Fillers:** hard fillers (um, uh, eh, öh, 嗯, 呃) are cut automatically when word-level timings exist.
Soft fillers (like, so, basically, liksom, typ, alltså, 那个, 就是, 然后) only when they add nothing. Listen
in context. With segment-level timings, list them as review items with approximate timestamps.

**Retakes:** when a sentence is restarted, keep the better (usually later) take. `--cut-retakes`
removes the earlier take for segment-level restarts; check the suggestions list for others.

**Pacing:** for talking heads, change something visually every 2-4 s: a punch-in (`--punch-in
1.12` alternates 100% / 112% zoom between segments, which reads like a second camera), B-roll, a text
pop-up, or a cut. Aim for 140-180 words per minute in the final edit. Most educational
Reels land at 20-45 s; cut anything that doesn't serve the one idea.

**Reframing horizontal footage:** `fit` options: `cover` (crop to fill; set `focus_x` per
segment with `edit --focus TIME=0.35` when the subject is off-center), `blur` (whole frame
over a blurred fill, good for screen recordings or wide shots), `pad` (black bars, rarely good).

**Ending:** end on the CTA or loop to the opening line so replays feel seamless.

## 4. Captions, on-screen text, graphics, transitions

- **Subtitles:** `transcript.py subtitles` builds short cues (max 2 lines, about 26 characters per line,
  at most about 2.8 s each), drops hard fillers from the text, and re-times to the cut list. `.ass` is
  styled (size, outline, position above the bottom UI zone) for burning in; `.srt` uploads to
  Instagram, TikTok and YouTube, or imports into editors. Correct misheard words in the text
  before rendering. Brand names and Swedish words are common errors.
- **On-screen hook text:** 3-7 words, top-center or upper third, on screen for the first 2-3 s,
  inside the safe zone (references/platform-specs.md).
- **Graphics:** suggest at most one per 5-8 s: numbered points ("1/3"), a key word highlight,
  arrows, a progress bar for lists. Give the timestamp, the text and its position.
- **Transitions:** prefer straight cuts and punch-ins; use a whip or zoom transition only to mark a
  new section. Specify at which cut and why.
- **Music:** suggest a mood and BPM range; add trending audio inside the Instagram app (licensed
  there), mixed at about -20 dB under the voice.
- **Cover frame:** pick a frame with a clear face or subject and readable space for a title;
  `video_tools.py thumbnail --at T --vertical`.

## 5. Rendering and verification

`render` cuts the keep segments, applies zoom and focus, fits to 1080x1920 at 30 fps, burns
captions if given, normalizes audio to -14 LUFS with `--loudnorm`, encodes H.264/AAC
with faststart, and then **re-opens the output** to verify resolution and duration. Only report
success when it printed `"verified": true`, and give the path and duration. Then make a contact
sheet of the output and look at it: caption position, framing and zoom jumps.

If render fails or ffmpeg is missing, say exactly that, and deliver section 6 instead.

## 6. Handing off to editing apps

Always deliver `cutlist.csv` (human-readable) and `cutlist.edl`, plus `captions.srt`.

- **Premiere Pro:** File > Import > choose the `.edl`, and link the clip when asked (the clip name
  is in the EDL). Captions: File > Import the `.srt`, then drag it onto the timeline.
  Sequence settings: 1080x1920, 30 fps.
- **DaVinci Resolve:** File > Import > Timeline > select the `.edl` (media must be in the Media Pool).
  Captions: import the `.srt` into the Media Pool and drag it onto a subtitle track.
- **CapCut / 剪映 (desktop or mobile):** no EDL import. Split the clip at each KEEP start and end in the CSV
  and delete the CUT parts (work from the end backwards so times don't shift). Captions: Text > Auto captions,
  or import the `.srt` on desktop.
- **Final Cut Pro:** import the EDL through a converter, or cut manually from the CSV.

## 7. Deliverable format (in chat)

1. **What I looked at:** duration, orientation, audio, speaking rate, key observations from the contact sheet.
2. **Edit summary:** original length, then edited length; what was removed (counts and seconds).
3. **Hook:** the opening line and on-screen text, plus 2 alternatives.
4. **Cut list table:** # | keep from to | length | notes (zoom, B-roll, graphic).
5. **Review items:** soft fillers and possible retakes with timestamps, and what you recommend.
6. **Captions, graphics, transitions, music** suggestions with timestamps.
7. **Files:** rendered video (only if verified), captions, cut list CSV and EDL, contact sheets.
8. **Caption for the post** and CTA, in the brand voice.
