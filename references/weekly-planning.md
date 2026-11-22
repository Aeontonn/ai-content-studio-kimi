# Weekly content planning

Plan 7 days of content (up to 28 items, max 4 per day) across Reels, Stories, carousels
and email, then render a visual calendar.

## Contents
1. Inputs
2. Step-by-step
3. Choosing ideas
4. What every item contains (per format)
5. Patch file format
6. Validation, calendar, exports
7. What to show the user

---

## 1. Inputs

Collect what is missing, in one short message (skip anything already in the profile):
- **Week:** which week (default: next Monday to Sunday).
- **Focus:** theme, campaign, launch, promotion, holiday, event (with dates and offer details).
- **Goals this week:** e.g. grow, sell X, newsletter sign-ups, engagement.
- **Footage on hand:** clips or photos to build around (also check `library.py media --unused`).
- **Frequency:** default from the brand kit (`balanced`). Light = 7, balanced = 13,
  heavy = 28, or a custom mix like `reel=4,story=7,carousel=2,email=1`.
- **Constraints:** filming days, travel, busy days to keep light.

If the user says "just plan my week", use the defaults and say which assumptions you made.

## 2. Step-by-step

```bash
WS=<workspace>
python scripts/library.py recent --workspace $WS            # what exists, what worked, backlog, unused footage
python scripts/plan_tool.py new --workspace $WS --week 2026-W48 --preset balanced \
    --theme "Slow mornings" --goals "Grow saves;Newsletter sign-ups"      # skeleton with ids, days, times
# write content for every item into $WS/weeks/2026-W48.patch.json   (section 5)
python scripts/plan_tool.py update $WS/weeks/2026-W48.json --patch $WS/weeks/2026-W48.patch.json --note "first draft"
python scripts/library.py check --workspace $WS --plan $WS/weeks/2026-W48.json   # repeats vs history
python scripts/plan_tool.py validate $WS/weeks/2026-W48.json                      # structure + in-week repeats
python scripts/plan_tool.py render $WS/weeks/2026-W48.json --workspace $WS --out $WS/exports/calendar-2026-W48.html
python scripts/plan_tool.py export $WS/weeks/2026-W48.json --format md --out $WS/exports/plan-2026-W48.md
python scripts/library.py add-week --workspace $WS $WS/weeks/2026-W48.json
```

`new` decides days and times from the brand kit (preferred days, default times, cross-posting).
Move slots afterwards if the content needs it (`plan_tool.py move`), for example putting
a launch Reel on launch day. A campaign or promotion can shift the mix: add slots with
`plan_tool.py add`, remove with `remove`.

Fix every validation **error**. For **warnings**, fix repeats and missing fields;
"planned but missing fields" is fine for items the user wants to write later.

## 3. Choosing ideas

Work like an editor, not a random generator:

1. **Balance pillars** using the shares in the profile (e.g. 40/30/20/10). Note which
   pillars were under-used in `recent`.
2. **Map the week's story:** Monday sets up the theme, mid-week delivers value, the
   end of the week converts or connects. Promotions get a runway: tease, then value tied to the
   offer, then proof, then direct offer, then last call.
3. **Mix intents:** reach (broad, shareable), trust (teach, show expertise), connection
   (story, behind the scenes, opinions), conversion (offer, testimonial, objection-handling).
   Balanced week: Reels lean reach, carousels lean saves and trust, Stories lean connection and
   conversion, email leans depth and conversion.
4. **Use what exists:** build around footage on hand first, then the idea backlog, then
   new ideas. Note footage in `footage` and use a frame as `thumbnail` when possible
   (`video_tools.py thumbnail`).
5. **Angles generator** when you need fresh ideas: for each pillar, combine an audience
   pain or desire with one angle: mistake, myth, how-to, list, story, before/after, opinion,
   behind the scenes, Q&A from comments, comparison, challenge, tool or resource, mini case study.
6. **Repeat-check:** `library.py check` plus in-week `validate`. Change the angle,
   not just the wording.
7. **Vary hooks:** never more than two items in a week with the same hook type
   (references/copywriting.md lists the types).

## 4. What every item contains

All formats: `title` (internal, short), `pillar`, `campaign` (or empty), `hook`, `concept`,
`script`, `cta`, `creative_direction`, `checklist` (pre-filled per format; edit or extend),
`hashtags` (3-5, specific), `thumbnail` (image path, optional), `footage` (paths, optional),
`notes`, and `repurposed_from` (the id of the post this one deliberately reuses, e.g. a
carousel made from Tuesday's Reel; it tells the repeat checks this overlap is intended).

**Reel** (`platforms`: instagram plus cross-posts)
- `hook`: what is *said or shown* in the first 1-2 s, plus the on-screen hook text.
- `concept`: 1-3 sentences: the idea, the angle, why the audience cares.
- `script`: list of beats with timing, e.g.
  `[{"time": "0-2s", "visual": "...", "voiceover": "...", "on_screen": "..."}, ...]`, 15-45 s total
  unless the idea needs longer. End on the CTA beat or a loop back to the opening.
- `caption`: first line repeats or extends the hook (it shows before "more"), then 2-5 short
  lines of value or context, then the CTA. Write in the brand's caption language.
- `creative_direction`: shot type, framing, setting, light, wardrobe, B-roll list, text style,
  music or sound mood, pacing notes.
- `platform_variants`: for `tiktok` and `youtube_shorts`, a native caption (TikTok: keyword-rich,
  conversational; Shorts: add a `title` up to 100 characters) and keep or adjust the `time`.

**Story set** (one item = a sequence of 3-7 frames)
- `hook`: frame 1 text.
- `script`: list of frames `[{"frame": 1, "visual": "...", "text": "...", "sticker": "poll: A / B"}]`.
  Use one interactive sticker (poll, quiz, question box, slider, link) per set.
- `caption`: not needed. `cta`: the action (vote, reply, tap link).

**Carousel**
- `hook`: the cover headline (and kicker).
- `script`: slide outline `[{"slide": 1, "type": "cover", "headline": "...", "subhead": "..."}, ...]`
  using the slide types of carousel.py, 5-10 slides (see references/video-to-carousel.md).
- `caption`, `cta` (usually save or share), alt text in `notes`.

**Email** (`platforms`: email)
- `subject` (30-50 characters), `preview_text` (40-90 characters); `hook` = opening line.
- `script`: outline or full draft: greeting, story or insight, the value, one clear CTA, P.S.
- `concept`: why this email, this week. `cta`: the single link or action.

## 5. Patch file format

A JSON list; each object has the item `id` from `new` plus any fields to set. Only
include fields you are setting. ids, dates and times come from the skeleton, so the
schedule stays intact.

```json
[
  {
    "id": "2026W48-tue-reel1",
    "title": "3 reasons your morning routine fails",
    "pillar": "Habits",
    "status": "drafted",
    "hook": "Your morning routine isn't failing because you're lazy.",
    "concept": "Reframe failed routines as a design problem...",
    "script": [{"time": "0-2s", "visual": "Close-up, kitchen, morning light", "voiceover": "Your morning routine isn't failing because you're lazy.", "on_screen": "it's not laziness"}],
    "caption": "Your morning routine isn't failing because you're lazy...",
    "cta": "Save this for tomorrow morning",
    "hashtags": ["#morningroutine", "#habits", "#slowliving"],
    "creative_direction": "Talking head at counter, natural window light...",
    "platform_variants": {"tiktok": {"caption": "...", "time": "19:00"}, "youtube_shorts": {"title": "...", "caption": "...", "time": "17:00"}}
  }
]
```

Set `status` to `drafted` once hook, concept, script, caption (not Stories) and CTA are written.
`ready` and `published` are for the user's progress. Leave them unless the user says so.

## 6. Validation, calendar, exports

- `validate` checks: Monday-Sunday dates, valid formats, statuses, times, max 4 per day and
  28 per week, two posts on the same platform at the same minute, required fields per status,
  and near-duplicate ideas inside the week.
- `render` writes the calendar HTML (references/calendar.md). Thumbnails: local image paths in
  `thumbnail` are embedded; otherwise a colored card shows the hook.
- `export --format md` writes a production doc; `csv` is for spreadsheets or schedulers;
  `ics` adds posting reminders to Google, Apple or Outlook calendars.

## 7. What to show the user

1. One-line summary: week, theme, item count by format.
2. A compact table: Day | Time | Format | Title | Hook (short).
3. The calendar HTML file (attach it, or give its path), plus the Markdown production doc path.
4. Full details for the first 2-3 items inline. The rest are in the doc and calendar, so don't paste 13 full briefs into chat unless asked.
5. Repeats or warnings you resolved, assumptions made, and what the user needs to film or provide.
