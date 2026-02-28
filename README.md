# Meetcap

A macOS utility that captures audio from Zoom meetings, transcribes them locally using Whisper, summarizes with Claude API, and stores organized markdown files.

## Prerequisites

1. **BlackHole 2ch** - Virtual audio device for capturing system audio
   ```bash
   brew install blackhole-2ch
   ```

2. **FFmpeg** - For audio processing
   ```bash
   brew install ffmpeg
   ```

3. **Python 3.10+**

## Installation

```bash
cd ~/Projects/meetcap
pip install -e .
```

## Audio Setup

After installing BlackHole, you need to create a Multi-Output Device:

1. Open **Audio MIDI Setup** (Applications → Utilities)
2. Click the **+** button → **Create Multi-Output Device**
3. Check both your speakers/headphones AND **BlackHole 2ch**
4. Set this Multi-Output Device as your system output in System Preferences → Sound

This allows you to hear audio AND record it simultaneously.

## Configuration

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or configure via CLI:

```bash
meetcap configure --api-key "sk-ant-..."
```

View current configuration:

```bash
meetcap status
```

## Usage

### Manual Recording

Start a recording:
```bash
meetcap start
```

The recording runs until you press Ctrl+C.

### Automatic Processing

Install the background watch service:
```bash
meetcap install
```

This will:
- Watch `~/MeetingRecordings/raw/` for new WAV files
- Automatically transcribe and summarize them
- Save markdown files to `~/Documents/MeetingNotes/YYYY/MM/`
- Start automatically on login

To uninstall:
```bash
meetcap uninstall
```

### Manual Processing

Process an existing audio file:
```bash
meetcap process /path/to/recording.wav
```

### Other Commands

```bash
meetcap devices    # List audio devices
meetcap status     # Show configuration
meetcap watch      # Run watch service in foreground
```

## Output

Meeting notes are saved as markdown files:

```
~/Documents/MeetingNotes/
└── 2026/
    └── 02/
        └── meeting-2026-02-28-1430.md
```

Each file contains:
- YAML frontmatter with date, time, duration
- AI-generated summary with key points and action items
- Full timestamped transcript

## Troubleshooting

### "BlackHole audio device not found"
Install BlackHole: `brew install blackhole-2ch`

### No audio captured
Make sure your Multi-Output Device is set as the system output and BlackHole is enabled in it.

### API key not configured
Set `ANTHROPIC_API_KEY` environment variable or run `meetcap configure --api-key "..."`
