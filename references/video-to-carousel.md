# Video or transcript to carousel

Turn a Reel, long video or transcript into a 5-10 slide Instagram carousel that
stands on its own: someone who never saw the video should get the full value.

## 1. Get the words

- Transcript file (.srt, .vtt, .json, .txt): `python scripts/transcript.py text <file>`
- Video only: transcribe (`video_tools.py transcribe`) or ask for the captions export.
  If neither is possible, ask the user to paste the script or key points.
- Optional visuals: `video_tools.py thumbnail <video> --at T` for frames to use on
  cover or image slides; `contact-sheet` to choose them.

## 2. Extract before you write

Write these down first (briefly, in your reasoning or for the user):
- **Core message** in one sentence: what the viewer should believe or do afterwards.
- **Strongest 3-6 points**, in the speaker's own phrasing where it is vivid.
- **Proof:** numbers, examples, stories, quotable lines.
- **Audience tension:** the problem or desire the cover must hit.
Drop tangents, repetition and anything that needs the video to make sense.

## 3. Pick a narrative arc

| Arc | Slides | Best for |
|---|---|---|
| Listicle | cover, why it matters, point 1..n, recap, CTA | tips, mistakes, reasons |
| Myth vs truth | cover, myth 1/truth 1..., takeaway, CTA | correcting misconceptions |
| Problem, then solution | cover, the pain, why it happens, the fix in steps, result, CTA | how-to, frameworks |
| Story | cover, setup, conflict, turning point, lesson, CTA | personal, behind the scenes |
| Before / after | cover, before, what changed 1..n, after, CTA | transformations, case studies |

## 4. Write the slides

- **Cover (slide 1):** the hook as a promise or tension, 4-10 words in the headline. Optional
  kicker (topic label) and subhead (what they'll get). Must work as a thumbnail in the grid.
- **Body:** one idea per slide. Headline 3-9 words; body under ~30 words. Number the
  points when it's a list ("1. ..."). Use `**double asterisks**` around 1-3 key words per
  slide for the accent color. Never emphasize whole sentences.
- **Recap slide:** the whole carousel on one screen. It's the most saved slide.
- **CTA (last slide):** one action that matches the brand goal (save, share with someone,
  comment a keyword, follow, link in bio), plus a reason.
- Keep the speaker's meaning; tighten the wording. Never invent statistics or claims.
- Language: the brand's on-screen language.

## 5. Spec file and rendering

```json
{
  "schema": "ai-content-studio/carousel@1",
  "title": "internal name",
  "size": "1080x1350",
  "slides": [
    {"type": "cover", "kicker": "Topic", "headline": "Hook with **emphasis**", "subhead": "What you'll get", "image": "optional/photo.jpg"},
    {"type": "text", "headline": "...", "body": "..."},
    {"type": "list", "headline": "...", "items": ["...", "..."]},
    {"type": "stat", "stat": "73%", "headline": "...", "body": "..."},
    {"type": "quote", "quote": "...", "attribution": "..."},
    {"type": "image", "image": "path.jpg", "headline": "...", "body": "..."},
    {"type": "cta", "headline": "...", "body": "...", "button": "Follow for more"}
  ],
  "caption": "...", "hashtags": ["#..."], "alt_text": "..."
}
```

`examples/sample-carousel.json` is a complete example. Image paths resolve relative to the spec file,
the workspace, `media/` and `brand/assets/`. Add `"notes"` to a slide for speaker notes in the PPTX.

```bash
python scripts/carousel.py validate spec.json
python scripts/carousel.py render spec.json --workspace <ws> --out <ws>/exports/carousel-<name> --pptx [--pdf]
```

Outputs: `slide-01.png` and so on (upload these to Instagram in order), `carousel.pptx` (editable in
PowerPoint, Keynote or Google Slides; Canva can import it), `overview.png`, `caption.txt`, and
optionally `carousel.pdf`.

**Always open `overview.png` and look at it** before presenting. Fix crowded slides,
unbalanced emphasis, or headlines that wrap badly by editing the spec (shorter text) and
re-rendering. Read the `warnings` in the output: they flag text that had to shrink or overflow.

Chinese text is laid out character by character and needs a Chinese font. It is found
automatically on Windows and macOS; on Linux install Noto Sans CJK, or set `fonts.cjk.file` in
the brand kit. Check `fonts` and `warnings` in the render output before presenting.

If Pillow is missing, deliver the slide copy as a table plus design notes (colors, fonts,
layout per slide) for Canva, and say that images were not created.

## 6. Present

Show the slide copy as a numbered list (headline plus body) so it can be reviewed in chat,
then the files, the caption with hashtags and alt text, and which frames or photos to swap in.
