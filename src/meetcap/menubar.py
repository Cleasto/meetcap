"""macOS menu bar application for Meetcap."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from subprocess import Popen
from typing import Optional, Set

import rumps

from .config import get_output_dir, get_processed_dir, get_raw_dir, load_config
from .processor import parse_filename_datetime, process_recording
from .recorder import AudioRecorder, generate_filename


def _make_bubble_icon():
    """Build a 22×22 speech-bubble NSImage with 'hi' cut out.

    Drawn as a template image so macOS tints it automatically for both the
    light and dark menu-bar appearances.
    """
    from AppKit import (
        NSBezierPath, NSColor, NSFont, NSFontAttributeName,
        NSForegroundColorAttributeName, NSGraphicsContext, NSImage,
    )
    from Foundation import NSMakeRect, NSMakeSize, NSString

    w, h = 22.0, 22.0
    image = NSImage.alloc().initWithSize_(NSMakeSize(w, h))
    image.lockFocus()

    # Transparent canvas
    NSColor.clearColor().set()
    NSBezierPath.fillRect_(NSMakeRect(0, 0, w, h))

    NSColor.blackColor().set()

    # Bubble body — rounded rect in the upper portion of the canvas
    body_x, body_y, body_w, body_h = 0.5, 5.5, 20.0, 14.0
    bubble = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(body_x, body_y, body_w, body_h), 3.5, 3.5
    )
    bubble.fill()

    # Speech tail — small triangle at bottom-left
    tail = NSBezierPath.bezierPath()
    tail.moveToPoint_((5.0, body_y))
    tail.lineToPoint_((2.5, 2.5))
    tail.lineToPoint_((10.0, body_y))
    tail.closePath()
    tail.fill()

    # "hi" text cut out of the solid bubble using the Clear compositing op
    ctx = NSGraphicsContext.currentContext()
    ctx.setCompositingOperation_(0)  # NSCompositingOperationClear

    font = NSFont.boldSystemFontOfSize_(8.0)
    attrs = {
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: NSColor.blackColor(),
    }
    label = NSString.stringWithString_("hi")
    sz = label.sizeWithAttributes_(attrs)
    label.drawAtPoint_withAttributes_(
        (
            round(body_x + (body_w - sz.width) / 2),
            round(body_y + (body_h - sz.height) / 2),
        ),
        attrs,
    )

    ctx.setCompositingOperation_(2)  # NSCompositingOperationSourceOver

    image.unlockFocus()
    image.setTemplate_(True)
    return image


class MeetcapStatusApp(rumps.App):
    """macOS menu bar app for recording and processing meetings."""

    def __init__(self):
        super().__init__("Meetcap", quit_button="Quit")

        # Inject the programmatically drawn icon.  App.__init__ sets
        # _icon_nsimage = None; overwrite it here before run() calls
        # initializeStatusBar(), which reads exactly this attribute.
        self._icon_nsimage = _make_bubble_icon()
        self._title = None  # icon only; no text in the idle state

        self._config = load_config()
        self._recorder: Optional[AudioRecorder] = None
        self._recording = False
        self._current_filepath: Optional[Path] = None
        self._processing: Set[str] = set()
        self._playback: Optional[Popen] = None

        # Persistent menu items
        self._record_btn = rumps.MenuItem("⏺ Start Recording", callback=self._toggle_recording)
        self._raw_menu = rumps.MenuItem("Raw Recordings")
        self._search_btn = rumps.MenuItem("Search Recordings...", callback=self._search_recordings)
        self._search_results_item = rumps.MenuItem("Search Results")
        self._status_item = rumps.MenuItem("⏳ Processing...")
        self._refresh_btn = rumps.MenuItem("Refresh", callback=self._rebuild_menus)

        self.menu = [
            self._record_btn,
            None,
            self._raw_menu,
            None,
            self._search_btn,
            self._search_results_item,
            None,
            self._status_item,
            self._refresh_btn,
        ]

        # Hide items that start hidden
        self._status_item._menuitem.setHidden_(True)
        self._search_results_item._menuitem.setHidden_(True)

        # Disable AppKit's automatic item validation on the top-level status bar
        # menu so that container items (no callback, but with submenus) are never
        # auto-grayed.  Submenus that contain actionable buttons keep their own
        # autoenablesItems=True so the "Process" button is still grayed while busy.
        self.menu._menu.setAutoenablesItems_(False)

        self._rebuild_menus()

        # Auto-refresh every 10 seconds
        rumps.Timer(self._rebuild_menus, 10).start()

    def _rebuild_menus(self, _ = None) -> None:
        """Scan raw recordings directory and rebuild the Raw Recordings submenu."""
        raw_dir = get_raw_dir(self._config)
        wavs: list[Path] = []
        if raw_dir.exists():
            wavs = sorted(
                raw_dir.glob("*.wav"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

        if self._raw_menu._menu is not None:
            self._raw_menu.clear()

        for wav in wavs:
            mb = wav.stat().st_size / (1024 * 1024)
            label = f"{wav.stem}  ({mb:.1f} MB)"
            item = rumps.MenuItem(label)

            play_item = rumps.MenuItem("▶ Play", callback=lambda s, p=wav: self._play(p))

            process_cb = None if wav.stem in self._processing else (lambda s, p=wav: self._process(p))
            process_item = rumps.MenuItem("⚙ Process", callback=process_cb)

            delete_item = rumps.MenuItem("🗑 Delete", callback=lambda s, p=wav: self._delete(p))

            item["▶ Play"] = play_item
            item["⚙ Process"] = process_item
            item["🗑 Delete"] = delete_item

            self._raw_menu[label] = item

        # Keep recording-entry rows enabled so they can expand their submenus.
        # (Play/Process/Delete buttons inside each row keep autoenablesItems=True
        # so "Process" is correctly grayed while a job is running.)
        if self._raw_menu._menu is not None:
            self._raw_menu._menu.setAutoenablesItems_(False)

        self._raw_menu.title = f"Raw Recordings ({len(wavs)})"

    def _toggle_recording(self, sender) -> None:
        """Start or stop audio recording."""
        if not self._recording:
            raw_dir = get_raw_dir(self._config)
            raw_dir.mkdir(parents=True, exist_ok=True)

            self._recorder = AudioRecorder(
                device=self._config.get("audio_device"),
                sample_rate=self._config.get("sample_rate", 44100),
                channels=self._config.get("channels", 2),
                mic_device=self._config.get("mic_device"),
            )

            filename = generate_filename()
            self._current_filepath = raw_dir / filename

            try:
                self._recorder.start()
            except RuntimeError as e:
                rumps.alert(title="Recording Error", message=str(e))
                self._recorder = None
                self._current_filepath = None
                return

            self._recording = True
            self.title = " REC"
            sender.title = "⏹ Stop Recording"
        else:
            audio_data = self._recorder.stop() if self._recorder else None
            if audio_data is not None and len(audio_data) > 0 and self._current_filepath:
                self._recorder.save(audio_data, self._current_filepath)

            self._recorder = None
            self._recording = False
            self._current_filepath = None
            self.title = ""
            sender.title = "⏺ Start Recording"
            self._rebuild_menus()

    def _play(self, path: Path) -> None:
        """Play an audio file using afplay."""
        if self._playback and self._playback.poll() is None:
            self._playback.terminate()
        self._playback = subprocess.Popen(["afplay", str(path)])

    def _process(self, path: Path) -> None:
        """Start background processing of a recording."""
        self._processing.add(path.stem)
        self._status_item.title = f"⏳ Processing {path.stem}..."
        self._status_item._menuitem.setHidden_(False)
        self._rebuild_menus()
        threading.Thread(target=self._run_processing, args=(path,), daemon=True).start()

    def _run_processing(self, path: Path) -> None:
        """Background thread: run the full processing pipeline."""
        stem = path.stem
        try:
            process_recording(path, self._config)
            rumps.notification("Meetcap", "Processing complete", stem)
        except Exception as e:
            rumps.notification("Meetcap", "Processing failed", str(e))
        finally:
            self._processing.discard(stem)
            if not self._processing:
                self._status_item._menuitem.setHidden_(True)
            self._rebuild_menus()

    def _delete(self, path: Path) -> None:
        """Confirm and delete a recording."""
        response = rumps.alert(
            title="Delete Recording",
            message=f"Delete {path.name}?",
            ok="Delete",
            cancel="Cancel",
        )
        if response == 1:
            path.unlink(missing_ok=True)
            self._rebuild_menus()

    def _search_recordings(self, sender) -> None:
        """Open a search dialog and update the Search Results submenu."""
        window = rumps.Window(
            message="Search transcripts:",
            title="Search Recordings",
            ok="Search",
            cancel="Cancel",
            dimensions=(320, 20),
        )
        response = window.run()

        if response.clicked != 1:
            return

        query = response.text.strip()
        if not query:
            return

        output_dir = get_output_dir(self._config)
        processed_dir = get_processed_dir(self._config)

        matches = []
        if output_dir.exists():
            for md_path in output_dir.glob("**/*.md"):
                try:
                    if query.lower() in md_path.read_text(encoding="utf-8", errors="ignore").lower():
                        wav_path = processed_dir / (md_path.stem + ".wav")
                        matches.append((md_path, wav_path if wav_path.exists() else None))
                except Exception:
                    continue

        if self._search_results_item._menu is not None:
            self._search_results_item.clear()

        if matches:
            self._search_results_item.title = f"Search Results ({len(matches)})"
            self._search_results_item._menuitem.setHidden_(False)

            for md_path, wav_path in matches:
                item = rumps.MenuItem(md_path.stem)

                if wav_path:
                    item["▶ Play Recording"] = rumps.MenuItem(
                        "▶ Play Recording",
                        callback=lambda s, p=wav_path: self._play(p),
                    )

                item["📄 View Transcript"] = rumps.MenuItem(
                    "📄 View Transcript",
                    callback=lambda s, p=md_path: self._view_transcript(p),
                )

                self._search_results_item[md_path.stem] = item

            # Keep match rows enabled so they expand to Play / View Transcript.
            if self._search_results_item._menu is not None:
                self._search_results_item._menu.setAutoenablesItems_(False)
        else:
            self._search_results_item.title = f"No results for '{query}'"
            self._search_results_item._menuitem.setHidden_(False)

    def _view_transcript(self, md_path: Path) -> None:
        """Open a transcript file in the default application."""
        subprocess.run(["open", str(md_path)])

    def _find_markdown(self, wav_path: Path) -> Optional[Path]:
        """Find the markdown file corresponding to a processed WAV."""
        meeting_dt = parse_filename_datetime(wav_path.name)
        output_dir = get_output_dir(self._config)
        md_path = (
            output_dir
            / meeting_dt.strftime("%Y")
            / meeting_dt.strftime("%m")
            / (wav_path.stem + ".md")
        )
        return md_path if md_path.exists() else None
