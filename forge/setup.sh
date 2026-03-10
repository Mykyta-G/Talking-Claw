#!/usr/bin/env bash
#
# Talking-Claw Forge Pipeline -- One-Command Setup
#
# Run this on the Forge GPU server to set up everything:
#   chmod +x setup.sh
#   ./setup.sh
#
# Requirements:
#   - NVIDIA GPU with 6+ GB VRAM
#   - CUDA 12.x installed
#   - Python 3.10+
#   - Internet connection (downloads models ~3 GB)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

info "Talking-Claw Forge Pipeline Setup"
echo "=================================================="
echo

# Check Python version
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    error "Python 3.10+ is required but not found."
    error "Install it: sudo apt install python3.11 python3.11-venv"
    exit 1
fi
info "Using Python: $PYTHON ($($PYTHON --version))"

# Check NVIDIA GPU
if command -v nvidia-smi &>/dev/null; then
    info "GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1
else
    warn "nvidia-smi not found -- CUDA may not be installed."
    warn "Pipeline requires an NVIDIA GPU with CUDA 12.x."
    echo "  Install CUDA: https://developer.nvidia.com/cuda-downloads"
    read -p "Continue anyway? [y/N] " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Create virtual environment
# ---------------------------------------------------------------------------

info "Creating virtual environment..."
if [ -d "venv" ]; then
    warn "venv/ already exists -- reusing it"
else
    "$PYTHON" -m venv venv
fi
source venv/bin/activate
info "Virtual environment active: $(which python)"

# Upgrade pip
pip install --upgrade pip wheel setuptools 2>&1 | tail -1

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------

info "Installing Python dependencies (this may take a few minutes)..."
pip install -r requirements.txt 2>&1 | tail -5

# ---------------------------------------------------------------------------
# Download models
# ---------------------------------------------------------------------------

info "Downloading models (first run only, ~3 GB total)..."

# Whisper model -- downloaded by faster-whisper on first use
info "  Testing Whisper STT (will download model if needed)..."
python -c "
from faster_whisper import WhisperModel
model = WhisperModel('distil-medium.en', device='cuda', compute_type='float16')
print('  Whisper STT: OK')
" 2>&1

# Kokoro TTS model -- downloaded by kokoro-onnx on first use
info "  Testing Kokoro TTS..."
python -c "
from kokoro_onnx import Kokoro
kokoro = Kokoro('kokoro-v1.0.onnx', 'voices-v1.0.bin')
samples, sr = kokoro.create('Test.', voice='bm_lewis', speed=1.0)
print(f'  Kokoro TTS: OK ({len(samples)} samples at {sr}Hz)')
" 2>&1

# Silero VAD -- downloaded on first use
info "  Testing Silero VAD..."
python -c "
import torch
torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', onnx=True)
print('  Silero VAD: OK')
" 2>&1

# ---------------------------------------------------------------------------
# Environment file
# ---------------------------------------------------------------------------

if [ ! -f .env ]; then
    info "Creating .env from template..."
    cp .env.example .env
    warn "IMPORTANT: Edit .env with your clawdbot gateway details!"
    warn "  nano $SCRIPT_DIR/.env"
else
    info ".env file already exists -- not overwriting"
fi

# ---------------------------------------------------------------------------
# Systemd service (optional)
# ---------------------------------------------------------------------------

echo
read -p "Install systemd service? [y/N] " -r
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SERVICE_FILE="services/talking-claw-pipeline.service"
    if [ -f "$SERVICE_FILE" ]; then
        # Replace placeholder paths with actual paths
        REAL_USER="$(whoami)"
        REAL_DIR="$SCRIPT_DIR"
        sed "s|/home/YOUR_USER/talking-claw/forge|$REAL_DIR|g; s|YOUR_USER|$REAL_USER|g" \
            "$SERVICE_FILE" | sudo tee /etc/systemd/system/talking-claw-pipeline.service >/dev/null
        sudo systemctl daemon-reload
        sudo systemctl enable talking-claw-pipeline
        info "Service installed. Start with: sudo systemctl start talking-claw-pipeline"
    else
        warn "Service file not found at $SERVICE_FILE"
    fi
fi

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

echo
echo "=================================================="
info "Setup complete!"
echo
echo "Next steps:"
echo "  1. Edit .env with your clawdbot gateway URL and token"
echo "  2. Test the pipeline:"
echo "       cd $SCRIPT_DIR"
echo "       source venv/bin/activate"
echo "       python pipeline.py"
echo
echo "  3. Or start as a service:"
echo "       sudo systemctl start talking-claw-pipeline"
echo
echo "The pipeline will listen on ws://0.0.0.0:8790 for"
echo "incoming audio connections from the Pi caller."
echo "=================================================="
