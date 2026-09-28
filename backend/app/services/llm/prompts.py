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
EXTRACTION_PROMPT_V1 = """You are an AI meeting assistant. You will be given a cleaned meeting transcript. Extract structured information from it and respond with ONLY a single JSON object -- no markdown code fences, no preamble, no explanation, just the raw JSON.

The JSON object must have exactly these fields:

{{
  "summary": "A concise 2-4 sentence summary of what was discussed and decided.",
  "action_items": [
    {{"person": "Name of who is responsible", "task": "What they need to do", "deadline": "When it's due, or null if not stated"}}
  ],
  "decisions": ["A concrete decision that was made", "..."],
  "keywords": ["short-topic-keyword", "..."],
  "sentiment": "positive" | "neutral" | "negative"
}}

Rules:
- Only extract action items that are clearly assigned to a specific named person. Do not invent a person if the transcript doesn't name one.
- Only include decisions that were actually settled/agreed upon in the transcript, not open questions or things still being discussed.
- deadline should be null if no deadline was stated, not a guessed date.
- keywords should be short (1-3 words each), at most 15 total, and drawn from actual topics/technologies/projects mentioned.
- sentiment reflects the overall tone of the meeting: "positive" for productive/upbeat, "negative" for tense/frustrated, "neutral" otherwise.
- If the transcript is too short or unclear to extract something meaningful, use an empty list (for action_items/decisions/keywords) rather than fabricating content.

Transcript:
---
{transcript}
---

Respond with ONLY the JSON object described above."""


def build_extraction_prompt(cleaned_transcript: str) -> str:
    """
    Returns the fully-formed prompt for a given transcript.

    A thin wrapper function (rather than callers formatting the constant
    directly) so the call site reads as intent ("build a prompt for this
    transcript") and so we have one place to swap prompt versions later
    (e.g. build_extraction_prompt could pick V1 vs V2 based on config).
    """
    return EXTRACTION_PROMPT_V1.format(transcript=cleaned_transcript)


CHAT_PROMPT_V1 = """You are a Q&A assistant for a specific meeting. Answer the user's question \
using ONLY the information in the meeting content below. If the answer isn't \
in the content, say "I don't have enough information in this meeting to answer that." \
Do not guess or use outside knowledge.

--- Meeting Summary ---
{summary}

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
) -> str:
    """
    Returns the fully-formed chat prompt for a given question and meeting context.

    A thin wrapper following the same versioning pattern as build_extraction_prompt.
    """
    return CHAT_PROMPT_V1.format(
        question=question,
        summary=summary or "No summary available.",
        decisions="\n".join(decisions) if decisions else "None recorded.",
        keywords=", ".join(keywords) if keywords else "None recorded.",
        transcript=transcript or "Not available.",
    )
