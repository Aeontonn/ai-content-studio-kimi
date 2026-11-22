# Visual calendar and revising single items

## The calendar file

`python scripts/plan_tool.py render <plan.json> --workspace <ws> --out <ws>/exports/calendar-<week>.html`

One self-contained HTML file (no internet needed) with:
- seven columns, Monday to Sunday, with dates; stacks into day sections on phones
- a card per item: thumbnail (embedded image or a colored hook card), format badge (Reel,
  Story, Carousel, Email), publishing time, title, platforms, checklist progress, status chip
- status chips: **planned** (slot and idea), **drafted** (copy written), **ready**
  (produced, approved, ready to post), **published**
- a counter "X / N published · Y ready" with a progress bar by status
- filters by format and by status, light and dark theme, print layout
- a detail view per item: hook, concept, script, caption, CTA, hashtags, creative direction,
  cross-posting, checklist, copy buttons, and **Copy "regenerate" request**

**Showing it:** give the user the HTML file (attach it, or give its path in Kimi Code / Kimi Work);
it opens in any browser, also on a phone. Re-render after
every change; it takes a second.

**Limits, stated honestly:** the page is a static file. Clicking a status or a checklist box
saves only in that browser (when storage is allowed). It cannot write back to the plan or call
the assistant by itself. The **Save changes** button produces (a) a short change list to paste
into the Kimi chat and (b) the full plan JSON to download. A live, multi-user calendar that
updates itself needs a separate app or database (for example a Notion database,
Airtable or Google Sheets); the plan JSON maps onto any of them
via `plan_tool.py export --format csv`.

## Applying changes the user pastes from the calendar

The pasted text looks like:
```
Using AI Content Studio, apply these changes to my week 2026-W48 plan:
- 2026W48-tue-reel1 status → ready
- 2026W48-mon-carousel1 checklist "Design slides with brand kit" → done
```
With a Chinese brand kit the page writes the same list in Chinese, with the English status in
brackets, e.g. `- 2026W48-tue-reel1 状态 → 待发布 (ready)`. Status names: 已计划 = planned,
已起草 = drafted, 待发布 = ready, 已发布 = published; 清单 = checklist, 已完成 = done.

Apply status lines with `set-status`; apply checklist lines by loading the item, flipping
`done` on the matching task and writing the full `checklist` back with `update --patch`. Then
re-render and run `library.py add-week` to sync statuses. If the user attaches a downloaded
plan JSON instead, diff it against the stored plan and apply only status/checklist differences
(their file may be older for other fields).

## Revising one item without touching the rest

| User says | Do |
|---|---|
| "Change the hook on Thursday's reel" | `show --id`, write the new hook, `update --id ... --set hook="..." --note "..."` |
| "Regenerate Wednesday's carousel, make it about X" | Rewrite all content fields of that item only (title, hook, concept, script, caption, cta, creative_direction, hashtags) into a one-object patch, `update --patch`, keep id/date/time/format |
| "Make the email a reel instead" | `update --id ... --set format=reel` plus new content; check platforms and checklist fit the new format |
| "Move Friday's story to Saturday 19:00" | `move --id ... --day sat --time 19:00` |
| "Add a story on Sunday" | `add --format story --day sun`, then fill it with `update` |
| "Drop the Monday carousel" | `remove --id ...` (restorable with `restore`) |
| "Undo that" | `revert --id ...` restores the previous values of the last change |
| "Mark it published" | `set-status --id ... --status published`, then ask for the post URL and, later, its numbers |

Every `update` records the previous values in the item's `history` and bumps `revision`,
so changes are reversible. After any change: `validate`, re-render, and mention only what
changed.

When regenerating, read the item's neighbors (same day, same pillar) to avoid creating a
repeat, and run `library.py check --text "<new hook>"`.

## Thumbnails

- From footage: `video_tools.py thumbnail clip.mp4 --at 3.2 --vertical --out <ws>/media/thumbs/<id>.jpg`,
  then `update --id <id> --set thumbnail="media/thumbs/<id>.jpg"`.
- From a carousel render: use its `slide-01.png`.
- Paths are resolved relative to the plan file, the workspace, and `<ws>/media`. Images are
  embedded (resized to 360 px wide) so the calendar file stays portable.
