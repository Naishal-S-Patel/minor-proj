"""
Transcript cleaning service.

Pure-function text cleaning — no I/O, no DB calls, fully unit-testable
without infrastructure. Handles common transcript formats from Zoom, Teams,
Otter.ai, and other meeting platforms.
"""

import re


class TranscriptService:
    """Cleans raw transcript text through a series of normalization steps."""

    def clean(self, raw_text: str) -> str:
        """
        Returns a cleaned version of a raw transcript string.

        Cleaning steps (applied in order):
        1. Normalize line endings (\r\n → \n)
        2. Strip timestamp patterns like [00:01:23], (00:01:23), 00:01:23 -
        3. Normalize speaker labels: SPEAKER_00: → Speaker 1:; collapse duplicates
        4. Collapse 3+ blank lines to 2
        5. Strip leading/trailing whitespace per line
        6. Remove null bytes and non-printable characters
        """
        text = self._normalize_line_endings(raw_text)
        text = self._strip_timestamps(text)
        text = self._normalize_speaker_labels(text)
        text = self._collapse_blank_lines(text)
        text = self._strip_line_whitespace(text)
        text = self._remove_non_printable(text)
        return text.strip()

    def _normalize_line_endings(self, text: str) -> str:
        """Convert all line endings to Unix-style \\n."""
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _strip_timestamps(self, text: str) -> str:
        """
        Remove common timestamp patterns from transcript lines.

        Handles formats:
        - [00:01:23] or [00:01:23.456]
        - (00:01:23) or (00:01:23.456)
        - 00:01:23 - Speaker:
        - 00:01:23 - Speaker:
        """
        # Pattern for timestamps in brackets: [00:01:23] or (00:01:23)
        text = re.sub(r"[\[\(]\d{1,2}:\d{2}:\d{2}(?:\.\d+)?[\]\)]\s*", "", text)

        # Pattern for timestamps with dash: 00:01:23 - or 00:01:23-
        text = re.sub(r"\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\s*[-–—]\s*", "", text)

        return text

    def _normalize_speaker_labels(self, text: str) -> str:
        """
        Normalize speaker labels to consistent format.

        Converts SPEAKER_00:, SPEAKER_01:, etc. to Speaker 1:, Speaker 2:, etc.
        Also handles Speaker 0:, Speaker 1:, etc. (already normalized format).
        """
        # Track unique speakers to maintain consistent numbering
        speaker_map: dict[str, str] = {}
        speaker_counter = 0

        def replace_speaker(match: re.Match) -> str:
            nonlocal speaker_counter
            original = match.group(0).strip()

            if original not in speaker_map:
                speaker_counter += 1
                speaker_map[original] = f"Speaker {speaker_counter}"

            return speaker_map[original] + ":"

        # Match SPEAKER_XX: or Speaker X: patterns
        text = re.sub(
            r"(?:SPEAKER_\d+|Speaker\s+\d+)\s*:",
            replace_speaker,
            text,
        )

        return text

    def _collapse_blank_lines(self, text: str) -> str:
        """Collapse 3 or more consecutive blank lines to 2."""
        return re.sub(r"\n{3,}", "\n\n", text)

    def _strip_line_whitespace(self, text: str) -> str:
        """Strip leading/trailing whitespace from each line."""
        lines = text.split("\n")
        return "\n".join(line.strip() for line in lines)

    def _remove_non_printable(self, text: str) -> str:
        """Remove null bytes and non-printable characters."""
        # Remove null bytes
        text = text.replace("\x00", "")
        # Remove other control characters except newlines and tabs
        text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        return text
