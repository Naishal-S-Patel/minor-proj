"""
Speaker identity — turning anonymous voices into named, platform-tagged
participants.

  * Platform detection (Zoom / Google Meet) from the explicit platform,
    filename, title or transcript content.
  * Platform tag formatting: Zoom -> USR-101, USR-102, ...; Google Meet ->
    P01, P02, ...; anything else -> Speaker 1, Speaker 2, ...
  * Roster parsing: the optional "participants" text supplied at upload, e.g.
        USR-101: Ramesha            P01 = Naishal
        Ramesha (USR-101)           Ramesha, Naishal      (speaking order)
  * Name resolution: decides which voice cluster belongs to which person,
    combining (strongest first)
        1. self-introductions   "I'm Ramesha" / "मेरा नाम रमेशा है" / "main Naishal hoon"
        2. being addressed      "Hi Naishal" (next speaker) / "Thanks Ramesha" (previous speaker)
        3. explicit roster tags "USR-102: Naishal"
        4. roster order         first unresolved voice -> first unused roster name
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re

# --------------------------------------------------------------------------- #
# Platform detection & tags
# --------------------------------------------------------------------------- #

_ZOOM_TAG_RE = re.compile(r"\bUSR-\d{2,}\b", re.IGNORECASE)
_MEET_TAG_RE = re.compile(r"\bP\d{2}\b")


def detect_platform(
    platform: str | None = None,
    filename: str | None = None,
    title: str | None = None,
    text: str | None = None,
) -> str | None:
    """Returns "Zoom", "Google Meet", the explicit platform, or None."""
    explicit = (platform or "").strip()
    low = explicit.lower()
    if "zoom" in low:
        return "Zoom"
    if "meet" in low and "teams" not in low:
        return "Google Meet"
    if explicit and low not in ("meeting", "audio recording"):
        return explicit

    for hint in (filename, title):
        h = (hint or "").lower()
        if "zoom" in h:
            return "Zoom"
        if "google meet" in h or "gmeet" in h or re.search(r"\bmeet\b", h):
            return "Google Meet"

    if text:
        t = text[:20000]
        tl = t.lower()
        if "zoom" in tl or _ZOOM_TAG_RE.search(t):
            return "Zoom"
        if "google meet" in tl or "meet.google" in tl or _MEET_TAG_RE.search(t):
            return "Google Meet"
    return None


def is_zoom(platform: str | None) -> bool:
    return "zoom" in (platform or "").lower()


def is_meet(platform: str | None) -> bool:
    low = (platform or "").lower()
    return "meet" in low and "teams" not in low


def speaker_tag(platform: str | None, idx: int) -> str:
    """Tag for the idx-th distinct voice (0-based, first-appearance order)."""
    if is_zoom(platform):
        return f"USR-{101 + idx}"
    if is_meet(platform):
        return f"P{idx + 1:02d}"
    return f"Speaker {idx + 1}"


# --------------------------------------------------------------------------- #
# Roster parsing
# --------------------------------------------------------------------------- #

_TAG = r"(?:USR[-_]?\d{2,}|P\d{1,3}|Speaker\s*\d{1,3}|SPEAKER_\d{1,3}|[A-Z]{1,5}[-_]?\d{1,6})"
_NAME = r"[A-Za-zऀ-ॿ][A-Za-zऀ-ॿ .'\-]{0,60}"

_ROSTER_TAG_FIRST = re.compile(rf"^({_TAG})\s*(?:->|=>|=|:|\||-|–)\s*({_NAME})$", re.IGNORECASE)
_ROSTER_NAME_PAREN = re.compile(rf"^({_NAME}?)\s*\(\s*(?:ID[:\s]*)?({_TAG})\s*\)$", re.IGNORECASE)
_ROSTER_TAG_PAREN = re.compile(rf"^({_TAG})\s*\(\s*({_NAME})\s*\)$", re.IGNORECASE)


@dataclass
class Participant:
    name: str
    tag: str | None = None


def normalize_tag(tag: str) -> str:
    t = tag.strip()
    m = re.match(r"^usr[-_]?(\d+)$", t, re.IGNORECASE)
    if m:
        return f"USR-{m.group(1)}"
    m = re.match(r"^p(\d{1,3})$", t, re.IGNORECASE)
    if m:
        return f"P{int(m.group(1)):02d}"
    m = re.match(r"^speaker[\s_]*(\d+)$", t, re.IGNORECASE)
    if m:
        return f"Speaker {int(m.group(1))}"
    return t


def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" .-–|:")
    # Drop trailing role descriptors: "Sarah Chen - Product Lead" -> "Sarah Chen"
    name = re.split(r"\s+[-–|]\s+", name)[0]
    return name.strip()


def parse_participants(text: str | None) -> list[Participant]:
    """Parses a free-form participant roster. Order is preserved."""
    if not text or not text.strip():
        return []
    raw = text.replace("\r", "\n")
    entries = [e for e in re.split(r"[\n;]+", raw) if e.strip()]
    if len(entries) == 1 and "," in entries[0]:
        entries = entries[0].split(",")

    out: list[Participant] = []
    seen: set[str] = set()
    for entry in entries:
        e = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", entry).strip()
        if not e:
            continue
        tag = name = None
        for pattern, tag_group, name_group in (
            (_ROSTER_TAG_PAREN, 1, 2),
            (_ROSTER_TAG_FIRST, 1, 2),
            (_ROSTER_NAME_PAREN, 2, 1),
        ):
            m = pattern.match(e)
            if m:
                tag, name = normalize_tag(m.group(tag_group)), m.group(name_group)
                break
        if name is None:
            name = e
        name = _clean_name(name)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(Participant(name=name, tag=tag))
    return out


def roster_header(participants: list[Participant], platform: str | None, transcript: str = "") -> str:
    """
    Renders a roster as transcript header lines ("- USR-101 -> Ramesha") that
    both the local extractor and the LLM prompt already understand. Untagged
    names get tags in order of first appearance of IDs in the transcript.
    """
    if not participants:
        return ""
    present: list[str] = []
    for m in re.finditer(rf"\[?({_TAG})\]?\s*(?:\([^)]*\))?\s*\]?:", transcript or ""):
        tag = normalize_tag(m.group(1))
        if tag not in present:
            present.append(tag)

    used = {p.tag for p in participants if p.tag}
    free_tags = [t for t in present if t not in used]
    lines = ["Participants:"]
    idx = 0
    for p in participants:
        tag = p.tag
        if not tag:
            if free_tags:
                tag = free_tags.pop(0)
            else:
                while speaker_tag(platform, idx) in used:
                    idx += 1
                tag = speaker_tag(platform, idx)
            used.add(tag)
        lines.append(f"- {tag} -> {p.name}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Name evidence from speech (English / Hindi / Hinglish)
# --------------------------------------------------------------------------- #

_LATIN_NAME = r"[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20})?"
_DEVA_NAME = r"[ऀ-ॿ]{2,20}"

_SELF_INTRO_PATTERNS = [
    # English
    re.compile(rf"\bmy name is\s+({_LATIN_NAME})", re.IGNORECASE),
    re.compile(rf"\b(?:I'm|I am|[Tt]his is)\s+({_LATIN_NAME})(?=\s+(?:here|speaking|from|and|joining)\b|[,.!?]|$)"),
    re.compile(rf"\b({_LATIN_NAME})\s+(?:here|speaking)\b[,.!]"),
    # Hinglish (romanised Hindi)
    re.compile(rf"\bmera naam\s+({_LATIN_NAME})\s+(?:hai|he)\b", re.IGNORECASE),
    re.compile(rf"\b(?:[Mm]ain|[Mm]ai|[Mm]ein)\s+({_LATIN_NAME})\s+(?:hoon|hun|hu|bol raha|bol rahi)\b"),
    # Hindi (Devanagari)
    re.compile(rf"मेरा नाम\s+({_DEVA_NAME}|{_LATIN_NAME})\s+है"),
    re.compile(rf"मैं\s+({_DEVA_NAME}|{_LATIN_NAME})\s+(?:हूँ|हूं|बोल रहा|बोल रही)"),
]

# Only the keywords are case-insensitive; names must stay Capitalised so that
# "thanks for joining" never yields the "name" "for joining".
# Greeting/hand-off addressed to the NEXT speaker.
_ADDRESS_NEXT = [
    re.compile(rf"\b(?i:hi|hello|hey|namaste|namaskar|over to you|over to|go ahead|your turn)\s*,?\s+({_LATIN_NAME})\b"),
    re.compile(rf"(?:नमस्ते|हेलो|हाय)\s*,?\s*({_DEVA_NAME}|{_LATIN_NAME})"),
    re.compile(r"(?:^|[.?!]\s+)([A-Z][a-z]{1,20})\s*,\s*(?i:can|could|would|will|what|how|please|do|did|are|kya|aap|tum)\b"),
]
# Thanks addressed to the PREVIOUS speaker.
_ADDRESS_PREV = [
    re.compile(rf"\b(?i:thanks|thank you|thank u|great job|good point|shukriya|dhanyavaad|dhanyawad)\s*,?\s+({_LATIN_NAME})\b"),
    re.compile(rf"(?:धन्यवाद|शुक्रिया)\s*,?\s*({_DEVA_NAME}|{_LATIN_NAME})"),
]

_NOT_NAMES = {
    "everyone", "everybody", "all", "guys", "team", "folks", "there", "sir", "madam", "maam",
    "bro", "ji", "so", "sure", "here", "just", "going", "glad", "happy", "good", "fine", "okay",
    "ok", "the", "not", "very", "really", "back", "done", "ready", "sorry", "also", "still",
    "now", "on", "in", "at", "from", "with", "excited", "working", "looking", "trying",
    "you", "your", "and", "but", "yes", "no", "yeah", "hello", "hi", "hey", "thanks", "thank",
    "sab", "sabhi", "doston", "dosto", "bhai", "aap", "tum", "hum", "main", "theek", "accha",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "today",
    "tomorrow", "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "google", "zoom", "meet",
    "सभी", "सब", "दोस्तों", "आप", "जी", "टीम", "सर", "मैडम", "भाई",
}


def _clean_candidate(raw: str | None) -> str | None:
    if not raw:
        return None
    words = raw.strip().split()
    while words and words[-1].lower() in _NOT_NAMES:
        words.pop()
    if not words or words[0].lower() in _NOT_NAMES:
        return None
    return " ".join(words)


def _first_group(m: re.Match) -> str | None:
    for g in m.groups():
        if g:
            return g
    return None


def find_self_introduction(text: str) -> str | None:
    for pattern in _SELF_INTRO_PATTERNS:
        m = pattern.search(text)
        if m:
            name = _clean_candidate(_first_group(m))
            if name:
                return name
    return None


def _name_key(name: str) -> str:
    return re.sub(r"[^a-zऀ-ॿ]", "", name.lower())


def match_roster_name(candidate: str, roster: list[Participant]) -> str | None:
    """Fuzzy-matches a spoken name ("Nishal") to a roster name ("Naishal Patel")."""
    cand = _name_key(candidate)
    if not cand:
        return None
    best, best_score = None, 0.0
    for p in roster:
        for variant in {p.name, p.name.split()[0]}:
            score = SequenceMatcher(None, cand, _name_key(variant)).ratio()
            if score > best_score:
                best, best_score = p.name, score
    return best if best_score >= 0.75 else None


def resolve_speaker_names(
    turns: list[tuple[int, str]],
    roster: list[Participant],
    platform: str | None,
) -> dict[int, str]:
    """
    turns: (speaker_idx, text) in time order; speaker_idx is first-appearance
    ordered (0 = first voice). Returns speaker_idx -> person name for every
    voice that could be identified.
    """
    speakers = list(dict.fromkeys(idx for idx, _ in turns))
    votes: dict[int, dict[str, float]] = {s: {} for s in speakers}

    def vote(spk: int, raw_name: str | None, weight: float) -> None:
        name = _clean_candidate(raw_name)
        if not name:
            return
        if roster:
            name = match_roster_name(name, roster)
            if not name:
                return
        votes[spk][name] = votes[spk].get(name, 0.0) + weight

    for pos, (spk, text) in enumerate(turns):
        intro = find_self_introduction(text)
        if intro:
            vote(spk, intro, 3.0)

        nxt = next((s for s, _ in turns[pos + 1 : pos + 4] if s != spk), None)
        prev = next((s for s, _ in reversed(turns[max(0, pos - 3) : pos]) if s != spk), None)
        for pattern in _ADDRESS_NEXT:
            for m in pattern.finditer(text):
                if nxt is not None:
                    vote(nxt, _first_group(m), 1.0)
        for pattern in _ADDRESS_PREV:
            for m in pattern.finditer(text):
                if prev is not None:
                    vote(prev, _first_group(m), 1.0)

    # Greedy one-to-one assignment, strongest evidence first.
    result: dict[int, str] = {}
    used_names: set[str] = set()
    ranked = sorted(
        ((score, spk, name) for spk, cand in votes.items() for name, score in cand.items()),
        reverse=True,
    )
    for score, spk, name in ranked:
        if spk in result or name.lower() in used_names:
            continue
        result[spk] = name
        used_names.add(name.lower())

    # Explicit roster tags ("USR-102: Naishal") for still-unresolved voices.
    for p in roster:
        if not p.tag or p.name.lower() in used_names:
            continue
        for spk in speakers:
            if spk not in result and normalize_tag(speaker_tag(platform, spk)) == p.tag:
                result[spk] = p.name
                used_names.add(p.name.lower())
                break

    # Remaining roster names fill remaining voices in speaking order.
    remaining = [p for p in roster if p.name.lower() not in used_names]
    for spk in speakers:
        if spk in result or not remaining:
            continue
        result[spk] = remaining.pop(0).name

    return result


def format_speaker_label(platform: str | None, idx: int, name: str | None) -> str:
    """'USR-101 (Ramesha)' when the name is known, else just the tag."""
    tag = speaker_tag(platform, idx)
    return f"{tag} ({name})" if name else tag
