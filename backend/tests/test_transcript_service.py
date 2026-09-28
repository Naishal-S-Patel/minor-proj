"""
Unit tests for TranscriptService.

Pure unit tests for TranscriptService.clean() — no HTTP, no DB.
"""

from app.services.transcript_service import TranscriptService


def test_strips_timestamps():
    """Test that timestamps in various formats are stripped."""
    svc = TranscriptService()

    # Bracket format
    assert svc.clean("[00:01:23] Hello") == "Hello"

    # Parentheses format
    assert svc.clean("(00:01:23) Hello") == "Hello"

    # Dash format
    assert svc.clean("00:01:23 - Hello") == "Hello"

    # With milliseconds
    assert svc.clean("[00:01:23.456] Hello") == "Hello"


def test_normalizes_speaker_labels():
    """Test that speaker labels are normalized to consistent format."""
    svc = TranscriptService()

    # SPEAKER_XX format
    result = svc.clean("SPEAKER_00: Hi")
    assert result == "Speaker 1: Hi"

    # Multiple speakers
    result = svc.clean("SPEAKER_00: Hello\nSPEAKER_01: Hi")
    assert "Speaker 1:" in result
    assert "Speaker 2:" in result

    # Already normalized Speaker X format
    result = svc.clean("Speaker 0: Hello")
    assert result == "Speaker 1: Hello"


def test_collapses_blank_lines():
    """Test that 3+ blank lines are collapsed to 2."""
    svc = TranscriptService()

    # 5 blank lines should become 2
    text = "Line 1\n\n\n\n\nLine 2"
    result = svc.clean(text)
    assert result.count("\n\n") == 1

    # 3 blank lines should become 2
    text = "Line 1\n\n\nLine 2"
    result = svc.clean(text)
    assert result.count("\n\n") == 1


def test_handles_empty_string():
    """Test that empty string returns empty string."""
    svc = TranscriptService()
    assert svc.clean("") == ""


def test_handles_crlf():
    """Test that CRLF line endings are normalized to LF."""
    svc = TranscriptService()

    text = "line1\r\nline2"
    result = svc.clean(text)
    assert "\r" not in result
    assert "line1\nline2" in result


def test_strips_line_whitespace():
    """Test that leading/trailing whitespace is stripped from lines."""
    svc = TranscriptService()

    text = "  Hello  \n  World  "
    result = svc.clean(text)
    assert result == "Hello\nWorld"


def test_removes_non_printable_characters():
    """Test that null bytes and non-printable characters are removed."""
    svc = TranscriptService()

    # Null byte
    text = "Hello\x00World"
    result = svc.clean(text)
    assert "\x00" not in result
    assert "HelloWorld" in result

    # Other control characters
    text = "Hello\x01\x02World"
    result = svc.clean(text)
    assert "\x01" not in result
    assert "\x02" not in result


def test_complex_transcript():
    """Test cleaning a more complex transcript sample."""
    svc = TranscriptService()

    raw = """[00:01:23] SPEAKER_00: Hello everyone, welcome to the meeting.
SPEAKER_01: Thanks for joining. Let's get started.

[00:02:15] SPEAKER_00: First item on the agenda is the project update.
SPEAKER_01: I have the report ready.




[00:03:00] SPEAKER_00: Great, let's proceed."""

    result = svc.clean(raw)

    # Timestamps stripped
    assert "[00:01:23]" not in result
    assert "[00:02:15]" not in result
    assert "[00:03:00]" not in result

    # Speaker labels normalized
    assert "SPEAKER_00" not in result
    assert "SPEAKER_01" not in result
    assert "Speaker 1:" in result
    assert "Speaker 2:" in result

    # Blank lines collapsed
    assert "\n\n\n\n" not in result

    # Content preserved
    assert "Hello everyone" in result
    assert "project update" in result
