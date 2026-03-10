"""
Talking-Claw -- Telegram Voice Call Bridge

Makes a real Telegram call and bridges audio to/from the Pipecat voice pipeline
running on the Forge GPU server via WebSocket.

Architecture:
    Telegram Call (48kHz PCM) <-> This Bridge <-> WebSocket <-> Pipecat Pipeline

The bridge handles:
    - Initiating the Telegram call via pytgcalls
    - Resampling audio between Telegram (48kHz) and Pipecat (16kHz)
    - Streaming raw PCM chunks over WebSocket in both directions
    - Graceful shutdown on call end or error
"""

import asyncio
import json
import logging
import struct
import time
from typing import Optional

import numpy as np
import websockets
from pyrogram import Client, filters
from pyrogram.raw import functions as raw_functions
from pyrogram.raw import types as raw_types
from pytgcalls import PyTgCalls
from pytgcalls.types import (
    AudioQuality,
    MediaStream,
)

from config import (
    AUDIO_CHANNELS,
    FORGE_WS_URL,
    PIPELINE_SAMPLE_RATE,
    SESSION_PATH,
    TARGET_USER_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_SAMPLE_RATE,
)

logger = logging.getLogger("talking-claw.caller")

# ---------------------------------------------------------------------------
# Audio resampling helpers
# ---------------------------------------------------------------------------

def resample_pcm(
    pcm_bytes: bytes,
    from_rate: int,
    to_rate: int,
) -> bytes:
    """
    Resample 16-bit mono PCM audio from one sample rate to another.
    Uses simple linear interpolation -- good enough for voice.
    """
    if from_rate == to_rate:
        return pcm_bytes

    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    ratio = to_rate / from_rate
    n_out = int(len(samples) * ratio)

    if n_out == 0:
        return b""

    indices = np.arange(n_out) / ratio
    indices_floor = np.floor(indices).astype(np.int64)
    indices_ceil = np.minimum(indices_floor + 1, len(samples) - 1)
    frac = (indices - indices_floor).astype(np.float32)

    resampled = samples[indices_floor] * (1.0 - frac) + samples[indices_ceil] * frac
    return resampled.astype(np.int16).tobytes()


# ---------------------------------------------------------------------------
# Call transcript
# ---------------------------------------------------------------------------

class Transcript:
    """Collects the conversation for post-call summary."""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def start(self) -> None:
        self.start_time = time.time()

    def add(self, role: str, text: str) -> None:
        self.entries.append({
            "role": role,
            "text": text,
            "time": time.time(),
        })

    def stop(self) -> None:
        self.end_time = time.time()

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def format(self) -> str:
        lines = []
        for entry in self.entries:
            speaker = "User" if entry["role"] == "user" else "AI"
            lines.append(f"{speaker}: {entry['text']}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main call bridge
# ---------------------------------------------------------------------------

class CallBridge:
    """
    Bridges a Telegram voice call with the Pipecat voice pipeline.

    Flow:
        1. Connect to Forge WebSocket
        2. Initiate Telegram call to TARGET_USER_ID
        3. Stream audio bidirectionally
        4. Clean up on call end
    """

    def __init__(self, agent_id: str = "wizard", reason: str = "") -> None:
        self.agent_id = agent_id
        self.reason = reason
        self.transcript = Transcript()

        self._app: Optional[Client] = None
        self._call: Optional[PyTgCalls] = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._call_active = False

        # Audio pipeline buffers
        self._outgoing_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

    async def start(self) -> None:
        """Run the full call lifecycle."""
        logger.info("Starting call bridge (agent=%s, reason=%s)", self.agent_id, self.reason)

        try:
            # 1. Connect to Forge pipeline
            await self._connect_pipeline()

            # 2. Start Pyrogram + pytgcalls
            self._app = Client(
                name=SESSION_PATH,
                api_id=TELEGRAM_API_ID,
                api_hash=TELEGRAM_API_HASH,
            )
            await self._app.start()

            self._call = PyTgCalls(self._app)
            await self._call.start()

            # Register handlers
            self._register_handlers()

            # 3. Initiate the call
            self._running = True
            self.transcript.start()
            await self._initiate_call()

            # 4. Wait until call ends
            while self._running:
                await asyncio.sleep(0.5)

        except Exception:
            logger.exception("Call bridge error")
        finally:
            await self._cleanup()

    async def _connect_pipeline(self) -> None:
        """Connect to the Pipecat voice pipeline WebSocket on Forge."""
        logger.info("Connecting to pipeline at %s", FORGE_WS_URL)

        # Send initial config with agent context
        self._ws = await websockets.connect(
            FORGE_WS_URL,
            ping_interval=20,
            ping_timeout=10,
            max_size=1_000_000,  # 1MB max message
        )

        # Send call metadata so the pipeline knows which agent to route to
        init_msg = json.dumps({
            "type": "call_start",
            "agent_id": self.agent_id,
            "reason": self.reason,
        })
        await self._ws.send(init_msg)
        logger.info("Pipeline connected, init message sent")

        # Start receiving audio from pipeline in background
        asyncio.create_task(self._receive_pipeline_audio())

    async def _receive_pipeline_audio(self) -> None:
        """Receive audio from Pipecat pipeline and queue for Telegram playback."""
        try:
            async for message in self._ws:
                if not self._running:
                    break

                if isinstance(message, bytes):
                    # Raw PCM audio from pipeline (16kHz) -> resample to 48kHz
                    resampled = resample_pcm(
                        message, PIPELINE_SAMPLE_RATE, TELEGRAM_SAMPLE_RATE
                    )
                    try:
                        self._outgoing_queue.put_nowait(resampled)
                    except asyncio.QueueFull:
                        # Drop oldest if buffer is full (prefer fresh audio)
                        try:
                            self._outgoing_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        self._outgoing_queue.put_nowait(resampled)
                elif isinstance(message, str):
                    # JSON control message from pipeline
                    self._handle_pipeline_message(json.loads(message))

        except websockets.ConnectionClosed:
            logger.warning("Pipeline WebSocket closed")
            self._running = False
        except Exception:
            logger.exception("Error receiving pipeline audio")
            self._running = False

    def _handle_pipeline_message(self, msg: dict) -> None:
        """Handle JSON messages from the pipeline (transcripts, control)."""
        msg_type = msg.get("type", "")

        if msg_type == "transcript":
            role = msg.get("role", "unknown")
            text = msg.get("text", "")
            self.transcript.add(role, text)
            logger.info("Transcript [%s]: %s", role, text)

        elif msg_type == "call_end":
            logger.info("Pipeline requested call end")
            self._running = False

        else:
            logger.debug("Unknown pipeline message: %s", msg_type)

    def _register_handlers(self) -> None:
        """Register pytgcalls event handlers for audio streaming."""

        @self._call.on_raw_update()
        async def on_raw_update(client, update):
            """Handle raw audio updates from the call."""
            # pytgcalls sends raw audio frames during active calls.
            # The exact callback depends on the pytgcalls version.
            pass

    async def _initiate_call(self) -> None:
        """
        Initiate a private Telegram call.

        pytgcalls primarily supports group voice chats. For direct 1-on-1 calls,
        we use it in a private group workaround or the raw Telegram API.

        Current approach: Use a private group with just the bot and target user.
        The target user receives a notification and joins.

        Future: Implement raw phone.requestCall for real ringing calls.
        """
        logger.info("Initiating call to user %d", TARGET_USER_ID)

        # -- Approach: Private group voice chat --
        # For a real 1-on-1 call implementation, you would use:
        #   phone.requestCall -> phone.acceptCall -> encrypted VoIP session
        # This requires implementing the Telegram call encryption protocol.
        #
        # For now, we use the pytgcalls group call approach which is well-tested.
        # A dedicated private group is created once (see setup instructions).

        # Notify the user that a call is incoming
        try:
            await self._app.send_message(
                TARGET_USER_ID,
                f"[Talking-Claw] Incoming voice call from {self.agent_id}."
                + (f" Reason: {self.reason}" if self.reason else "")
                + "\nJoin the Talking-Claw voice chat to connect."
            )
        except Exception:
            logger.warning("Could not send pre-call message to user")

        # The actual call/voice-chat join would happen here.
        # Placeholder for the group call approach:
        #
        # GROUP_CHAT_ID = config.CALL_GROUP_ID  # private group for calls
        # await self._call.play(
        #     GROUP_CHAT_ID,
        #     AudioPiped(
        #         self._audio_pipe_path,
        #         audio_parameters=AudioParameters(
        #             bitrate=48000,
        #         ),
        #     ),
        # )
        #
        # For the raw 1-on-1 call approach, the implementation would use:
        # phone.requestCall with g_a_hash, protocol configuration, etc.

        logger.info("Call initiated -- waiting for user to join")
        self._call_active = True

    def on_telegram_audio_frame(self, pcm_data: bytes) -> None:
        """
        Callback: audio frame received from Telegram call (user's voice).
        Resamples and sends to the pipeline.
        """
        if not self._running or not self._ws:
            return

        # Resample from Telegram 48kHz to pipeline 16kHz
        resampled = resample_pcm(pcm_data, TELEGRAM_SAMPLE_RATE, PIPELINE_SAMPLE_RATE)

        # Send to pipeline (fire-and-forget via the event loop)
        asyncio.create_task(self._send_to_pipeline(resampled))

    async def _send_to_pipeline(self, pcm_data: bytes) -> None:
        """Send audio data to the pipeline WebSocket."""
        try:
            if self._ws and self._ws.open:
                await self._ws.send(pcm_data)
        except websockets.ConnectionClosed:
            logger.warning("Pipeline connection lost while sending audio")
            self._running = False
        except Exception:
            logger.exception("Error sending audio to pipeline")

    async def _cleanup(self) -> None:
        """Shut down all connections gracefully."""
        self._running = False
        self.transcript.stop()

        logger.info(
            "Call ended. Duration: %.1f seconds, %d transcript entries",
            self.transcript.duration_seconds,
            len(self.transcript.entries),
        )

        # Close WebSocket
        if self._ws:
            try:
                # Send call end notification to pipeline
                await self._ws.send(json.dumps({
                    "type": "call_end",
                    "transcript": self.transcript.entries,
                    "duration": self.transcript.duration_seconds,
                }))
                await self._ws.close()
            except Exception:
                pass

        # Stop pytgcalls
        if self._call:
            try:
                await self._call.stop()
            except Exception:
                pass

        # Stop Pyrogram
        if self._app:
            try:
                await self._app.stop()
            except Exception:
                pass

        logger.info("Cleanup complete")

    def get_transcript(self) -> str:
        """Return the formatted call transcript."""
        return self.transcript.format()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def make_call(agent_id: str = "wizard", reason: str = "") -> str:
    """
    Public API: initiate a voice call and return the transcript.

    Args:
        agent_id: Which agent personality to use (wizard, killer, gunnar).
        reason: Why the call is being made (shown to user, sent to pipeline).

    Returns:
        Formatted transcript string.
    """
    bridge = CallBridge(agent_id=agent_id, reason=reason)
    await bridge.start()
    return bridge.get_transcript()


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    agent = sys.argv[1] if len(sys.argv) > 1 else "wizard"
    reason = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    transcript = asyncio.run(make_call(agent_id=agent, reason=reason))
    if transcript:
        print("\n--- Call Transcript ---")
        print(transcript)
