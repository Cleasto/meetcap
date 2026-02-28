#!/bin/bash
# Meetcap Setup Script
# Run this script to set up all dependencies for meetcap

set -e

echo "=== Meetcap Setup ==="
echo

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Please install Homebrew first:"
    echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

# Install BlackHole
echo "Installing BlackHole 2ch (virtual audio device)..."
if brew list blackhole-2ch &>/dev/null; then
    echo "  BlackHole already installed"
else
    brew install blackhole-2ch
    echo "  BlackHole installed"
fi

# Install ffmpeg
echo "Installing ffmpeg..."
if brew list ffmpeg &>/dev/null; then
    echo "  ffmpeg already installed"
else
    brew install ffmpeg
    echo "  ffmpeg installed"
fi

# Install meetcap
echo "Installing meetcap..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
pip3 install -e "$PROJECT_DIR"

echo
echo "=== Setup Complete ==="
echo
echo "Next steps:"
echo
echo "1. Set up Multi-Output Device for audio routing:"
echo "   - Open 'Audio MIDI Setup' (in Applications/Utilities)"
echo "   - Click '+' button → 'Create Multi-Output Device'"
echo "   - Check your speakers/headphones AND 'BlackHole 2ch'"
echo "   - Set this Multi-Output Device as your system output"
echo
echo "2. Configure your API key:"
echo "   export ANTHROPIC_API_KEY='your-key-here'"
echo "   # Or: meetcap configure --api-key 'your-key-here'"
echo
echo "3. Test recording:"
echo "   meetcap start"
echo "   # Play some audio, then Ctrl+C to stop"
echo
echo "4. Install background watch service:"
echo "   meetcap install"
echo
