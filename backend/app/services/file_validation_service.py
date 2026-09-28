"""
File validation service for uploaded transcripts and audio files.

Validates file type, size, and encoding before any processing occurs.
Rejects invalid files early (no DB write) to avoid orphaned failed records.
"""

import logging
import os

import chardet
from fastapi import HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

# Text file constants
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {"text/plain"}
ALLOWED_EXTENSIONS = {".txt"}

# Audio file constants
AUDIO_CONTENT_TYPES = {
    "audio/mpeg",       # .mp3
    "audio/mp4",        # .mp4 audio
    "audio/wav",        # .wav
    "audio/x-wav",
    "audio/m4a",        # .m4a
    "audio/x-m4a",
    "video/mp4",        # .mp4 video (Whisper handles video too)
}
AUDIO_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".m4v"}


class FileValidationService:
    """Validates uploaded files and returns decoded text content."""

    async def validate_and_read_text(self, file: UploadFile) -> str:
        """
        Validates file type/size and returns decoded text content.

        Raises HTTPException on validation failure:
        - 415 Unsupported Media Type for wrong file type
        - 413 Request Entity Too Large for oversized files
        - 422 Unprocessable Entity for encoding issues or empty files
        """
        # Check file extension
        if file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Invalid file type. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No filename provided",
            )

        # Check content type if provided
        if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Invalid content type. Allowed: {', '.join(ALLOWED_CONTENT_TYPES)}",
            )

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Check file size
        if file_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB",
            )

        # Check for empty file
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File is empty",
            )

        # Detect encoding
        detection = chardet.detect(content)
        encoding = detection.get("encoding", "utf-8")
        confidence = detection.get("confidence", 0)

        logger.info(
            "File encoding detected: %s (confidence: %.2f)",
            encoding,
            confidence,
        )

        # Try to decode with detected encoding, fallback to utf-8, then latin-1
        decoded_text = None
        for enc in [encoding, "utf-8", "latin-1"]:
            try:
                decoded_text = content.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if decoded_text is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unable to decode file. Please ensure the file is UTF-8 or Latin-1 encoded.",
            )

        return decoded_text

    async def validate_audio(self, file: UploadFile, max_size_mb: int) -> bytes:
        """
        Validates an audio file upload. Returns raw bytes for the worker to use.

        Checks: extension, content-type, size <= max_size_mb, non-empty.
        Does NOT check audio duration — that requires pydub parse (done in AudioService).
        Raises HTTPException on any validation failure.
        """
        # Check file extension
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No filename provided",
            )

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Invalid file type. Allowed audio extensions: {', '.join(sorted(AUDIO_EXTENSIONS))}",
            )

        # Check content type if provided
        if file.content_type and file.content_type not in AUDIO_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Invalid content type. Allowed: {', '.join(sorted(AUDIO_CONTENT_TYPES))}",
            )

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Check file size
        max_size_bytes = max_size_mb * 1024 * 1024
        if file_size > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {max_size_mb} MB",
            )

        # Check for empty file
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File is empty",
            )

        return content
