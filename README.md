# Talking-Claw

**Have you imagined an AI that calls you? Now it can.**

Your AI agents work autonomously. When they finish a task or need your input, they call you on Telegram. Your phone rings. You pick up and have a real-time voice conversation. After the call, the AI summarizes and continues working.

## Features

- **Real Telegram calls** — your phone actually rings
- **Talk to your real AI agent** — same personality, memory, and tools
- **~1-1.5 second response time** — streamed sentence-by-sentence
- **100% local pipeline** — STT, TTS, and VAD run on your own GPU
- **$0 infrastructure cost** — runs on hardware you own

## Architecture

```
Your Phone ←── Telegram Call ──→ Orchestrator (Pi/Server)
                                      │
                              WebSocket (audio)
                                      │
                                 GPU Server
                            ┌─────────────────┐
                            │ Silero VAD       │
                            │ Whisper STT      │
                            │ Your AI Agent    │
                            │ Kokoro TTS       │
                            └─────────────────┘
```

## Requirements

- **Orchestrator**: Any Linux machine (Raspberry Pi, VPS, etc.)
- **GPU Server**: NVIDIA GPU with 6+ GB VRAM (GTX 1060 or better)
- **A second Telegram account** for the AI (free via TextNow)
- **Python 3.10+**

## Quick Start

See the [plans/](./plans/) folder for the full build guide:

1. **[Phase 1](./plans/PHASE-1-TELEGRAM-ACCOUNT.md)** — Create AI's Telegram account (15 min)
2. **[Phase 2](./plans/PHASE-2-VOICE-PIPELINE.md)** — Set up voice pipeline on GPU (1-2 hours)
3. **[Phase 3](./plans/PHASE-3-TELEGRAM-CALLER.md)** — Set up Telegram caller (1-2 hours)
4. **[Phase 4](./plans/PHASE-4-VOICE-PERSONALITY.md)** — Voice personality & agent integration (30 min)
5. **[Phase 5](./plans/PHASE-5-TESTING.md)** — Testing & optimization (1 hour)

**Total build time: One afternoon.**

## How It Works

1. Your AI agent decides it needs to talk to you
2. It runs `python trigger.py "I finished the deployment"`
3. The voice pipeline spins up on your GPU server
4. The Telegram userbot calls your real Telegram account
5. Your phone rings — you pick up
6. Your speech → Whisper STT → Agent → Kokoro TTS → your ear
7. You have a natural voice conversation (~1s response time)
8. Call ends → transcript saved → agent continues working

## Tech Stack

| Component | Purpose | License |
|-----------|---------|---------|
| [Pipecat](https://github.com/pipecat-ai/pipecat) | Voice pipeline framework | BSD |
| [Pyrogram](https://github.com/pyrogram/pyrogram) | Telegram MTProto client | LGPL |
| [pytgcalls](https://github.com/pytgcalls/pytgcalls) | Telegram VoIP bridge | LGPL |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech-to-text | MIT |
| [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) | Text-to-speech (82M) | Apache |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Voice activity detection | MIT |

## LLM Options

| Mode | Latency | Cost | Quality |
|------|---------|------|---------|
| Ollama (local) | ~400ms TTFT | Free | Good |
| Claude Haiku | ~300ms TTFT | ~$0.001/turn | Great |
| Claude Sonnet | ~600ms TTFT | ~$0.005/turn | Excellent |
| Any OpenAI-compatible API | Varies | Varies | Varies |

## License

MIT — do whatever you want with it.

---

*Built by [Mykyta-G](https://github.com/Mykyta-G) because talking to your AI should be as easy as picking up the phone.*
