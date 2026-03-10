"""
Talking-Claw Forge Pipeline -- Configuration

Reads all settings from .env file. Runs on the GPU server.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the forge/ directory
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


# -- Clawdbot Gateway --
CLAWDBOT_GATEWAY: str = _require("CLAWDBOT_GATEWAY")
GATEWAY_TOKEN: str = _optional("GATEWAY_TOKEN")
DEFAULT_AGENT_ID: str = _optional("AGENT_ID", "wizard")

# -- Pipeline server --
PIPELINE_HOST: str = _optional("PIPELINE_HOST", "0.0.0.0")
PIPELINE_PORT: int = int(_optional("PIPELINE_PORT", "8790"))

# -- Whisper STT --
WHISPER_MODEL: str = _optional("WHISPER_MODEL", "distil-medium.en")
WHISPER_DEVICE: str = _optional("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE: str = _optional("WHISPER_COMPUTE_TYPE", "float16")
WHISPER_LANGUAGE: str = _optional("WHISPER_LANGUAGE", "en")

# -- VAD --
VAD_THRESHOLD: float = float(_optional("VAD_THRESHOLD", "0.5"))

# -- Voice / TTS --
DEFAULT_VOICE: str = _optional("DEFAULT_VOICE", "bm_lewis")

# Per-agent voice mapping
_voice_map_raw = _optional("VOICE_MAP", '{}')
try:
    VOICE_MAP: dict[str, str] = json.loads(_voice_map_raw)
except json.JSONDecodeError:
    VOICE_MAP = {}

# Ensure defaults exist in the map
VOICE_MAP.setdefault("wizard", "bm_lewis")
VOICE_MAP.setdefault("killer", "am_michael")
VOICE_MAP.setdefault("gunnar", "am_adam")
VOICE_MAP.setdefault("default", DEFAULT_VOICE)


def get_voice(agent_id: str) -> str:
    """Get the TTS voice for a given agent."""
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
