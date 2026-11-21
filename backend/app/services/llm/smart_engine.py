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
from app.services.llm.schemas import (
    ExtractionResult,
    LLMActionItem,
    LLMCalendarEvent,
    LLMDialogueTurn,
)

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
    "well", "hello", "hi", "hey", "thanks", "thank", "meeting", "everyone", "today",
    # Hindi Stopwords
    "है", "हैं", "हो", "का", "की", "के", "में", "से", "पर", "और", "तो", "यह", "वह",
    "था", "थी", "थे", "भी", "ने", "को", "एक", "किया", "गया", "कर", "दिया", "रहा", "रही", "रहे",
    "aap", "hum", "main", "yeh", "woh", "hai", "hain", "kya", "tha", "thi", "the"
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

        # Pattern 1: ID (Name) e.g. USR-101 (Sarah Chen) or P01 (Sarah Chen)
        m1 = re.match(r"^([A-Za-z]+[-_]?\d+|\d{4,})\s*\(([^)]+)\)$", label)
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
            r"^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*)?(?:\[?([^:\[\]]+?)\]?):\s*(.+)$"
        )

        for line in lines:
            # Skip obvious dialogue turns with timestamps when checking roster_arrow
            if not re.match(r"^\[?\d{1,2}:\d{2}", line):
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

            # 2. Inline labels & self-introductions in dialogue turns
            m_turn = turn_pattern.match(line)
            if m_turn:
                raw_label = m_turn.group(2).strip()
                text = m_turn.group(3).strip()
                if len(raw_label) > 50 or raw_label.lower() in cls._HEADER_IGNORE:
                    continue

                pid, name = cls._split_inline_id_and_name(raw_label)
                if pid and name and name != pid:
                    speaker_map[pid] = name
                elif pid and pid not in speaker_map:
                    # Check self-introductions in English, Hindi, and Devanagari
                    intro = re.search(
                        r"\b(?:I'm|I am|this is|my name is|speaking is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
                        text,
                        flags=re.IGNORECASE,
                    )
                    if not intro:
                        intro = re.search(
                            r"(?:मेरा\s+नाम|मैं\s+हूँ|मैं)\s+([\u0900-\u097F]+)(?:\s+हूँ|\s+है|\s+बोल)?",
                            text,
                        )
                    if not intro:
                        intro = re.search(
                            r"\b(?:mera\s+naam|mai|main)\s+([A-Z][a-z]+)\b",
                            text,
                            flags=re.IGNORECASE,
                        )
                    if intro:
                        speaker_map[pid] = intro.group(1).strip()

        # 3. Associate conversational partners from direct addresses or handoffs
        # e.g., "So hello, Nishal" spoken by USR-101 -> the other speaker USR-102 is Nishal!
        if len(speaker_map) < 10:
            for line in lines:
                m_turn = turn_pattern.match(line)
                if not m_turn:
                    continue
                raw_label = m_turn.group(2).strip()
                text = m_turn.group(3).strip()
                pid, _ = cls._split_inline_id_and_name(raw_label)
                if not pid:
                    continue

                greet_match = re.search(
                    r"\b(?:hello|hi|hey|thanks|thank you|assignment to|over to)\s*,?\s+([A-Z][a-z]+)\b",
                    text,
                    flags=re.IGNORECASE,
                )
                if greet_match:
                    addressed_name = greet_match.group(1).strip()
                    if addressed_name.lower() in ("everyone", "guys", "bro", "all", "sir", "maam", "team", "there"):
                        continue
                    if pid in speaker_map and speaker_map[pid].lower() == addressed_name.lower():
                        continue
                    for other_line in lines:
                        m_other = turn_pattern.match(other_line)
                        if m_other:
                            other_pid, _ = cls._split_inline_id_and_name(m_other.group(2).strip())
                            if other_pid and other_pid != pid and (other_pid not in speaker_map or speaker_map[other_pid] == other_pid):
                                speaker_map[other_pid] = addressed_name
                                break

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
            r"^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*)?(?:\[?([^:\[\]]+?)\]?):\s*(.+)$"
        )

        # Roster lines that shouldn't be treated as spoken dialogue turns
        roster_line_re = re.compile(
            r"^(?:[-*•]\s*)?(?:(?:Participant|Person|User|Speaker)?\s*(?:ID)?[:\s]*)?([A-Za-z]+[-_]?\d+|Speaker\s+\d+|SPEAKER_\d+|\d{4,})\s*(?:->|=>|=|:|\|)\s*([A-Za-z][A-Za-z\s\.\-]{1,40}?)(?:\s*\([^)]+\))?$",
            re.IGNORECASE,
        )

        for line in lines:
            # Skip explicit roster mapping lines from dialogue turns
            if not re.match(r"^\[?\d{1,2}:\d{2}", line):
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
        platform_lower = (platform or "").lower()
        title_lower = (meeting_title or "").lower()
        transcript_lower = cleaned_transcript.lower()

        is_zoom = bool(
            "zoom" in platform_lower
            or "zoom" in title_lower
            or "zoom" in transcript_lower
            or "usr-" in transcript_lower
        )
        is_google_meet = bool(
            "meet" in platform_lower
            or "google meet" in title_lower
            or "google meet" in transcript_lower
            or "meet.google" in transcript_lower
            or bool(re.search(r"\bP0\d\b", cleaned_transcript))
        )

        # Ensure Zoom (USR-xxx) or Google Meet (P0x) tag IDs are assigned to every participant
        if is_zoom or is_google_meet:
            prefix = "USR-" if is_zoom else "P"
            start_num = 101 if is_zoom else 1
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
                    candidate = f"{prefix}{tag_counter}" if is_zoom else f"{prefix}{tag_counter:02d}"
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
        keywords = cls._extract_keywords(cleaned_transcript, meeting_title)

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
        # e.g. "25th of November", "25th November", "November 25", "Nov 25", "submit on 25 Nov", "25 नवंबर"
        months_map = {
            "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
            "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
            "nov": 11, "november": 11, "dec": 12, "december": 12,
            # Hindi / Devanagari months
            "जनवरी": 1, "फ़रवरी": 2, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6,
            "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "अक्टूबर": 10, "नवंबर": 11, "दिसंबर": 12
        }
        explicit_date_1 = re.compile(
            r"\b(?:on\s+(?:the\s+)?)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
            re.IGNORECASE,
        )
        explicit_date_2 = re.compile(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            re.IGNORECASE,
        )
        hi_date_1 = re.compile(
            r"(\d{1,2})\s*(?:तारीख|तारीख़|ko|\s)?\s*(जनवरी|फ़रवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर)",
            re.IGNORECASE,
        )
        hi_date_2 = re.compile(
            r"(जनवरी|फ़रवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर)\s*(\d{1,2})",
            re.IGNORECASE,
        )

        for line in lines:
            m_exp = (
                explicit_date_1.search(line)
                or explicit_date_2.search(line)
                or hi_date_1.search(line)
                or hi_date_2.search(line)
            )
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
                    elif "exam" in full_corpus or "test" in full_corpus or "quiz" in full_corpus:
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

        for line in lines:
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
                            speaker=cls._find_speaker_for_text(line, turns),
                            context=line,
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
                            speaker=cls._find_speaker_for_text(line, turns),
                            context=line,
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
                            speaker=cls._find_speaker_for_text(line, turns),
                            context=line,
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
                            speaker=cls._find_speaker_for_text(line, turns),
                            context=line,
                            category="meeting",
                        )
                    )

            # Check Hindi relative days: e.g. "3 दिन बाद"
            m_hi_days = re.search(r"(\d+)\s*दिन\s*बाद", line)
            if m_hi_days:
                days = int(m_hi_days.group(1))
                key = f"hi_days_{days}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    events.append(
                        LLMCalendarEvent(
                            title="निर्धारित परीक्षा / कार्यक्रम",
                            relative_time=f"{days} दिन बाद",
                            days_from_now=days,
                            speaker=cls._find_speaker_for_text(line, turns),
                            context=line,
                            category="exam",
                        )
                    )

            # Check Hindi tomorrow: "कल"
            if "कल" in line and any(w in line for w in ("परीक्षा", "टेस्ट", "मीटिंग", "सबमिशन", "exam", "test", "quiz", "meeting")):
                key = "hi_tomorrow_1"
                if key not in seen_keys:
                    seen_keys.add(key)
                    events.append(
                        LLMCalendarEvent(
                            title="निर्धारित परीक्षा / बैठक (कल)",
                            relative_time="कल (Tomorrow)",
                            days_from_now=1,
                            speaker=cls._find_speaker_for_text(line, turns),
                            context=line,
                            category="deadline",
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
        action_keywords = [
            "will", "shall", "to do", "assigned to", "responsible for", "needs to",
            "must prepare", "have to complete", "follow up", "work on", "take care of",
            "look into", "send the", "share the", "create", "fix", "update", "deploy",
            "karega", "karenge", "karegi", "kar dunga", "kar dungi", "submit", "share",
            "karna hai", "karna hoga", "karna padega", "bhejna", "dekhna",
            # Devanagari Action Keywords
            "करना है", "करेगा", "करेंगे", "करेगी", "कर देना", "करना पड़ेगा", "सबमिट",
            "तैयार", "भेजना", "अपडेट", "पढ़ना", "देखना", "पूरा करना", "फाइनल करना", "करना"
        ]

        turn_speaker_map = {}
        for turn in turns:
            turn_speaker_map[turn.text.strip()] = turn.speaker

        for line in lines:
            line_lower = line.lower()
            if any(kw in line_lower for kw in action_keywords):
                # Clean up speaker/timestamp prefix if present
                clean_line = re.sub(r"^(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(?:\[?[^\]:]+\]?:\s*)?", "", line).strip()
                if len(clean_line) < 10:
                    continue

                # Determine person
                speaker = cls._find_speaker_for_text(line, turns) or "Team"
                NON_PERSON_WORDS = {"there", "here", "it", "this", "that", "we", "you", "they", "someone", "please", "remember", "note", "today", "tomorrow", "also", "just", "now"}
                name_match = re.search(r"\b([A-Z][a-z]+)\s+(?:will|should|to|must)\b", clean_line)
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
            "decide kiya", "tay kiya", "faisla",
            # Devanagari Decision Markers
            "तय हुआ", "तय किया", "फैसला", "फाइनल", "अंतिम निर्णय", "निर्णय लिया", "सहमति", "निश्चय"
        ]

        for line in lines:
            line_lower = line.lower()
            if any(marker in line_lower for marker in decision_markers):
                clean_line = re.sub(r"^(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(?:\[?[^\]:]+\]?:\s*)?", "", line).strip()
                if clean_line and clean_line not in decisions:
                    decisions.append(clean_line)
                    if len(decisions) >= 5:
                        break

        if not decisions:
            # Extract first high-confidence declarative statement
            for line in lines:
                clean_line = re.sub(r"^(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(?:\[?[^\]:]+\]?:\s*)?", "", line).strip()
                if len(clean_line) > 20 and not clean_line.endswith("?"):
                    decisions.append(clean_line)
                    break

        return decisions[:5]

    @classmethod
    def _extract_keywords(cls, text: str, title: str) -> list[str]:
        # Tokenize English and Devanagari words
        words = re.findall(r"[\u0900-\u097F]{2,25}|\b[A-Za-z0-9_\-\.]{3,25}\b", text)
        freq: dict[str, int] = {}

        # Title words get extra weight
        title_words = set(re.findall(r"[\u0900-\u097F]{2,25}|\b[A-Za-z0-9_\-\.]{3,25}\b", title.lower()))

        for w in words:
            wl = w.strip("।॥,.-_!?:;\"'()[]{}").lower()
            if not wl or wl in STOPWORDS or wl.isdigit() or len(wl) < 2:
                continue
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
        text_lower = text.lower()
        pos_count = sum(1 for w in POSITIVE_WORDS if w in text_lower)
        neg_count = sum(1 for w in NEGATIVE_WORDS if w in text_lower)

        if pos_count > neg_count + 1:
            return "positive"
        elif neg_count > pos_count + 1:
            return "negative"
        return "neutral"

    @classmethod
    def _detect_language(cls, text: str) -> str:
        # Check Devanagari script for Hindi/Gujarati/Marathi/Sanskrit
        if re.search(r"[\u0900-\u097F]", text):
            return "hi"
        # Check Gujarati script
        if re.search(r"[\u0A80-\u0AFF]", text):
            return "gu"
        # Check Spanish markers (ñ, ¿, ¡, á, é, í, ó, ú)
        if re.search(r"[¿¡áéíóúñÁÉÍÓÚÑ]", text):
            return "es"
        # Check French markers (ç, è, é, à, ù, œ)
        if re.search(r"[œçèéàùêîôâ]", text):
            return "fr"
        # Check German markers (ä, ö, ü, ß)
        if re.search(r"[äöüßÄÖÜ]", text):
            return "de"
        return "en"

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

        # Highlight key decision or dialogue point
        if decisions:
            summary_sentences.append(f"Decisions made include: {decisions[0]}.")
        elif len(lines) > 2:
            clean_pt = re.sub(r"^(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(?:\[?[^\]:]+\]?:\s*)?", "", lines[1]).strip()
            if clean_pt:
                summary_sentences.append(f"Major discussion points centered on: {clean_pt}.")

        # Action items summary
        if actions:
            summary_sentences.append(
                f"Action items were assigned to {actions[0].person} to {actions[0].task.lower()}."
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
