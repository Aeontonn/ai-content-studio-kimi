# Repurposing: one piece in, many pieces out

Take one original (long video, Reel, podcast, live, blog post, transcript, newsletter)
and turn it into a set of native pieces for each format, without changing what it means.

## 1. Extract once (the "content atoms")

From the transcript or text (`transcript.py text <file>`), list:
- **Core idea:** one sentence.
- **Key points:** 3-7, in order of strength.
- **Stories and examples:** with timestamps if from video.
- **Quotable lines:** short, punchy, exact wording (with timestamps), ideal for hooks and quote slides.
- **Data and claims:** exactly as stated. Never round up, never invent.
- **Questions it answers / raises:** these become Story stickers and email openers.
- **Clip candidates:** timestamp ranges of 15-45 s that stand alone (they start with a strong line
  and finish a thought).

Check the library (`library.py check --text ...`) so the pieces don't repeat recent posts.

## 2. Default output set

| Piece | How many | Built from |
|---|---|---|
| Reel concepts | 3 (or more for long sources) | clip candidates or re-filmed angles; each with hook, timestamps or script beats, on-screen text, caption, CTA |
| Carousel | 1 | key points as listicle or framework (references/video-to-carousel.md), rendered if possible |
| Story sequence | 1 set of 4-6 frames | a question or poll opener, 2-3 value frames, link or reply CTA |
| Email newsletter | 1 | subject plus preview, personal opening, the deeper version of the idea, one CTA, P.S. |
| Alternative hooks | 5-10 | different hook types (references/copywriting.md) for testing |
| Alternative captions | 3 | short (1-2 lines), medium (value list), long (story-led) |
| TikTok / Shorts | per Reel | native caption (TikTok) and title (Shorts) |

Adjust to the request: fewer pieces for a short source, more Reels for a long one.

## 3. Adapting without distorting

- Same meaning, native form: a Reel needs a spoken hook and pace; a carousel needs scannable
  steps; Stories need interaction; email needs a personal voice and depth.
- Each piece must stand alone. Don't write "as I said in the video".
- Keep claims, numbers and advice identical across pieces. If a point needs nuance (health,
  money, legal), keep the nuance in every format.
- Vary the angle per piece so a follower who sees all of them gets new value each time:
  the Reel teases the problem, the carousel gives the steps, the email tells the story behind it.
- Quote the speaker accurately when using quotes; tidy fillers only.

## 4. Output template

```
## Source summary
Core idea · key points · best quotes (with timestamps)

## Reels (3)
### Reel 1: <title>
Clip: 00:41-01:12 (or "re-film")  |  Hook (spoken): ...  |  On-screen: ...
Beats: ...  |  Caption: ...  |  CTA: ...  |  TikTok caption / Shorts title: ...

## Carousel
Slides 1-n (headline / body)  |  caption  |  alt text  |  files (if rendered)

## Story sequence
Frame 1..n: visual / text / sticker

## Email
Subject (2 options) · preview text · body · CTA · P.S.

## Alternative hooks (by type) and captions (short / medium / long)

## Suggested schedule
Which day and slot each piece fits, if a week plan exists
```

## 5. Into the calendar (optional)

If the user wants the pieces scheduled, add them to the current or next week plan:
`plan_tool.py add --format reel --day thu`, then `update --patch` with the content, set
`campaign` to the source name so the pieces are grouped, and set `repurposed_from` to the
source item's id when the source is in the plan or library. That tells `validate` and
`library.py check` the overlap is deliberate, so they keep flagging only accidental repeats.
Run `validate` and re-render the calendar.

`examples/sample-repurpose-output.md` shows a complete run on `examples/sample-transcript.srt`.
