"""Audio transcription using Whisper."""

import logging
from pathlib import Path

import whisper

logger = logging.getLogger(__name__)


class Transcriber:
    """Transcribes audio files using OpenAI Whisper."""

    def __init__(self, model_name: str = "base.en"):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        """Lazy load the Whisper model."""
        if self._model is None:
            logger.info(f"Loading Whisper model: {self.model_name}")
            self._model = whisper.load_model(self.model_name)
        return self._model

    def transcribe(self, audio_path: Path) -> dict:
        """
        Transcribe an audio file.

        Returns:
            dict with keys:
                - text: Full transcript text
                - segments: List of segments with timestamps
                - language: Detected language
        """
        logger.info(f"Transcribing: {audio_path}")

        result = self.model.transcribe(
            str(audio_path),
            language="en",
            verbose=False,
        )

        return {
            "text": result["text"].strip(),
            "segments": result["segments"],
            "language": result.get("language", "en"),
        }

    def format_transcript(self, result: dict) -> str:
        """Format transcript with timestamps."""
        lines = []

        for segment in result["segments"]:
            start = segment["start"]
            text = segment["text"].strip()

            # Format timestamp as HH:MM:SS
            hours = int(start // 3600)
            minutes = int((start % 3600) // 60)
            seconds = int(start % 60)
            timestamp = f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"

            lines.append(f"{timestamp} {text}")

        return "\n".join(lines)


def transcribe_file(audio_path: Path, model_name: str = "base.en") -> tuple[str, str]:
    """
    Convenience function to transcribe a file.

    Returns:
        Tuple of (raw_text, formatted_transcript)
    """
    transcriber = Transcriber(model_name=model_name)
    result = transcriber.transcribe(audio_path)
    formatted = transcriber.format_transcript(result)
    return result["text"], formatted
