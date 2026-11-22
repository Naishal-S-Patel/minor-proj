"""
AWSTranscribeService — AWS Transcribe cloud ASR with S3 integration and speaker diarization.

Features:
  - Fast cloud transcription (~5-10s for typical meeting clips).
  - Built-in speaker diarization (`ShowSpeakerLabels=True`).
  - Native support for Indian English (en-IN) and Hindi (hi-IN) with auto-language identification.
  - Automatically cleans up audio files in S3 after transcription.
"""

import json
import logging
import os
import time
import urllib.request
import uuid
from typing import Any

from app.core.config import settings
from app.services.speaker_identity import (
    Participant,
    detect_platform,
    format_speaker_label,
    resolve_speaker_names,
)

logger = logging.getLogger(__name__)


class AWSTranscribeError(Exception):
    """Raised when AWS Transcribe job or S3 upload fails."""


class AWSTranscribeService:
    """Uploads audio to S3, runs AWS Transcribe job with speaker diarization, and returns transcript."""

    def __init__(self) -> None:
        if not settings.aws_s3_bucket:
            raise AWSTranscribeError("AWS_S3_BUCKET is not configured in settings")

        try:
            import boto3

            session_kwargs: dict[str, Any] = {}
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
                session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
                if settings.aws_session_token:
                    session_kwargs["aws_session_token"] = settings.aws_session_token

            region = settings.aws_region or "ap-south-1"
            self._s3 = boto3.client("s3", region_name=region, **session_kwargs)
            self._transcribe = boto3.client("transcribe", region_name=region, **session_kwargs)
            self._bucket = settings.aws_s3_bucket
            logger.info("Initialized AWSTranscribeService (bucket: %s, region: %s)", self._bucket, region)
        except Exception as exc:
            logger.error("Failed to initialize AWS Transcribe clients: %s", exc)
            raise AWSTranscribeError(f"AWS Transcribe init failed: {exc}") from exc

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
        platform: str | None = None,
        participants: list[Participant] | None = None,
        timeout_seconds: int = 120,
    ) -> tuple[str, str | None]:
        """
        Executes cloud transcription with speaker labels.
        Returns (formatted_transcript, detected_language_code).
        """
        roster = list(participants or [])
        platform = detect_platform(platform, filename)

        # 1. Upload audio to S3
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
        job_id = f"meet_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        s3_key = f"transcription_audio/{job_id}.{ext}"

        logger.info("Uploading %d bytes to s3://%s/%s", len(audio_bytes), self._bucket, s3_key)
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=s3_key,
                Body=audio_bytes,
            )
        except Exception as exc:
            logger.warning("S3 upload failed: %s", exc)
            raise AWSTranscribeError(f"S3 upload error: {exc}") from exc

        media_uri = f"s3://{self._bucket}/{s3_key}"

        # 2. Configure AWS Transcribe Job
        job_kwargs: dict[str, Any] = {
            "TranscriptionJobName": job_id,
            "Media": {"MediaFileUri": media_uri},
            "Settings": {
                "ShowSpeakerLabels": True,
                "MaxSpeakerLabels": min(max(len(roster), 2), 8) if roster else 8,
            },
        }

        lang_code = (language or "").strip().lower()
        if lang_code in ("hi", "hindi", "hinglish"):
            job_kwargs["LanguageCode"] = "hi-IN"
        elif lang_code in ("en", "english"):
            job_kwargs["LanguageCode"] = "en-IN"
        else:
            # Auto-identify between Indian English and Hindi
            job_kwargs["IdentifyLanguage"] = True
            job_kwargs["LanguageOptions"] = ["en-IN", "hi-IN", "en-US"]

        logger.info("Starting AWS Transcribe job %s (language: %s)", job_id, job_kwargs.get("LanguageCode", "auto"))
        try:
            self._transcribe.start_transcription_job(**job_kwargs)
        except Exception as exc:
            self._cleanup_s3(s3_key)
            raise AWSTranscribeError(f"StartTranscriptionJob failed: {exc}") from exc

        # 3. Poll for completion
        transcript_data: dict[str, Any] = {}
        detected_lang: str | None = None
        start_time = time.time()

        try:
            while time.time() - start_time < timeout_seconds:
                status_res = self._transcribe.get_transcription_job(TranscriptionJobName=job_id)
                job = status_res.get("TranscriptionJob", {})
                status = job.get("TranscriptionJobStatus")

                if status == "COMPLETED":
                    transcript_uri = job.get("Transcript", {}).get("TranscriptFileUri")
                    detected_lang = job.get("LanguageCode", "en-IN")
                    logger.info("AWS Transcribe job %s completed in %.1fs", job_id, time.time() - start_time)
                    if transcript_uri:
                        with urllib.request.urlopen(transcript_uri, timeout=15) as resp:
                            transcript_data = json.loads(resp.read().decode("utf-8"))
                    break
                elif status == "FAILED":
                    failure_reason = job.get("FailureReason", "Unknown AWS Transcribe failure")
                    logger.error("AWS Transcribe job failed: %s", failure_reason)
                    raise AWSTranscribeError(f"Transcribe job failed: {failure_reason}")

                time.sleep(2.0)
            else:
                raise AWSTranscribeError(f"AWS Transcribe job timed out after {timeout_seconds}s")
        finally:
            self._cleanup_s3(s3_key)

        # 4. Parse speaker segments into standard meeting transcript
        lines = self._format_transcribe_output(transcript_data, roster, platform)
        if not lines:
            # Fallback to plain transcript text if speaker labels were sparse
            raw_text = transcript_data.get("results", {}).get("transcripts", [{}])[0].get("transcript", "").strip()
            if raw_text:
                lines = [f"[00:00] [Speaker 1]: {raw_text}"]

        detected_code = "hi" if "hi" in (detected_lang or "").lower() else "en"
        return "\n".join(lines), detected_code

    def _cleanup_s3(self, s3_key: str) -> None:
        """Silently deletes temporary audio file from S3."""
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=s3_key)
            logger.debug("Deleted temporary S3 object: %s", s3_key)
        except Exception as exc:
            logger.debug("Could not delete S3 object %s: %s", s3_key, exc)

    @staticmethod
    def _format_transcribe_output(
        data: dict[str, Any],
        roster: list[Participant],
        platform: str | None,
    ) -> list[str]:
        """Maps AWS Transcribe speaker_labels and items into timestamped speaker turns."""
        results = data.get("results", {})
        speaker_labels = results.get("speaker_labels", {})
        segments = speaker_labels.get("segments", [])
        items = results.get("items", [])

        if not segments:
            return []

        # Build map of word start_time -> word text
        words_by_time: dict[float, str] = {}
        for item in items:
            if item.get("type") == "pronunciation":
                start = float(item.get("start_time", 0.0))
                word = item.get("alternatives", [{}])[0].get("content", "")
                words_by_time[round(start, 2)] = word

        # Group words by speaker segments
        turns: list[list[Any]] = []  # [start_sec, speaker_id_int, text]
        speaker_map: dict[str, int] = {}

        for seg in segments:
            spk_label = seg.get("speaker_label", "spk_0")
            if spk_label not in speaker_map:
                speaker_map[spk_label] = len(speaker_map)
            spk_id = speaker_map[spk_label]
            seg_start = float(seg.get("start_time", 0.0))

            seg_words = []
            for item in seg.get("items", []):
                s = round(float(item.get("start_time", 0.0)), 2)
                if s in words_by_time:
                    seg_words.append(words_by_time[s])

            seg_text = " ".join(seg_words).strip()
            if not seg_text:
                continue

            if turns and turns[-1][1] == spk_id:
                turns[-1][2] = f"{turns[-1][2]} {seg_text}".strip()
            else:
                turns.append([seg_start, spk_id, seg_text])

        # Resolve speaker names with roster / platform format
        names = resolve_speaker_names([(t[1], t[2]) for t in turns], roster, platform)
        lines = []
        for start_sec, spk_id, text in turns:
            mins, secs = divmod(int(start_sec), 60)
            label = format_speaker_label(platform, spk_id, names.get(spk_id))
            lines.append(f"[{mins:02d}:{secs:02d}] [{label}]: {text}")

        return lines

