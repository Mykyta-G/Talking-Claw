# Talking-Claw

**Give your AI agent a phone call.**

Your AI agent works autonomously. When it finishes a task or needs your input, it calls
you on Telegram. Your phone rings. You pick up and have a real voice conversation.
After the call, the AI summarizes and continues working.

The key idea: the voice pipeline connects to **your own AI agent** via HTTP API. Your
agent keeps its personality, memory, and tools. This is not a generic chatbot -- it is
your agent, speaking.

---

## How It Works

```
Your phone rings (Telegram call)
         |
         v
   [ Your Machine ]         [ External Services ]
   Caller (Telegram VoIP)    Groq Whisper API (free STT)
   Piper TTS (local)         Your Agent API (any LLM backend)
   Silero VAD (local)
```

1. Your AI agent runs `python trigger.py "task finished"`
2. The caller initiates a real Telegram VoIP call to your account
3. Your phone rings -- you pick up
4. Your speech is sent to Groq's Whisper API for transcription (~200ms)
5. The transcript goes to your agent's HTTP API, which responds with text
6. Piper TTS speaks the response locally (~100ms)
7. You have a natural voice conversation with ~1-1.5 second response time
8. Call ends, transcript is saved, agent continues working

---

## Recommended Setup

Everything runs on **one low-power machine** -- a Raspberry Pi 5, Intel NUC, old laptop,
or any Linux box. No GPU required.

```
[ Phone ]                              [ External ]
Telegram call                           Groq Whisper API
    |                                   (free, ~200ms)
    v                                       ^
[ Pi 5 / NUC / Laptop ]                    |
  caller/          Telegram VoIP bridge ----+
  pipeline/        Silero VAD (local)       |
                   Agent Bridge ----------->+--- Your Agent API
                   Piper TTS (local)            (Claude, GPT, custom, etc.)
```

| Component | Where | Cost | Latency |
|-----------|-------|------|---------|
| STT (Groq Whisper) | Groq cloud API | Free tier (28,800s/day) | ~200ms |
| LLM (your agent) | Your agent's API | Depends on your backend | ~300-600ms |
| TTS (Piper) | Local on your machine | Free | ~100ms |
| VAD (Silero) | Local on your machine | Free | ~100ms |

**Total cost for the voice pipeline: $0.** You only pay for your LLM backend
(and many options are free or pennies per call).

---

## Alternative Configurations

The recommended setup works for most people, but you can swap components depending
on your hardware and preferences:

### GPU Local

Run everything locally on a machine with an NVIDIA GPU (6+ GB VRAM).
Fastest option, zero API costs, but needs a GPU.

- STT: faster-whisper (local, ~200ms)
- TTS: Kokoro (local, ~150ms, better voice quality)
- LLM: Your agent API (or Ollama for fully local)

Set `STT_BACKEND=local` and `TTS_BACKEND=kokoro` in `pipeline/.env`.
Install GPU dependencies: `pip install -r requirements-gpu.txt`

### Full Cloud

No local compute at all. Run the caller on any VPS and use cloud APIs for everything.
Simplest setup, highest ongoing cost.

- STT: OpenAI Whisper API or Groq
- TTS: OpenAI TTS API or ElevenLabs
- LLM: Any cloud LLM API

### Full Local (Offline)

Run everything locally including the LLM via Ollama. Free, fully offline after setup,
but needs a GPU and the LLM is a generic model (not your agent with its memory/tools).

- STT: faster-whisper (local)
- TTS: Kokoro or Piper (local)
- LLM: Ollama (local) -- see pipeline.py comments for setup

### PersonaPlex (NVIDIA)

NVIDIA's speech-to-speech pipeline replaces the entire STT+LLM+TTS chain with a single
model. Very fast, impressive quality, but requires an NVIDIA GPU and is its own model --
you cannot plug in your own agent as the brain.

---

## Requirements

- **Python 3.10+**
- **A second Telegram account** for the AI (free via TextNow or a cheap prepaid SIM)
- **For the recommended setup:** Any Linux machine (Pi 5, NUC, old laptop). No GPU needed.
- **For GPU local mode:** An NVIDIA GPU with 6+ GB VRAM (GTX 1060 or better)
- **A Groq API key** (free tier): https://console.groq.com

---

## Quick Start

### 1. Create the AI's Telegram Account (15 min)

The AI needs its own Telegram account to call you from. See
[Phase 1](./plans/PHASE-1-TELEGRAM-ACCOUNT.md) for full instructions.

Short version:
1. Get a phone number (TextNow app on an old phone, or a prepaid SIM)
2. Create a Telegram account with that number
3. Get API credentials from https://my.telegram.org

### 2. Set Up the Voice Pipeline

```bash
cd pipeline/
cp .env.example .env
# Edit .env:
#   - Set GROQ_API_KEY (free from https://console.groq.com)
#   - Set AGENT_API_URL (your agent's HTTP endpoint)

# Automatic setup (installs deps, downloads Piper voice model):
chmod +x setup.sh
./setup.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python pipeline.py
```

For GPU local mode, use `./setup.sh --gpu` or install `requirements-gpu.txt` manually
and set `STT_BACKEND=local` / `TTS_BACKEND=kokoro` in `.env`.

### 3. Set Up the Caller

```bash
cd caller/
cp .env.example .env
# Edit .env with your Telegram API credentials
# PIPELINE_HOST defaults to localhost (same machine as pipeline)

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# One-time authentication (needs the phone for a verification code):
python auth.py

# Test a call:
python trigger.py "Hello, this is a test call"
```

### 4. Your Phone Rings

Pick up. Talk. Enjoy.

---

## Project Structure

```
Talking-Claw/
  caller/                 Telegram call bridge
    auth.py               One-time Pyrogram authentication
    caller.py             VoIP audio bridge (Telegram <-> pipeline)
    trigger.py            Entry point -- agents call this to start a call
    config.py             Configuration (reads from .env)
    .env.example          Template for secrets and settings

  pipeline/               Voice processing pipeline
    pipeline.py           Pipecat pipeline (VAD -> STT -> Agent -> TTS)
    agent_bridge.py       Routes transcriptions to your AI agent backend
    config.py             Configuration with backend selection
    .env.example          Template for settings
    setup.sh              One-command installer
    requirements.txt      Base dependencies (no GPU needed)
    requirements-gpu.txt  Additional GPU dependencies (optional)

  plans/                  Detailed build guides for each phase
```

---

## LLM Backend Options

The pipeline supports any LLM backend via the Agent Bridge HTTP API:

| Backend | Latency | Cost | Setup |
|---------|---------|------|-------|
| Custom agent API | Varies | Varies | Any HTTP POST endpoint returning JSON |
| OpenAI API | ~300ms | ~$0.002/turn | Set `AGENT_API_URL` + `AGENT_API_TOKEN` |
| Anthropic (Claude) | ~300ms | ~$0.001/turn | Same, point at Anthropic-compatible endpoint |
| Ollama (local) | ~400ms | Free | `AGENT_API_URL=http://localhost:11434` |

The Agent Bridge sends a POST with the user's transcribed speech and expects a text
response back. See `pipeline/.env.example` and `pipeline/agent_bridge.py` for the
full HTTP contract. It works with any backend that speaks this simple protocol.

---

## Latency

With the recommended setup (Groq + Piper), response time is:

| Step | Time |
|------|------|
| Voice activity detection (Silero) | ~100ms |
| Speech-to-text (Groq Whisper API) | ~200ms |
| LLM / agent API (time to first token) | ~300-600ms |
| Text-to-speech (Piper, local) | ~100ms |
| **Total to first audio** | **~0.8-1.2s** |

With GPU local mode (faster-whisper + Kokoro):

| Step | Time |
|------|------|
| Voice activity detection (Silero) | ~100ms |
| Speech-to-text (local Whisper) | ~200ms |
| LLM / agent API (time to first token) | ~300-600ms |
| Text-to-speech (Kokoro) | ~150ms |
| **Total to first audio** | **~1.0-1.5s** |

Responses are **streamed sentence-by-sentence**. TTS starts speaking the first sentence
while the agent is still generating the rest. You hear the AI start talking in about one
second.

---

## Tech Stack

| Component | Purpose | License |
|-----------|---------|---------|
| [Pipecat](https://github.com/pipecat-ai/pipecat) | Voice pipeline framework | BSD |
| [Pyrogram](https://github.com/pyrogram/pyrogram) | Telegram MTProto client | LGPL |
| [pytgcalls](https://github.com/pytgcalls/pytgcalls) | Telegram VoIP bridge | LGPL |
| [Groq Whisper API](https://console.groq.com) | Speech-to-text (recommended) | Proprietary (free tier) |
| [Piper](https://github.com/rhasspy/piper) | Text-to-speech, local (recommended) | MIT |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech-to-text, local (GPU mode) | MIT |
| [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) | Text-to-speech, local (GPU mode) | Apache |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Voice activity detection | MIT |

---

## License

MIT -- see [LICENSE](./LICENSE). Use it, modify it, share it. Just keep the copyright notice.
