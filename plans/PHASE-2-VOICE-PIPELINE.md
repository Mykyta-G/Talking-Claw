# Phase 2 -- Voice Pipeline on GPU Server

> **Time:** 1-2 hours
> **What:** Install Pipecat + STT + TTS on your GPU machine.

## Requirements

- NVIDIA GPU with 6+ GB VRAM (GTX 1060 or better)
- CUDA 12.x installed
- Python 3.10+

## 2.1 -- Install

```bash
# SSH into your GPU server
mkdir -p ~/talking-claw/pipeline
cd ~/talking-claw/pipeline
python3 -m venv venv
source venv/bin/activate

# Core pipeline
pip install "pipecat-ai[silero,whisper,kokoro,websocket]"
pip install aiohttp numpy soundfile
```

## 2.2 -- Test Each Component

**Test STT:**
```bash
python -c "
from faster_whisper import WhisperModel
model = WhisperModel('distil-medium.en', device='cuda', compute_type='float16')
print('STT ready')
"
```

**Test TTS:**
```bash
python -c "
from kokoro_onnx import Kokoro
kokoro = Kokoro('kokoro-v1.0.onnx', 'voices-v1.0.bin')
samples, sr = kokoro.create('Hello, this is a test.', voice='bm_lewis', speed=1.0)
print(f'TTS ready -- generated {len(samples)} samples at {sr}Hz')
"
```

## 2.3 -- Agent Bridge

The Agent Bridge replaces the LLM in the pipeline. Instead of running a local model, it sends the transcribed text to your AI agent and returns the response.

Three modes are supported:

### Mode A: HTTP Bridge (for any REST API)

```python
# agent_bridge.py -- sends text to your agent's API endpoint
import aiohttp

class AgentBridge:
    def __init__(self, endpoint: str, token: str = "", agent_id: str = "assistant"):
        self.endpoint = endpoint
        self.token = token
        self.agent_id = agent_id

    async def send(self, text: str) -> str:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            async with session.post(self.endpoint, json={
                "message": text,
                "agentId": self.agent_id,
            }, headers=headers) as resp:
                data = await resp.json()
                return data.get("response", "Sorry, no response.")
```

### Mode B: Ollama Bridge (free, fully local)

```python
# For users who want 100% local -- uses Ollama on the same GPU server
from pipecat.services.ollama import OllamaLLMService

llm = OllamaLLMService(
    model="llama3.1:8b",  # or any Ollama model
    base_url="http://localhost:11434/v1",
)
```

### Mode C: Direct Anthropic (Claude API)

```python
# For users with Claude API access
from pipecat.services.anthropic import AnthropicLLMService

llm = AnthropicLLMService(
    model="claude-haiku-4-5",
    api_key="sk-ant-...",
)
```

## 2.4 -- Full Pipeline

```python
# pipeline.py
import asyncio
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.transports.network.websocket_server import (
    WebSocketServerTransport,
    WebSocketServerParams,
)
from pipecat.services.whisper import WhisperSTTService
from pipecat.services.kokoro import KokoroTTSService
from pipecat.vad.silero import SileroVADAnalyzer

WEBSOCKET_PORT = 8790

async def main():
    transport = WebSocketServerTransport(
        params=WebSocketServerParams(
            host="0.0.0.0",
            port=WEBSOCKET_PORT,
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        )
    )

    stt = WhisperSTTService(
        model="distil-medium.en",
        device="cuda",
        no_speech_prob=0.4,
        language="en",
    )

    # Choose your LLM mode (see 2.3 above)
    # For now, using Ollama as the default (free, local)
    from pipecat.services.ollama import OllamaLLMService
    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

    llm = OllamaLLMService(
        model="llama3.1:8b",
        base_url="http://localhost:11434/v1",
    )

    tts = KokoroTTSService(voice="bm_lewis")

    context = OpenAILLMContext(messages=[
        {"role": "system", "content": (
            "You are in a live voice call. Keep responses to 1-3 sentences. "
            "Speak naturally and conversationally. No markdown. "
            "Use contractions. Be concise."
        )}
    ])
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline([
        transport.input(),
        stt,
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])

    task = PipelineTask(
        pipeline,
        PipelineParams(allow_interruptions=True),
    )

    runner = PipelineRunner()
    print(f"Voice pipeline listening on ws://0.0.0.0:{WEBSOCKET_PORT}")
    await runner.run(task)

if __name__ == "__main__":
    asyncio.run(main())
```

## 2.5 -- Run as Service (Optional)

```bash
# /etc/systemd/system/talking-claw-pipeline.service
[Unit]
Description=Talking-Claw Voice Pipeline
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/talking-claw/pipeline
ExecStart=/home/YOUR_USER/talking-claw/pipeline/venv/bin/python pipeline.py
Restart=always
RestartSec=5
Environment=CUDA_VISIBLE_DEVICES=0

[Install]
WantedBy=multi-user.target
```

## What You Have After This Phase

```
Pipecat voice pipeline running on GPU server
Silero VAD detecting speech
Whisper transcribing speech to text (~200ms)
LLM generating responses (local or cloud)
Kokoro speaking responses (~150ms)
WebSocket endpoint ready for audio streaming
```
