"""
Tests for AWSTranscribeService and AudioService cloud fallback.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.services.aws_transcribe_service import AWSTranscribeError, AWSTranscribeService


def _make_mocked_transcribe_service():
    with patch("app.services.aws_transcribe_service.settings") as mock_settings:
        mock_settings.aws_access_key_id = "test-key"
        mock_settings.aws_secret_access_key = "test-secret"
        mock_settings.aws_session_token = ""
        mock_settings.aws_region = "ap-south-1"
        mock_settings.aws_s3_bucket = "test-bucket"

        with patch("boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_transcribe = MagicMock()

            def client_factory(service_name, **kwargs):
                if service_name == "s3":
                    return mock_s3
                return mock_transcribe

            mock_boto.side_effect = client_factory

            svc = AWSTranscribeService()
            return svc, mock_s3, mock_transcribe


def test_missing_bucket_raises_error():
    with patch("app.services.aws_transcribe_service.settings") as mock_settings:
        mock_settings.aws_s3_bucket = ""
        with pytest.raises(AWSTranscribeError, match="AWS_S3_BUCKET is not configured"):
            AWSTranscribeService()


def test_format_transcribe_output():
    fake_data = {
        "results": {
            "speaker_labels": {
                "segments": [
                    {
                        "start_time": "0.0",
                        "speaker_label": "spk_0",
                        "items": [{"start_time": "0.5"}],
                    },
                    {
                        "start_time": "3.0",
                        "speaker_label": "spk_1",
                        "items": [{"start_time": "3.2"}],
                    },
                ]
            },
            "items": [
                {
                    "type": "pronunciation",
                    "start_time": "0.5",
                    "alternatives": [{"content": "Hello"}],
                },
                {
                    "type": "pronunciation",
                    "start_time": "3.2",
                    "alternatives": [{"content": "World"}],
                },
            ],
        }
    }

    lines = AWSTranscribeService._format_transcribe_output(fake_data, roster=[], platform="zoom")
    assert len(lines) == 2
    assert "Hello" in lines[0]
    assert "World" in lines[1]

