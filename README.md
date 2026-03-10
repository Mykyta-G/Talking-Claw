# Talking-Claw

**An AI that calls you on the phone.**

Your AI agent works autonomously. When it finishes a task or needs your input, it calls
you on Telegram. Your phone rings. You pick up and have a real voice conversation.
After the call, the AI summarizes and continues working.

---

## How It Works

```
Your phone rings (Telegram call)
         |
         v
   [ Caller ]              [ Voice Pipeline ]
   Telegram userbot         Whisper STT
   initiates VoIP call  <-> Agent (LLM)
   bridges audio            Kokoro TTS
```

1. Your AI agent runs `python trigger.py "task finished"`
2. The caller initiates a real Telegram VoIP call to your account
3. Your phone rings -- you pick up
4. Your speech is transcribed (Whisper), sent to the LLM, response is spoken back (Kokoro)
5. You have a natural voice conversation with ~1-1.5 second response time
6. Call ends, transcript is saved, agent continues working

---

## Deployment Options

Talking-Claw has two components: the **caller** (Telegram call bridge) and the
**pipeline** (voice processing). You can run them however fits your setup:

### Single Machine (Simplest)

If you have a PC, Mac Mini, or server with a decent GPU:

```
[ Your Machine ]
  caller/    -- Telegram userbot
  pipeline/  -- STT + LLM + TTS
```

Both components run on the same machine. Set `PIPELINE_HOST=localhost` in your .env.

### Two Machines (Recommended for Always-On)

If you have a low-power server (Raspberry Pi, NUC, old laptop) that runs 24/7 and a
separate GPU machine for processing:

```
[ Always-On Server ]          [ GPU Machine ]
  caller/                       pipeline/
  Telegram userbot              Whisper STT
  bridges audio over network    LLM (local or API)
                                Kokoro TTS
```

The caller runs on the always-on machine and streams audio to the GPU machine over
your local network (or Tailscale, WireGuard, etc). Set `PIPELINE_HOST` to the GPU
machine's IP address.

This is useful when your GPU machine sleeps to save power -- the caller can wake it
with Wake-on-LAN before starting a call.

### Cloud GPU (No Local GPU)

You can run the pipeline on a cloud GPU instance (Lambda, RunPod, Vast.ai) and the
caller on any cheap VPS or home server. Just point `PIPELINE_HOST` at the cloud instance.

---

## Requirements

- **Python 3.10+**
- **A second Telegram account** for the AI (free via TextNow or a cheap prepaid SIM)
- **For the pipeline:** An NVIDIA GPU with 6+ GB VRAM (GTX 1060 or better)
  - Or run without a GPU using CPU-only mode (slower, ~3-5s response time)

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
# Edit .env with your settings

# Automatic setup (installs deps, downloads models, tests everything):
chmod +x setup.sh
./setup.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python pipeline.py
```

### 3. Set Up the Caller

```bash
cd caller/
cp .env.example .env
# Edit .env with your Telegram API credentials and pipeline server address

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
    pipeline.py           Pipecat pipeline (VAD -> STT -> LLM -> TTS)
    agent_bridge.py       Routes transcriptions to your AI agent backend
    config.py             Configuration (reads from .env)
    .env.example          Template for settings
    setup.sh              One-command installer (GPU server)

  plans/                  Detailed build guides for each phase
```

---

## LLM Backend Options

The pipeline supports multiple LLM backends via the Agent Bridge:

| Backend | Latency | Cost | Setup |
|---------|---------|------|-------|
| Ollama (local) | ~400ms | Free | `AGENT_API_URL=http://localhost:11434` |
| OpenAI API | ~300ms | ~$0.002/turn | Set `AGENT_API_URL` + `AGENT_API_TOKEN` |
| Anthropic (Claude) | ~300ms | ~$0.001/turn | Same, point at Anthropic-compatible endpoint |
| Custom agent API | Varies | Varies | Any HTTP POST endpoint returning JSON |

See `pipeline/.env.example` for configuration details.

---

## Latency

With streaming (sentence-by-sentence TTS), the response time is:

| Step | Time |
|------|------|
| Voice activity detection | ~100ms |
| Speech-to-text (Whisper) | ~200ms |
| LLM (time to first token) | ~300-600ms |
| Text-to-speech (Kokoro) | ~150ms |
| **Total to first audio** | **~1.0-1.5s** |

You hear the AI start talking in about one second. The rest of the response streams
while the first sentence is being spoken.

---

## Tech Stack

| Component | Purpose | License |
|-----------|---------|---------|
| [Pipecat](https://github.com/pipecat-ai/pipecat) | Voice pipeline framework | BSD |
| [Pyrogram](https://github.com/pyrogram/pyrogram) | Telegram MTProto client | LGPL |
| [pytgcalls](https://github.com/pytgcalls/pytgcalls) | Telegram VoIP bridge | LGPL |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech-to-text | MIT |
| [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) | Text-to-speech (82M) | Apache |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Voice activity detection | MIT |

---

## License

MIT -- see [LICENSE](./LICENSE). Use it, modify it, share it. Just keep the copyright notice.
