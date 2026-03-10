# Phase 5 -- Testing & Optimization

> **Time:** 1 hour
> **What:** Test end-to-end, optimize latency, fix audio issues.

## 5.1 -- Component Checklist

```
[ ] TextNow number works, Telegram account created
[ ] Pyrogram session authenticated on orchestrator
[ ] Pipecat pipeline starts without errors on GPU server
[ ] Whisper transcribes test audio correctly
[ ] Kokoro generates speech that sounds natural
[ ] WebSocket connection works between orchestrator and GPU server
[ ] pytgcalls can initiate a call (group chat or direct)
[ ] Audio streams correctly: your voice -> pipeline -> AI voice -> back
[ ] Post-call summary generates correctly
[ ] Agent trigger script works end-to-end
```

## 5.2 -- End-to-End Test

```bash
# On the orchestrator:
cd ~/talking-claw/caller
source venv/bin/activate
python trigger.py assistant "Test call -- checking if everything works"
```

Expected:
1. Your phone rings (Telegram call)
2. Pick up, say "Hello"
3. AI responds within 1-2 seconds
4. Have a short conversation
5. Say "Goodbye"
6. Call ends
7. Summary appears in agent session

## 5.3 -- Latency Debugging

If latency is too high, check each step:

```bash
# Test STT speed in isolation
time python -c "
from faster_whisper import WhisperModel
m = WhisperModel('distil-medium.en', device='cuda', compute_type='float16')
segs, _ = m.transcribe('test.wav')
for s in segs: print(s.text)
"

# Test TTS speed
time python -c "
from kokoro_onnx import Kokoro
k = Kokoro('kokoro-v1.0.onnx', 'voices-v1.0.bin')
s, sr = k.create('This is a latency test.', voice='bm_lewis')
print(f'{len(s)/sr:.2f}s of audio generated')
"

# Test LLM speed (if using Ollama)
time curl -s http://localhost:11434/acaller/generate -d '{
  "model": "llama3.1:8b",
  "prompt": "Say hello in one sentence.",
  "stream": false
}' | jq -r '.response'
```

## 5.4 -- Latency Optimization Moves

| Problem | Fix | Impact |
|---------|-----|--------|
| STT too slow | Switch to `distil-small.en` | -100ms, slight accuracy loss |
| LLM too slow (cloud) | Use a faster model (e.g. Haiku) | -500ms |
| LLM too slow (local) | Use smaller model (3B) | -200ms |
| TTS too slow | Run Kokoro on GPU (default) | Already optimized |
| Network latency | Use local network instead of Tailscale | -20ms |
| Audio buffering | Reduce Pipecat buffer sizes | -50ms |

## 5.5 -- Audio Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Robotic / choppy voice | Sample rate mismatch | Resample 48kHz to 16kHz |
| Echo / feedback | Audio looping back | Add echo cancellation or mute during playback |
| Long silence before response | VAD not detecting end of speech | Lower VAD threshold |
| AI interrupts you | VAD too sensitive | Raise VAD threshold |
| No audio in call | WebSocket not connected | Check firewall, port 8790 |

## 5.6 -- Future Upgrades

| Upgrade | What | VRAM |
|---------|------|------|
| Orpheus TTS | Emotional voice (laughs, sighs) | +5 GB |
| Sesame CSM | Most human-sounding TTS | +5 GB |
| F5-TTS | Clone any voice | +4 GB |
| Whisper large-v3-turbo | Better accuracy | +3 GB |
| Wake word detection | Trigger calls by voice command | +0.5 GB |

## What You Have After This Phase

```
Full working voice call system
AI calls you, you pick up, have a conversation
Sub-2 second response time
Post-call summaries saved
System runs as background services
```
