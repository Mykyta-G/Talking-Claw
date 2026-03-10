"""
Talking-Claw Caller -- Configuration

Reads all settings from .env file. Never hardcode secrets.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the caller/ directory
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

# Session file name (stored in caller/ directory)
SESSION_NAME: str = "talking_claw_userbot"
SESSION_PATH: str = str(Path(__file__).parent / SESSION_NAME)

# -- pipeline server --
PIPELINE_HOST: str = _optional("PIPELINE_HOST", "YOUR_GPU_SERVER_IP")
PIPELINE_WS_PORT: int = int(_optional("PIPELINE_WS_PORT", "8790"))
PIPELINE_HEALTH_PORT: int = int(_optional("PIPELINE_HEALTH_PORT", "8790"))
PIPELINE_WS_URL: str = f"ws://{PIPELINE_HOST}:{PIPELINE_WS_PORT}/ws"
PIPELINE_HEALTH_URL: str = f"http://{PIPELINE_HOST}:{PIPELINE_HEALTH_PORT}/health"

# -- Wake-on-LAN (optional) --
WOL_MAC_ADDRESS: str = _optional("WOL_MAC_ADDRESS")
WOL_BROADCAST: str = _optional("WOL_BROADCAST", "255.255.255.255")

# -- Agent context --
AGENT_ID: str = _optional("AGENT_ID", "assistant")

# -- Audio settings --
# Telegram uses 16-bit PCM at 48kHz mono for calls.
# Pipecat typically expects 16kHz. We resample at the bridge.
TELEGRAM_SAMPLE_RATE: int = 48000
PIPELINE_SAMPLE_RATE: int = 16000
AUDIO_CHANNELS: int = 1
AUDIO_SAMPLE_WIDTH: int = 2  # 16-bit = 2 bytes

# -- Timeouts --
WOL_TIMEOUT: int = 120  # seconds to wait for pipeline server to come online
HEALTH_TIMEOUT: int = 5  # seconds for health check HTTP request
CALL_RING_TIMEOUT: int = 30  # seconds to wait for user to pick up
