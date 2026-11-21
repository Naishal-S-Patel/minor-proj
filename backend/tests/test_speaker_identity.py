"""Unit tests for roster parsing, platform tags and name <-> voice resolution."""

from app.services.speaker_identity import (
    Participant,
    detect_platform,
    find_self_introduction,
    format_speaker_label,
    parse_participants,
    resolve_speaker_names,
    roster_header,
    speaker_tag,
)


def test_platform_tags():
    assert [speaker_tag("Zoom", i) for i in range(2)] == ["USR-101", "USR-102"]
    assert [speaker_tag("Google Meet", i) for i in range(2)] == ["P01", "P02"]
    assert speaker_tag("In-Person", 0) == "Speaker 1"
    assert format_speaker_label("Zoom", 1, "Naishal") == "USR-102 (Naishal)"
    assert format_speaker_label("Google Meet", 0, None) == "P01"


def test_detect_platform_does_not_match_loose_p0_substring():
    assert detect_platform(None, None, None, "we need to stop0 the top0 job") is None
    assert detect_platform(None, None, None, "[00:01] [P01]: hi") == "Google Meet"
    assert detect_platform(None, None, None, "[00:01] [USR-101]: hi") == "Zoom"
    assert detect_platform("Audio Recording", "zoom_call.m4a") == "Zoom"
    assert detect_platform("Microsoft Teams") == "Microsoft Teams"


def test_parse_participants_formats():
    roster = parse_participants(
        "USR-101: Ramesha\nP2 = Naishal Patel\nSarah Chen (USR-103)\n- Alex Rivera - Lead Architect"
    )
    assert [(p.tag, p.name) for p in roster] == [
        ("USR-101", "Ramesha"),
        ("P02", "Naishal Patel"),
        ("USR-103", "Sarah Chen"),
        (None, "Alex Rivera"),
    ]
    assert [p.name for p in parse_participants("Ramesha, Naishal")] == ["Ramesha", "Naishal"]
    assert parse_participants("   ") == []


def test_self_introductions_en_hi_hinglish():
    assert find_self_introduction("Hi everyone, I'm Priya Sharma from Product.") == "Priya Sharma"
    assert find_self_introduction("namaste, mera naam Ramesha hai") == "Ramesha"
    assert find_self_introduction("Main Naishal hoon, backend dekh raha hoon") == "Naishal"
    assert find_self_introduction("नमस्ते, मेरा नाम रमेशा है") == "रमेशा"
    # Not introductions
    assert find_self_introduction("I'm going to share my screen.") is None
    assert find_self_introduction("It's Monday, let's start.") is None


def test_resolve_names_from_greetings_uses_turn_order():
    turns = [
        (0, "Hello everyone, thanks for joining. Hi Naishal, can you start?"),
        (1, "Sure. Thanks Ramesha. The API is ready."),
        (2, "I'm Vikram from QA."),
    ]
    assert resolve_speaker_names(turns, [], "Zoom") == {0: "Ramesha", 1: "Naishal", 2: "Vikram"}


def test_resolve_names_roster_fuzzy_match_and_order_fill():
    roster = parse_participants("Ramesha, Naishal, Vikram")
    # "Nishal" (Whisper spelling) must map to roster "Naishal"; Vikram fills by order.
    turns = [(0, "Hi Nishal, go ahead."), (1, "Okay."), (2, "Done.")]
    names = resolve_speaker_names(turns, roster, "Google Meet")
    assert names[1] == "Naishal"
    assert set(names.values()) == {"Ramesha", "Naishal", "Vikram"}


def test_resolve_names_explicit_tags():
    roster = parse_participants("USR-102: Bina\nUSR-101: Asha")
    assert resolve_speaker_names([(0, "ok let's start"), (1, "yes")], roster, "Zoom") == {
        0: "Asha",
        1: "Bina",
    }


def test_roster_header_assigns_tags_in_transcript_order():
    header = roster_header(
        [Participant("Ramesha"), Participant("Naishal")],
        "Google Meet",
        "[00:01] [P01]: hi\n[00:05] [P02]: hello",
    )
    assert header.splitlines() == ["Participants:", "- P01 -> Ramesha", "- P02 -> Naishal"]
