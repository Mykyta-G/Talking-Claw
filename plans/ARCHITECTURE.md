# Talking-Claw — Architecture

> Your AI agents call you on Telegram. Your phone rings. You pick up and talk.
> After the call, the AI summarizes the conversation and continues working.

## How It Works

```
┌────────────────────────────────┐
│  YOUR PHONE                    │
│  Telegram call → pick up       │
└──────────────┬─────────────────┘
               │ real Telegram VoIP call
┌──────────────▼─────────────────┐
│  ORCHESTRATOR (Raspberry Pi)   │
│                                │
│  Telegram Userbot              │
│  (Pyrogram + pytgcalls)        │
│  • Initiates real 1-on-1 call  │
│  • Bridges PCM audio ←→ WS    │
│                                │
│  Your AI Agent (clawdbot, etc) │
│  • Receives transcribed text   │
│  • Responds naturally          │
│  • Full tools + memory access  │
└──────────────┬─────────────────┘
               │ WebSocket (PCM audio)
               │ (local network / Tailscale)
┌──────────────▼─────────────────┐
│  GPU SERVER (any NVIDIA GPU)   │
│                                │
│  Pipecat Voice Pipeline:       │
│                                │
│  ┌──────────────────────┐      │
│  │ Silero VAD           │ 0 GB │
│  │ (voice detection)    │      │
│  └──────────┬───────────┘      │
│             ▼                  │
│  ┌──────────────────────┐      │
│  │ Whisper STT          │ 3 GB │
│  │ (speech → text)      │      │
│  └──────────┬───────────┘      │
│             ▼                  │
│  ┌──────────────────────┐      │
│  │ Agent Bridge         │ 0 GB │
│  │ (sends text to agent │      │
│  │  returns response)   │      │
│  └──────────┬───────────┘      │
│             ▼                  │
│  ┌──────────────────────┐      │
│  │ Kokoro TTS           │ 2 GB │
│  │ (text → speech)      │      │
│  └──────────────────────┘      │
│                                │
│  Total VRAM: ~5 GB             │
│  Min GPU: 6 GB (GTX 1060+)    │
└────────────────────────────────┘
```

## Latency (Streamed)

| Step | Time |
|------|------|
| Silero VAD (end of speech) | ~100ms |
| Whisper STT | ~200ms |
| LLM API (time to first token) | ~300-600ms |
| First sentence complete | ~300ms |
| Kokoro TTS (first chunk) | ~150ms |
| **Total to first audio** | **~1.0-1.5s** |

Key: responses are **streamed sentence-by-sentence**. TTS starts speaking the first sentence while the LLM is still generating the rest. You hear the AI start talking in ~1 second.

## Components

| Component | What | Runs On | Open Source |
|-----------|------|---------|-------------|
| Pyrogram | Telegram MTProto client | Orchestrator | MIT |
| pytgcalls | Telegram VoIP bridge | Orchestrator | LGPL |
| Pipecat | Voice AI pipeline framework | GPU Server | BSD |
| Silero VAD | Voice activity detection | GPU Server | MIT |
| faster-whisper | Speech-to-text (CTranslate2) | GPU Server | MIT |
| Kokoro | Text-to-speech (82M ONNX) | GPU Server | Apache |

## Cost

**$0 for the pipeline.** Everything runs locally.

Only cost is your existing LLM API (if using a cloud model). Local models (Ollama) are free.
