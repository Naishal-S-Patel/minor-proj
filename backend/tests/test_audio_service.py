"""
Unit tests for AudioService.

Tests the get_duration_seconds method without making real Whisper calls.
"""

import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock

from app.services.audio_service import AudioService
from tests.conftest import SAMPLE_AUDIO_BYTES


def test_get_duration_valid_wav():
    """Test that get_duration_seconds returns a valid duration for WAV bytes."""
    # Mock pydub to avoid needing actual audio parsing
    with patch("app.services.audio_service.AudioSegment") as mock_audio_segment:
        # Mock a segment with 5 seconds duration (5000 milliseconds)
        mock_segment = MagicMock()
        mock_segment.__len__ = MagicMock(return_value=5000)
        mock_audio_segment.from_file.return_value = mock_segment

        service = AudioService()
        duration = service.get_duration_seconds(SAMPLE_AUDIO_BYTES, "test.wav")

        assert duration == 5.0
        mock_audio_segment.from_file.assert_called_once()


def test_get_duration_invalid_bytes():
    """Test that get_duration_seconds raises ValueError for garbage bytes."""
    service = AudioService()

    with pytest.raises(ValueError, match="Cannot parse audio file"):
        service.get_duration_seconds(b"not audio data", "test.wav")


def test_get_duration_no_extension():
    """Test that get_duration_seconds handles files without extension."""
    with patch("app.services.audio_service.AudioSegment") as mock_audio_segment:
        # When there's no extension, pydub will raise an error
        mock_audio_segment.from_file.side_effect = Exception("No format specified")

        service = AudioService()
        # This should raise an error because there's no extension
        with pytest.raises(ValueError, match="Cannot parse audio file"):
            service.get_duration_seconds(SAMPLE_AUDIO_BYTES, "noextension")
