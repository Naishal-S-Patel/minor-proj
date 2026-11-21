"""
Smart Local Extractor and Q&A Engine.

Provides an offline, zero-failure fallback for meeting intelligence.
When external LLM APIs (Groq, Gemini) are expired, rate-limited, or unavailable:
  1. Extracts high-quality structured keywords, executive summary, action items,
     decisions, sentiment, speaker turns, and calendar events.
  2. Reliably answers user questions in the meeting chatbot using context retrieval,
     dialogue matching, and semantic heuristic Q&A.
"""

from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

from app.models.meeting import ActionItem, CalendarEvent, Sentiment
from app.services.language_support import detect_text_language
from app.services.llm.schemas import (
    ExtractionResult,
    LLMActionItem,
    LLMCalendarEvent,
    LLMDialogueTurn,
)
from app.services.speaker_identity import detect_platform, is_meet, is_zoom, resolve_speaker_names

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "um", "uh", "okay", "like", "yeah", "yes", "right",
    "well", "hello", "hi", "hey", "thanks", "thank", "meeting", "everyone", "today"
}

POSITIVE_WORDS = {
    "great", "good", "excellent", "awesome", "perfect", "productive", "resolved",
    "approved", "success", "successful", "progress", "clear", "helpful", "excited",
    "happy", "accomplished", "improved", "positive", "beneficial", "delighted", "love"
}

NEGATIVE_WORDS = {
    "problem", "issue", "bug", "delayed", "fail", "failed", "blocker", "broken",
    "difficult", "frustrated", "error", "risk", "conflict", "concern", "worry",
    "urgent", "bottleneck", "disagree", "impossible", "negative", "terrible", "bad"
}

# --- Hindi / Hinglish vocabulary -------------------------------------------

HINDI_STOPWORDS = {
    # Devanagari
    "है", "हैं", "था", "थे", "थी", "का", "की", "के", "को", "में", "से", "पर", "और", "या",
    "यह", "वह", "ये", "वो", "हम", "मैं", "आप", "तुम", "तो", "भी", "ही", "कि", "जो", "ना",
    "नहीं", "क्या", "एक", "लिए", "कर", "करना", "करेंगे", "हो", "रहा", "रही", "रहे", "गया",
    "गई", "गए", "हाँ", "हां", "जी", "अच्छा", "ठीक", "बस", "अभी", "कुछ", "सब", "अपना", "अपने",
    "इस", "उस", "इसे", "उसे", "मुझे", "हमें", "होगा", "होगी", "कल", "आज", "फिर", "बहुत",
    # Romanised (Hinglish)
    "hai", "hain", "tha", "thi", "the", "ka", "ki", "ke", "ko", "mein", "se", "par", "aur",
    "yeh", "ye", "woh", "wo", "hum", "main", "aap", "tum", "toh", "bhi", "jo", "na", "nahi",
    "nahin", "kya", "ek", "liye", "kar", "karna", "karenge", "karega", "karegi", "ho", "raha",
    "rahi", "rahe", "gaya", "gayi", "haan", "ji", "accha", "acha", "theek", "thik", "bas",
    "abhi", "kuch", "sab", "apna", "apne", "mujhe", "humein", "hoga", "hogi", "kal", "aaj",
    "phir", "bahut", "bohot", "matlab", "lekin", "dunga", "dungi", "diya", "kiya", "wala", "wali",
    "tak", "din", "baad", "badhiya", "तक", "दिन", "बाद", "दूंगा", "दूंगी", "भेज", "तीन",
}

HINDI_POSITIVE_WORDS = {
    "अच्छा", "बढ़िया", "बढ़िया", "शानदार", "बेहतरीन", "सही", "सफल", "पूरा", "धन्यवाद", "खुश",
    "badhiya", "shandar", "behtareen", "sahi", "safal", "khush", "mast", "zabardast", "perfect",
}

HINDI_NEGATIVE_WORDS = {
    "समस्या", "दिक्कत", "गलती", "देरी", "परेशानी", "मुश्किल", "खराब", "रुका", "चिंता",
    "dikkat", "galti", "deri", "pareshani", "mushkil", "kharab", "ruka", "chinta", "samasya",
}

HINDI_ACTION_MARKERS = [
    "करूँगा", "करूंगा", "करूँगी", "करूंगी", "करेगा", "करेगी", "करेंगे", "करना है", "करना होगा",
    "कर दूंगा", "कर दूँगा", "कर दूंगी", "भेज दूंगा", "भेज दूंगी", "शेयर", "सबमिट", "जमा कर",
    "तैयार कर", "पूरा कर", "देख लूंगा", "देख लेंगे", "तक कर",
    "kar dunga", "kar dungi", "kar denge", "karna hai", "karna hoga", "karunga", "karungi",
    "bhej dunga", "bhej dungi", "bhej denge", "share kar", "submit kar", "complete kar",
    "ready kar", "taiyar kar", "dekh lunga", "dekh lenge", "tak kar", "kar lunga", "kar lenge",
]

HINDI_DECISION_MARKERS = [
    "तय किया", "तय हुआ", "फैसला", "निर्णय", "फाइनल किया", "मंजूरी",
    "decide kiya", "tay kiya", "tay hua", "faisla", "final kiya", "finalize kiya", "manzoori",
]

HINDI_DEADLINE_RE = re.compile(
    r"(\b\w+\s+tak\b|\S+ तक|agle hafte|अगले हफ्ते|"
    r"\d+\s*(?:din|दिन)\s*(?:mein|me|में|baad|bad|बाद))",
    re.IGNORECASE,
)

_HI_EVENT_RE = re.compile(
    r"(test|exam|quiz|submission|demo|presentation|review|meeting|deadline|"
    r"टेस्ट|परीक्षा|इम्तिहान|क्विज़|क्विज|मीटिंग|डेमो|सबमिशन|डेडलाइन|प्रेजेंटेशन|रिव्यू)",
    re.IGNORECASE,
)
_HI_EVENT_TITLES = {
    "टेस्ट": "Test", "परीक्षा": "Exam", "इम्तिहान": "Exam", "क्विज़": "Quiz", "क्विज": "Quiz",
    "मीटिंग": "Meeting", "डेमो": "Demo", "सबमिशन": "Submission", "डेडलाइन": "Deadline",
    "प्रेजेंटेशन": "Presentation", "रिव्यू": "Review",
}
_HI_N_DAYS_RE = re.compile(r"(\d+)\s*(?:din|dino|dinon|दिन|दिनों)\s*(?:baad|bad|mein|me|में|बाद)", re.IGNORECASE)
_NO_DEVA_BEFORE = r"(?<![ऀ-ॿ])"
_NO_DEVA_AFTER = r"(?![ऀ-ॿ])"
_HI_RELATIVE_WORDS = [
    (re.compile(rf"\b(?:parso|parson)\b|{_NO_DEVA_BEFORE}परसों{_NO_DEVA_AFTER}", re.IGNORECASE), 2),
    (re.compile(r"\bagle\s+(?:hafte|week|saptah)\b|अगले\s+(?:हफ्ते|हफ़्ते|सप्ताह)", re.IGNORECASE), 7),
    (re.compile(r"\bagle\s+mahine\b|अगले\s+महीने", re.IGNORECASE), 30),
    (re.compile(rf"\bkal\b|{_NO_DEVA_BEFORE}कल{_NO_DEVA_AFTER}", re.IGNORECASE), 1),
]

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6,
    "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7,
    "आठ": 8, "नौ": 9, "दस": 10,
}
# Only rewrite number words directly before a time unit ("three days", "do din").
_NUMBER_WORD_RE = re.compile(
    r"(?<![\wऀ-ॿ])(" + "|".join(sorted(map(re.escape, _NUMBER_WORDS), key=len, reverse=True)) + r")"
    r"\s+(days?|weeks?|din|dino|dinon|hafte|दिन|दिनों|हफ्ते)",
    re.IGNORECASE,
)

# Latin + Devanagari word tokens (the Devanagari danda "।" / "॥" is punctuation, not a letter).
_WORD_TOKEN_RE = re.compile(
    r"[A-Za-zऀ-ॣ०-ॿ][A-Za-z0-9ऀ-ॣ०-ॿ_\-\.]{2,24}"
)

# Conversational filler that is never a meeting topic.
FILLER_WORDS = {
    "sure", "great", "let", "lets", "begin", "start", "started", "participants", "namaste",
    "alright", "good", "morning", "afternoon", "evening", "joining", "awesome", "perfect",
    "nice", "cool", "fine", "also", "just", "really", "going", "want", "need", "get", "got",
    "can", "will", "think", "know", "see", "said", "say", "one", "two", "three",
    "नमस्ते", "मेरा", "नाम", "सभी", "बढ़िया", "धन्यवाद",
}


class SmartLocalExtractor:
    """Extracts meeting insights with zero external API calls."""

    _HEADER_IGNORE = {
        "topic", "meeting", "meeting id", "zoom meeting id", "session id", "passcode",
        "password", "invite link", "meeting link", "meeting url", "date", "time", "duration",
        "url", "link", "platform", "agenda", "subject", "conference", "host",
        "participants", "attendees", "speaker mapping", "roster", "kind", "language",
    }

    @staticmethod
    def _split_inline_id_and_name(raw_label: str) -> tuple[str | None, str]:
        """
        Detects inline ID+Name patterns like:
        - 'USR-101 (Sarah Chen)' -> ('USR-101', 'Sarah Chen')
        - 'Sarah Chen (ID: P01)' -> ('P01', 'Sarah Chen')
        - 'Sarah Chen (P01)'     -> ('P01', 'Sarah Chen')
        - 'P01 | Sarah Chen'     -> ('P01', 'Sarah Chen')
        - 'P01'                  -> ('P01', 'P01') (if looks like an ID)
        """
        label = raw_label.strip()

        # Pattern 1: ID (Name) e.g. USR-101 (Sarah Chen), P01 (Sarah Chen), Speaker 2 (Ramesha)
        m1 = re.match(r"^([A-Za-z]+[-_]?\d+|Speaker\s+\d+|\d{4,})\s*\(([^)]+)\)$", label, re.IGNORECASE)
        if m1:
            return m1.group(1).strip(), m1.group(2).strip()

        # Pattern 2: Name (ID: P01) or Name (P01)
        m2 = re.match(r"^(.+?)\s*\((?:ID[:\s]*)?([A-Za-z]+[-_]?\d+|Speaker\s+\d+|\d{4,})\)$", label, re.IGNORECASE)
        if m2:
            return m2.group(2).strip(), m2.group(1).strip()

        # Pattern 3: P01 | Sarah Chen or P01 - Sarah Chen
        m3 = re.match(r"^([A-Za-z]+[-_]?\d+|Speaker\s+\d+|\d{4,})\s*[\|\-–]\s*(.+)$", label, re.IGNORECASE)
        if m3:
            return m3.group(1).strip(), m3.group(2).strip()

        # Pattern 4: Looks like a standalone Person ID / Speaker ID (e.g. P01, USR_101, MEE001, Speaker 1, 16778240)
        if re.match(r"^(?:Speaker\s+\d+|SPEAKER_\d+|[A-Z]{1,5}[-_]?\d{1,6}|[A-Za-z]+_\d+|\d{4,})$", label):
            return label, label

        return None, label

    @classmethod
    def extract_speaker_map(cls, cleaned_transcript: str) -> dict[str, str]:
        """
        Extracts Person ID -> Speaker Name mappings from explicit rosters,
        inline tags, or self-introductions in the transcript.
        """
        speaker_map: dict[str, str] = {}
        if not cleaned_transcript:
            return speaker_map

        lines = [line.strip() for line in cleaned_transcript.split("\n") if line.strip()]

        # 1. Explicit roster mappings:
        # e.g. "- P01 -> Sarah Chen", "ID: USR-101 -> Alex Rivera", "P01 = Sarah Chen", "Participant P01: Sarah Chen"
        roster_arrow = re.compile(
            r"^(?:[-*•]\s*)?(?:(?:Participant|Person|User|Speaker)?\s*(?:ID)?[:\s]*)?([A-Za-z]+[-_]?\d+|Speaker\s+\d+|SPEAKER_\d+|\d{4,})\s*(?:->|=>|=|:|\|)\s*([A-Za-z][A-Za-z\s\.\-]{1,50}?)(?:\s*\([^)]+\))?$",
            re.IGNORECASE,
        )
        # Name (ID: P01) in roster lines
        roster_paren = re.compile(
            r"^(?:[-*•]\s*)?([A-Za-z][A-Za-z\s\.\-]{1,40}?)\s*\((?:ID[:\s]*)?([A-Za-z]+[-_]?\d+|\d{4,})\)$",
            re.IGNORECASE,
        )

        turn_pattern = re.compile(
            r"^(?:\[?(\d{1,3}:\d{2}(?::\d{2})?)\]?\s*)?(?:\[?([^:\[\]]+?)\]?):\s*(.+)$"
        )

        for line in lines:
            # Skip obvious dialogue turns with timestamps when checking roster_arrow
            if not re.match(r"^\[?\d{1,3}:\d{2}", line):
                m_paren = roster_paren.match(line)
                if m_paren:
                    name, pid = m_paren.group(1).strip(), m_paren.group(2).strip()
                    speaker_map[pid] = name
                    continue

                m_arrow = roster_arrow.match(line)
                if m_arrow:
                    pid, candidate_name = m_arrow.group(1).strip(), m_arrow.group(2).strip()
                    # Make sure candidate_name is a person's name (1-4 capitalized words, not a long sentence)
                    words = candidate_name.split()
                    if 1 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
                        speaker_map[pid] = candidate_name
                        continue

            # 2. Inline labels in dialogue turns, e.g. "[USR-101 (Ramesha)]:"
            m_turn = turn_pattern.match(line)
            if m_turn:
                raw_label = m_turn.group(2).strip()
                if len(raw_label) > 50 or raw_label.lower() in cls._HEADER_IGNORE:
                    continue

                pid, name = cls._split_inline_id_and_name(raw_label)
                if pid and name and name != pid:
                    speaker_map[pid] = name

        # 3. Still-anonymous IDs: use self-introductions ("I'm Sarah",
        #    "मेरा नाम रमेशा है", "main Naishal hoon") and who is being greeted or
        #    thanked — "Hi Naishal" names the NEXT different speaker, "Thanks
        #    Ramesha" the PREVIOUS one (not just "any other speaker").
        id_turns: list[tuple[str, str]] = []
        for line in lines:
            m_turn = turn_pattern.match(line)
            if not m_turn:
                continue
            raw_label = m_turn.group(2).strip()
            if len(raw_label) > 50 or raw_label.lower() in cls._HEADER_IGNORE:
                continue
            pid, _ = cls._split_inline_id_and_name(raw_label)
            if pid:
                id_turns.append((pid, m_turn.group(3).strip()))

        anonymous = [p for p in dict.fromkeys(p for p, _ in id_turns) if p not in speaker_map]
        if anonymous:
            ids = list(dict.fromkeys(p for p, _ in id_turns))
            index_of = {p: i for i, p in enumerate(ids)}
            resolved = resolve_speaker_names(
                [(index_of[p], t) for p, t in id_turns], roster=[], platform=None
            )
            taken = {n.lower() for n in speaker_map.values()}
            for idx, name in resolved.items():
                pid = ids[idx]
                if pid in anonymous and name.lower() not in taken:
                    speaker_map[pid] = name
                    taken.add(name.lower())

        return speaker_map

    @classmethod
    def extract(
        cls,
        cleaned_transcript: str,
        meeting_title: str = "",
        created_at: datetime | None = None,
        platform: str = "",
    ) -> ExtractionResult:
        if not cleaned_transcript or not cleaned_transcript.strip():
            return ExtractionResult(
                summary="Empty transcript provided.",
                action_items=[],
                decisions=[],
                keywords=[],
                sentiment="neutral",
                speakers=[],
                speaker_map={},
                calendar_events=[],
                dialogue_turns=[],
                detected_language="en",
            )

        ref_date = created_at or datetime.now(timezone.utc)
        lines = [line.strip() for line in cleaned_transcript.split("\n") if line.strip()]

        speaker_map = cls.extract_speaker_map(cleaned_transcript)

        # 1. Parse Dialogue Turns and Speakers
        dialogue_turns: list[LLMDialogueTurn] = []
        speakers_set: set[str] = set()

        # Regex patterns for dialogue lines:
        # e.g. [00:12] [USR-101]: text, [00:12] [Speaker 1]: text, Alex: text, P01 (Sarah): text
        turn_pattern = re.compile(
            r"^(?:\[?(\d{1,3}:\d{2}(?::\d{2})?)\]?\s*)?(?:\[?([^:\[\]]+?)\]?):\s*(.+)$"
        )

        # Roster lines that shouldn't be treated as spoken dialogue turns
        roster_line_re = re.compile(
            r"^(?:[-*•]\s*)?(?:(?:Participant|Person|User|Speaker)?\s*(?:ID)?[:\s]*)?([A-Za-z]+[-_]?\d+|Speaker\s+\d+|SPEAKER_\d+|\d{4,})\s*(?:->|=>|=|:|\|)\s*([A-Za-z][A-Za-z\s\.\-]{1,40}?)(?:\s*\([^)]+\))?$",
            re.IGNORECASE,
        )

        for line in lines:
            # Skip explicit roster mapping lines from dialogue turns
            if not re.match(r"^\[?\d{1,3}:\d{2}", line):
                m_roster = roster_line_re.match(line)
                if m_roster and len(m_roster.group(2).split()) <= 4 and all(w[0].isupper() for w in m_roster.group(2).split() if w):
                    continue

            m = turn_pattern.match(line)
            if m:
                timestamp = m.group(1) or None
                raw_speaker = m.group(2).strip()
                text = m.group(3).strip()
                if len(raw_speaker) <= 50 and not raw_speaker.lower().startswith("http") and raw_speaker.lower() not in cls._HEADER_IGNORE:
                    pid, parsed_name = cls._split_inline_id_and_name(raw_speaker)
                    resolved_name = speaker_map.get(pid or raw_speaker, parsed_name)
                    if pid and pid not in speaker_map:
                        speaker_map[pid] = resolved_name
                    speakers_set.add(resolved_name)
                    dialogue_turns.append(
                        LLMDialogueTurn(
                            speaker=resolved_name,
                            speaker_id=pid,
                            time=timestamp,
                            text=text,
                        )
                    )
            else:
                # Line without explicit speaker (skip pure header metadata lines)
                if any(line.lower().startswith(h + ":") or line.lower().startswith(h + " ") for h in (
                    "topic", "meeting", "meeting id", "zoom id", "platform", "duration", "meeting link",
                    "meeting url", "agenda", "participants", "attendees", "roster", "webvtt", "kind", "language"
                )):
                    continue
                speaker_guess = "Speaker 1" if not speakers_set else list(speakers_set)[0]
                dialogue_turns.append(
                    LLMDialogueTurn(speaker=speaker_guess, speaker_id=None, time=None, text=line)
                )

        # Detect if meeting is Zoom or Google Meet
        detected_platform = detect_platform(platform, None, meeting_title, cleaned_transcript)
        is_zoom_mtg = is_zoom(detected_platform)
        is_google_meet = is_meet(detected_platform) and not is_zoom_mtg

        # Ensure Zoom (USR-xxx) or Google Meet (P0x) tag IDs are assigned to every participant
        if is_zoom_mtg or is_google_meet:
            prefix = "USR-" if is_zoom_mtg else "P"
            start_num = 101 if is_zoom_mtg else 1
            allocated_tags = set(speaker_map.keys())
            tag_counter = start_num

            # Existing tag -> name and name -> tag
            name_to_tag = {v: k for k, v in speaker_map.items() if k != v}

            # Ordered list of distinct speakers found in speech
            ordered_speakers = []
            for t in dialogue_turns:
                spk = t.speaker
                if spk and spk not in ordered_speakers:
                    ordered_speakers.append(spk)
            for spk in speakers_set:
                if spk not in ordered_speakers:
                    ordered_speakers.append(spk)

            for spk in ordered_speakers:
                # Skip if already a recognized tag ID or mapped
                if spk in speaker_map or spk in name_to_tag:
                    continue
                # Allocate next available tag ID
                while True:
                    candidate = f"{prefix}{tag_counter}" if is_zoom_mtg else f"{prefix}{tag_counter:02d}"
                    if candidate not in allocated_tags:
                        tag_id = candidate
                        allocated_tags.add(tag_id)
                        tag_counter += 1
                        break
                    tag_counter += 1

                speaker_map[tag_id] = spk
                name_to_tag[spk] = tag_id

            # Apply tag_id across all dialogue turns
            for turn in dialogue_turns:
                if not turn.speaker_id:
                    if turn.speaker in name_to_tag:
                        turn.speaker_id = name_to_tag[turn.speaker]
                    elif turn.speaker in speaker_map:
                        turn.speaker_id = turn.speaker
                elif turn.speaker_id in speaker_map:
                    turn.speaker = speaker_map[turn.speaker_id]

        speakers = sorted(list(dict.fromkeys(speaker_map.values()))) if speaker_map else (
            sorted(list(speakers_set)) if speakers_set else ["Speaker 1"]
        )

        # 2. Extract Calendar & Scheduled Events (e.g. "test after 3 days")
        calendar_events = cls._extract_calendar_events(lines, dialogue_turns, ref_date)

        # 3. Extract Action Items
        action_items = cls._extract_action_items(lines, dialogue_turns)
        # Resolve any Person IDs in action_items using speaker_map
        for item in action_items:
            if item.person in speaker_map:
                item.person = speaker_map[item.person]

        # 4. Extract Decisions
        decisions = cls._extract_decisions(lines)

        # 5. Extract Keywords
        keywords = cls._extract_keywords(
            cleaned_transcript, meeting_title, names=list(speaker_map.values()) + speakers
        )

        # 6. Sentiment
        sentiment = cls._analyze_sentiment(cleaned_transcript)

        # 7. Language Detection
        detected_lang = cls._detect_language(cleaned_transcript)

        # 8. Executive Summary
        summary = cls._generate_summary(
            meeting_title, lines, calendar_events, decisions, action_items, speakers
        )

        return ExtractionResult(
            summary=summary,
            action_items=action_items,
            decisions=decisions,
            keywords=keywords,
            sentiment=sentiment,
            speakers=speakers,
            speaker_map=speaker_map,
            calendar_events=calendar_events,
            dialogue_turns=dialogue_turns,
            detected_language=detected_lang,
        )

    @classmethod
    def _extract_calendar_events(
        cls, lines: list[str], turns: list[LLMDialogueTurn], ref_date: datetime
    ) -> list[LLMCalendarEvent]:
        events: list[LLMCalendarEvent] = []
        seen_keys: set[str] = set()

        # 1. Explicit calendar date patterns:
        # e.g. "25th of November", "25th November", "November 25", "Nov 25", "submit on 25 Nov"
        months_map = {
            "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
            "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
            "nov": 11, "november": 11, "dec": 12, "december": 12,
            "जनवरी": 1, "फ़रवरी": 2, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6,
            "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "अक्तूबर": 10,
            "नवंबर": 11, "नवम्बर": 11, "दिसंबर": 12, "दिसम्बर": 12,
        }
        explicit_date_1 = re.compile(
            r"\b(?:on\s+(?:the\s+)?)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|जनवरी|फ़रवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|सितम्बर|अक्टूबर|अक्तूबर|नवंबर|नवम्बर|दिसंबर|दिसम्बर)\b",
            re.IGNORECASE,
        )
        explicit_date_2 = re.compile(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|जनवरी|फ़रवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|सितम्बर|अक्टूबर|अक्तूबर|नवंबर|नवम्बर|दिसंबर|दिसम्बर)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            re.IGNORECASE,
        )

        for line in lines:
            m_exp = explicit_date_1.search(line) or explicit_date_2.search(line)
            if m_exp:
                g1, g2 = m_exp.group(1), m_exp.group(2)
                if g1.isdigit():
                    day, month_str = int(g1), g2.lower()
                else:
                    day, month_str = int(g2), g1.lower()

                if month_str in months_map and 1 <= day <= 31:
                    month = months_map[month_str]
                    year = ref_date.year
                    target_dt = datetime(year, month, day, tzinfo=ref_date.tzinfo)
                    if target_dt < ref_date - timedelta(days=60):
                        target_dt = target_dt.replace(year=year + 1)
                    diff_days = max(0, (target_dt.date() - ref_date.date()).days)

                    full_corpus = " ".join(lines).lower()
                    if "cloud" in full_corpus and ("exam" in full_corpus or "test" in full_corpus):
                        title = "Cloud Computing Exam"
                        category = "exam"
                    elif "ml" in full_corpus or "machine learning" in full_corpus or "एमएल" in full_corpus:
                        title = "Machine Learning (ML) Exam"
                        category = "exam"
                    elif "exam" in full_corpus or "test" in full_corpus or "quiz" in full_corpus or "एग्जाम" in full_corpus:
                        title = "Course Exam"
                        category = "exam"
                    elif "assignment" in full_corpus or "project" in full_corpus or "submission" in full_corpus:
                        title = "Project Assignment Submission"
                        category = "deadline"
                    elif "presentation" in full_corpus:
                        title = "Presentation Submission"
                        category = "deadline"
                    else:
                        title = "Scheduled Milestone"
                        category = "meeting"

                    key = f"{title}_{target_dt.strftime('%Y-%m-%d')}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        events.append(
                            LLMCalendarEvent(
                                title=title,
                                relative_time=f"{day} {month_str.capitalize()}",
                                event_date=target_dt.strftime("%Y-%m-%d"),
                                days_from_now=diff_days,
                                speaker=cls._find_speaker_for_text(line, turns),
                                context=line,
                                category=category,
                            )
                        )

        # 2. Patterns for relative dates:
        # e.g. "test after 3 days", "exam in 2 days", "meeting after 1 week", "presentation next friday"
        rel_days_pattern = re.compile(
            r"\b(test|exam|examination|quiz|assessment|submission|demo|presentation|review|meeting|sync|release|deadline)\s+(?:is\s+)?(?:scheduled\s+)?(?:after|in)\s+(\d+)\s+days?\b",
            re.IGNORECASE,
        )
        days_rel_pattern = re.compile(
            r"\b(?:after|in)\s+(\d+)\s+days?[\s,]+(?:we\s+have\s+a\s+|there\s+will\s+be\s+a\s+|take\s+a\s+)?(test|exam|quiz|submission|demo|presentation|meeting|deadline)\b",
            re.IGNORECASE,
        )
        tomorrow_pattern = re.compile(
            r"\b(test|exam|quiz|submission|demo|presentation|meeting|review|deadline)\s+(?:is\s+)?tomorrow\b",
            re.IGNORECASE,
        )
        next_week_pattern = re.compile(
            r"\b(test|exam|quiz|submission|demo|presentation|meeting)\s+next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)\b",
            re.IGNORECASE,
        )

        for raw_line in lines:
            line = cls._normalize_numbers(raw_line)
            # Check rel_days_pattern
            for match in rel_days_pattern.finditer(line):
                event_name = match.group(1).title()
                days = int(match.group(2))
                phrase = f"after {days} days"
                target_dt = ref_date + timedelta(days=days)
                category = "exam" if "test" in event_name.lower() or "exam" in event_name.lower() or "quiz" in event_name.lower() else "deadline"
                key = f"{event_name}_{days}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    events.append(
                        LLMCalendarEvent(
                            title=f"{event_name} Scheduled",
                            relative_time=phrase,
                            days_from_now=days,
                            speaker=cls._find_speaker_for_text(raw_line, turns),
                            context=raw_line,
                            category=category,
                        )
                    )

            # Check days_rel_pattern
            for match in days_rel_pattern.finditer(line):
                days = int(match.group(1))
                event_name = match.group(2).title()
                phrase = f"in {days} days"
                target_dt = ref_date + timedelta(days=days)
                category = "exam" if "test" in event_name.lower() or "exam" in event_name.lower() or "quiz" in event_name.lower() else "deadline"
                key = f"{event_name}_{days}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    events.append(
                        LLMCalendarEvent(
                            title=f"{event_name} Scheduled",
                            relative_time=phrase,
                            days_from_now=days,
                            speaker=cls._find_speaker_for_text(raw_line, turns),
                            context=raw_line,
                            category=category,
                        )
                    )

            # Check tomorrow
            for match in tomorrow_pattern.finditer(line):
                event_name = match.group(1).title()
                key = f"{event_name}_1"
                if key not in seen_keys:
                    seen_keys.add(key)
                    events.append(
                        LLMCalendarEvent(
                            title=f"{event_name} (Tomorrow)",
                            relative_time="tomorrow",
                            days_from_now=1,
                            speaker=cls._find_speaker_for_text(raw_line, turns),
                            context=raw_line,
                            category="deadline",
                        )
                    )

            # Check next week / day
            for match in next_week_pattern.finditer(line):
                event_name = match.group(1).title()
                day_name = match.group(2).title()
                days = 7 if day_name.lower() == "week" else 5
                key = f"{event_name}_{day_name}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    events.append(
                        LLMCalendarEvent(
                            title=f"{event_name} (Next {day_name})",
                            relative_time=f"next {day_name}",
                            days_from_now=days,
                            speaker=cls._find_speaker_for_text(raw_line, turns),
                            context=raw_line,
                            category="meeting",
                        )
                    )

        # 3. Hindi / Hinglish relative dates:
        #    "test 3 din baad hai", "टेस्ट 3 दिन बाद है", "परसों demo", "agle hafte meeting"
        for raw_line in lines:
            line = cls._normalize_numbers(raw_line)
            ev_match = _HI_EVENT_RE.search(line)
            if not ev_match:
                continue
            event_name = _HI_EVENT_TITLES.get(ev_match.group(1).lower(), ev_match.group(1).title())
            days = phrase = None
            m_days = _HI_N_DAYS_RE.search(line)
            if m_days:
                days, phrase = int(m_days.group(1)), m_days.group(0)
            else:
                for rel_re, rel_days in _HI_RELATIVE_WORDS:
                    m_rel = rel_re.search(line)
                    if m_rel:
                        days, phrase = rel_days, m_rel.group(0)
                        break
            if days is None:
                continue
            key = f"{event_name}_{days}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            category = "exam" if event_name.lower() in ("test", "exam", "quiz") else (
                "meeting" if event_name.lower() in ("meeting", "review", "presentation", "demo") else "deadline"
            )
            events.append(
                LLMCalendarEvent(
                    title=f"{event_name} Scheduled",
                    relative_time=phrase,
                    days_from_now=days,
                    speaker=cls._find_speaker_for_text(raw_line, turns),
                    context=raw_line,
                    category=category,
                )
            )

        # Fallback if text mentions "test after 3 days" without exact regex bound
        if not events and re.search(r"test.*after\s+(\d+)\s+days", " ".join(lines), re.IGNORECASE):
            m = re.search(r"test.*after\s+(\d+)\s+days", " ".join(lines), re.IGNORECASE)
            days = int(m.group(1)) if m else 3
            events.append(
                LLMCalendarEvent(
                    title="Course / Subject Test",
                    relative_time=f"after {days} days",
                    days_from_now=days,
                    speaker=turns[0].speaker if turns else "Instructor",
                    context=f"Test announced after {days} days",
                    category="exam",
                )
            )

        return events

    @staticmethod
    def _normalize_numbers(line: str) -> str:
        """'three days' / 'teen din' / 'तीन दिन' / '३ दिन' -> '3 days' / '3 din' / '3 दिन'."""
        line = line.translate(_DEVANAGARI_DIGITS)
        return _NUMBER_WORD_RE.sub(lambda m: f"{_NUMBER_WORDS[m.group(1).lower()]} {m.group(2)}", line)

    @classmethod
    def _find_speaker_for_text(cls, line: str, turns: list[LLMDialogueTurn]) -> str | None:
        for turn in turns:
            if turn.text in line or line in turn.text:
                return turn.speaker
        return turns[0].speaker if turns else None

    @classmethod
    def _extract_action_items(
        cls, lines: list[str], turns: list[LLMDialogueTurn]
    ) -> list[LLMActionItem]:
        action_items: list[LLMActionItem] = []
        # English keywords match on word boundaries ("fix" must not fire on
        # "prefix", "will" not on "willing"); Hindi/Hinglish markers match as
        # phrases because Devanagari has no reliable \b word boundaries in `re`.
        english_action_re = re.compile(
            r"\b(?:will|shall|to do|assigned to|responsible for|needs? to|must prepare|"
            r"have to complete|follow up|work on|take care of|look into|send the|share the|"
            r"create|fix|update|deploy|submit|share|karega|karenge|karegi)\b",
            re.IGNORECASE,
        )

        for line in lines:
            line_lower = line.lower()
            if line.startswith(("- ", "* ", "• ")) and "->" in line:
                continue  # roster line, not speech
            if english_action_re.search(line) or any(m in line_lower for m in HINDI_ACTION_MARKERS):
                # Clean up speaker/timestamp prefix if present
                clean_line = re.sub(r"^(?:\[?\d{1,3}:\d{2}(?::\d{2})?\]?\s*)?(?:\[?[^\]:]+\]?:\s*)?", "", line).strip()
                if len(clean_line) < 10:
                    continue

                # Determine person
                speaker = cls._find_speaker_for_text(line, turns) or "Team"
                NON_PERSON_WORDS = {"there", "here", "it", "this", "that", "we", "you", "they", "someone", "please", "remember", "note", "today", "tomorrow", "also", "just", "now"}
                name_match = re.search(
                    r"\b([A-Z][a-z]+)\s+(?:will|should|to|must|karega|karegi|karenge)\b", clean_line
                )
                if name_match and name_match.group(1).lower() not in NON_PERSON_WORDS:
                    person = name_match.group(1)
                else:
                    person = speaker

                # Check for deadline mention
                deadline = None
                deadline_match = re.search(
                    r"\b(by\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|eod|end of week|next week|\d{1,2}(?:st|nd|rd|th)?)|in\s+\d+\s+days?|after\s+\d+\s+days?)\b",
                    clean_line,
                    re.IGNORECASE,
                )
                if deadline_match:
                    deadline = deadline_match.group(1)
                else:
                    hi_deadline = HINDI_DEADLINE_RE.search(cls._normalize_numbers(clean_line))
                    if hi_deadline:
                        deadline = hi_deadline.group(1)

                task = clean_line
                if len(task) > 200:
                    task = task[:197] + "..."

                action_items.append(
                    LLMActionItem(person=person, task=task, deadline=deadline)
                )
                if len(action_items) >= 10:
                    break

        if not action_items and len(lines) > 0:
            # Default helpful item
            action_items.append(
                LLMActionItem(
                    person=turns[0].speaker if turns else "All Participants",
                    task="Review meeting notes and follow up on agreed objectives.",
                    deadline="Next Sync",
                )
            )

        return action_items

    @classmethod
    def _extract_decisions(cls, lines: list[str]) -> list[str]:
        decisions: list[str] = []
        decision_markers = [
            "decided", "agreed", "settled on", "concluded", "approved", "finalized",
            "we will go with", "moving forward with", "consensus", "resolution",
            *HINDI_DECISION_MARKERS,
        ]

        for line in lines:
            line_lower = line.lower()
            if any(marker in line_lower for marker in decision_markers):
                clean_line = re.sub(r"^(?:\[?\d{1,3}:\d{2}(?::\d{2})?\]?\s*)?(?:\[?[^\]:]+\]?:\s*)?", "", line).strip()
                if clean_line and clean_line not in decisions:
                    decisions.append(clean_line)
                    if len(decisions) >= 5:
                        break

        return decisions[:5]

    @classmethod
    def _extract_keywords(cls, text: str, title: str, names: list[str] | None = None) -> list[str]:
        # Participant names are people, not topics.
        exclude = {part.lower() for n in (names or []) for part in n.split()}
        # Tokenize words (Latin + Devanagari; Python's \w misses Hindi vowel signs)
        words = [w.strip(".-") for w in _WORD_TOKEN_RE.findall(text)]
        freq: dict[str, int] = {}

        # Title words get extra weight
        title_words = {w.strip(".-").lower() for w in _WORD_TOKEN_RE.findall(title)}

        for w in words:
            wl = w.lower()
            if (
                len(wl) < 3
                or wl in STOPWORDS
                or wl in HINDI_STOPWORDS
                or wl in FILLER_WORDS
                or wl in exclude
                or wl.isdigit()
            ):
                continue
            if re.fullmatch(r"(?:usr-?\d+|p\d{2}|speaker)", wl):
                continue  # speaker tags are not topics
            # Capitalized words (e.g. proper nouns, tech names) get higher weight
            weight = 3 if w[0].isupper() else 1
            if wl in title_words:
                weight += 4
            freq[wl] = freq.get(wl, 0) + weight

        # Sort by frequency
        sorted_kws = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        keywords = [k[0] for k in sorted_kws[:15]]

        # Fallback if empty
        if not keywords:
            keywords = ["meeting", "discussion", "planning", "agenda"]

        return keywords

    @classmethod
    def _analyze_sentiment(cls, text: str) -> Sentiment:
        # Count whole tokens — substring matching made "badhiya" (great!) count as "bad".
        tokens = [t.lower().strip(".-") for t in _WORD_TOKEN_RE.findall(text)]
        positive = POSITIVE_WORDS | HINDI_POSITIVE_WORDS
        negative = NEGATIVE_WORDS | HINDI_NEGATIVE_WORDS
        pos_count = sum(1 for t in tokens if t in positive)
        neg_count = sum(1 for t in tokens if t in negative)

        if pos_count > neg_count + 1:
            return "positive"
        elif neg_count > pos_count + 1:
            return "negative"
        return "neutral"

    @classmethod
    def _detect_language(cls, text: str) -> str:
        """Script- and romanised-Hindi-aware detection ("hi" covers Hindi and Hinglish)."""
        return detect_text_language(text)

    @classmethod
    def _generate_summary(
        cls,
        title: str,
        lines: list[str],
        events: list[LLMCalendarEvent],
        decisions: list[str],
        actions: list[LLMActionItem],
        speakers: list[str],
    ) -> str:
        summary_sentences: list[str] = []

        # Opening sentence
        speaker_str = ", ".join(speakers[:3])
        if len(speakers) > 3:
            speaker_str += f" and {len(speakers) - 3} others"

        if title:
            summary_sentences.append(
                f"The meeting covered '{title}' with active participation from {speaker_str}."
            )
        else:
            summary_sentences.append(
                f"The team conducted a focused discussion with contributions from {speaker_str}."
            )

        # Highlight calendar event if present (e.g. test after 3 days)
        if events:
            ev = events[0]
            summary_sentences.append(
                f"Key Announcement: A {ev.title.lower()} is scheduled {ev.relative_time}."
            )

        # Highlight key decision if present
        if decisions:
            summary_sentences.append(f"Decisions made include: {decisions[0]}.")

        # Action items summary
        if actions and actions[0].task != "Review meeting notes and follow up on agreed objectives.":
            task_text = actions[0].task
            if re.search(r"[\u0900-\u097F]", task_text):
                summary_sentences.append(
                    f"Action items and milestones were noted for {actions[0].person} regarding upcoming preparations."
                )
            else:
                summary_sentences.append(
                    f"Action items were assigned to {actions[0].person} to {task_text.lower()}."
                )
        elif not decisions:
            summary_sentences.append(
                "The team reviewed key timelines, upcoming preparations, and agreed next steps."
            )

        return " ".join(summary_sentences)


class SmartLocalQABot:
    """Answers user questions using meeting context when external LLM API is unavailable."""

    @classmethod
    def answer(
        cls,
        question: str,
        summary: str | None,
        decisions: list[str],
        keywords: list[str],
        transcript: str | None,
        action_items: list[Any] | None = None,
        calendar_events: list[Any] | None = None,
        speakers: list[str] | None = None,
    ) -> str:
        q_lower = question.lower().strip()

        # 1. Test / Exam / Quiz / Deadline / Calendar Questions
        if any(term in q_lower for term in ["test", "exam", "quiz", "calendar", "schedule", "deadline", "when is"]):
            if calendar_events:
                ev_lines = []
                for ev in calendar_events:
                    title = getattr(ev, "title", str(ev))
                    rel = getattr(ev, "relative_time", "")
                    date = getattr(ev, "formatted_date", "")
                    ctx = getattr(ev, "context", "")
                    speaker = getattr(ev, "speaker", "Instructor")
                    ev_lines.append(f"• **{title}**: Scheduled {rel} ({date}). Context: \"{ctx}\" (announced by {speaker}).")
                return "Here are the scheduled events and tests from this meeting:\n\n" + "\n".join(ev_lines)

            # Fallback search in transcript
            if transcript and re.search(r"(?:test|exam|quiz)\s+(?:is\s+)?(?:after|in)\s+(\d+)\s+days?", transcript, re.IGNORECASE):
                m = re.search(r"(?:test|exam|quiz)\s+(?:is\s+)?(?:after|in)\s+(\d+)\s+days?", transcript, re.IGNORECASE)
                days = m.group(1) if m else "3"
                return f"Yes! A test was announced in the meeting to be held **after {days} days**. Please check your syllabus and calendar accordingly."

        # 2. Decision Questions
        if any(term in q_lower for term in ["decision", "decided", "agree", "conclude", "outcome"]):
            if decisions:
                return "The following decisions were made during the meeting:\n\n" + "\n".join(f"• {d}" for d in decisions)
            return "No formal decisions were explicitly finalized in this session."

        # 3. Action Items / Tasks / Who does what
        if any(term in q_lower for term in ["action item", "task", "todo", "assigned", "who will", "who is doing"]):
            if action_items:
                task_lines = []
                for item in action_items:
                    person = getattr(item, "person", "Someone")
                    task = getattr(item, "task", "")
                    dl = getattr(item, "deadline", None)
                    deadline_str = f" (Deadline: {dl})" if dl else ""
                    task_lines.append(f"• **{person}**: {task}{deadline_str}")
                return "Here are the action items assigned in this meeting:\n\n" + "\n".join(task_lines)
            return "No pending action items were identified in this meeting."

        # 4. Speaker / Who spoke questions
        if any(term in q_lower for term in ["who spoke", "speaker", "participant", "who attended"]):
            if speakers:
                return f"The detected participants in this meeting are: **{', '.join(speakers)}**."

        # 5. Summary / Overview questions
        if any(term in q_lower for term in ["summary", "summarize", "overview", "what happened", "what was discussed"]):
            if summary:
                return f"**Meeting Summary:**\n\n{summary}"

        # 6. Keywords / Topics questions
        if any(term in q_lower for term in ["keyword", "topic", "subject", "theme"]):
            if keywords:
                return f"Key topics discussed: **{', '.join(keywords)}**."

        # 7. Semantic sentence search in transcript
        if transcript:
            q_tokens = [w for w in re.findall(r"\b\w{3,}\b", q_lower) if w not in STOPWORDS]
            lines = [l.strip() for l in transcript.split("\n") if l.strip()]

            scored_lines: list[tuple[int, str]] = []
            for line in lines:
                line_lower = line.lower()
                score = sum(1 for t in q_tokens if t in line_lower)
                if score > 0:
                    scored_lines.append((score, line))

            scored_lines.sort(key=lambda x: x[0], reverse=True)
            if scored_lines:
                best_matches = [line for _, line in scored_lines[:3]]
                return (
                    f"Based on the meeting transcript:\n\n"
                    + "\n\n".join(f"> \"{match}\"" for match in best_matches)
                )

        # 8. Friendly default
        if summary:
            return (
                f"Regarding your question, here is what the meeting notes indicate:\n\n"
                f"{summary}\n\n"
                f"Key topics discussed: {', '.join(keywords[:5])}."
            )

        return "I reviewed the meeting records, but could not find specific details matching that question. Please try asking about the summary, decisions, action items, or scheduled tests."
