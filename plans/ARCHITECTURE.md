# Talking-Claw -- Architecture

> Your AI agent calls you on Telegram. Your phone rings. You pick up and talk.
> After the call, the AI summarizes the conversation and continues working.

## Recommended Setup (No GPU)

Everything runs on one low-power machine (Pi 5, NUC, old laptop).
STT is handled by a free cloud API. TTS and VAD run locally on CPU.

```
+--------------------------------+
|  YOUR PHONE                    |
|  Telegram call -> pick up      |
+---------------+----------------+
                | real Telegram VoIP call
+---------------v----------------+
|  YOUR MACHINE (Pi 5 / NUC)    |
|                                |
|  Telegram Userbot              |
|  (Pyrogram + pytgcalls)        |
|  * Initiates real 1-on-1 call  |
|  * Bridges PCM audio <-> WS   |
|                                |
|  Pipecat Voice Pipeline:       |
|                                |
|  +----------------------+      |
|  | Silero VAD           |      |
|  | (voice detection)    |      |
|  +----------+-----------+      |
|             v                  |
|  +----------------------+      |     +-----------------------+
|  | Groq Whisper API     |------+---->| Groq Cloud (free)     |
|  | (speech -> text)     |      |     | whisper-large-v3-turbo|
|  +----------+-----------+      |     +-----------------------+
|             v                  |
|  +----------------------+      |     +-----------------------+
|  | Agent Bridge         |------+---->| Your Agent API        |
|  | (sends text to agent |      |     | (Claude, GPT, custom) |
|  |  returns response)   |      |     | Full tools + memory   |
|  +----------+-----------+      |     +-----------------------+
|             v                  |
|  +----------------------+      |
|  | Piper TTS            |      |
|  | (text -> speech)     |      |
|  | CPU-only, ~100ms     |      |
|  +----------------------+      |
|                                |
|  Total VRAM: 0 GB              |
|  Min hardware: Pi 5 / NUC     |
+--------------------------------+
```

## GPU Local Setup (Alternative)

The pipeline runs on a machine with an NVIDIA GPU. Caller can run on
the same machine or on a separate always-on server.

```
+--------------------------------+
|  YOUR PHONE                    |
|  Telegram call -> pick up      |
+---------------+----------------+
                | real Telegram VoIP call
+---------------v----------------+
|  CALLER (always-on server)     |
|                                |
|  Telegram Userbot              |
|  (Pyrogram + pytgcalls)        |
|  * Initiates real 1-on-1 call  |
|  * Bridges PCM audio <-> WS   |
+---------------+----------------+
                | WebSocket (PCM audio)
                | (local network / Tailscale)
+---------------v----------------+
|  GPU SERVER (any NVIDIA GPU)   |
|                                |
|  Pipecat Voice Pipeline:       |
|                                |
|  +----------------------+      |
|  | Silero VAD           | 0 GB |
|  | (voice detection)    |      |
|  +----------+-----------+      |
|             v                  |
|  +----------------------+      |
|  | Whisper STT          | 3 GB |
|  | (speech -> text)     |      |
|  +----------+-----------+      |
|             v                  |
|  +----------------------+      |
|  | Agent Bridge         | 0 GB |
|  | (sends text to agent |      |
|  |  returns response)   |      |
|  +----------+-----------+      |
|             v                  |
|  +----------------------+      |
|  | Kokoro TTS           | 2 GB |
|  | (text -> speech)     |      |
|  +----------------------+      |
|                                |
|  Total VRAM: ~5 GB             |
|  Min GPU: 6 GB (GTX 1060+)    |
+--------------------------------+
```

## Latency (Recommended Setup -- Groq + Piper)

| Step | Time |
|------|------|
| Silero VAD (end of speech) | ~100ms |
| Groq Whisper API | ~200ms |
| LLM / Agent API (time to first token) | ~300-600ms |
| Piper TTS (first chunk) | ~100ms |
| **Total to first audio** | **~0.8-1.2s** |

## Latency (GPU Local -- Whisper + Kokoro)

| Step | Time |
|------|------|
| Silero VAD (end of speech) | ~100ms |
| Local Whisper STT | ~200ms |
| LLM / Agent API (time to first token) | ~300-600ms |
| First sentence complete | ~300ms |
| Kokoro TTS (first chunk) | ~150ms |
| **Total to first audio** | **~1.0-1.5s** |

Key: responses are **streamed sentence-by-sentence**. TTS starts speaking the first
sentence while the LLM is still generating the rest.

## Components

| Component | What | Runs On | License |
|-----------|------|---------|---------|
| Pyrogram | Telegram MTProto client | Caller | MIT |
| pytgcalls | Telegram VoIP bridge | Caller | LGPL |
| Pipecat | Voice AI pipeline framework | Pipeline | BSD |
| Silero VAD | Voice activity detection | Pipeline | MIT |
| Groq Whisper API | Speech-to-text (recommended) | Cloud (free) | Proprietary |
| Piper | Text-to-speech (recommended) | Pipeline (CPU) | MIT |
| faster-whisper | Speech-to-text (GPU mode) | Pipeline (GPU) | MIT |
| Kokoro | Text-to-speech (GPU mode) | Pipeline (GPU) | Apache |

## Cost

**Recommended setup: $0 for the voice pipeline.** Groq's free tier provides 28,800
audio-seconds per day (about 8 hours of transcription). Piper TTS is free and local.

Only cost is your LLM backend (if using a cloud model). Local models via Ollama are free.

**GPU local setup: $0.** Everything runs locally. Same LLM cost caveat applies.

## Configuration

Backend selection is done via environment variables in `pipeline/.env`:

```
STT_BACKEND=groq     # or "local" for GPU mode
TTS_BACKEND=piper    # or "kokoro" for GPU mode
```

The pipeline code uses factory functions to instantiate the correct Pipecat services
based on these settings. See `pipeline/config.py` and `pipeline/pipeline.py`.
