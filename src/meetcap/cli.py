"""Command-line interface for meetcap."""

import sys

import click

from . import __version__
from .config import (
    CONFIG_FILE,
    LOG_FILE,
    expand_path,
    get_output_dir,
    get_raw_dir,
    load_config,
    save_config,
)


@click.group()
@click.version_option(version=__version__)
def main():
    """Meetcap - Zoom meeting transcription and summarization utility."""
    pass


@main.command()
def start():
    """Start recording audio from BlackHole device."""
    from .recorder import start_recording

    try:
        start_recording()
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


@main.command()
def stop():
    """Stop the current recording."""
    from .recorder import stop_recording

    stop_recording()


@main.command()
def watch():
    """Start the watch folder service (foreground)."""
    from .watcher import run_watcher

    click.echo("Starting watch service... (Ctrl+C to stop)")
    run_watcher()


@main.command()
@click.argument("audio_file", type=click.Path(exists=True))
def process(audio_file: str):
    """Manually process an audio file."""
    from pathlib import Path

    from .processor import process_recording

    audio_path = Path(audio_file)
    if audio_path.suffix.lower() != ".wav":
        click.echo("Error: Only WAV files are supported", err=True)
        sys.exit(1)

    click.echo(f"Processing: {audio_path}")
    try:
        output_path = process_recording(audio_path)
        click.echo(f"Created: {output_path}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def status():
    """Show meetcap status and configuration."""
    config = load_config()

    click.echo("Meetcap Status")
    click.echo("=" * 40)
    click.echo(f"Config file: {CONFIG_FILE}")
    click.echo(f"Log file: {LOG_FILE}")
    click.echo(f"Recordings dir: {get_raw_dir(config)}")
    click.echo(f"Output dir: {get_output_dir(config)}")
    click.echo(f"Whisper model: {config.get('whisper_model', 'base.en')}")
    click.echo(f"API key configured: {'Yes' if config.get('anthropic_api_key') else 'No'}")

    # Check for capture devices
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        capture_device = None
        for i, dev in enumerate(devices):
            if "BlackHole" in dev["name"]:
                capture_device = dev["name"]
                break
        if not capture_device:
            for i, dev in enumerate(devices):
                if "ZoomAudioDevice" in dev["name"]:
                    capture_device = dev["name"]
                    break
        click.echo(f"Capture device: {capture_device or 'Not found (install BlackHole)'}")
    except Exception:
        click.echo("Capture device: Unable to check")

    # Count pending recordings
    raw_dir = get_raw_dir(config)
    if raw_dir.exists():
        pending = list(raw_dir.glob("*.wav"))
        click.echo(f"Pending recordings: {len(pending)}")


@main.command()
@click.option("--api-key", help="Anthropic API key")
@click.option("--whisper-model", help="Whisper model (tiny, base, small, medium, large)")
@click.option("--output-dir", help="Directory for meeting notes")
@click.option("--recordings-dir", help="Directory for recordings")
def configure(api_key, whisper_model, output_dir, recordings_dir):
    """Configure meetcap settings."""
    config = load_config()

    if api_key:
        config["anthropic_api_key"] = api_key
    if whisper_model:
        config["whisper_model"] = whisper_model
    if output_dir:
        config["output_dir"] = output_dir
    if recordings_dir:
        config["recordings_dir"] = recordings_dir

    save_config(config)
    click.echo(f"Configuration saved to {CONFIG_FILE}")


@main.command()
def devices():
    """List available audio input devices."""
    try:
        import sounddevice as sd

        click.echo("Available audio input devices:")
        click.echo("-" * 50)

        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                if "BlackHole" in dev["name"]:
                    marker = " <-- BlackHole (recommended)"
                elif "ZoomAudioDevice" in dev["name"]:
                    marker = " <-- ZoomAudioDevice"
                else:
                    marker = ""
                click.echo(f"[{i}] {dev['name']}{marker}")
                click.echo(f"    Channels: {dev['max_input_channels']}, "
                          f"Sample Rate: {dev['default_samplerate']}")

    except ImportError:
        click.echo("sounddevice not installed. Run: pip install sounddevice", err=True)
        sys.exit(1)


@main.command()
def install():
    """Install the LaunchAgent for background watch service."""
    import os
    import subprocess
    from pathlib import Path

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)

    plist_path = plist_dir / "com.meetcap.watcher.plist"

    # Find the meetcap-watch executable
    meetcap_watch = subprocess.run(
        ["which", "meetcap-watch"],
        capture_output=True,
        text=True,
    )

    if meetcap_watch.returncode != 0:
        click.echo("Error: meetcap-watch not found in PATH", err=True)
        click.echo("Make sure meetcap is installed: pip install -e .", err=True)
        sys.exit(1)

    watch_path = meetcap_watch.stdout.strip()

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.meetcap.watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>{watch_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>{LOG_FILE}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>ANTHROPIC_API_KEY</key>
        <string>{os.environ.get('ANTHROPIC_API_KEY', '')}</string>
    </dict>
</dict>
</plist>
"""

    plist_path.write_text(plist_content)
    click.echo(f"Created: {plist_path}")

    # Load the agent
    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo("Watch service installed and started!")
        click.echo("It will automatically start on login.")
    else:
        click.echo(f"Warning: Could not start service: {result.stderr}", err=True)
        click.echo("You may need to run: launchctl load " + str(plist_path))


@main.command()
def uninstall():
    """Uninstall the LaunchAgent."""
    import subprocess
    from pathlib import Path

    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.meetcap.watcher.plist"

    if not plist_path.exists():
        click.echo("Watch service is not installed.")
        return

    # Unload the agent
    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True,
    )

    plist_path.unlink()
    click.echo("Watch service uninstalled.")


@main.command()
def ui():
    """Launch the menu bar app."""
    from .menubar import MeetcapStatusApp

    MeetcapStatusApp().run()


if __name__ == "__main__":
    main()
