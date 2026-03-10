# Phase 4 — Voice Personality & Agent Integration

> **Time:** 30 minutes
> **What:** Make the AI sound and behave like a real person on the phone.

## 4.1 — Voice Call System Prompt

When a voice call starts, inject this into the agent's context:

```
You are in a LIVE VOICE CALL. Your text is being spoken aloud.

VOICE RULES:
- 1-3 sentences max per turn. This is a conversation, not an essay.
- Use contractions: don't, can't, I'll, that's, we're, it's.
- Natural fillers are OK: "well", "so", "right", "hmm", "look".
- No markdown. No bullet points. No code blocks. No emojis.
- No asterisks for emphasis — use word stress naturally.
- If asked about code or long content, say "I'll send that to you in chat."
- Match your personality but keep it CONCISE.
- When wrapping up, say goodbye naturally — don't just stop.
- You can still use tools silently. The user only hears your spoken words.
```

## 4.2 — TTS Voice Selection

Kokoro voices that work well for AI assistants:

| Voice ID | Style | Good For |
|----------|-------|----------|
| `bm_lewis` | Deep, authoritative British | Wizard, formal assistants |
| `am_michael` | Confident American | General purpose, professional |
| `am_adam` | Casual younger male | Friendly, informal assistants |
| `af_heart` | Warm female | Approachable, empathetic |
| `af_bella` | Professional female | Business, formal |

### Per-Agent Voice Mapping Example

```python
VOICES = {
    "wizard": "bm_lewis",     # deep wizard energy
    "killer": "am_michael",   # confident coder
    "gunnar": "am_adam",      # chill teen
    "default": "bm_lewis",
}
```

## 4.3 — Conversation Flow

```
Phone rings → You pick up
     ↓
AI: "Hey, it's [Agent]. I just finished [task]. Got a minute?"
     ↓
You talk naturally back and forth (1-2 sec response time)
     ↓
Either side says goodbye
     ↓
Call ends → AI saves transcript → Continues working
```

## 4.4 — Post-Call Summary

After the call ends, the pipeline sends the full transcript back to the agent:

```python
async def on_call_ended(transcript: list[dict]):
    """Called when the voice call disconnects."""
    # Format the transcript
    text = "\n".join(
        f"{'You' if msg['role'] == 'user' else 'AI'}: {msg['text']}"
        for msg in transcript
    )

    # Send to the agent's session
    await send_to_agent(
        f"[Voice call ended. Transcript:]\n\n{text}\n\n"
        f"[Summarize any action items and continue working.]"
    )
```

## 4.5 — When Should the AI Call?

Guidelines for agents:

**DO call when:**
- Finished a major task and need confirmation to proceed
- Hit a blocker that can't be resolved without human input
- Something urgent happened (build failure, security issue)
- User explicitly asked to be called when something completes

**DON'T call when:**
- Routine status updates (use text)
- Late night (respect quiet hours)
- The answer could be found by searching/reading
- Multiple quick questions (batch them into text)

## What You Have After This Phase

```
✅ AI speaks with appropriate voice for its personality
✅ Conversations feel natural (short, conversational, human-like)
✅ Post-call summaries saved to agent memory
✅ Agents know when to call vs. text
```
