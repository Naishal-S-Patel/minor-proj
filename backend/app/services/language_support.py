"""
Language support for English, Hindi and Hinglish (code-mixed Hindi-English).

  * normalize_language(): maps the upload form's language choice to a
    transcription "mode" and the Whisper language code to force.
  * choose_auto_language(): picks a mode from Whisper's language
    probabilities. Whisper frequently labels spoken Hindi as Urdu (and then
    writes Urdu script), so Urdu is folded into Hindi; mixed English/Hindi
    speech is routed to Hinglish mode.
  * initial_prompt(): Whisper "style" prompts. Whisper imitates the script
    and spelling of its prompt, so a romanised Hinglish prompt yields
    romanised output, a Devanagari prompt yields Devanagari, and listing
    participant names fixes their spelling.
  * is_hallucination(): filters Whisper's well-known silence hallucinations
    ("Thanks for watching", repeated phrases, ...).
  * transliterate_devanagari(): Devanagari -> readable Latin, used in
    Hinglish mode if Whisper still emits Devanagari.
  * detect_text_language(): en / hi detection for typed transcripts,
    including romanised Hindi.
"""

from __future__ import annotations

import re

LANG_AUTO = "auto"
LANG_EN = "en"
LANG_HI = "hi"
LANG_HINGLISH = "hinglish"

# Whisper language codes that are, for transcription purposes, spoken Hindi.
_HINDI_LIKE = {"hi", "ur"}


def normalize_language(language: str | None) -> tuple[str, str | None]:
    """
    Returns (mode, whisper_language).
        mode: "auto" | "en" | "hi" | "hinglish" | any other ISO code
        whisper_language: code to force in Whisper, or None for auto-detect
    """
    lang = (language or "").strip().lower()
    if lang in ("", "auto", "none", "detect"):
        return LANG_AUTO, None
    if lang in ("en", "english", "en-us", "en-gb", "en-in"):
        return LANG_EN, "en"
    if lang in ("hi", "hindi", "hi-in", "हिन्दी", "हिंदी", "ur"):
        return LANG_HI, "hi"
    if lang in ("hinglish", "hi-latn", "hi_en", "hien", "mixed", "en-hi"):
        return LANG_HINGLISH, "hi"
    return lang, lang


def choose_auto_language(probs: dict[str, float]) -> tuple[str, str]:
    """
    Given Whisper's language probabilities, returns (mode, whisper_language).
    """
    if not probs:
        return LANG_EN, "en"
    p_en = probs.get("en", 0.0)
    p_hi = sum(probs.get(code, 0.0) for code in _HINDI_LIKE)
    top, p_top = max(probs.items(), key=lambda kv: kv[1])

    # Another language clearly dominates (e.g. Spanish, Gujarati) — respect it.
    if top not in _HINDI_LIKE and top != "en" and p_top > max(p_en, p_hi):
        return top, top
    # Genuinely mixed speech -> Hinglish (romanised, readable for everyone).
    if p_en >= 0.2 and p_hi >= 0.2:
        return LANG_HINGLISH, "hi"
    if p_hi > p_en:
        return LANG_HI, "hi"
    return LANG_EN, "en"


def stored_language_code(mode: str) -> str:
    """Language code persisted on the meeting (Hinglish is stored as Hindi)."""
    return LANG_HI if mode == LANG_HINGLISH else mode


_PROMPTS = {
    LANG_EN: "Hello everyone, welcome to the meeting. Let's go through the agenda, decisions and action items.",
    LANG_HI: "नमस्ते सभी, आज की मीटिंग में हम प्रोजेक्ट, डेडलाइन और एक्शन आइटम्स पर चर्चा करेंगे।",
    LANG_HINGLISH: (
        "नमस्ते टीम, आज की मीटिंग में हम प्रोजेक्ट, डेडलाइन और जरूरी बातों पर चर्चा करेंगे। "
        "मैं कल तक रिपोर्ट शेयर kar dunga, और टेस्टिंग पूरी हो जाएगी। ठीक है?"
    ),
}


def initial_prompt(mode: str, names: list[str] | None = None, context: str = "") -> str | None:
    """Builds Whisper's initial_prompt (kept well under Whisper's 224-token prompt limit)."""
    parts: list[str] = []
    if mode in _PROMPTS:
        parts.append(_PROMPTS[mode])
    if names:
        parts.append("Participants: " + ", ".join(names[:12]) + ".")
    if context:
        parts.append(context[-200:])
    prompt = " ".join(parts).strip()
    return prompt or None


# --------------------------------------------------------------------------- #
# Hallucination filtering
# --------------------------------------------------------------------------- #

_HALLUCINATION_PHRASES = {
    "thank you for watching", "thanks for watching", "please subscribe",
    "subscribe to my channel", "like and subscribe", "see you in the next video",
    "thank you so much for watching", "subtitles by", "transcribed by",
    "please like share and subscribe", "amara.org",
    "धन्यवाद", "देखने के लिए धन्यवाद", "सब्सक्राइब",
}


def _norm(text: str) -> str:
    return re.sub(r"[^\w\sऀ-ॿ]", "", text.lower()).strip()


def is_hallucination(text: str, segment: dict) -> bool:
    """True for segments that are almost certainly Whisper hallucinations."""
    t = _norm(text)
    if not t:
        return True
    no_speech = float(segment.get("no_speech_prob", 0.0) or 0.0)
    avg_logprob = float(segment.get("avg_logprob", 0.0) or 0.0)
    compression = float(segment.get("compression_ratio", 1.0) or 1.0)

    if no_speech > 0.6 and avg_logprob < -1.0:
        return True
    if compression > 2.6:  # degenerate repetition loop
        return True
    if any(p in t for p in _HALLUCINATION_PHRASES) and (no_speech > 0.25 or len(t.split()) <= 6):
        return True
    words = t.split()
    if len(words) >= 8 and len(set(words)) / len(words) < 0.25:
        return True
    return False


# --------------------------------------------------------------------------- #
# Devanagari -> Latin transliteration (for Hinglish mode)
# --------------------------------------------------------------------------- #

_INDEPENDENT_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ॲ": "e",
}
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}
_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh",
    "ज": "j", "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh",
    "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p",
    "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l",
    "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "rh", "फ़": "f", "य़": "y",
}
_NUKTA_FORMS = {"क": "क़", "ख": "ख़", "ग": "ग़", "ज": "ज़", "ड": "ड़", "ढ": "ढ़", "फ": "फ़", "य": "य़"}
_SIGNS = {"ं": "n", "ँ": "n", "ः": "h", "।": ".", "॥": ".", "ॐ": "om"}
_VIRAMA = "्"
_NUKTA = "़"
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def transliterate_devanagari(text: str) -> str:
    """Rough, readable Devanagari -> Latin (e.g. 'मैं कल तक कर दूंगा' -> 'main kal tak kar doonga')."""
    if not re.search(r"[ऀ-ॿ]", text):
        return text
    text = text.translate(_DIGITS)
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if i + 1 < n and text[i + 1] == _NUKTA and ch in _NUKTA_FORMS:
            ch = _NUKTA_FORMS[ch]
            i += 1
        if ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
            nxt = text[i + 1] if i + 1 < n else ""
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                i += 2
                continue
            if nxt == _VIRAMA:
                i += 2
                continue
            # Inherent 'a' — dropped at the end of a word (Hindi schwa deletion).
            if nxt and re.match(r"[ऀ-ॿ]", nxt) and nxt not in _SIGNS or nxt in ("ं", "ँ"):
                out.append("a")
            i += 1
            continue
        if ch in _INDEPENDENT_VOWELS:
            out.append(_INDEPENDENT_VOWELS[ch])
        elif ch in _SIGNS:
            out.append(_SIGNS[ch])
        elif ch in _MATRAS:
            out.append(_MATRAS[ch])
        elif ch in (_VIRAMA, _NUKTA, "‌", "‍"):
            pass
        else:
            out.append(ch)
        i += 1
    latin = "".join(out)
    # Common Hinglish spelling: word-final long vowels are written short
    # ("gayaa" -> "gaya", "kyaa" -> "kya", "zarooree" -> "zaroori").
    latin = re.sub(r"aa\b", "a", latin)
    latin = re.sub(r"ee\b", "i", latin)
    return latin


# --------------------------------------------------------------------------- #
# Text language detection (typed transcripts / post-transcription)
# --------------------------------------------------------------------------- #

# High-frequency romanised Hindi function words — rarely English words.
_HINGLISH_MARKERS = {
    "hai", "hain", "nahi", "nahin", "kya", "kyun", "kaise", "kaisa", "mein", "hum", "humne",
    "aap", "tum", "mujhe", "humein", "karna", "karenge", "karega", "karegi", "kar", "kiya",
    "dunga", "dungi", "raha", "rahi", "rahe", "tha", "thi", "aur", "lekin", "matlab", "accha",
    "acha", "theek", "thik", "haan", "bhi", "toh", "yeh", "woh", "kal", "aaj", "abhi",
    "kuch", "sab", "bahut", "bohot", "badhiya", "chahiye", "hoga", "hogi", "gaya", "gayi",
    "liye", "baad", "pehle", "wala", "wali", "ke", "ki", "ka", "ko", "se", "par",
}


def detect_text_language(text: str) -> str:
    """Returns an ISO-ish code for the dominant language of a transcript."""
    if not text:
        return "en"
    deva = len(re.findall(r"[ऀ-ॿ]", text))
    guj = len(re.findall(r"[઀-૿]", text))
    arabic = len(re.findall(r"[؀-ۿ]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    letters = deva + guj + arabic + latin or 1

    if guj / letters > 0.2:
        return "gu"
    if (deva + arabic) / letters > 0.15:
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    if words:
        hits = sum(1 for w in words if w in _HINGLISH_MARKERS)
        if hits / len(words) >= 0.12 and hits >= 3:
            return "hi"
    if re.search(r"[¿¡ñÑ]", text):
        return "es"
    if re.search(r"[äöüßÄÖÜ]", text):
        return "de"
    if re.search(r"[œçèàùêîôâ]", text):
        return "fr"
    return "en"
