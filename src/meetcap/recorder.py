"""Audio recording functionality using sounddevice."""
from __future__ import annotations

import signal
import sys
import threading
import wave
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import sounddevice as sd

from .config import PID_FILE, get_raw_dir, load_config


class AudioRecorder:
    """Records audio from system audio device (BlackHole)."""

    def __init__(
        self,
        device: Optional[Union[str, int]] = None,
        sample_rate: int = 44100,
        channels: int = 2,
    ):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self.frames: List[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream: Optional[sd.InputStream] = None

    def _find_capture_device(self) -> Optional[int]:
        """Find a suitable audio capture device (BlackHole or ZoomAudioDevice)."""
        devices = sd.query_devices()

        # First try BlackHole
        for i, dev in enumerate(devices):
            if "BlackHole" in dev["name"] and dev["max_input_channels"] >= 2:
                return i

        # Fall back to ZoomAudioDevice if available
        for i, dev in enumerate(devices):
            if "ZoomAudioDevice" in dev["name"] and dev["max_input_channels"] >= 2:
                return i

        return None

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Callback for audio stream."""
        if status:
            print(f"Audio status: {status}", file=sys.stderr)
        with self._lock:
            if self.recording:
                self.frames.append(indata.copy())

    def start(self) -> None:
        """Start recording audio."""
        if self.recording:
            raise RuntimeError("Already recording")

        # Find device
        device = self.device
        if device is None:
            device = self._find_capture_device()
            if device is None:
                raise RuntimeError(
                    "No audio capture device found. "
                    "Please install BlackHole: brew install blackhole-2ch\n"
                    "Or use ZoomAudioDevice if Zoom is running."
                )

        self.frames = []
        self.recording = True

        self._stream = sd.InputStream(
            device=device,
            channels=self.channels,
            samplerate=self.sample_rate,
            callback=self._audio_callback,
            dtype=np.int16,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Stop recording and return audio data."""
        if not self.recording:
            raise RuntimeError("Not recording")

        self.recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            if not self.frames:
                return np.array([], dtype=np.int16)
            return np.concatenate(self.frames)

    def save(self, audio_data: np.ndarray, filepath: Path) -> None:
        """Save audio data to WAV file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())


def generate_filename() -> str:
    """Generate filename based on current timestamp."""
    now = datetime.now()
    return f"meeting-{now.strftime('%Y-%m-%d-%H%M')}.wav"


def start_recording() -> None:
    """Start recording in foreground mode with signal handling."""
    config = load_config()
    raw_dir = get_raw_dir(config)
    raw_dir.mkdir(parents=True, exist_ok=True)

    recorder = AudioRecorder(
        device=config.get("audio_device"),
        sample_rate=config.get("sample_rate", 44100),
        channels=config.get("channels", 2),
    )

    filename = generate_filename()
    filepath = raw_dir / filename

    print(f"Starting recording to {filepath}")
    print("Press Ctrl+C to stop recording...")

    # Write PID file
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(filepath))

    recorder.start()

    # Handle interrupt signal
    stop_event = threading.Event()

    def signal_handler(sig, frame):
        print("\nStopping recording...")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Wait for stop signal
    stop_event.wait()

    # Stop and save
    audio_data = recorder.stop()

    if len(audio_data) > 0:
        recorder.save(audio_data, filepath)
        duration = len(audio_data) / recorder.sample_rate / recorder.channels
        print(f"Recording saved: {filepath}")
        print(f"Duration: {duration:.1f} seconds")
    else:
        print("No audio data captured.")

    # Clean up PID file
    if PID_FILE.exists():
        PID_FILE.unlink()


def stop_recording() -> None:
    """Signal a running recording to stop."""
    import os
    import signal

    if not PID_FILE.exists():
        print("No active recording found.")
        return

    # The PID file contains the output path, not a PID
    # We need to find the actual meetcap process
    import subprocess

    result = subprocess.run(
        ["pgrep", "-f", "meetcap start"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        pids = result.stdout.strip().split("\n")
        for pid in pids:
            if pid and pid != str(os.getpid()):
                os.kill(int(pid), signal.SIGTERM)
                print("Stop signal sent to recording process.")
                return

    print("No active recording process found.")
    if PID_FILE.exists():
        PID_FILE.unlink()
