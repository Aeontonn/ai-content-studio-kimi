---
name: ai-content-studio-kimi
description: Plan, write, edit and repurpose social media content (Instagram Reels, Stories, carousels, TikTok, YouTube Shorts, email newsletters) with a saved brand profile, a visual weekly calendar and a content library. Works in English and Chinese. Use it whenever the user wants a weekly content plan or calendar (内容日历, 一周选题), post ideas, hooks, scripts, captions or CTAs (文案, 脚本, 开头钩子); wants raw video edited into a Reel (cut list, filler and pause removal, subtitles, 9:16; 剪辑, 字幕, 去掉口头禅); wants a video or transcript turned into a carousel (轮播图); wants one piece of content repurposed into many formats (一稿多用); or wants to set up their brand voice, brand kit, content library or post results (品牌设定, 数据复盘). Also use it to revise one post in an existing plan, and for casual asks like "what should I post this week" or "这周发什么".
---

# AI Content Studio (Kimi edition)

A content studio for one creator brand: weekly planning with a visual calendar,
Reel editing, video-to-carousel, repurposing, and a brand memory that keeps
everything on-voice and non-repetitive.

**Skill folder:** `${KIMI_SKILL_DIR}`. If that still reads as a literal `${...}` placeholder,
the skill folder is simply the directory that contains this SKILL.md. Below, `<skill>` means
that folder. Run scripts as `python "<skill>/scripts/<script>.py" ...` (use `python3` where
`python` is not found). Every script has `--help`.

## Language

Reply in the language the user writes in. Write content (hooks, captions, scripts, slides,
emails) in the language the user asks for; if they don't say, use the brand profile's content
language; if that is not set, use the user's language. Chinese and English both work in every
workflow. Technical names (file names, script names, item ids, JSON keys) stay in English.
For Chinese copy follow section 9 of references/copywriting.md.

## Ground rules

1. **Brand memory before content.** Read the brand profile and the library digest before
   writing anything. Generic content is the failure mode this skill exists to prevent.
2. **Only claim files that exist.** Say a video was edited, rendered or exported, or that
   slides or files were created, only after the script printed `"ok": true` /
   `"verified": true` and you can give the path or attach the file. If a tool is missing,
   say so plainly and deliver the fallback (cut list, slide copy, plan table). The user will
   publish based on what you say; a fake "done" costs a missed post and their trust.
3. **The week plan JSON is the source of truth.** Change one item with
   `plan_tool.py update --id`. Never rewrite the whole week to change one post; the user
   may already be filming the others.
4. **Write in the brand's voice**, following the profile's do/don't list and banned words.
5. **Never copy other creators.** Reference accounts are for style cues only.

## Two ways of working

**Script mode** (preferred): you can run Python 3.9+ and read/write files. This is the case in
Kimi Code, usually in Kimi Work (it asks the user before running code), and in any agent
sandbox that can execute code. Use the scripts: they keep ids, dates, validation, rendering
and exports exact.

**Chat-only mode**: you cannot run code or save files. Do the same workflows by hand:
- Plans: produce the full content for every slot as a Markdown table plus one section per
  item (hook, concept, script, caption, CTA, creative direction, checklist). Use the frequency
  presets and posting times from references/weekly-planning.md and references/platform-specs.md.
- Calendar: if the user wants the visual calendar, build the plan JSON in the exact shape of
  `<skill>/examples/sample-week-plan.json`, then output the file `<skill>/assets/calendar_template.html`
  with `/*__PLAN_JSON__*/null` replaced by that JSON, `/*__BRAND_JSON__*/null` replaced by
  `{"name": "...", "handle": "...", "accent": "#hex", "language": "zh"}` (or `"en"`) and
  `__PAGE_TITLE__` by a title, in one code block for the user to save as `calendar.html`.
- Reel edits: read the timestamps in the user's .srt and list exact cuts (keep from/to,
  reason), plus a re-timed .srt and CapCut steps. Never claim a rendered video.
- Carousels: deliver the slide copy as a numbered list plus design notes (colors, fonts,
  layout per slide) for Canva, PowerPoint or 美图/稿定设计 style tools.
- Memory: ask the user to paste or attach their `brand-profile.md` and `library.json`, and
  give updated versions back as code blocks to save.
Tell the user once, briefly, which mode you are in and what that means for files.

## Start of every session

1. Script mode check: `python "<skill>/scripts/check_env.py"` shows which features can run here
   (Pillow, python-pptx, ffmpeg, transcription, Chinese fonts) and where to save files. Offer
   only what is marked OK; offer the fallback for the rest.
2. Workspace: `$CONTENT_STUDIO_DIR`, or `./content-studio` in the current folder. If the user
   attached a previous `content-studio.zip` or `library.json`, restore it there first
   (references/brand-memory.md). Pass `--workspace <path>` to the scripts.
3. `python "<skill>/scripts/library.py" status --workspace <ws>`
   - Workspace missing: `library.py init --workspace <ws>`.
   - Brand not configured: run **onboarding** (references/brand-memory.md has the questions in
     English and Chinese). For a quick text-only request you may proceed with a short
     provisional profile, then offer onboarding afterwards.
4. Read `<ws>/brand/brand-profile.md` in full and run `library.py recent --workspace <ws>`
   before generating ideas.

## Workflows

| The user wants... | Read | Main scripts |
|---|---|---|
| A week of content, ideas, a calendar | references/weekly-planning.md, references/copywriting.md | plan_tool.py, library.py |
| To change, regenerate, move, add or drop one post; sync calendar clicks | references/calendar.md | plan_tool.py |
| A Reel edited from raw footage | references/reel-editing.md, references/platform-specs.md | video_tools.py, transcript.py |
| A Reel / transcript turned into a carousel | references/video-to-carousel.md | transcript.py, carousel.py |
| One piece of content turned into many | references/repurposing.md | transcript.py, carousel.py, plan_tool.py |
| Brand setup, voice, assets, results, idea backlog | references/brand-memory.md | library.py |

Read the reference file for the workflow before starting it; each has the exact steps,
output formats and quality checks. Script commands in the references are written as
`python scripts/...`: run them from the skill folder, or prefix `<skill>/`.

### 1. Weekly content plan
Gather: theme or campaign, promotions and dates, goals, footage on hand, frequency (default
from brand kit; `balanced` = 3 Reels, 2 carousels, 7 Story sets, 1 email; `light` = 7 items;
`heavy` = 28, the maximum, 4 per day). Then: `plan_tool.py new` (skeleton with days, times and
stable ids), write the content for every item into a patch file, `plan_tool.py update --patch`,
`library.py check --plan` (repeats against history), `plan_tool.py validate`,
`plan_tool.py render` (visual calendar), `library.py add-week`. Each item gets hook, concept,
script/outline, caption, CTA, creative direction and a production checklist.

### 2. Reel editing
Probe, contact sheet (look at it), transcript (the user's .srt/.vtt, or `transcribe`; add
`--language zh` for Chinese speech), `transcript.py analyze`, `video_tools.py silences`,
`video_tools.py cutlist`, review the suggestions and `edit`, captions, `render` (only with
ffmpeg; it verifies the output). Always also hand over the cut list CSV/EDL and the .srt so
the edit can be finished in CapCut (剪映), Premiere Pro or DaVinci Resolve.

### 3. Video / transcript to carousel
Transcript text, core message plus 3-6 strongest points, narrative arc, slide spec (5-10
slides: cover, body, recap, CTA), `carousel.py validate`, `carousel.py render --pptx`, then view
`overview.png` and fix anything that reads badly. Chinese slides need a Chinese font
(check_env shows whether one was found).

### 4. Repurposing
Extract the core idea, key points, quotable lines and stories once, then adapt per format
(Reel concepts, carousel, Story sequence, newsletter, alternative hooks and captions)
without changing the meaning. Optionally slot the pieces into the week plan with
`repurposed_from` set.

### 5. Brand memory
`library.py` keeps the idea history, idea backlog, media index, post results and learnings.
After publishing: `log-performance`; after spotting a pattern: `add-learning`.

### 6. Calendar
`plan_tool.py render` writes one self-contained HTML calendar: Monday-Sunday columns,
thumbnail cards, format labels, times, status chips (planned, drafted, ready, published), a
published/total counter, filters and a detail view per post. With a Chinese brand kit
(`"language": "zh-CN"`) the page is in Chinese. Give the user the file (attach it, or give the
path). Status and checklist clicks stay in that browser until the user presses
**Save changes** and pastes the change list back to you; apply it with
`plan_tool.py set-status` / `update` and re-render.

## Quality bar for everything you write

- **Hook first.** The first 1-2 seconds of a Reel, the first caption line, the cover slide and
  the subject line carry the piece. Write 3 options, keep the strongest, vary hook types.
- **One idea per piece**, said specifically, in the audience's own words from the profile.
- **CTA matches the goal** in the profile (save, share, comment, follow, link, reply).
- **No repetition.** Check new ideas against the library and within the week.
- **Production-ready.** Scripts have timings and on-screen text; creative direction says shot,
  setting, light, wardrobe, B-roll, music mood; checklists are concrete.

## End every task with

- **Created:** each verified file with its path (or "nothing was rendered, because...").
- **Needs you:** filming, approvals, uploads, missing brand details.
- **Next:** one suggested next step.
