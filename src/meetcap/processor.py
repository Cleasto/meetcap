"""Pipeline for processing meeting recordings."""
from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from .config import get_output_dir, get_processed_dir, load_config
from .summarizer import summarize_transcript
from .transcriber import transcribe_file

logger = logging.getLogger(__name__)


def parse_filename_datetime(filename: str) -> datetime:
    """Parse datetime from meeting filename."""
    # Expected format: meeting-YYYY-MM-DD-HHMM.wav
    try:
        base = filename.replace("meeting-", "").replace(".wav", "")
        return datetime.strptime(base, "%Y-%m-%d-%H%M")
    except ValueError:
        # Fall back to current time
        return datetime.now()


def calculate_duration(audio_path: Path) -> str:
    """Calculate audio duration using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            seconds = float(result.stdout.strip())
            minutes = int(seconds // 60)
            return f"{minutes} minutes"
    except Exception as e:
        logger.warning(f"Could not determine duration: {e}")
    return "unknown"


def create_markdown(
    meeting_dt: datetime,
    duration: str,
    audio_filename: str,
    transcript: str,
    summary: str,
) -> str:
    """Create the final markdown document."""
    return f"""---
date: {meeting_dt.strftime('%Y-%m-%d')}
time: "{meeting_dt.strftime('%H:%M')}"
duration: {duration}
audio_file: {audio_filename}
---

# Meeting Summary

{summary}

---

# Full Transcript

{transcript}
"""


def process_recording(audio_path: Path, config: Optional[Dict] = None) -> Path:
    """
    Process a meeting recording through the full pipeline.

    Args:
        audio_path: Path to the WAV file
        config: Optional config dict, will load from file if not provided

    Returns:
        Path to the created markdown file
    """
    if config is None:
        config = load_config()

    logger.info(f"Processing recording: {audio_path}")

    # Parse meeting datetime from filename
    meeting_dt = parse_filename_datetime(audio_path.name)

    # Calculate duration
    duration = calculate_duration(audio_path)
    logger.info(f"Duration: {duration}")

    # Transcribe
    logger.info("Transcribing audio...")
    raw_text, formatted_transcript = transcribe_file(
        audio_path,
        model_name=config.get("whisper_model", "base.en"),
    )
    logger.info(f"Transcription complete: {len(raw_text)} characters")

    # Summarize
    logger.info("Generating summary...")
    api_key = config.get("anthropic_api_key", "")
    if api_key:
        summary = summarize_transcript(raw_text, api_key)
    else:
        logger.warning("No API key configured, skipping summarization")
        summary = "_Summary not available: Anthropic API key not configured_"

    # Create output directory structure
    output_dir = get_output_dir(config)
    year_month_dir = output_dir / meeting_dt.strftime("%Y") / meeting_dt.strftime("%m")
    year_month_dir.mkdir(parents=True, exist_ok=True)

    # Create markdown file
    md_filename = audio_path.stem + ".md"
    md_path = year_month_dir / md_filename

    markdown = create_markdown(
        meeting_dt=meeting_dt,
        duration=duration,
        audio_filename=audio_path.name,
        transcript=formatted_transcript,
        summary=summary,
    )

    md_path.write_text(markdown)
    logger.info(f"Created markdown: {md_path}")

    # Move audio to processed directory
    processed_dir = get_processed_dir(config)
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_path = processed_dir / audio_path.name
    shutil.move(str(audio_path), str(processed_path))
    logger.info(f"Moved audio to: {processed_path}")

    # Send notification if enabled
    if config.get("notify_on_complete", True):
        send_notification(f"Meeting processed: {md_filename}")

    return md_path


def send_notification(message: str) -> None:
    """Send a macOS notification."""
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "Meetcap"',
            ],
            capture_output=True,
        )
    except Exception as e:
        logger.debug(f"Could not send notification: {e}")
