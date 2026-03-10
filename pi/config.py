"""
Talking-Claw Pi Caller -- Configuration

Reads all settings from .env file. Never hardcode secrets.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the pi/ directory
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


# -- Telegram credentials --
TELEGRAM_API_ID: int = int(_require("TELEGRAM_API_ID"))
TELEGRAM_API_HASH: str = _require("TELEGRAM_API_HASH")
TELEGRAM_2FA_PASSWORD: str = _optional("TELEGRAM_2FA_PASSWORD")
TARGET_USER_ID: int = int(_require("TARGET_USER_ID"))

# Session file name (stored in pi/ directory)
SESSION_NAME: str = "talking_claw_userbot"
SESSION_PATH: str = str(Path(__file__).parent / SESSION_NAME)

# -- Forge GPU server --
FORGE_HOST: str = _optional("FORGE_HOST", "100.85.217.17")
FORGE_WS_PORT: int = int(_optional("FORGE_WS_PORT", "8790"))
FORGE_HEALTH_PORT: int = int(_optional("FORGE_HEALTH_PORT", "8790"))
FORGE_WS_URL: str = f"ws://{FORGE_HOST}:{FORGE_WS_PORT}/ws"
FORGE_HEALTH_URL: str = f"http://{FORGE_HOST}:{FORGE_HEALTH_PORT}/health"

# -- Wake-on-LAN (optional) --
FORGE_MAC_ADDRESS: str = _optional("FORGE_MAC_ADDRESS")
FORGE_BROADCAST: str = _optional("FORGE_BROADCAST", "100.85.255.255")

# -- Agent context --
AGENT_ID: str = _optional("AGENT_ID", "wizard")

# -- Audio settings --
# Telegram uses 16-bit PCM at 48kHz mono for calls.
# Pipecat typically expects 16kHz. We resample at the bridge.
TELEGRAM_SAMPLE_RATE: int = 48000
PIPELINE_SAMPLE_RATE: int = 16000
AUDIO_CHANNELS: int = 1
AUDIO_SAMPLE_WIDTH: int = 2  # 16-bit = 2 bytes

# -- Timeouts --
FORGE_WAKE_TIMEOUT: int = 120  # seconds to wait for Forge to come online
FORGE_HEALTH_TIMEOUT: int = 5  # seconds for health check HTTP request
CALL_RING_TIMEOUT: int = 30  # seconds to wait for user to pick up
