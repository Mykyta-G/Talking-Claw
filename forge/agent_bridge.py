"""
Talking-Claw -- Clawdbot Agent Bridge

Custom Pipecat FrameProcessor that routes transcribed text to a clawdbot
agent via the gateway HTTP API and streams the response back for TTS.

Instead of running a local LLM, this sends the user's speech to the same
AI agent they interact with in chat -- same personality, memory, and tools.

The response is streamed sentence-by-sentence so TTS can start speaking
the first sentence while the agent is still generating the rest.
"""

import asyncio
import logging
import re
import time
from typing import AsyncGenerator, Optional

import aiohttp

from config import (
    CLAWDBOT_GATEWAY,
    GATEWAY_TOKEN,
    VOICE_SYSTEM_PROMPT,
    get_voice,
)

logger = logging.getLogger("talking-claw.bridge")

# Sentence boundary pattern for streaming TTS
# Splits on . ! ? followed by space or end of string, preserving the punctuation
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


class ClawdBridge:
    """
    Bridges voice transcriptions to a clawdbot agent session.

    For each user utterance:
        1. Sends the transcribed text to the clawdbot gateway
        2. Receives the agent's text response
        3. Splits into sentences for streaming TTS
        4. Tracks the conversation transcript
    """

    def __init__(self, agent_id: str = "wizard") -> None:
        self.agent_id = agent_id
        self.session_id: Optional[str] = None
        self.transcript: list[dict] = []
        self._session: Optional[aiohttp.ClientSession] = None
        self._voice_prompt_injected = False

    async def start(self) -> None:
        """Initialize the HTTP session."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        logger.info("ClawdBridge started (agent=%s)", self.agent_id)

    async def stop(self) -> None:
        """Clean up resources."""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("ClawdBridge stopped")

    async def send(self, text: str) -> AsyncGenerator[str, None]:
        """
        Send user speech text to the agent and yield response sentences.

        This is an async generator: it yields individual sentences as they
        become available, allowing the TTS to start speaking immediately.

        Args:
            text: Transcribed user speech.

        Yields:
            Individual sentences from the agent's response.
        """
        if not text.strip():
            return

        logger.info("User said: %s", text)
        self.transcript.append({
            "role": "user",
            "text": text,
            "time": time.time(),
        })

        # Build the request
        message = text
        if not self._voice_prompt_injected:
            # Prepend the voice system prompt on first message
            message = (
                f"[SYSTEM: {VOICE_SYSTEM_PROMPT}]\n\n"
                f"[The user is speaking to you in a live voice call. "
                f"Respond conversationally.]\n\n"
                f"{text}"
            )
            self._voice_prompt_injected = True

        try:
            response_text = await self._call_gateway(message)
        except Exception as exc:
            logger.error("Gateway request failed: %s", exc)
            response_text = "Sorry, I had trouble processing that. Could you say it again?"

        logger.info("Agent response: %s", response_text)
        self.transcript.append({
            "role": "assistant",
            "text": response_text,
            "time": time.time(),
        })

        # Stream sentence by sentence
        sentences = _SENTENCE_RE.split(response_text)
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                yield sentence

    async def _call_gateway(self, message: str) -> str:
        """
        Send a message to the clawdbot gateway and return the response.

        The gateway endpoint accepts a POST with the message and returns
        the agent's response text.
        """
        if not self._session:
            raise RuntimeError("Bridge not started -- call start() first")

        url = f"{CLAWDBOT_GATEWAY}/api/v1/message"

        headers = {
            "Content-Type": "application/json",
        }
        if GATEWAY_TOKEN:
            headers["Authorization"] = f"Bearer {GATEWAY_TOKEN}"

        payload = {
            "message": message,
            "agentId": self.agent_id,
        }

        # Include session ID for conversation continuity
        if self.session_id:
            payload["sessionId"] = self.session_id

        async with self._session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.error("Gateway error %d: %s", resp.status, body[:200])
                raise RuntimeError(f"Gateway returned {resp.status}")

            data = await resp.json()

            # Capture session ID for subsequent messages
            if "sessionId" in data:
                self.session_id = data["sessionId"]

            return data.get("response", data.get("text", ""))

    async def send_transcript_summary(self) -> Optional[str]:
        """
        After the call ends, send the full transcript back to the agent
        so it can summarize and continue working.

        Returns the summary text, or None if it fails.
        """
        if not self.transcript:
            return None

        # Format the transcript
        lines = []
        for entry in self.transcript:
            speaker = "User" if entry["role"] == "user" else "AI"
            lines.append(f"{speaker}: {entry['text']}")
        transcript_text = "\n".join(lines)

        summary_prompt = (
            "[Voice call ended. Here is the full transcript:]\n\n"
            f"{transcript_text}\n\n"
            "[Summarize any action items from this call and continue working. "
            "You are no longer in voice mode -- respond normally.]"
        )

        try:
            response = await self._call_gateway(summary_prompt)
            logger.info("Post-call summary: %s", response[:200])
            return response
        except Exception as exc:
            logger.error("Failed to send post-call summary: %s", exc)
            return None

    def get_voice(self) -> str:
        """Get the TTS voice for the current agent."""
        return get_voice(self.agent_id)
