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
    """Records audio from system audio device (BlackHole) and microphone."""

    def __init__(
        self,
        device: Optional[Union[str, int]] = None,
        sample_rate: int = 44100,
        channels: int = 2,
        mic_device: Optional[Union[str, int]] = None,
    ):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.mic_device = mic_device
        self.recording = False
        self.frames: List[np.ndarray] = []
        self.mic_frames: List[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream: Optional[sd.InputStream] = None
        self._mic_stream: Optional[sd.InputStream] = None

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

    def _find_mic_device(self) -> Optional[int]:
        """Find a suitable microphone device (not BlackHole or ZoomAudioDevice)."""
        try:
            default_input = sd.default.device[0]
        except Exception:
            default_input = None

        devices = sd.query_devices()

        # Try the system default input first if it's not a virtual device
        if default_input is not None and default_input >= 0:
            dev = devices[default_input]
            name = dev["name"]
            if (
                dev["max_input_channels"] >= 1
                and "BlackHole" not in name
                and "ZoomAudioDevice" not in name
            ):
                return default_input

        # Fall back: find any real input device
        for i, dev in enumerate(devices):
            name = dev["name"]
            if (
                dev["max_input_channels"] >= 1
                and "BlackHole" not in name
                and "ZoomAudioDevice" not in name
            ):
                return i

        return None

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Callback for system audio stream."""
        if status:
            print(f"Audio status: {status}", file=sys.stderr)
        with self._lock:
            if self.recording:
                self.frames.append(indata.copy())

    def _mic_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Callback for microphone stream."""
        if status:
            print(f"Mic status: {status}", file=sys.stderr)
        with self._lock:
            if self.recording:
                self.mic_frames.append(indata.copy())

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
        self.mic_frames = []
        self.recording = True

        self._stream = sd.InputStream(
            device=device,
            channels=self.channels,
            samplerate=self.sample_rate,
            callback=self._audio_callback,
            dtype=np.int16,
        )
        self._stream.start()

        # Start microphone stream
        mic_device = self.mic_device
        if mic_device is None:
            mic_device = self._find_mic_device()

        if mic_device is not None:
            try:
                self._mic_stream = sd.InputStream(
                    device=mic_device,
                    channels=1,
                    samplerate=self.sample_rate,
                    callback=self._mic_callback,
                    dtype=np.int16,
                )
                self._mic_stream.start()
                mic_name = sd.query_devices(mic_device)["name"]
                print(f"Microphone capture: {mic_name}")
            except Exception as e:
                print(f"Warning: could not open microphone ({e}), recording system audio only.", file=sys.stderr)
                self._mic_stream = None
        else:
            print("No microphone found, recording system audio only.")

    def stop(self) -> np.ndarray:
        """Stop recording and return audio data."""
        if not self.recording:
            raise RuntimeError("Not recording")

        self.recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if self._mic_stream:
            self._mic_stream.stop()
            self._mic_stream.close()
            self._mic_stream = None

        with self._lock:
            if not self.frames:
                return np.array([], dtype=np.int16)
            system_audio = np.concatenate(self.frames)
            if self.mic_frames:
                mic_audio = np.concatenate(self.mic_frames)
                return self._mix_audio(system_audio, mic_audio)
            return system_audio

    def _mix_audio(self, system: np.ndarray, mic: np.ndarray) -> np.ndarray:
        """Mix system (stereo) and mic (mono) audio into a stereo track."""
        # Upmix mono mic to stereo
        mic_stereo = np.column_stack([mic, mic])

        # Trim both to the same length
        n = min(len(system), len(mic_stereo))
        system = system[:n]
        mic_stereo = mic_stereo[:n]

        # Mix by adding, clipped to int16 range
        mixed = system.astype(np.int32) + mic_stereo.astype(np.int32)
        mixed = np.clip(mixed, np.iinfo(np.int16).min, np.iinfo(np.int16).max)
        return mixed.astype(np.int16)

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
        mic_device=config.get("mic_device"),
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
