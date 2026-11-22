#!/usr/bin/env python3
"""AI Content Studio - weekly content plan tool.

The week plan JSON is the single source of truth for one week. This tool
builds the schedule skeleton (days, times, formats, IDs), edits ONE item at a
time with a revision history (so revising a post never disturbs the rest of
the week), validates the plan, and renders or exports it.

Commands
  new         Create a week skeleton from a frequency preset or custom mix
  show        Print one item as JSON
  update      Change fields on one item, or apply a list of patches by id
  revert      Undo the last update of one item
  set-status  Move an item to planned / drafted / ready / published
  move        Move an item to another day and/or time
  add         Add one empty slot
  remove      Remove one item (kept in plan["removed"] so it can be restored)
  restore     Bring a removed item back
  validate    Check structure, limits, required fields and repeated ideas
  summary     Print a compact overview table
  render      Build the visual Monday-Sunday HTML calendar
  export      Export as Markdown production doc, CSV, or .ics calendar file

Examples
  python plan_tool.py new --week 2026-W48 --preset balanced --theme "Slow mornings" --out weeks/2026-W48.json
  python plan_tool.py update weeks/2026-W48.json --patch content.json
  python plan_tool.py update weeks/2026-W48.json --id 2026W48-thu-reel1 --set hook="New hook" --note "punchier"
  python plan_tool.py set-status weeks/2026-W48.json --id 2026W48-thu-reel1 --status ready
  python plan_tool.py render weeks/2026-W48.json --out calendar-2026-W48.html
"""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402
import dedupe  # noqa: E402

SCHEMA = "ai-content-studio/week-plan@1"
PROTECTED_FIELDS = {"id", "history", "revision", "created_at", "updated_at"}
HISTORY_LIMIT = 15

REQUIRED_FIELDS = {
    "reel": ["title", "hook", "concept", "script", "caption", "cta"],
    "carousel": ["title", "hook", "concept", "script", "caption", "cta"],
    "story": ["title", "hook", "concept", "script", "cta"],
    "email": ["title", "subject", "preview_text", "concept", "script", "cta"],
}

DEFAULT_CHECKLISTS = {
    "reel": [
        "Script and hook approved",
        "Film A-roll vertical (9:16, 1080x1920 or 4K, 30 fps)",
        "Capture 3-5 B-roll clips",
        "Edit: cuts, pacing, music",
        "Subtitles and on-screen text",
        "Choose cover frame",
        "Caption, hashtags and alt text",
        "Publish on Instagram",
    ],
    "story": [
        "Plan frames",
        "Capture or design frames (9:16)",
        "Add interactive sticker (poll, quiz, question or link)",
        "Publish",
        "Add to Highlight if evergreen",
    ],
    "carousel": [
        "Outline approved",
        "Write slide copy",
        "Design slides with brand kit",
        "Proofread every slide",
        "Caption, hashtags and alt text",
        "Publish",
    ],
    "email": [
        "Subject line and preview text",
        "Draft body",
        "Add links and CTA button",
        "Send test email and check on mobile",
        "Schedule send",
    ],
}

DEFAULT_CHECKLISTS_ZH = {
    "reel": [
        "脚本和开头钩子已确认",
        "竖屏拍摄主画面（9:16，1080x1920 或 4K，30 fps）",
        "补拍 3-5 段空镜（B-roll）",
        "剪辑：剪切、节奏、音乐",
        "字幕和画面文字",
        "选择封面帧",
        "文案、话题标签和替代文字",
        "发布到 Instagram",
    ],
    "story": [
        "规划每一帧",
        "拍摄或设计画面（9:16）",
        "添加互动贴纸（投票、测验、提问或链接）",
        "发布",
        "长期有用的内容加入精选快拍",
    ],
    "carousel": [
        "大纲已确认",
        "撰写每一页文字",
        "按品牌模板设计",
        "逐页校对",
        "文案、话题标签和替代文字",
        "发布",
    ],
    "email": [
        "邮件标题和预览文字",
        "撰写正文",
        "添加链接和行动按钮",
        "发送测试邮件并在手机上检查",
        "定时发送",
    ],
}


def checklist_for(fmt: str, lang) -> List[str]:
    """Production checklist in the brand's language."""
    return (DEFAULT_CHECKLISTS_ZH if C.is_zh(lang) else DEFAULT_CHECKLISTS)[fmt]

PRIORITY_TO_MOVE = ["story", "carousel", "email", "reel"]  # what moves first when a day is overloaded


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- building a week

def parse_mix(text: str) -> Dict[str, int]:
    mix: Dict[str, int] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            C.die(f"Mix entry '{part}' should look like reel=3")
        key, value = part.split("=", 1)
        key = key.strip().lower().rstrip("s")
        if key not in C.FORMATS:
            C.die(f"Unknown format '{key}' in mix. Use: {', '.join(C.FORMATS)}")
        try:
            mix[key] = int(value)
        except ValueError:
            C.die(f"Count for '{key}' must be a whole number")
    return mix


def resolve_mix(preset: Optional[str], mix_text: Optional[str], kit: dict) -> Dict[str, int]:
    schedule = kit.get("schedule", {})
    if mix_text:
        mix = parse_mix(mix_text)
    else:
        name = preset or schedule.get("frequency_preset") or "balanced"
        if name == "custom":
            mix = {k: int(v) for k, v in (schedule.get("custom_mix") or {}).items()}
            if not mix:
                C.die("Preset 'custom' needs schedule.custom_mix in the brand kit, or pass --mix")
        elif name in C.PRESETS:
            mix = dict(C.PRESETS[name])
        else:
            C.die(f"Unknown preset '{name}'. Use: {', '.join(C.PRESETS)} or custom")
    full = {fmt: max(0, int(mix.get(fmt, 0))) for fmt in C.FORMATS}
    total = sum(full.values())
    if total == 0:
        C.die("The mix has zero items")
    if total > C.MAX_PER_WEEK:
        C.die(f"The mix has {total} items; the maximum is {C.MAX_PER_WEEK} per week ({C.MAX_PER_DAY} per day)")
    return full


def distribute(count: int, preferred: List[str]) -> List[str]:
    """Spread `count` items over the week: whole rounds over all days, remainder on preferred days."""
    order = [d for d in preferred if d in C.DAYS] + [d for d in C.DAYS if d not in preferred]
    rounds, extra = divmod(count, 7)
    days = [day for day in C.DAYS for _ in range(rounds)]
    days.extend(order[:extra])
    return days


def slot_time(kit: dict, fmt: str, day: str, index: int) -> str:
    times = kit["schedule"]["default_times"].get(fmt, {})
    key = "weekend" if day in ("sat", "sun") else "weekday"
    options = times.get(key) or ["12:00"]
    if isinstance(options, str):
        options = [options]
    if index < len(options):
        return options[index]
    hour, minute = map(int, options[-1].split(":"))
    hour = min(23, hour + 2 * (index - len(options) + 1))
    return f"{hour:02d}:{minute:02d}"


def platforms_for(fmt: str, kit: dict) -> List[str]:
    enabled = set(kit.get("platforms") or C.PLATFORMS)
    if fmt == "email":
        return ["email"]
    platforms = ["instagram"]
    if fmt == "reel":
        platforms += [p for p in kit.get("reels", {}).get("crosspost", []) if p in enabled and p != "instagram"]
    return platforms


def empty_item(fmt: str, date: dt.date, time: str, platforms: List[str], kit: dict) -> dict:
    item = {
        "id": "",
        "date": date.isoformat(),
        "day": C.day_code(date),
        "time": time,
        "format": fmt,
        "platforms": platforms,
        "status": "planned",
        "pillar": "",
        "campaign": "",
        "title": "",
        "hook": "",
        "concept": "",
        "script": "",
        "caption": "",
        "cta": "",
        "hashtags": [],
        "creative_direction": "",
        "checklist": [{"task": task, "done": False} for task in checklist_for(fmt, kit.get("language"))],
        "thumbnail": "",
        "footage": [],
        "platform_variants": {},
        "notes": "",
        "revision": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "history": [],
    }
    if fmt == "email":
        item["subject"] = ""
        item["preview_text"] = ""
        item["checklist"] = [{"task": task, "done": False} for task in checklist_for("email", kit.get("language"))]
    if fmt == "reel":
        extra = [p for p in platforms if p != "instagram"]
        for platform in extra:
            item["checklist"].append({"task": (f"同步发布到 {C.PLATFORM_LABELS[platform]}（使用该平台的原生文案）" if C.is_zh(kit.get("language")) else f"Cross-post to {C.PLATFORM_LABELS[platform]} with native caption"), "done": False})
            item["platform_variants"][platform] = {
                "time": kit["schedule"].get("platform_times", {}).get(platform, time),
                "caption": "",
            }
    return item


def assign_ids_and_times(plan: dict, kit: dict, retime: bool) -> None:
    compact = plan["week"].replace("-", "")
    counters: Dict[tuple, int] = {}
    for item in sorted(plan["items"], key=lambda it: (it["date"], C.FORMATS.index(it["format"]))):
        key = (item["day"], item["format"])
        index = counters.get(key, 0)
        counters[key] = index + 1
        if retime:
            item["time"] = slot_time(kit, item["format"], item["day"], index)
        if not item.get("id"):
            item["id"] = f"{compact}-{item['day']}-{item['format']}{index + 1}"
    sort_items(plan)


def sort_items(plan: dict) -> None:
    plan["items"].sort(key=lambda it: (it["date"], it.get("time", ""), C.FORMATS.index(it["format"]) if it["format"] in C.FORMATS else 9))


def balance_days(plan: dict, monday: dt.date) -> None:
    """Enforce the max-items-per-day limit by moving the most movable items to the lightest days."""
    def load() -> Dict[str, List[dict]]:
        by_day: Dict[str, List[dict]] = {d: [] for d in C.DAYS}
        for item in plan["items"]:
            by_day[item["day"]].append(item)
        return by_day

    for _ in range(100):
        by_day = load()
        heavy = [d for d in C.DAYS if len(by_day[d]) > C.MAX_PER_DAY]
        if not heavy:
            return
        day = heavy[0]
        candidates = sorted(by_day[day], key=lambda it: PRIORITY_TO_MOVE.index(it["format"]))
        mover = candidates[0]
        target = min(C.DAYS, key=lambda d: (len(by_day[d]), C.DAYS.index(d)))
        new_date = monday + dt.timedelta(days=C.DAYS.index(target))
        mover["date"], mover["day"] = new_date.isoformat(), target


def build_week(monday: dt.date, mix: Dict[str, int], kit: dict, theme: str, goals: List[str]) -> dict:
    plan = {
        "schema": SCHEMA,
        "week": C.week_label(monday),
        "start_date": monday.isoformat(),
        "end_date": (monday + dt.timedelta(days=6)).isoformat(),
        "timezone": kit.get("timezone", ""),
        "language": kit.get("language") or "en",
        "brand": kit.get("brand_name", ""),
        "handle": kit.get("handle", ""),
        "theme": theme,
        "goals": goals,
        "campaigns": [],
        "frequency": {"mix": mix, "total": sum(mix.values())},
        "items": [],
        "removed": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    preferred = kit["schedule"].get("preferred_days", {})
    for fmt in C.FORMATS:
        for day in distribute(mix.get(fmt, 0), preferred.get(fmt, list(C.DAYS))):
            date = monday + dt.timedelta(days=C.DAYS.index(day))
            plan["items"].append(empty_item(fmt, date, "", platforms_for(fmt, kit), kit))
    balance_days(plan, monday)
    assign_ids_and_times(plan, kit, retime=True)
    for item in plan["items"]:
        for platform, variant in item["platform_variants"].items():
            variant.setdefault("time", item["time"])
    return plan


# --------------------------------------------------------------------------- loading and editing

def load_plan(path: str) -> dict:
    plan = C.load_json(Path(path))
    if not isinstance(plan, dict) or "items" not in plan:
        C.die(f"{path} does not look like a week plan (no 'items' list)")
    plan.setdefault("removed", [])
    return plan


def save_plan(path: str, plan: dict) -> None:
    plan["updated_at"] = now_iso()
    sort_items(plan)
    C.save_json(Path(path), plan)


def find_item(plan: dict, item_id: str) -> dict:
    for item in plan["items"]:
        if item.get("id") == item_id:
            return item
    known = ", ".join(it.get("id", "?") for it in plan["items"])
    C.die(f"No item with id '{item_id}'. Known ids: {known}")
    return {}  # unreachable


def parse_value(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def check_field_value(plan: dict, key: str, value) -> None:
    if key == "status" and value not in C.STATUSES:
        C.die(f"Status must be one of {', '.join(C.STATUSES)}")
    if key == "format" and value not in C.FORMATS:
        C.die(f"Format must be one of {', '.join(C.FORMATS)}")
    if key == "time" and not C.valid_time(value):
        C.die(f"Time '{value}' must be HH:MM (24h)")
    if key == "day" and value not in C.DAYS:
        C.die(f"Day must be one of {', '.join(C.DAYS)}")
    if key == "date":
        try:
            date = dt.date.fromisoformat(value)
        except (TypeError, ValueError):
            C.die(f"Date '{value}' must be YYYY-MM-DD")
        if not (plan["start_date"] <= date.isoformat() <= plan["end_date"]):
            C.die(f"Date {value} is outside this week ({plan['start_date']} to {plan['end_date']})")


def apply_changes(plan: dict, item_id: str, changes: dict, note: str = "") -> dict:
    item = find_item(plan, item_id)
    changes = {k: v for k, v in changes.items() if k != "id"}
    bad = sorted(set(changes) & PROTECTED_FIELDS)
    if bad:
        C.die(f"These fields are managed by the tool and cannot be set: {', '.join(bad)}")
    for key, value in changes.items():
        check_field_value(plan, key, value)
    monday = dt.date.fromisoformat(plan["start_date"])
    if "day" in changes and "date" not in changes:
        changes["date"] = (monday + dt.timedelta(days=C.DAYS.index(changes["day"]))).isoformat()
    if "date" in changes:
        changes["day"] = C.day_code(dt.date.fromisoformat(changes["date"]))
    changed = {k: v for k, v in changes.items() if item.get(k) != v}
    if not changed:
        return item
    item.setdefault("history", []).append({
        "revision": item.get("revision", 1),
        "at": now_iso(),
        "note": note,
        "previous": {k: copy.deepcopy(item.get(k)) for k in changed},
    })
    item["history"] = item["history"][-HISTORY_LIMIT:]
    item.update(copy.deepcopy(changed))
    item["revision"] = item.get("revision", 1) + 1
    item["updated_at"] = now_iso()
    return item


def cmd_new(args) -> None:
    workspace = C.workspace_dir(args.workspace)
    kit, kit_path = C.load_brand_kit(workspace, args.brand_kit)
    monday = C.monday_of(args.week or (dt.date.today() + dt.timedelta(days=7 - dt.date.today().weekday())).isoformat())
    mix = resolve_mix(args.preset, args.mix, kit)
    goals = [g.strip() for g in (args.goals or "").split(";") if g.strip()]
    plan = build_week(monday, mix, kit, args.theme or "", goals)
    out = Path(args.out) if args.out else workspace / "weeks" / f"{plan['week']}.json"
    if out.exists() and not args.force:
        C.die(f"{out} already exists. Edit it with 'update', or pass --force to overwrite the whole week.")
    C.save_json(out, plan)
    if kit_path is None:
        C.warn("No brand kit found; used neutral default posting times. Run library.py status.")
    C.print_json({"created": str(out), "week": plan["week"], "items": len(plan["items"]), "mix": mix,
                  "ids": [f"{it['id']} {it['time']}" for it in plan["items"]]})


def cmd_show(args) -> None:
    plan = load_plan(args.plan)
    item = copy.deepcopy(find_item(plan, args.id))
    if not args.with_history:
        item.pop("history", None)
    C.print_json(item)


def cmd_update(args) -> None:
    plan = load_plan(args.plan)
    patches: List[dict] = []
    if args.patch:
        data = C.load_json(Path(args.patch))
        if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
            data = data["items"]
        if isinstance(data, list):
            patches = data
        elif isinstance(data, dict):
            if not args.id and "id" not in data:
                C.die("A single-object patch needs --id or an 'id' field")
            patches = [dict(data, id=data.get("id", args.id))]
        else:
            C.die("Patch file must be a JSON object or a list of objects")
    if args.set:
        if not args.id:
            C.die("--set needs --id")
        fields = {}
        for pair in args.set:
            if "=" not in pair:
                C.die(f"--set expects field=value, got '{pair}'")
            key, raw = pair.split("=", 1)
            fields[key.strip()] = parse_value(raw)
        patches.append(dict(fields, id=args.id))
    if not patches:
        C.die("Nothing to update: pass --patch FILE or --id ID --set field=value")
    updated = []
    for patch in patches:
        if "id" not in patch:
            C.die("Every patch in a list needs an 'id'")
        item = apply_changes(plan, patch["id"], patch, args.note or "")
        updated.append(f"{item['id']} (rev {item['revision']})")
    save_plan(args.plan, plan)
    C.print_json({"updated": updated, "untouched": len(plan["items"]) - len(updated)})


def cmd_revert(args) -> None:
    plan = load_plan(args.plan)
    item = find_item(plan, args.id)
    if not item.get("history"):
        C.die(f"{args.id} has no earlier revision to go back to")
    last = item["history"].pop()
    item.update(copy.deepcopy(last["previous"]))
    item["revision"] = last.get("revision", max(1, item.get("revision", 2) - 1))
    item["updated_at"] = now_iso()
    save_plan(args.plan, plan)
    C.print_json({"reverted": args.id, "restored_fields": sorted(last["previous"]), "revision": item["revision"]})


def cmd_set_status(args) -> None:
    plan = load_plan(args.plan)
    item = apply_changes(plan, args.id, {"status": args.status}, args.note or f"status -> {args.status}")
    problems = missing_for_status(item, args.status)
    save_plan(args.plan, plan)
    result = {"id": item["id"], "status": item["status"]}
    if problems:
        result["warning"] = f"Marked {args.status} but missing: {', '.join(problems)}"
    C.print_json(result)


def cmd_move(args) -> None:
    plan = load_plan(args.plan)
    changes = {}
    if args.date:
        changes["date"] = args.date
    if args.day:
        changes["day"] = args.day
    if args.time:
        changes["time"] = args.time
    if not changes:
        C.die("Pass --day, --date and/or --time")
    item = apply_changes(plan, args.id, changes, args.note or "moved")
    day_count = sum(1 for it in plan["items"] if it["day"] == item["day"])
    save_plan(args.plan, plan)
    result = {"id": item["id"], "date": item["date"], "day": item["day"], "time": item["time"]}
    if day_count > C.MAX_PER_DAY:
        result["warning"] = f"{C.DAY_NAMES[item['day']]} now has {day_count} items (limit {C.MAX_PER_DAY})"
    C.print_json(result)


def cmd_add(args) -> None:
    plan = load_plan(args.plan)
    workspace = C.workspace_dir(args.workspace)
    kit, _ = C.load_brand_kit(workspace, args.brand_kit)
    if len(plan["items"]) >= C.MAX_PER_WEEK:
        C.die(f"This week already has {C.MAX_PER_WEEK} items")
    monday = dt.date.fromisoformat(plan["start_date"])
    date = monday + dt.timedelta(days=C.DAYS.index(args.day))
    same = [it for it in plan["items"] if it["day"] == args.day and it["format"] == args.format]
    time = args.time or slot_time(kit, args.format, args.day, len(same))
    if not C.valid_time(time):
        C.die(f"Time '{time}' must be HH:MM")
    item = empty_item(args.format, date, time, platforms_for(args.format, kit), kit)
    compact = plan["week"].replace("-", "")
    existing = {it["id"] for it in plan["items"]} | {it["id"] for it in plan.get("removed", [])}
    n = len(same) + 1
    while f"{compact}-{args.day}-{args.format}{n}" in existing:
        n += 1
    item["id"] = f"{compact}-{args.day}-{args.format}{n}"
    if args.title:
        item["title"] = args.title
    plan["items"].append(item)
    plan["frequency"]["total"] = len(plan["items"])
    save_plan(args.plan, plan)
    warning = None
    if sum(1 for it in plan["items"] if it["day"] == args.day) > C.MAX_PER_DAY:
        warning = f"{C.DAY_NAMES[args.day]} now has more than {C.MAX_PER_DAY} items"
    C.print_json({"added": item["id"], "time": time, "warning": warning})


def cmd_remove(args) -> None:
    plan = load_plan(args.plan)
    item = find_item(plan, args.id)
    plan["items"].remove(item)
    item["removed_at"] = now_iso()
    plan.setdefault("removed", []).append(item)
    plan["frequency"]["total"] = len(plan["items"])
    save_plan(args.plan, plan)
    C.print_json({"removed": args.id, "restore_with": f"plan_tool.py restore {args.plan} --id {args.id}"})


def cmd_restore(args) -> None:
    plan = load_plan(args.plan)
    for item in plan.get("removed", []):
        if item.get("id") == args.id:
            plan["removed"].remove(item)
            item.pop("removed_at", None)
            plan["items"].append(item)
            plan["frequency"]["total"] = len(plan["items"])
            save_plan(args.plan, plan)
            C.print_json({"restored": args.id})
            return
    C.die(f"No removed item with id '{args.id}'")


# --------------------------------------------------------------------------- validation

def is_filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def missing_for_status(item: dict, status: str) -> List[str]:
    if status == "planned":
        return [] if is_filled(item.get("title")) else ["title"]
    needed = list(REQUIRED_FIELDS.get(item.get("format", ""), []))
    if status in ("ready", "published"):
        needed.append("creative_direction")
    missing = [field for field in needed if not is_filled(item.get(field))]
    if status in ("ready", "published"):
        open_tasks = [c.get("task") for c in item.get("checklist", []) if not c.get("done")]
        if open_tasks:
            missing.append(f"{len(open_tasks)} unchecked checklist task(s)")
    return missing


def validate_plan(plan: dict) -> dict:
    errors: List[str] = []
    warnings: List[str] = []
    items = plan.get("items", [])
    try:
        start = dt.date.fromisoformat(plan["start_date"])
        end = dt.date.fromisoformat(plan["end_date"])
        if start.weekday() != 0 or (end - start).days != 6:
            errors.append("start_date must be a Monday and end_date the following Sunday")
    except (KeyError, ValueError):
        errors.append("Plan needs start_date and end_date as YYYY-MM-DD")
        start = end = None
    if plan.get("schema") != SCHEMA:
        warnings.append(f"schema is '{plan.get('schema')}', expected '{SCHEMA}'")
    if not plan.get("timezone"):
        warnings.append("No timezone set; publishing times are ambiguous. Set brand kit 'timezone'.")
    if len(items) > C.MAX_PER_WEEK:
        errors.append(f"{len(items)} items; the weekly maximum is {C.MAX_PER_WEEK}")

    seen = set()
    per_day: Dict[str, int] = {d: 0 for d in C.DAYS}
    slots: Dict[tuple, str] = {}
    for item in items:
        iid = item.get("id") or "(no id)"
        if iid in seen:
            errors.append(f"Duplicate id {iid}")
        seen.add(iid)
        fmt = item.get("format")
        if fmt not in C.FORMATS:
            errors.append(f"{iid}: unknown format '{fmt}'")
            continue
        if item.get("status") not in C.STATUSES:
            errors.append(f"{iid}: unknown status '{item.get('status')}'")
        if not C.valid_time(item.get("time", "")):
            errors.append(f"{iid}: time '{item.get('time')}' is not HH:MM")
        try:
            date = dt.date.fromisoformat(item.get("date", ""))
            if start and not (start <= date <= end):
                errors.append(f"{iid}: date {date} is outside the week")
            if item.get("day") != C.day_code(date):
                errors.append(f"{iid}: day '{item.get('day')}' does not match date {date}")
            per_day[C.day_code(date)] += 1
        except ValueError:
            errors.append(f"{iid}: date '{item.get('date')}' is not YYYY-MM-DD")
        for platform in item.get("platforms", []):
            key = (item.get("date"), item.get("time"), platform)
            if key in slots and fmt != "story":
                warnings.append(f"{iid} and {slots[key]} publish on {platform} at the same date and time")
            slots[key] = iid
        missing = missing_for_status(item, item.get("status", "planned"))
        if missing:
            warnings.append(f"{iid} is '{item.get('status')}' but missing: {', '.join(missing)}")
    for day, count in per_day.items():
        if count > C.MAX_PER_DAY:
            errors.append(f"{C.DAY_NAMES[day]} has {count} items (limit {C.MAX_PER_DAY})")
    for a, b, score in dedupe.duplicates_within([it for it in items if is_filled(it.get("title")) or is_filled(it.get("hook"))]):
        warnings.append(f"{a} and {b} look like the same idea (similarity {score}); vary one of them")

    counts = {
        "total": len(items),
        "by_status": {s: sum(1 for it in items if it.get("status") == s) for s in C.STATUSES},
        "by_format": {f: sum(1 for it in items if it.get("format") == f) for f in C.FORMATS},
        "by_day": per_day,
    }
    return {"ok": not errors, "errors": errors, "warnings": warnings, "counts": counts}


def cmd_validate(args) -> None:
    plan = load_plan(args.plan)
    report = validate_plan(plan)
    if args.strict and report["warnings"]:
        report["ok"] = False
    C.print_json(report)
    sys.exit(0 if report["ok"] else 1)


# --------------------------------------------------------------------------- summary / export

def cmd_summary(args) -> None:
    plan = load_plan(args.plan)
    items = plan["items"]
    published = sum(1 for it in items if it["status"] == "published")
    ready = sum(1 for it in items if it["status"] == "ready")
    print(f"{plan.get('brand') or 'Content plan'} | {plan['week']} ({plan['start_date']} to {plan['end_date']})"
          + (f" | theme: {plan['theme']}" if plan.get("theme") else ""))
    print(f"Progress: {published}/{len(items)} published, {ready} ready")
    print()
    print(f"{'Day':<4} {'Time':<6} {'Format':<9} {'Status':<10} {'Id':<24} Title")
    print("-" * 96)
    for it in items:
        title = (it.get("title") or "(untitled)").replace("\n", " ")
        print(f"{it['day']:<4} {it['time']:<6} {C.FORMAT_LABELS.get(it['format'], it['format']):<9} "
              f"{it['status']:<10} {it['id']:<24} {title[:60]}")


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        lines = []
        for i, entry in enumerate(value, 1):
            if isinstance(entry, dict):
                lines.append(f"{i}. " + " | ".join(f"{k}: {v}" for k, v in entry.items() if v not in ("", None)))
            else:
                lines.append(f"{i}. {entry}")
        return "\n".join(lines)
    if isinstance(value, dict):
        return "\n".join(f"{k}: {as_text(v)}" for k, v in value.items())
    return str(value)


def export_markdown(plan: dict) -> str:
    zh = C.is_zh(plan.get("language"))
    days = C.L10N_ZH["days"] if zh else {d: C.DAY_NAMES[d] for d in C.DAYS}
    formats = C.L10N_ZH["formats"] if zh else C.FORMAT_LABELS
    statuses = C.L10N_ZH["statuses"] if zh else {s: s for s in C.STATUSES}
    platforms = C.L10N_ZH["platforms"] if zh else C.PLATFORM_LABELS
    L = (lambda en, cn: cn) if zh else (lambda en, cn: en)
    out = io.StringIO()
    out.write(f"# {L('Content plan', '内容计划')} {plan['week']}\n\n")
    out.write(f"{plan['start_date']} {L('to', '至')} {plan['end_date']}")
    if plan.get("timezone"):
        out.write(f" ({L('times in', '时间：')} {plan['timezone']})")
    out.write("\n\n")
    if plan.get("theme"):
        out.write(f"**{L('Theme', '主题')}:** {plan['theme']}\n\n")
    if plan.get("goals"):
        out.write(f"**{L('Goals', '目标')}:** " + "; ".join(plan["goals"]) + "\n\n")
    for day in C.DAYS:
        day_items = [it for it in plan["items"] if it["day"] == day]
        if not day_items:
            continue
        out.write(f"## {days[day]} {day_items[0]['date']}\n\n")
        for it in day_items:
            out.write(f"### {it['time']} {formats[it['format']]}: {it.get('title') or L('(untitled)', '（未命名）')}\n\n")
            out.write(f"`{it['id']}` | {L('status', '状态')}: **{statuses.get(it['status'], it['status'])}** | {L('platforms', '平台')}: "
                      f"{', '.join(platforms.get(p, p) for p in it.get('platforms', []))}\n\n")
            fields = [(L("Pillar", "内容支柱"), "pillar"), (L("Campaign", "活动"), "campaign")]
            if it["format"] == "email":
                fields += [(L("Subject", "邮件标题"), "subject"), (L("Preview text", "预览文字"), "preview_text")]
            fields += [(L("Hook", "开头钩子"), "hook"), (L("Concept", "创意概念"), "concept"),
                       (L("Script / outline", "脚本 / 大纲"), "script"), (L("Caption", "文案"), "caption"),
                       (L("CTA", "行动号召"), "cta"), (L("Creative direction", "创意方向"), "creative_direction")]
            for label_text, key in fields:
                text = as_text(it.get(key))
                if text.strip():
                    out.write(f"**{label_text}:**\n{text}\n\n")
            if it.get("hashtags"):
                out.write(f"**{L('Hashtags', '话题标签')}:** " + " ".join(it["hashtags"]) + "\n\n")
            for platform, variant in (it.get("platform_variants") or {}).items():
                bits = [f"{k}: {v}" for k, v in variant.items() if v]
                if bits:
                    out.write(f"**{platforms.get(platform, platform)}:** " + " | ".join(bits) + "\n\n")
            if it.get("checklist"):
                out.write(f"**{L('Production checklist', '制作清单')}:**\n")
                for task in it["checklist"]:
                    out.write(f"- [{'x' if task.get('done') else ' '}] {task.get('task')}\n")
                out.write("\n")
    return out.getvalue()

def export_csv(plan: dict) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "day", "time", "format", "platforms", "status", "title", "hook",
                     "caption", "cta", "hashtags", "pillar", "campaign", "id"])
    for it in plan["items"]:
        caption = it.get("caption") if it["format"] != "email" else it.get("preview_text", "")
        hook = it.get("hook") if it["format"] != "email" else it.get("subject", "")
        writer.writerow([it["date"], it["day"], it["time"], it["format"], " ".join(it.get("platforms", [])),
                         it["status"], it.get("title", ""), as_text(hook), as_text(caption), as_text(it.get("cta")),
                         " ".join(it.get("hashtags", [])), it.get("pillar", ""), it.get("campaign", ""), it["id"]])
    return out.getvalue()


def ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def ics_fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, current = [], b""
    for ch in line:
        encoded = ch.encode("utf-8")
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += encoded
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def export_ics(plan: dict) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tz = plan.get("timezone") or ""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AI Content Studio//Week Plan//EN", "CALSCALE:GREGORIAN"]
    if tz:
        lines.append(f"X-WR-TIMEZONE:{tz}")
    for it in plan["items"]:
        start = dt.datetime.fromisoformat(f"{it['date']}T{it['time']}")
        end = start + dt.timedelta(minutes=30)
        fmt = "%Y%m%dT%H%M%S"
        dtstart = f"DTSTART;TZID={tz}:{start.strftime(fmt)}" if tz else f"DTSTART:{start.strftime(fmt)}"
        dtend = f"DTEND;TZID={tz}:{end.strftime(fmt)}" if tz else f"DTEND:{end.strftime(fmt)}"
        description = "\n".join(filter(None, [
            f"Status: {it['status']}",
            f"Hook: {as_text(it.get('subject') if it['format'] == 'email' else it.get('hook'))}",
            f"CTA: {as_text(it.get('cta'))}",
            "",
            as_text(it.get("caption") if it["format"] != "email" else it.get("preview_text")),
        ]))
        lines += [
            "BEGIN:VEVENT",
            f"UID:{it['id']}@ai-content-studio",
            f"DTSTAMP:{stamp}",
            dtstart,
            dtend,
            ics_fold("SUMMARY:" + ics_escape(f"[{C.FORMAT_LABELS[it['format']]}] {it.get('title') or '(untitled)'}")),
            ics_fold("DESCRIPTION:" + ics_escape(description)),
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def cmd_export(args) -> None:
    plan = load_plan(args.plan)
    if args.format == "md":
        text, default_ext = export_markdown(plan), ".md"
    elif args.format == "csv":
        text, default_ext = export_csv(plan), ".csv"
    else:
        text, default_ext = export_ics(plan), ".ics"
    out = Path(args.out) if args.out else Path(args.plan).with_suffix(default_ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if args.format == "csv" else "utf-8"
    newline = "" if args.format in ("csv", "ics") else None
    with open(out, "w", encoding=encoding, newline=newline) as handle:
        handle.write(text)
    C.print_json({"exported": str(out), "format": args.format, "bytes": out.stat().st_size})


# --------------------------------------------------------------------------- render calendar

def thumbnail_data_uri(path: Path, max_width: int = 360) -> Optional[str]:
    suffix = path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(suffix)
    if not mime:
        return None
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.width > max_width:
                img = img.resize((max_width, round(img.height * max_width / img.width)))
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=82)
            return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except ImportError:
        if path.stat().st_size > 400_000:
            C.warn(f"Pillow missing and {path.name} is large; skipping embed")
            return None
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception as exc:  # unreadable image
        C.warn(f"Could not read thumbnail {path}: {exc}")
        return None


def cmd_render(args) -> None:
    plan = load_plan(args.plan)
    workspace = C.workspace_dir(args.workspace)
    kit, _ = C.load_brand_kit(workspace, args.brand_kit)
    template_path = C.ASSETS_DIR / "calendar_template.html"
    template = C.read_text(template_path)
    view = copy.deepcopy(plan)
    view.pop("removed", None)
    plan_dir = Path(args.plan).resolve().parent
    embedded = 0
    for item in view["items"]:
        item.pop("history", None)
        thumb = item.get("thumbnail") or ""
        if thumb and not thumb.startswith(("http://", "https://", "data:")):
            resolved = C.resolve_relative(thumb, plan_dir, workspace, workspace / "media")
            uri = thumbnail_data_uri(resolved) if resolved and not args.no_embed else None
            item["thumbnail"] = uri or ""
            embedded += 1 if uri else 0
    brand = {
        "name": kit.get("brand_name") or plan.get("brand") or "",
        "handle": kit.get("handle") or plan.get("handle") or "",
        "primary": kit["colors"].get("primary"),
        "accent": kit["colors"].get("accent"),
        "language": plan.get("language") or kit.get("language") or "en",
    }
    data = json.dumps(view, ensure_ascii=False).replace("</", "<\\/")
    brand_json = json.dumps(brand, ensure_ascii=False).replace("</", "<\\/")
    title = "内容日历" if C.is_zh(brand["language"]) else "Content Calendar"
    html = (template.replace("__PAGE_TITLE__", title)
            .replace("/*__PLAN_JSON__*/null", data)
            .replace("/*__BRAND_JSON__*/null", brand_json))
    out = Path(args.out) if args.out else Path(args.plan).with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    C.print_json({"calendar": str(out), "items": len(view["items"]), "thumbnails_embedded": embedded,
                  "bytes": out.stat().st_size})


# --------------------------------------------------------------------------- CLI

def main() -> None:
    C.setup_stdio()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def with_workspace(p):
        p.add_argument("--workspace", help="Content studio folder (default $CONTENT_STUDIO_DIR or ./content-studio)")
        p.add_argument("--brand-kit", help="Explicit brand-kit.json path")
        return p

    p = with_workspace(sub.add_parser("new", help="Create a week skeleton"))
    p.add_argument("--week", help="2026-W48 or any date in that week (default: next week)")
    p.add_argument("--preset", choices=list(C.PRESETS) + ["custom"])
    p.add_argument("--mix", help="Custom mix, e.g. reel=4,story=7,carousel=2,email=1")
    p.add_argument("--theme", help="Weekly theme or campaign focus")
    p.add_argument("--goals", help="Goals separated by ';'")
    p.add_argument("--out", help="Output path (default workspace/weeks/WEEK.json)")
    p.add_argument("--force", action="store_true", help="Overwrite an existing week file")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("show", help="Print one item")
    p.add_argument("plan")
    p.add_argument("--id", required=True)
    p.add_argument("--with-history", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("update", help="Update one item or apply patches")
    p.add_argument("plan")
    p.add_argument("--id")
    p.add_argument("--patch", help="JSON file: one object (with --id or 'id') or a list of objects with 'id'")
    p.add_argument("--set", action="append", help="field=value (value may be JSON). Repeatable.")
    p.add_argument("--note", help="Why it changed (kept in history)")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("revert", help="Undo the last update of one item")
    p.add_argument("plan")
    p.add_argument("--id", required=True)
    p.set_defaults(func=cmd_revert)

    p = sub.add_parser("set-status", help="Change status of one item")
    p.add_argument("plan")
    p.add_argument("--id", required=True)
    p.add_argument("--status", required=True, choices=C.STATUSES)
    p.add_argument("--note")
    p.set_defaults(func=cmd_set_status)

    p = sub.add_parser("move", help="Move one item")
    p.add_argument("plan")
    p.add_argument("--id", required=True)
    p.add_argument("--day", choices=C.DAYS)
    p.add_argument("--date")
    p.add_argument("--time")
    p.add_argument("--note")
    p.set_defaults(func=cmd_move)

    p = with_workspace(sub.add_parser("add", help="Add one empty slot"))
    p.add_argument("plan")
    p.add_argument("--format", required=True, choices=C.FORMATS)
    p.add_argument("--day", required=True, choices=C.DAYS)
    p.add_argument("--time")
    p.add_argument("--title")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("remove", help="Remove one item (restorable)")
    p.add_argument("plan")
    p.add_argument("--id", required=True)
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("restore", help="Restore a removed item")
    p.add_argument("plan")
    p.add_argument("--id", required=True)
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("validate", help="Validate a plan")
    p.add_argument("plan")
    p.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("summary", help="Overview table")
    p.add_argument("plan")
    p.set_defaults(func=cmd_summary)

    p = with_workspace(sub.add_parser("render", help="Build the HTML calendar"))
    p.add_argument("plan")
    p.add_argument("--out")
    p.add_argument("--no-embed", action="store_true", help="Do not embed local thumbnail images")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("export", help="Export md / csv / ics")
    p.add_argument("plan")
    p.add_argument("--format", required=True, choices=["md", "csv", "ics"])
    p.add_argument("--out")
    p.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
