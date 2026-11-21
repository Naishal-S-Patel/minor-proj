"""Unit tests for English / Hindi / Hinglish language helpers."""

from app.services.language_support import (
    choose_auto_language,
    detect_text_language,
    initial_prompt,
    is_hallucination,
    normalize_language,
    transliterate_devanagari,
)


def test_normalize_language():
    assert normalize_language("auto") == ("auto", None)
    assert normalize_language(None) == ("auto", None)
    assert normalize_language("en") == ("en", "en")
    assert normalize_language("hi") == ("hi", "hi")
    assert normalize_language("Hinglish") == ("hinglish", "hi")
    assert normalize_language("gu") == ("gu", "gu")


def test_auto_language_folds_urdu_into_hindi_and_detects_mixed():
    # Whisper often labels spoken Hindi as Urdu.
    assert choose_auto_language({"ur": 0.5, "hi": 0.3, "en": 0.1}) == ("hi", "hi")
    assert choose_auto_language({"en": 0.55, "hi": 0.3}) == ("hinglish", "hi")
    assert choose_auto_language({"en": 0.95}) == ("en", "en")
    assert choose_auto_language({"es": 0.7, "en": 0.2}) == ("es", "es")


def test_transliteration_is_readable_hinglish():
    assert transliterate_devanagari("मैं कल तक कर दूंगा") == "main kal tak kar doonga"
    assert transliterate_devanagari("समझ गया") == "samajh gaya"
    assert transliterate_devanagari("टेस्ट ३ दिन बाद") == "test 3 din baad"
    assert transliterate_devanagari("already latin") == "already latin"


def test_detect_text_language():
    assert detect_text_language("We will ship it by Friday and the team is ready.") == "en"
    assert detect_text_language("मैं कल तक रिपोर्ट भेज दूंगा") == "hi"
    assert detect_text_language(
        "Namaste team, aaj hum sprint planning aur testing discuss karenge. Main kal tak kar dunga."
    ) == "hi"


def test_hallucination_filter():
    assert is_hallucination("Thanks for watching!", {"no_speech_prob": 0.5})
    assert is_hallucination("you you you you you you you you you", {"compression_ratio": 3.0})
    assert is_hallucination("Okay.", {"no_speech_prob": 0.9, "avg_logprob": -1.4})
    assert not is_hallucination("Let's review the sprint backlog.", {"no_speech_prob": 0.05, "avg_logprob": -0.3})
    assert not is_hallucination(
        "Thanks for watching the demo and see you Monday", {"no_speech_prob": 0.01}
    )


def test_initial_prompt_includes_names_and_style():
    prompt = initial_prompt("hinglish", ["Ramesha", "Naishal"])
    assert "Ramesha, Naishal" in prompt
    assert "kar dunga" in prompt
    assert initial_prompt("ja") is None
