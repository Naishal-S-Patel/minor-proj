"""
LLM prompt templates for meeting extraction.

Kept in its own file, separate from the client and extraction service, so
that iterating on prompt wording is a focused, single-file diff -- changing
how well the LLM extracts action items shouldn't require touching any code
that calls the API or parses its response.

Versioned by function name (EXTRACTION_PROMPT_V1) rather than by mutating
this constant in place, so that if a future prompt revision needs
comparison/rollback (e.g. A/B testing prompt quality), older versions stay
available side-by-side rather than being overwritten with no history.
"""

# The schema description embedded in the prompt is intentionally written in
# plain English, not as literal JSON-schema syntax -- LLMs generally follow
# a clearly-described example structure more reliably than a formal schema
# dump, and the actual validation of correctness happens afterward via
# ExtractionResult (a Pydantic model), not by trusting the LLM's compliance.
EXTRACTION_PROMPT_V1 = """You are an AI meeting assistant with multilingual and calendar intelligence. You will be given a cleaned meeting transcript. Extract structured information from it and respond with ONLY a single JSON object -- no markdown code fences, no preamble, no explanation, just the raw JSON.

The transcript may contain Person IDs or speaker labels such as [P01]: text, [USR-101]: text, [MEE001]: text, [Speaker 1]: text, or Person Name: text, or participant rosters (e.g. "P01 -> Sarah Chen" or "USR-101 (Sarah Chen)"), and timestamps like [00:15].
Always map every Person ID / Speaker ID to the person's actual Speaker Name using any participant list/header OR conversational cues (e.g. "Hi, I'm Sarah" or "Alex, can you handle..."). If no real name exists, map the ID to a clean label like the ID itself.
Use the mapped Speaker Name consistently in action_items, calendar_events, speakers, and dialogue_turns, while preserving the original ID in speaker_map and dialogue_turns[].speaker_id.

Multi-language instructions:
If the meeting is in Hindi, Spanish, French, Gujarati, German, or any other language, keep summaries, action items, and keywords accurate, preserving speaker names and providing helpful English explanations or native terms where relevant.

The JSON object must have exactly these fields:

{{
  "summary": "A concise 2-4 sentence executive summary of what was discussed, decided, and announced.",
  "action_items": [
    {{"person": "Mapped Speaker Name of who is responsible", "task": "What they need to do", "deadline": "When it's due, or null if not stated"}}
  ],
  "decisions": ["A concrete decision that was made", "..."],
  "keywords": ["short-topic-keyword", "..."],
  "sentiment": "positive" | "neutral" | "negative",
  "speakers": ["Mapped Speaker Name 1", "Mapped Speaker Name 2"],
  "speaker_map": {{"P01": "Mapped Speaker Name 1", "P02": "Mapped Speaker Name 2"}},
  "calendar_events": [
    {{"title": "Event or Test name e.g. Test / Exam / Demo", "relative_time": "e.g. after 3 days / next Friday", "days_from_now": 3, "speaker": "Mapped Speaker Name who scheduled it", "context": "quote from transcript", "category": "exam" | "deadline" | "meeting"}}
  ],
  "dialogue_turns": [
    {{"speaker": "Mapped Speaker Name", "speaker_id": "Original Person ID or Speaker ID e.g. P01, USR-101, Speaker 1", "time": "00:15 or null", "text": "What they said"}}
  ],
  "detected_language": "en" | "hi" | "es" | "fr" | "de" | "gu" | "other"
}}

Rules:
- Person ID to Speaker Mapping: Populate speaker_map with every Person ID / Speaker ID found in the transcript mapped to their real Speaker Name (e.g. {{"USR-101": "Sarah Chen", "USR-102": "Alex Rivera"}} or {{"Speaker 1": "Sarah Chen"}}). Use the mapped Speaker Name in dialogue_turns[].speaker, action_items[].person, calendar_events[].speaker, and speakers[]. Keep the original ID in dialogue_turns[].speaker_id.
- Calendar & Test Detection: If anyone mentions a test, exam, quiz, submission, demo, or deadline scheduled in the future (such as 'test after 3 days', 'exam in 2 weeks', 'submission next Monday'), create an entry in calendar_events with estimated days_from_now and category ('exam', 'deadline', etc.).
- Only extract action items clearly assigned to a person or speaker.
- Only include decisions that were agreed upon.
- keywords should be high-signal topics/technologies (at most 15).
- sentiment reflects the overall tone.
- speakers should list all unique mapped participant names or speaker labels found.

Transcript:
---
{transcript}
---

Respond with ONLY the JSON object described above."""


def build_extraction_prompt(cleaned_transcript: str) -> str:
    """Returns the fully-formed prompt for a given transcript."""
    return EXTRACTION_PROMPT_V1.format(transcript=cleaned_transcript)


CHAT_PROMPT_V1 = """You are a helpful, accurate Q&A assistant for a specific meeting. Answer the user's question \
using the meeting content below. If asked about tests, deadlines, or dates, check both the Calendar Events \
and Full Transcript sections.

--- Meeting Summary ---
{summary}

--- Calendar & Scheduled Events ---
{calendar_events}

--- Action Items ---
{action_items}

--- Decisions ---
{decisions}

--- Keywords ---
{keywords}

--- Full Transcript ---
{transcript}

--- Question ---
{question}

Answer:"""


def build_chat_prompt(
    question: str,
    summary: str | None,
    decisions: list[str],
    keywords: list[str],
    transcript: str | None,
    action_items: list | None = None,
    calendar_events: list | None = None,
) -> str:
    """Returns the fully-formed chat prompt for a given question and meeting context."""
    events_str = "None recorded."
    if calendar_events:
        events_str = "\n".join(
            f"- {getattr(e, 'title', str(e))}: {getattr(e, 'relative_time', '')} ({getattr(e, 'formatted_date', '')}) - {getattr(e, 'context', '')}"
            for e in calendar_events
        )

    actions_str = "None recorded."
    if action_items:
        actions_str = "\n".join(
            f"- {getattr(a, 'person', '')}: {getattr(a, 'task', '')} (Deadline: {getattr(a, 'deadline', 'None')})"
            for a in action_items
        )

    return CHAT_PROMPT_V1.format(
        question=question,
        summary=summary or "No summary available.",
        calendar_events=events_str,
        action_items=actions_str,
        decisions="\n".join(decisions) if decisions else "None recorded.",
        keywords=", ".join(keywords) if keywords else "None recorded.",
        transcript=transcript or "Not available.",
    )
