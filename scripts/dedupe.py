"""Near-duplicate detection for content ideas (titles, hooks, concepts).

Used by plan_tool.py (duplicates inside one week) and library.py (new ideas
versus everything already planned or published). Works for English, Swedish
and Chinese text; other languages still work, just without stopword removal.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Sequence, Set, Tuple

STOPWORDS = set(
    """
    a an the and or but if then so to of in on at by for with from up out about into over after
    is are was were be been being am do does did done have has had having it its this that these those
    i me my we our you your he she they them their his her us what which who whom how why when where
    can could should would will just not no yes very really more most much many some any all every
    get got make made let lets here there than too also only even ever now today
    och att det som en ett är på av för med till den har de inte om ett jag du vi ni han hon man
    så men var vad när hur min mitt mina din ditt dina sin sitt sina från eller kan ska vill bara
    nu här där mycket mer också alla allt något några denna detta dessa
    """.split()
)

_SUFFIXES = ("arna", "erna", "orna", "ande", "ende", "ing", "ed", "es", "ar", "er", "or", "en", "et")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    text = re.sub(r"https?://\S+|[@#]\w+", " ", text)
    return re.sub(r"[^\w\s]", " ", text)


def _stem(word: str) -> str:
    # Plural -s first, so "mornings" and "morning" (or "routines" / "routine") end up identical.
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    if len(word) <= 5:
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


CJK_RUN_RE = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
# Very common Chinese function characters; text is split at them before taking two-character pieces.
ZH_STOP = "的了是在我你他她它们这那个和与及就都也很吗呢吧啊呀哦么着过被把给对让从到为以而但并或之其还有没要会能可"


def keywords(text: str) -> Set[str]:
    """Meaningful, lightly stemmed words from a title/hook/concept.

    Chinese has no spaces, so Chinese runs become two-character pieces ("晨间习惯" ->
    晨间, 间习, 习惯), the standard way to compare Chinese text without a dictionary.
    """
    norm = normalize(text)
    found: Set[str] = set()
    for run in CJK_RUN_RE.findall(norm):
        for piece in re.split(f"[{ZH_STOP}]+", run):
            found.update(piece[i:i + 2] for i in range(len(piece) - 1))
    latin = CJK_RUN_RE.sub(" ", norm)
    found.update(_stem(w) for w in latin.split() if len(w) > 2 and w not in STOPWORDS and not w.isdigit())
    return found


# How similar two ideas must be (0..1) before they are flagged as repeats.
# Calibrated on the sample week: a reworded copy scores ~0.6, a near-repeat ~0.5,
# deliberately related campaign pieces ~0.35, unrelated ideas under ~0.3.
DUPLICATE_THRESHOLD = 0.45


def idea_similarity(a: str, b: str) -> float:
    """Return how similar two content ideas are, from 0.0 (unrelated) to 1.0 (same idea).

    The score averages two views of keyword overlap:
      * Jaccard (shared / all words) is strict and stable, but a short hook compared
        with a long concept scores low even when the hook is fully inside it.
      * Containment (shared / smaller set) catches "the same idea, said at more length",
        but one shared word between two tiny texts would already score 0.5+, so it only
        counts once at least two keywords are shared.
    """
    ka, kb = keywords(a), keywords(b)
    if not ka or not kb:
        return 0.0
    shared = len(ka & kb)
    if shared == 0:
        return 0.0
    jaccard = shared / len(ka | kb)
    containment = shared / min(len(ka), len(kb)) if shared >= 2 else jaccard
    return (jaccard + containment) / 2


def item_text(item: dict) -> str:
    """The text that represents an idea: title + hook + first sentence of the concept."""
    concept = str(item.get("concept") or item.get("concept_summary") or "")
    first_sentence = re.split(r"(?<=[.!?])\s", concept, maxsplit=1)[0] if concept else ""
    return " ".join(str(part) for part in (item.get("title", ""), item.get("hook", ""), first_sentence) if part)


def find_similar(
    candidate: str,
    corpus: Iterable[Tuple[str, str]],
    threshold: float = DUPLICATE_THRESHOLD,
) -> List[Tuple[str, float]]:
    """Compare one idea with (id, text) pairs; return matches at or above threshold, best first."""
    matches = []
    for ref_id, text in corpus:
        score = idea_similarity(candidate, text)
        if score >= threshold:
            matches.append((ref_id, round(score, 3)))
    return sorted(matches, key=lambda pair: pair[1], reverse=True)


def intentionally_related(a: dict, b: dict) -> bool:
    """Deliberate repurposing ('repurposed_from': other id) is not an accidental repeat."""
    return bool(a.get("id")) and bool(b.get("id")) and (
        a.get("repurposed_from") == b.get("id") or b.get("repurposed_from") == a.get("id"))


def duplicates_within(items: Sequence[dict], threshold: float = DUPLICATE_THRESHOLD) -> List[Tuple[str, str, float]]:
    """All pairs of items in one list that look like the same idea (deliberate repurposes excepted)."""
    texts = [(item.get("id", f"#{i}"), item_text(item)) for i, item in enumerate(items)]
    pairs = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if not texts[i][1].strip() or not texts[j][1].strip():
                continue
            if intentionally_related(items[i], items[j]):
                continue
            score = idea_similarity(texts[i][1], texts[j][1])
            if score >= threshold:
                pairs.append((texts[i][0], texts[j][0], round(score, 3)))
    return sorted(pairs, key=lambda triple: triple[2], reverse=True)
