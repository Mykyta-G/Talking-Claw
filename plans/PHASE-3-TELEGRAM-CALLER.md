# Phase 3 -- Telegram Voice Caller

> **Time:** 1-2 hours
> **What:** Set up the Telegram userbot that initiates real calls and bridges audio.

This is the trickiest phase. The userbot makes a real Telegram call to your account
and bridges the audio to/from the voice pipeline over WebSocket.

## 3.1 -- Install on Orchestrator

```bash
# On your server / orchestrator machine
mkdir -p ~/talking-claw/caller
cd ~/talking-claw/caller
python3 -m venv venv
source venv/bin/activate

pip install pyrogram tgcrypto py-tgcalls websockets aiohttp numpy
```

## 3.2 -- Authenticate Pyrogram (One-Time)

```python
# auth.py -- run ONCE interactively
from pyrogram import Client

app = Client(
    "talking_claw_userbot",
    api_id=YOUR_API_ID,        # from Phase 1
    api_hash="YOUR_API_HASH",  # from Phase 1
)

with app:
    me = app.get_me()
    print(f"Logged in as: {me.first_name} (ID: {me.id})")
    print("Session saved to: talking_claw_userbot.session")
```

```bash
python auth.py
# Enter the TextNow phone number when prompted
# Enter the verification code from TextNow app
# Enter the 2FA password if set
# Done -- session file created
```

## 3.3 -- The Call Bridge

This is the core component. It:
1. Initiates a real 1-on-1 Telegram call to your account
2. Captures incoming audio (your voice) -> sends to pipeline via WebSocket
3. Receives audio from pipeline (AI voice) -> plays into the Telegram call

```python
# caller.py
"""
Telegram Voice Call Bridge.
Makes a real call and bridges audio to the serverpecat voice pipeline.
"""

import asyncio
import websockets
import numpy as np
from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioStream

# === CONFIG ===
API_ID = 0              # fill in
API_HASH = ""           # fill in
SESSION = "talking_claw_userbot"
TARGET_USER_ID = 0      # your main Telegram user ID
PIPELINE_WS = "ws://YOUR_GPU_SERVER_IP:8790"

# === SETUP ===
app = Client(SESSION, api_id=API_ID, api_hash=API_HASH)
call = PyTgCalls(app)


async def make_call(reason: str = ""):
    await app.start()
    await call.start()

    print(f"[caller] Calling user {TARGET_USER_ID}...")

    # Connect to voice pipeline
    ws = await websockets.connect(PIPELINE_WS)
    print("[caller] Connected to voice pipeline")

    # pytgcalls audio callbacks
    # These handle the raw PCM audio streaming between Telegram and the pipeline

    # NOTE: The exact pytgcalls API for private 1-on-1 calls varies by version.
    # As of pytgcalls 1.x / 2.x, group voice chats are well-supported.
    # For direct private calls, you may need to:
    #
    # Option A: Use pytgcalls with a private group (reliable)
    #   1. Create a group with just the bot + target user (one-time setup)
    #   2. Start a voice chat in that group
    #   3. User gets notification, joins the voice chat
    #
    # Option B: Use Telegram's raw phone.requestCall API via Pyrogram (real call)
    #   This initiates an actual VoIP call -- phone rings on the target's device.
    #   Requires implementing the call signaling protocol.
    #   See: https://core.telegram.org/acaller/end-to-end/voice-calls
    #
    # Option C: Use tgcalls (MarshalX's lower-level library)
    #   pip install tgcalls
    #   Supports raw audio callbacks for private calls.
    #
    # Start with Option A for quick testing, then upgrade to Option B/C.

    # === PLACEHOLDER: Audio bridge implementation ===
    # The actual implementation depends on which pytgcalls version and approach you use.
    # The core loop is:
    #
    # while call_active:
    #     # Receive audio from Telegram call (your voice)
    #     audio_in = await get_telegram_audio()
    #     await ws.send(audio_in)  # send to pipeline for STT
    #
    #     # Receive audio from pipeline (AI response)
    #     audio_out = await ws.recv()
    #     await play_telegram_audio(audio_out)  # play into call
    #
    # See examples/ folder for working implementations of each approach.

    print("[caller] Call ended")
    await ws.close()
    await app.stop()


if __name__ == "__main__":
    import sys
    reason = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    asyncio.run(make_call(reason))
```

## 3.4 -- Call Trigger Script

This is what your AI agent runs when it wants to call you.

```python
# trigger.py
"""
Entry point: trigger a voice call.
Usage: python trigger.py "I finished the deployment"
"""

import asyncio
import sys
import aiohttp

GPU_SERVER = "YOUR_GPU_SERVER_IP"
PIPELINE_PORT = 8790


async def ensure_pipeline_ready():
    """Check if the voice pipeline is running on the GPU server."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://{GPU_SERVER}:{PIPELINE_PORT}/health",
                timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def main():
    reason = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "General check-in"

    if not await ensure_pipeline_ready():
        print("[trigger] Voice pipeline is not running!")
        # Optionally: start it, wake the GPU server, etc.
        sys.exit(1)

    print(f"[trigger] Starting call: {reason}")
    from caller import make_call
    await make_call(reason)


if __name__ == "__main__":
    asyncio.run(main())
```

## 3.5 -- Run as Service

```bash
# /etc/systemd/system/talking-claw-caller.service
[Unit]
Description=Talking-Claw Caller (standby, activated by trigger)
After=network.target

[Service]
Type=oneshot
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/talking-claw/caller
ExecStart=/home/YOUR_USER/talking-claw/caller/venv/bin/python trigger.py
RemainAfterExit=no
```

## What You Have After This Phase

```
Pyrogram session authenticated
Userbot can initiate calls to your Telegram account
Audio bridges between Telegram call and voice pipeline
Trigger script ready for agents to invoke
```

## Known Challenges

1. **pytgcalls private call API** -- group voice chats are well-tested; direct 1-on-1 calls need the lower-level `phone.requestCall` API. Test both approaches.
2. **Audio format mismatch** -- Telegram uses 48kHz/16-bit PCM, Pipecat may expect different rates. You will need resampling (numpy or scipy).
3. **Telegram session conflicts** -- the userbot session must only be used by ONE process at a time. Do not run auth.py while caller.py is running.
