#!/usr/bin/env bash
#
# Talking-Claw Voice Pipeline -- One-Command Setup
#
# Run this to set up the voice pipeline:
#   chmod +x setup.sh
#   ./setup.sh
#
# Two modes:
#   Recommended (default): Groq Whisper API + Piper TTS
#     - No GPU required. Runs on Pi 5, NUC, old laptop, etc.
#     - Needs internet for Groq API calls and initial model download.
#
#   GPU Local: Local Whisper + Kokoro TTS
#     - Requires NVIDIA GPU with 6+ GB VRAM and CUDA 12.x
#     - Pass --gpu flag: ./setup.sh --gpu

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

# Parse arguments
GPU_MODE=false
if [[ "${1:-}" == "--gpu" ]]; then
    GPU_MODE=true
fi

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

info "Talking-Claw Voice Pipeline Setup"
if [ "$GPU_MODE" = true ]; then
    echo "Mode: GPU Local (Whisper + Kokoro)"
else
    echo "Mode: Recommended (Groq API + Piper TTS)"
fi
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

# Check GPU for GPU mode
if [ "$GPU_MODE" = true ]; then
    if command -v nvidia-smi &>/dev/null; then
        info "GPU detected:"
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1
    else
        warn "nvidia-smi not found -- CUDA may not be installed."
        warn "GPU mode requires an NVIDIA GPU with CUDA 12.x."
        echo "  Install CUDA: https://developer.nvidia.com/cuda-downloads"
        read -p "Continue anyway? [y/N] " -r
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
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

if [ "$GPU_MODE" = true ]; then
    info "Installing GPU dependencies..."
    pip install -r requirements-gpu.txt 2>&1 | tail -5
fi

# ---------------------------------------------------------------------------
# Download / test models
# ---------------------------------------------------------------------------

info "Testing components..."

# Silero VAD -- downloaded on first use
info "  Testing Silero VAD..."
python -c "
import torch
torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', onnx=True)
print('  Silero VAD: OK')
" 2>&1

if [ "$GPU_MODE" = true ]; then
    # Whisper model -- downloaded by faster-whisper on first use
    info "  Testing local Whisper STT (will download model if needed)..."
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
else
    # Piper TTS -- download voice model
    info "  Testing Piper TTS (will download voice model if needed)..."
    mkdir -p models
    python -c "
from pathlib import Path
from piper import PiperVoice
from piper.download_voices import download_voice

voice_name = 'en_US-ryan-high'
model_dir = Path('models')
model_file = model_dir / f'{voice_name}.onnx'

if not model_file.exists():
    print(f'  Downloading Piper voice: {voice_name}...')
    download_voice(voice_name, model_dir)

voice = PiperVoice.load(model_file)
print(f'  Piper TTS: OK (voice={voice_name})')
" 2>&1

    info "  Groq STT: Uses API (no local model needed)"
    info "    Get your free API key at https://console.groq.com"
fi

# ---------------------------------------------------------------------------
# Environment file
# ---------------------------------------------------------------------------

if [ ! -f .env ]; then
    info "Creating .env from template..."
    cp .env.example .env

    if [ "$GPU_MODE" = true ]; then
        # Switch defaults to GPU mode
        sed -i 's/^STT_BACKEND=groq/STT_BACKEND=local/' .env
        sed -i 's/^TTS_BACKEND=piper/TTS_BACKEND=kokoro/' .env
    fi

    warn "IMPORTANT: Edit .env with your settings!"
    if [ "$GPU_MODE" = false ]; then
        warn "  You MUST set GROQ_API_KEY (free from https://console.groq.com)"
    fi
    warn "  You MUST set AGENT_API_URL (your agent's HTTP endpoint)"
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
        sed "s|/home/YOUR_USER/Talking-Claw/pipeline|$REAL_DIR|g; s|YOUR_USER|$REAL_USER|g" \
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
if [ "$GPU_MODE" = false ]; then
    echo "  1. Get a free Groq API key: https://console.groq.com"
    echo "  2. Edit .env:"
    echo "       - Set GROQ_API_KEY"
    echo "       - Set AGENT_API_URL (your agent's HTTP endpoint)"
else
    echo "  1. Edit .env:"
    echo "       - Set AGENT_API_URL (your agent's HTTP endpoint)"
fi
echo
echo "  Test the pipeline:"
echo "       cd $SCRIPT_DIR"
echo "       source venv/bin/activate"
echo "       python pipeline.py"
echo
echo "  Or start as a service:"
echo "       sudo systemctl start talking-claw-pipeline"
echo
echo "The pipeline will listen on ws://0.0.0.0:8790 for"
echo "incoming audio connections from the caller."
echo "=================================================="
