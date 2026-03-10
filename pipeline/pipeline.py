"""
Talking-Claw -- Pipecat Voice Pipeline

Processes voice audio through a configurable STT -> Agent Bridge -> TTS chain.
Accepts WebSocket connections from the caller and handles bidirectional audio
streaming with the AI agent.

Supports two configurations via STT_BACKEND and TTS_BACKEND in .env:

    Recommended (no GPU, runs on Pi 5 / NUC / old laptop):
        Silero VAD -> Groq Whisper API -> Agent Bridge -> Piper TTS

    GPU Local (needs NVIDIA GPU with 6+ GB VRAM):
        Silero VAD -> Local Whisper STT -> Agent Bridge -> Kokoro TTS

The pipeline uses Pipecat's framework for managing the audio processing
chain, with a custom Agent Bridge processor that routes to your agent API.

--- Switching to a local LLM (Ollama) ---

If you want to skip the HTTP agent bridge and use a fully local LLM,
replace the AgentBridge + AgentBridgeProcessor section with:

    from pipecat.services.ollama import OllamaLLMService
    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

    llm = OllamaLLMService(
        model="llama3.1:8b",
        base_url="http://localhost:11434/v1",
    )
    context = OpenAILLMContext(messages=[
        {"role": "system", "content": VOICE_SYSTEM_PROMPT}
    ])
    context_aggregator = llm.create_context_aggregator(context)

    # Then in the pipeline list, replace agent_processor with:
    #   context_aggregator.user(), llm, context_aggregator.assistant()

--- Switching to OpenAI-compatible API ---

    from pipecat.services.openai import OpenAILLMService

    llm = OpenAILLMService(
        model="gpt-4o-mini",
        api_key="sk-...",
    )

--- Switching to Anthropic Claude ---

    from pipecat.services.anthropic import AnthropicLLMService

    llm = AnthropicLLMService(
        model="claude-haiku-4-5",
        api_key="sk-ant-...",
    )
"""

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
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
from pipecat.transports.network.websocket_server import (
    WebSocketServerParams,
    WebSocketServerTransport,
)
from pipecat.vad.silero import SileroVADAnalyzer

from agent_bridge import AgentBridge
from config import (
    DEFAULT_AGENT_ID,
    PIPELINE_HOST,
    PIPELINE_PORT,
    PIPELINE_SAMPLE_RATE,
    STT_BACKEND,
    TTS_BACKEND,
    VAD_THRESHOLD,
)

logger = logging.getLogger("talking-claw.pipeline")


# ---------------------------------------------------------------------------
# STT factory
# ---------------------------------------------------------------------------

def create_stt_service():
    """
    Create the speech-to-text service based on STT_BACKEND config.

    Returns a Pipecat STT service instance.

    Groq (recommended): Uses the Groq Whisper API. Free tier available.
        No GPU needed. Requires GROQ_API_KEY in .env.

    Local: Uses faster-whisper running locally. Requires NVIDIA GPU.
        Set WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE in .env.
    """
    if STT_BACKEND == "groq":
        from pipecat.services.groq.stt import GroqSTTService

        from config import GROQ_API_KEY, GROQ_WHISPER_MODEL, WHISPER_LANGUAGE

        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is required when STT_BACKEND=groq. "
                "Get a free key at https://console.groq.com"
            )

        logger.info("STT backend: Groq Whisper API (model=%s)", GROQ_WHISPER_MODEL)
        return GroqSTTService(
            api_key=GROQ_API_KEY,
            model=GROQ_WHISPER_MODEL,
        )

    elif STT_BACKEND == "local":
        from pipecat.services.whisper import WhisperSTTService

        from config import WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_LANGUAGE, WHISPER_MODEL

        logger.info(
            "STT backend: Local Whisper (model=%s, device=%s, compute=%s)",
            WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
        )
        return WhisperSTTService(
            model=WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
            no_speech_prob=0.4,
            language=WHISPER_LANGUAGE,
        )

    else:
        raise RuntimeError(
            f"Unknown STT_BACKEND: {STT_BACKEND}. Use 'groq' or 'local'."
        )


# ---------------------------------------------------------------------------
# TTS factory
# ---------------------------------------------------------------------------

def create_tts_service(agent_id: str):
    """
    Create the text-to-speech service based on TTS_BACKEND config.

    Returns a Pipecat TTS service instance.

    Piper (recommended): Runs locally on CPU. No GPU needed. Free.
        Uses piper-tts with downloadable ONNX voice models.
        Set PIPER_VOICE in .env (e.g. en_US-ryan-high).

    Kokoro: Runs locally on GPU. Better voice quality.
        Requires NVIDIA GPU. Set DEFAULT_VOICE in .env.
    """
    if TTS_BACKEND == "piper":
        from pipecat.services.piper.tts import PiperTTSService

        from config import PIPER_DOWNLOAD_DIR, PIPER_USE_CUDA, PIPER_VOICE

        download_dir = Path(PIPER_DOWNLOAD_DIR) if PIPER_DOWNLOAD_DIR else Path(__file__).parent / "models"
        download_dir.mkdir(parents=True, exist_ok=True)

        logger.info("TTS backend: Piper (voice=%s, cuda=%s)", PIPER_VOICE, PIPER_USE_CUDA)
        return PiperTTSService(
            voice_id=PIPER_VOICE,
            download_dir=download_dir,
            use_cuda=PIPER_USE_CUDA,
        )

    elif TTS_BACKEND == "kokoro":
        from pipecat.services.kokoro import KokoroTTSService

        from config import get_voice

        voice = get_voice(agent_id)
        logger.info("TTS backend: Kokoro (voice=%s)", voice)
        return KokoroTTSService(
            voice=voice,
            sample_rate=PIPELINE_SAMPLE_RATE,
        )

    else:
        raise RuntimeError(
            f"Unknown TTS_BACKEND: {TTS_BACKEND}. Use 'piper' or 'kokoro'."
        )


# ---------------------------------------------------------------------------
# Custom Pipecat processor: Agent Bridge
# ---------------------------------------------------------------------------

class AgentBridgeProcessor(FrameProcessor):
    """
    Pipecat FrameProcessor that routes transcribed text to the agent API
    and emits text frames for TTS.

    Sits between STT and TTS in the pipeline:
        STT -> [TranscriptionFrame] -> AgentBridgeProcessor -> [TextFrame] -> TTS
    """

    def __init__(self, bridge: AgentBridge, **kwargs) -> None:
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
            "stt_backend": STT_BACKEND,
            "tts_backend": TTS_BACKEND,
        })


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_pipeline(agent_id: str = DEFAULT_AGENT_ID) -> None:
    """
    Start the Pipecat voice pipeline.

    Sets up the full processing chain based on configured backends:
        WebSocket Input -> Silero VAD -> STT -> Agent Bridge -> TTS -> WebSocket Output
    """
    logger.info("Starting pipeline (agent=%s, stt=%s, tts=%s)", agent_id, STT_BACKEND, TTS_BACKEND)

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

    # -- STT: configurable backend --
    stt = create_stt_service()

    # -- Agent Bridge: routes to your agent API --
    bridge = AgentBridge(agent_id=agent_id)
    await bridge.start()
    agent_processor = AgentBridgeProcessor(bridge=bridge)

    # -- TTS: configurable backend --
    tts = create_tts_service(agent_id)

    # -- Assemble pipeline --
    pipeline = Pipeline([
        transport.input(),       # WebSocket audio in (from caller)
        stt,                     # Speech to text
        agent_processor,         # Text to agent, agent response back
        tts,                     # Text to speech
        transport.output(),      # WebSocket audio out (to caller)
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
    logger.info("  STT:   %s", STT_BACKEND)
    logger.info("  TTS:   %s", TTS_BACKEND)
    logger.info("  Agent: %s via agent API", agent_id)
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
