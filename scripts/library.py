#!/usr/bin/env python3
"""AI Content Studio - brand memory and content library.

Workspace layout (created by `init`):
  content-studio/
    brand/brand-profile.md   niche, audience, voice, pillars, boundaries
    brand/brand-kit.json     colors, fonts, logo, handle, schedule defaults
    brand/fonts/             optional .ttf/.otf brand fonts
    brand/assets/            logo and other brand images
    library.json             planned + published items, idea backlog, media, learnings
    weeks/                   week plans (plan_tool.py)
    media/                   footage and images to reuse
    exports/                 calendars, carousels, rendered videos

Commands
  init             Create the workspace (never overwrites existing files)
  status           Is the brand configured? What is in the library?
  recent           Compact memory digest to read before planning
  add-week         Register / sync a week plan into the library
  check            Find repeats of new ideas in the library
  add-idea         Save an idea to the backlog
  ideas            List backlog ideas
  log-performance  Store metrics for a published item (or import a CSV)
  top              Best performers by a metric
  add-media        Register footage / photos / brand assets
  media            List registered media
  add-learning     Save an insight (what worked, what did not)
  bake             Build a copy of the skill ZIP with this brand baked in
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402
import dedupe  # noqa: E402

LIBRARY_SCHEMA = "ai-content-studio/library@1"
TEMPLATE_MARKER = "<!-- ACS:TEMPLATE"
METRICS = ("views", "reach", "likes", "comments", "saves", "shares", "follows", "clicks",
           "watch_time_avg", "retention_3s", "open_rate", "click_rate")


def today() -> str:
    return dt.date.today().isoformat()


def library_path(workspace: Path) -> Path:
    return workspace / "library.json"


def empty_library() -> dict:
    return {"schema": LIBRARY_SCHEMA, "items": [], "ideas": [], "media": [], "learnings": [], "updated_at": today()}


def load_library(workspace: Path, create: bool = False) -> dict:
    path = library_path(workspace)
    if not path.exists():
        if create:
            return empty_library()
        C.die(f"No library at {path}. Run: python library.py init --workspace {workspace}")
    data = C.load_json(path)
    for key in ("items", "ideas", "media", "learnings"):
        data.setdefault(key, [])
    return data


def save_library(workspace: Path, data: dict) -> None:
    data["updated_at"] = today()
    C.save_json(library_path(workspace), data)


def profile_configured(path: Optional[Path]) -> bool:
    if path is None or not path.exists():
        return False
    text = C.read_text(path)
    return TEMPLATE_MARKER not in text and len(text.strip()) > 200


# --------------------------------------------------------------------------- init / status

def cmd_init(args) -> None:
    workspace = C.workspace_dir(args.workspace)
    created: List[str] = []
    for sub in ("brand/fonts", "brand/assets", "weeks", "media", "exports"):
        folder = workspace / sub
        if not folder.exists():
            folder.mkdir(parents=True)
            created.append(str(folder))
    for name in ("brand-profile.md", "brand-kit.json"):
        target = workspace / "brand" / name
        if target.exists():
            continue
        baked = C.BAKED_BRAND_DIR / name
        source = baked if baked.exists() else C.TEMPLATES_DIR / name
        shutil.copyfile(source, target)
        created.append(f"{target} (from {'baked brand' if source == baked else 'template'})")
    baked_fonts = C.BAKED_BRAND_DIR / "fonts"
    if baked_fonts.exists():
        for font in baked_fonts.iterdir():
            target = workspace / "brand" / "fonts" / font.name
            if font.is_file() and not target.exists():
                shutil.copyfile(font, target)
                created.append(str(target))
    lib = library_path(workspace)
    if not lib.exists():
        C.save_json(lib, empty_library())
        created.append(str(lib))
    C.print_json({"workspace": str(workspace), "created": created or "nothing (already set up)"})


def cmd_status(args) -> None:
    workspace = C.workspace_dir(args.workspace)
    profile = C.brand_file("brand-profile.md", workspace)
    kit_path = C.brand_file("brand-kit.json", workspace)
    lib = load_library(workspace, create=True) if workspace.exists() else empty_library()
    weeks = sorted((workspace / "weeks").glob("*.json")) if (workspace / "weeks").exists() else []
    report = {
        "workspace": str(workspace),
        "workspace_exists": workspace.exists(),
        "brand_profile": str(profile) if profile else None,
        "brand_profile_configured": profile_configured(profile),
        "brand_kit": str(kit_path) if kit_path else None,
        "brand_kit_configured": C.brand_kit_configured(kit_path),
        "baked_brand_in_skill": (C.BAKED_BRAND_DIR / "brand-profile.md").exists(),
        "library": {
            "items": len(lib["items"]),
            "published": sum(1 for it in lib["items"] if it.get("status") == "published"),
            "with_performance": sum(1 for it in lib["items"] if it.get("performance")),
            "ideas_backlog": sum(1 for idea in lib["ideas"] if not idea.get("used_in")),
            "media": len(lib["media"]),
            "learnings": len(lib["learnings"]),
        },
        "latest_week_plan": str(weeks[-1]) if weeks else None,
    }
    next_steps = []
    if not report["workspace_exists"]:
        next_steps.append("Run library.py init to create the workspace")
    if not report["brand_profile_configured"]:
        next_steps.append("Run brand onboarding (references/brand-memory.md) and write brand/brand-profile.md")
    if not report["brand_kit_configured"]:
        next_steps.append("Fill brand/brand-kit.json (brand_name, handle, language, timezone, colors, fonts)")
    report["next_steps"] = next_steps or ["Brand memory is ready"]
    C.print_json(report)


# --------------------------------------------------------------------------- weeks and ideas

def summarize_concept(text) -> str:
    text = text if isinstance(text, str) else str(text or "")
    text = " ".join(text.split())
    return text[:220] + ("..." if len(text) > 220 else "")


def cmd_add_week(args) -> None:
    workspace = C.workspace_dir(args.workspace)
    lib = load_library(workspace, create=True)
    plan = C.load_json(Path(args.plan))
    index = {it["id"]: it for it in lib["items"]}
    added = updated = 0
    for item in plan.get("items", []):
        record = {
            "id": item["id"],
            "week": plan.get("week"),
            "date": item.get("date"),
            "time": item.get("time"),
            "format": item.get("format"),
            "platforms": item.get("platforms", []),
            "pillar": item.get("pillar", ""),
            "campaign": item.get("campaign", ""),
            "title": item.get("title", ""),
            "hook": item.get("subject") if item.get("format") == "email" else item.get("hook", ""),
            "concept_summary": summarize_concept(item.get("concept", "")),
            "status": item.get("status", "planned"),
            "published_url": item.get("published_url", ""),
            "footage": item.get("footage", []),
            "repurposed_from": item.get("repurposed_from", ""),
        }
        if item["id"] in index:
            existing = index[item["id"]]
            existing.update({k: v for k, v in record.items()})
            updated += 1
        else:
            record["performance"] = {}
            lib["items"].append(record)
            index[item["id"]] = record
            added += 1
        for path in item.get("footage", []):
            for media in lib["media"]:
                if media.get("path") == path and item["id"] not in media.setdefault("used_in", []):
                    media["used_in"].append(item["id"])
    for idea in lib["ideas"]:
        if idea.get("planned_as") and idea["planned_as"] in index:
            idea["used_in"] = idea["planned_as"]
    lib["items"].sort(key=lambda it: (it.get("date") or "", it.get("time") or ""))
    save_library(workspace, lib)
    C.print_json({"week": plan.get("week"), "added": added, "updated": updated, "library_items": len(lib["items"])})


def within_weeks(record: dict, weeks: Optional[int]) -> bool:
    if not weeks:
        return True
    try:
        date = dt.date.fromisoformat(record.get("date") or "")
    except ValueError:
        return True
    return date >= dt.date.today() - dt.timedelta(weeks=weeks)


def corpus_from_library(lib: dict, weeks: Optional[int], exclude_ids: set) -> List[tuple]:
    corpus = []
    for record in lib["items"]:
        if record["id"] in exclude_ids or not within_weeks(record, weeks):
            continue
        corpus.append((f"{record['id']} [{record.get('status')}]", dedupe.item_text(record)))
    for idea in lib["ideas"]:
        corpus.append((f"idea:{idea['id']}", dedupe.item_text(idea)))
    return corpus


def cmd_check(args) -> None:
    workspace = C.workspace_dir(args.workspace)
    lib = load_library(workspace, create=True)
    threshold = args.threshold if args.threshold is not None else dedupe.DUPLICATE_THRESHOLD
    candidates: List[tuple] = []
    exclude: set = set()
    related: Dict[str, str] = {}
    if args.text:
        candidates = [("text", t) for t in args.text]
    elif args.plan:
        plan = C.load_json(Path(args.plan))
        exclude = {it["id"] for it in plan.get("items", [])}
        candidates = [(it["id"], dedupe.item_text(it)) for it in plan.get("items", []) if dedupe.item_text(it).strip()]
        related = {it["id"]: it["repurposed_from"] for it in plan.get("items", []) if it.get("repurposed_from")}
    elif args.ideas:
        data = C.load_json(Path(args.ideas))
        for i, entry in enumerate(data if isinstance(data, list) else data.get("ideas", [])):
            if isinstance(entry, str):
                candidates.append((f"idea{i + 1}", entry))
            else:
                candidates.append((entry.get("id", f"idea{i + 1}"), dedupe.item_text(entry)))
    else:
        C.die("Pass --text, --plan or --ideas")
    corpus = corpus_from_library(lib, args.weeks, exclude)
    results = []
    for cid, text in candidates:
        matches = dedupe.find_similar(text, corpus, threshold)
        source = related.get(cid)
        if source:  # a deliberate repurpose of an earlier post is not a repeat of it
            matches = [m for m in matches if m[0].split(" ")[0] != source]
        if matches:
            results.append({"candidate": cid, "text": text[:160], "similar_to": [
                {"ref": ref, "score": score} for ref, score in matches[:3]]})
    C.print_json({"checked": len(candidates), "compared_against": len(corpus), "threshold": threshold,
                  "possible_repeats": results})


def cmd_add_idea(args) -> None:
    workspace = C.workspace_dir(args.workspace)
    lib = load_library(workspace, create=True)
    idea_id = f"I{len(lib['ideas']) + 1:03d}"
    lib["ideas"].append({"id": idea_id, "title": args.title, "hook": args.hook or "", "pillar": args.pillar or "",
                         "format": args.format or "", "source": args.source or "", "added": today()})
    save_library(workspace, lib)
    C.print_json({"added": idea_id})


def cmd_ideas(args) -> None:
    lib = load_library(C.workspace_dir(args.workspace), create=True)
    ideas = [i for i in lib["ideas"] if not (args.unused and i.get("used_in"))]
    C.print_json(ideas)


# --------------------------------------------------------------------------- performance

def to_number(value):
    if value in (None, ""):
        return None
    text = str(value).strip().replace("%", "").replace(" ", "").replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def engagement_rate(perf: dict) -> Optional[float]:
    base = perf.get("reach") or perf.get("views")
    if not base:
        return None
    interactions = sum(perf.get(k) or 0 for k in ("likes", "comments", "saves", "shares"))
    return round(100 * interactions / base, 2)


def record_performance(lib: dict, item_id: str, metrics: Dict, notes: str, title: str = "") -> dict:
    record = next((it for it in lib["items"] if it["id"] == item_id), None)
    if record is None:
        if not title:
            C.die(f"No library item '{item_id}'. Add --title to log a post that was not planned here.")
        record = {"id": item_id, "title": title, "status": "published", "date": today(), "performance": {}}
        lib["items"].append(record)
    perf = record.setdefault("performance", {})
    perf.update({k: v for k, v in metrics.items() if v is not None})
    rate = engagement_rate(perf)
    if rate is not None:
        perf["engagement_rate"] = rate
    perf["logged_at"] = today()
    if notes:
        perf["notes"] = notes
    record["status"] = "published"
    return record


def cmd_log_performance(args) -> None:
    workspace = C.workspace_dir(args.workspace)
    lib = load_library(workspace, create=True)
    logged = []
    if args.csv:
        with open(args.csv, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                row = {k.strip().lower(): v for k, v in row.items() if k}
                if not row.get("id"):
                    continue
                metrics = {m: to_number(row.get(m)) for m in METRICS}
                record_performance(lib, row["id"], metrics, row.get("notes", ""), row.get("title", ""))
                logged.append(row["id"])
    else:
        if not args.id:
            C.die("Pass --id (or --csv)")
        metrics = {m: to_number(getattr(args, m)) for m in METRICS}
        record = record_performance(lib, args.id, metrics, args.notes or "", args.title or "")
        logged.append(record["id"])
    save_library(workspace, lib)
    C.print_json({"logged": logged})


def cmd_top(args) -> None:
    lib = load_library(C.workspace_dir(args.workspace), create=True)
    rows = [it for it in lib["items"] if it.get("performance", {}).get(args.metric) is not None]
    if args.format:
        rows = [it for it in rows if it.get("format") == args.format]
    rows.sort(key=lambda it: it["performance"][args.metric], reverse=True)
    C.print_json([{"id": it["id"], "format": it.get("format"), "title": it.get("title"), "hook": it.get("hook"),
                   "pillar": it.get("pillar"), args.metric: it["performance"][args.metric]} for it in rows[: args.n]])


# --------------------------------------------------------------------------- media + learnings

def cmd_add_media(args) -> None:
    workspace = C.workspace_dir(args.workspace)
    lib = load_library(workspace, create=True)
    path = Path(args.path).expanduser()
    try:
        stored = str(path.resolve().relative_to(workspace)).replace("\\", "/")
    except ValueError:
        stored = str(path)
    if any(m.get("path") == stored for m in lib["media"]):
        C.die(f"{stored} is already registered")
    media_id = f"M{len(lib['media']) + 1:03d}"
    lib["media"].append({
        "id": media_id, "path": stored, "kind": args.kind, "description": args.description or "",
        "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
        "exists": path.exists(), "added": today(), "used_in": [],
    })
    save_library(workspace, lib)
    C.print_json({"added": media_id, "path": stored, "file_found": path.exists()})


def cmd_media(args) -> None:
    lib = load_library(C.workspace_dir(args.workspace), create=True)
    media = lib["media"]
    if args.tag:
        media = [m for m in media if args.tag.lower() in [t.lower() for t in m.get("tags", [])]]
    if args.unused:
        media = [m for m in media if not m.get("used_in")]
    C.print_json(media)


def cmd_add_learning(args) -> None:
    workspace = C.workspace_dir(args.workspace)
    lib = load_library(workspace, create=True)
    lib["learnings"].append({"date": today(), "insight": args.insight, "source": args.source or ""})
    save_library(workspace, lib)
    C.print_json({"learnings": len(lib["learnings"])})


# --------------------------------------------------------------------------- recent digest

def cmd_recent(args) -> None:
    """A compact digest the assistant reads before generating new ideas."""
    workspace = C.workspace_dir(args.workspace)
    lib = load_library(workspace, create=True)
    recent = [it for it in lib["items"] if within_weeks(it, args.weeks)]
    print(f"# Library digest (last {args.weeks} weeks, {len(recent)} items)")
    pillars: Dict[str, int] = {}
    formats: Dict[str, int] = {}
    for it in recent:
        pillars[it.get("pillar") or "(none)"] = pillars.get(it.get("pillar") or "(none)", 0) + 1
        formats[it.get("format") or "?"] = formats.get(it.get("format") or "?", 0) + 1
    print("Pillars used: " + (", ".join(f"{k} {v}" for k, v in sorted(pillars.items(), key=lambda kv: -kv[1])) or "none"))
    print("Formats used: " + (", ".join(f"{k} {v}" for k, v in formats.items()) or "none"))
    print("\n## Already covered (do not repeat these angles)")
    for it in recent[-args.limit:]:
        perf = it.get("performance") or {}
        score = f" | ER {perf['engagement_rate']}%" if "engagement_rate" in perf else ""
        print(f"- {it.get('date')} {it.get('format')} [{it.get('pillar') or '-'}] {it.get('title')}"
              f" | hook: {it.get('hook') or '-'}{score}")
    scored = [it for it in lib["items"] if (it.get("performance") or {}).get("engagement_rate") is not None]
    if scored:
        scored.sort(key=lambda it: it["performance"]["engagement_rate"], reverse=True)
        print("\n## Best performers (reuse the pattern, not the idea)")
        for it in scored[:5]:
            p = it["performance"]
            print(f"- {it.get('format')} '{it.get('title')}' ER {p['engagement_rate']}%"
                  f" saves {p.get('saves', '-')} shares {p.get('shares', '-')} notes: {p.get('notes', '')}")
    unused = [i for i in lib["ideas"] if not i.get("used_in")]
    if unused:
        print("\n## Idea backlog (use these first when they fit the week)")
        for idea in unused[:15]:
            print(f"- {idea['id']} [{idea.get('pillar') or '-'}] {idea.get('title')} {('| ' + idea['hook']) if idea.get('hook') else ''}")
    unused_media = [m for m in lib["media"] if not m.get("used_in")]
    if unused_media:
        print("\n## Unused footage and assets")
        for m in unused_media[:15]:
            print(f"- {m['id']} {m['kind']} {m['path']} | {m.get('description', '')} | tags: {', '.join(m.get('tags', []))}")
    if lib["learnings"]:
        print("\n## Learnings")
        for learning in lib["learnings"][-10:]:
            print(f"- {learning['date']}: {learning['insight']}")


# --------------------------------------------------------------------------- bake

def cmd_bake(args) -> None:
    """Copy the skill, put this workspace's brand files into brand/, and zip it for re-upload."""
    workspace = C.workspace_dir(args.workspace)
    skill_dir = Path(args.skill_dir).resolve() if args.skill_dir else C.SKILL_DIR
    brand_src = workspace / "brand"
    profile = brand_src / "brand-profile.md"
    if not profile_configured(profile):
        C.die(f"{profile} is missing or still the template. Finish onboarding before baking.")
    out = Path(args.out).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / skill_dir.name
        shutil.copytree(skill_dir, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals", ".DS_Store"))
        target = staged / "brand"
        target.mkdir(exist_ok=True)
        for entry in brand_src.rglob("*"):
            if entry.is_file():
                dest = target / entry.relative_to(brand_src)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(entry, dest)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(staged.rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(staged.parent).as_posix())
    with zipfile.ZipFile(out) as archive:
        names = archive.namelist()
    ok = f"{skill_dir.name}/SKILL.md" in names and f"{skill_dir.name}/brand/brand-profile.md" in names
    C.print_json({"zip": str(out), "files": len(names), "size": C.human_size(out.stat().st_size), "verified": ok,
                  "next": "Kimi Work: upload this ZIP as a local skill, replacing the old one. Kimi Code: unzip it into ~/.agents/skills/ (replace the old folder)."})
    sys.exit(0 if ok else 1)


# --------------------------------------------------------------------------- CLI

def main() -> None:
    C.setup_stdio()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", help="Content studio folder (default $CONTENT_STUDIO_DIR or ./content-studio)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    class _Sub:
        """Every subcommand accepts --workspace."""
        def add_parser(self, name, **kwargs):
            return subparsers.add_parser(name, parents=[common], **kwargs)

    sub = _Sub()
    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("status").set_defaults(func=cmd_status)

    p = sub.add_parser("recent")
    p.add_argument("--weeks", type=int, default=8)
    p.add_argument("--limit", type=int, default=60)
    p.set_defaults(func=cmd_recent)

    p = sub.add_parser("add-week")
    p.add_argument("plan")
    p.set_defaults(func=cmd_add_week)

    p = sub.add_parser("check")
    p.add_argument("--text", action="append", help="Idea text to check (repeatable)")
    p.add_argument("--plan", help="Check every item of a week plan")
    p.add_argument("--ideas", help="JSON list of ideas (strings or objects)")
    p.add_argument("--weeks", type=int, help="Only compare with items from the last N weeks")
    p.add_argument("--threshold", type=float)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("add-idea")
    p.add_argument("--title", required=True)
    p.add_argument("--hook")
    p.add_argument("--pillar")
    p.add_argument("--format", choices=C.FORMATS)
    p.add_argument("--source")
    p.set_defaults(func=cmd_add_idea)

    p = sub.add_parser("ideas")
    p.add_argument("--unused", action="store_true")
    p.set_defaults(func=cmd_ideas)

    p = sub.add_parser("log-performance")
    p.add_argument("--id")
    p.add_argument("--title", help="Only for posts that are not in the library yet")
    p.add_argument("--csv", help="CSV with an 'id' column plus metric columns")
    p.add_argument("--notes")
    for metric in METRICS:
        p.add_argument(f"--{metric.replace('_', '-')}", dest=metric)
    p.set_defaults(func=cmd_log_performance)

    p = sub.add_parser("top")
    p.add_argument("--metric", default="engagement_rate", choices=list(METRICS) + ["engagement_rate"])
    p.add_argument("--format", choices=C.FORMATS)
    p.add_argument("--n", type=int, default=5)
    p.set_defaults(func=cmd_top)

    p = sub.add_parser("add-media")
    p.add_argument("path")
    p.add_argument("--kind", default="footage", choices=["footage", "broll", "photo", "logo", "graphic", "audio", "other"])
    p.add_argument("--description")
    p.add_argument("--tags", help="Comma separated")
    p.set_defaults(func=cmd_add_media)

    p = sub.add_parser("media")
    p.add_argument("--tag")
    p.add_argument("--unused", action="store_true")
    p.set_defaults(func=cmd_media)

    p = sub.add_parser("add-learning")
    p.add_argument("insight")
    p.add_argument("--source")
    p.set_defaults(func=cmd_add_learning)

    p = sub.add_parser("bake")
    p.add_argument("--out", required=True, help="Output ZIP path")
    p.add_argument("--skill-dir", help="Skill folder to copy (default: this skill)")
    p.set_defaults(func=cmd_bake)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
