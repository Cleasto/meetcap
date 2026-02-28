"""Watch folder service for automatic processing."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Set

from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from watchdog.observers import Observer

from .config import LOG_FILE, get_raw_dir, load_config
from .processor import process_recording

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class RecordingHandler(FileSystemEventHandler):
    """Handles new recording files."""

    def __init__(self, config: Dict):
        self.config = config
        self._processing = set()

    def on_created(self, event: FileCreatedEvent) -> None:
        """Handle new file creation."""
        if event.is_directory:
            return

        filepath = Path(event.src_path)

        # Only process WAV files
        if filepath.suffix.lower() != ".wav":
            return

        # Skip if already processing
        if filepath in self._processing:
            return

        # Wait a moment for file to finish writing
        time.sleep(2)

        # Verify file still exists and has content
        if not filepath.exists() or filepath.stat().st_size == 0:
            logger.warning(f"File empty or missing: {filepath}")
            return

        self._processing.add(filepath)

        try:
            logger.info(f"New recording detected: {filepath}")
            output_path = process_recording(filepath, self.config)
            logger.info(f"Processing complete: {output_path}")
        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}", exc_info=True)
        finally:
            self._processing.discard(filepath)


def run_watcher(config: Optional[Dict] = None) -> None:
    """Run the watch folder service."""
    if config is None:
        config = load_config()

    watch_dir = get_raw_dir(config)
    watch_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting watch service on: {watch_dir}")

    event_handler = RecordingHandler(config)
    observer = Observer()
    observer.schedule(event_handler, str(watch_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watch service...")
        observer.stop()

    observer.join()
    logger.info("Watch service stopped")


def main() -> None:
    """Entry point for watch service."""
    run_watcher()


if __name__ == "__main__":
    main()
