"""Configuration management for meetcap."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIG = {
    "anthropic_api_key": "",
    "whisper_model": "base.en",
    "output_dir": "~/Documents/MeetingNotes",
    "recordings_dir": "~/MeetingRecordings",
    "notify_on_complete": True,
    "audio_device": None,  # None means use default/BlackHole
    "mic_device": None,  # None means auto-detect (first non-virtual input)
    "sample_rate": 44100,
    "channels": 2,
}

CONFIG_DIR = Path.home() / ".config" / "meetcap"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
LOG_FILE = CONFIG_DIR / "meetcap.log"
PID_FILE = CONFIG_DIR / "recording.pid"


def expand_path(path: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path)))


def load_config() -> Dict[str, Any]:
    """Load configuration from file, merging with defaults."""
    config = DEFAULT_CONFIG.copy()

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            user_config = yaml.safe_load(f) or {}
            config.update(user_config)

    # Check for API key in environment variable
    if not config["anthropic_api_key"]:
        config["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")

    return config


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Don't save API key if it came from environment
    save_config = config.copy()
    if os.environ.get("ANTHROPIC_API_KEY"):
        save_config["anthropic_api_key"] = ""

    with open(CONFIG_FILE, "w") as f:
        yaml.dump(save_config, f, default_flow_style=False)


def get_raw_dir(config: Dict[str, Any]) -> Path:
    """Get the raw recordings directory."""
    return expand_path(config["recordings_dir"]) / "raw"


def get_processed_dir(config: Dict[str, Any]) -> Path:
    """Get the processed recordings directory."""
    return expand_path(config["recordings_dir"]) / "processed"


def get_output_dir(config: Dict[str, Any]) -> Path:
    """Get the meeting notes output directory."""
    return expand_path(config["output_dir"])


def ensure_directories(config: Dict[str, Any]) -> None:
    """Ensure all required directories exist."""
    get_raw_dir(config).mkdir(parents=True, exist_ok=True)
    get_processed_dir(config).mkdir(parents=True, exist_ok=True)
    get_output_dir(config).mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
