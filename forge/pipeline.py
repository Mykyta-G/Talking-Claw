"""
Talking-Claw -- Pipecat Voice Pipeline

Runs on the Forge GPU server. Processes voice audio through:
    Silero VAD -> Whisper STT -> Agent Bridge -> Kokoro TTS

Accepts WebSocket connections from the Pi caller and handles
bidirectional audio streaming with the AI agent.

The pipeline uses Pipecat's framework for managing the audio processing
chain, with a custom Agent Bridge processor that routes to clawdbot
instead of a local LLM.
"""

import asyncio
import json
import logging
import signal
import sys
from typing import Optional

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.kokoro import KokoroTTSService
from pipecat.services.whisper import WhisperSTTService
from pipecat.transports.network.websocket_server import (
    WebSocketServerParams,
    WebSocketServerTransport,
)
from pipecat.vad.silero import SileroVADAnalyzer

from clawd_bridge import ClawdBridge
from config import (
    DEFAULT_AGENT_ID,
    PIPELINE_HOST,
    PIPELINE_PORT,
    PIPELINE_SAMPLE_RATE,
    VAD_THRESHOLD,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_LANGUAGE,
    WHISPER_MODEL,
    get_voice,
)

logger = logging.getLogger("talking-claw.pipeline")


# ---------------------------------------------------------------------------
# Custom Pipecat processor: Agent Bridge
# ---------------------------------------------------------------------------

class AgentBridgeProcessor(FrameProcessor):
    """
    Pipecat FrameProcessor that routes transcribed text to the clawdbot
    agent and emits text frames for TTS.

    Sits between STT and TTS in the pipeline:
        STT -> [TranscriptionFrame] -> AgentBridgeProcessor -> [TextFrame] -> TTS
    """

    def __init__(self, bridge: ClawdBridge, **kwargs) -> None:
        super().__init__(**kwargs)
        self._bridge = bridge

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process incoming frames from the pipeline."""
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            # User speech has been transcribed -- send to agent
            text = frame.text.strip()
            if not text:
                return

            logger.info("Transcription received: %s", text)

            # Stream response sentences to TTS
            try:
                async for sentence in self._bridge.send(text):
                    await self.push_frame(TextFrame(text=sentence))
            except Exception:
                logger.exception("Agent bridge error during response")
                await self.push_frame(
                    TextFrame(text="Sorry, I had a problem. Could you repeat that?")
                )

        elif isinstance(frame, EndFrame):
            # Call is ending -- send transcript summary
            logger.info("Pipeline ending -- sending post-call summary")
            try:
                await self._bridge.send_transcript_summary()
            except Exception:
                logger.exception("Failed to send post-call summary")
            await self.push_frame(frame)

        else:
            # Pass through all other frames unchanged
            await self.push_frame(frame, direction)


# ---------------------------------------------------------------------------
# Health check server
# ---------------------------------------------------------------------------

class HealthServer:
    """Simple HTTP health check endpoint for the pipeline."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._runner: Optional[object] = None

    async def start(self) -> None:
        from aiohttp import web

        app = web.Application()
        app.router.add_get("/health", self._handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        self._runner = runner
        logger.info("Health check server on http://%s:%d/health", self.host, self.port)

    async def _handle_health(self, request) -> "web.Response":
        from aiohttp import web
        return web.json_response({
            "status": "ok",
            "service": "talking-claw-pipeline",
        })


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_pipeline(agent_id: str = DEFAULT_AGENT_ID) -> None:
    """
    Start the Pipecat voice pipeline.

    Sets up the full processing chain:
        WebSocket Input -> Silero VAD -> Whisper STT -> Agent Bridge -> Kokoro TTS -> WebSocket Output
    """
    voice = get_voice(agent_id)
    logger.info("Starting pipeline (agent=%s, voice=%s)", agent_id, voice)

    # -- Transport: WebSocket server for audio I/O --
    transport = WebSocketServerTransport(
        params=WebSocketServerParams(
            host=PIPELINE_HOST,
            port=PIPELINE_PORT,
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(
                params={"threshold": VAD_THRESHOLD},
            ),
            audio_in_sample_rate=PIPELINE_SAMPLE_RATE,
            audio_out_sample_rate=PIPELINE_SAMPLE_RATE,
        )
    )

    # -- STT: Whisper (runs on GPU) --
    stt = WhisperSTTService(
        model=WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
        no_speech_prob=0.4,
        language=WHISPER_LANGUAGE,
    )

    # -- Agent Bridge: routes to clawdbot --
    bridge = ClawdBridge(agent_id=agent_id)
    await bridge.start()
    agent_processor = AgentBridgeProcessor(bridge=bridge)

    # -- TTS: Kokoro (runs on GPU) --
    tts = KokoroTTSService(
        voice=voice,
        sample_rate=PIPELINE_SAMPLE_RATE,
    )

    # -- Assemble pipeline --
    pipeline = Pipeline([
        transport.input(),       # WebSocket audio in (from Pi)
        stt,                     # Speech to text
        agent_processor,         # Text to agent, agent response back
        tts,                     # Text to speech
        transport.output(),      # WebSocket audio out (to Pi)
    ])

    task = PipelineTask(
        pipeline,
        PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    # -- Run --
    runner = PipelineRunner()

    logger.info(
        "Voice pipeline ready on ws://%s:%d",
        PIPELINE_HOST,
        PIPELINE_PORT,
    )
    logger.info("  STT:   %s on %s (%s)", WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE)
    logger.info("  TTS:   Kokoro voice=%s", voice)
    logger.info("  Agent: %s via %s", agent_id, "clawdbot gateway")
    logger.info("Waiting for caller connection...")

    try:
        await runner.run(task)
    finally:
        await bridge.stop()
        logger.info("Pipeline shut down")


async def main() -> None:
    """Entry point: start health server + pipeline."""
    # Determine agent from CLI args or config
    agent_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_AGENT_ID

    # Start health check on a separate port if pipeline port is in use,
    # otherwise reuse the same port (health runs before pipeline accepts WS).
    # For simplicity, we embed health in the pipeline's HTTP layer.
    # The WebSocket transport in Pipecat handles this.

    # Run the pipeline
    await run_pipeline(agent_id=agent_id)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Handle graceful shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: loop.stop())

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Interrupted -- shutting down")
    finally:
        loop.close()
