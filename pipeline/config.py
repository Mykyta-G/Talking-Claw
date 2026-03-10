"""
Talking-Claw Voice Pipeline -- Configuration

Reads all settings from .env file.

Supports two modes:
    - Recommended (no GPU): Groq Whisper API + Piper TTS (runs on Pi 5, NUC, etc.)
    - GPU Local: Local faster-whisper + Kokoro TTS (needs NVIDIA GPU)

Set STT_BACKEND and TTS_BACKEND in .env to switch between them.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the pipeline/ directory
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)


def _require(key: str) -> str:
    """Get a required environment variable or raise."""
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {key}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    """Get an optional environment variable with a default."""
    return os.getenv(key, default).strip()


# -- Agent API --
AGENT_API_URL: str = _require("AGENT_API_URL")
GATEWAY_TOKEN: str = _optional("GATEWAY_TOKEN")
DEFAULT_AGENT_ID: str = _optional("AGENT_ID", "assistant")

# -- Pipeline server --
PIPELINE_HOST: str = _optional("PIPELINE_HOST", "0.0.0.0")
PIPELINE_PORT: int = int(_optional("PIPELINE_PORT", "8790"))

# -- Backend selection --
STT_BACKEND: str = _optional("STT_BACKEND", "groq")       # "groq" or "local"
TTS_BACKEND: str = _optional("TTS_BACKEND", "piper")       # "piper" or "kokoro"

# -- Groq STT (recommended, no GPU needed) --
GROQ_API_KEY: str = _optional("GROQ_API_KEY")
GROQ_WHISPER_MODEL: str = _optional("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")

# -- Local Whisper STT (GPU mode) --
WHISPER_MODEL: str = _optional("WHISPER_MODEL", "distil-medium.en")
WHISPER_DEVICE: str = _optional("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE: str = _optional("WHISPER_COMPUTE_TYPE", "float16")
WHISPER_LANGUAGE: str = _optional("WHISPER_LANGUAGE", "en")

# -- Piper TTS (recommended, no GPU needed) --
PIPER_VOICE: str = _optional("PIPER_VOICE", "en_US-ryan-high")
PIPER_DOWNLOAD_DIR: str = _optional("PIPER_DOWNLOAD_DIR", "")
PIPER_USE_CUDA: bool = _optional("PIPER_USE_CUDA", "false").lower() in ("true", "1", "yes")

# -- VAD --
VAD_THRESHOLD: float = float(_optional("VAD_THRESHOLD", "0.5"))

# -- Voice / TTS (Kokoro, GPU mode) --
DEFAULT_VOICE: str = _optional("DEFAULT_VOICE", "bm_lewis")

# Per-agent voice mapping (for Kokoro)
# Set VOICE_MAP in .env as JSON, e.g.: {"assistant":"bm_lewis","helper":"am_adam"}
_voice_map_raw = _optional("VOICE_MAP", '{}')
try:
    VOICE_MAP: dict[str, str] = json.loads(_voice_map_raw)
except json.JSONDecodeError:
    VOICE_MAP = {}

# Ensure a default entry exists in the map
VOICE_MAP.setdefault("default", DEFAULT_VOICE)


def get_voice(agent_id: str) -> str:
    """Get the TTS voice for a given agent (Kokoro mode)."""
    return VOICE_MAP.get(agent_id, VOICE_MAP["default"])


# -- Voice system prompt --
VOICE_SYSTEM_PROMPT: str = _optional(
    "VOICE_SYSTEM_PROMPT",
    "You are in a LIVE VOICE CALL. Your text is being spoken aloud. "
    "Keep responses to 1-3 sentences. Use contractions. Speak naturally. "
    "No markdown, no bullet points, no code blocks. "
    "If asked about code or long content, say you will send it in chat. "
    "Match your personality but keep it CONCISE."
)

# -- Audio settings --
PIPELINE_SAMPLE_RATE: int = 16000  # What Pipecat/Whisper expects
AUDIO_CHANNELS: int = 1
AUDIO_SAMPLE_WIDTH: int = 2  # 16-bit PCM
