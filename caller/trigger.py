"""
Talking-Claw -- Call Trigger

Entry point for AI agents to initiate a voice call. Handles:
    1. Waking the pipeline server (Wake-on-LAN if configured)
    2. Waiting for the voice pipeline to come online
    3. Starting the Telegram call bridge

Usage:
    python trigger.py                           # default agent, no reason
    python trigger.py assistant "task complete"  # specific agent + reason
    python trigger.py --check                   # just check pipeline health

Exit codes:
    0 = call completed successfully
    1 = pipeline unreachable / call failed
    2 = bad arguments
"""

import asyncio
import logging
import subprocess
import sys
import time
from typing import Optional

import aiohttp

from config import (
    AGENT_ID,
    WOL_BROADCAST,
    HEALTH_TIMEOUT,
    PIPELINE_HEALTH_URL,
    PIPELINE_HOST,
    WOL_MAC_ADDRESS,
    WOL_TIMEOUT,
)

logger = logging.getLogger("talking-claw.trigger")


# ---------------------------------------------------------------------------
# pipeline server management
# ---------------------------------------------------------------------------

def send_wake_on_lan(mac_address: str, broadcast: str) -> bool:
    """
    Send a Wake-on-LAN magic packet to wake the pipeline server.
    Returns True if the packet was sent (not that the server woke up).
    """
    if not mac_address:
        logger.info("No MAC address configured -- skipping WoL")
        return False

    try:
        # Try using wakeonlan command if available
        result = subprocess.run(
            ["wakeonlan", "-i", broadcast, mac_address],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            logger.info("WoL packet sent to %s via %s", mac_address, broadcast)
            return True
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("wakeonlan command failed: %s", exc)

    # Fallback: craft the magic packet manually
    try:
        import socket
        mac_bytes = bytes.fromhex(mac_address.replace(":", "").replace("-", ""))
        magic = b"\xff" * 6 + mac_bytes * 16
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic, (broadcast, 9))
        sock.close()
        logger.info("WoL magic packet sent to %s (manual)", mac_address)
        return True
    except Exception as exc:
        logger.error("Failed to send WoL packet: %s", exc)
        return False


async def check_pipeline_health() -> bool:
    """Check if the Pipecat voice pipeline is running and healthy."""
    try:
        timeout = aiohttp.ClientTimeout(total=HEALTH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(PIPELINE_HEALTH_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info("Pipeline health: %s", data)
                    return True
                else:
                    logger.warning("Pipeline returned status %d", resp.status)
                    return False
    except asyncio.TimeoutError:
        logger.debug("Pipeline health check timed out")
        return False
    except aiohttp.ClientConnectorError:
        logger.debug("Pipeline not reachable at %s", PIPELINE_HEALTH_URL)
        return False
    except Exception as exc:
        logger.debug("Pipeline health check failed: %s", exc)
        return False


async def wait_for_pipeline(timeout: int = WOL_TIMEOUT) -> bool:
    """
    Wait for the voice pipeline to become available.
    Sends WoL if configured, then polls the health endpoint.
    """
    # Quick check -- maybe it's already running
    if await check_pipeline_health():
        logger.info("Pipeline already online")
        return True

    # Try to wake the pipeline server
    send_wake_on_lan(WOL_MAC_ADDRESS, WOL_BROADCAST)

    # Poll until healthy or timeout
    start = time.time()
    attempt = 0
    while time.time() - start < timeout:
        attempt += 1
        wait_time = min(5, 1 + attempt * 0.5)  # backoff: 1.5, 2, 2.5, ... 5s
        await asyncio.sleep(wait_time)

        if await check_pipeline_health():
            elapsed = time.time() - start
            logger.info("Pipeline came online after %.1f seconds", elapsed)
            return True

        if attempt % 5 == 0:
            logger.info(
                "Still waiting for pipeline... (%.0fs / %ds)",
                time.time() - start,
                timeout,
            )

    logger.error(
        "Pipeline did not come online within %d seconds. "
        "Is the pipeline server running? Check: %s",
        timeout,
        PIPELINE_HEALTH_URL,
    )
    return False


# ---------------------------------------------------------------------------
# Main trigger
# ---------------------------------------------------------------------------

async def trigger_call(agent_id: str = AGENT_ID, reason: str = "") -> int:
    """
    Full trigger sequence: wake pipeline server -> check health -> make call.

    Returns:
        0 on success, 1 on failure.
    """
    logger.info("=" * 50)
    logger.info("Talking-Claw call trigger")
    logger.info("  Agent:  %s", agent_id)
    logger.info("  Reason: %s", reason or "(none)")
    logger.info("  pipeline server:  %s", PIPELINE_HOST)
    logger.info("=" * 50)

    # Step 1: Ensure pipeline is available
    if not await wait_for_pipeline():
        logger.error("Cannot proceed without voice pipeline")
        return 1

    # Step 2: Start the call
    try:
        from caller import make_call
        transcript = await make_call(agent_id=agent_id, reason=reason)

        if transcript:
            logger.info("Call completed with transcript (%d chars)", len(transcript))
        else:
            logger.info("Call completed (no transcript)")

        return 0

    except Exception:
        logger.exception("Call failed")
        return 1


def print_usage() -> None:
    """Print CLI usage information."""
    print("Talking-Claw -- Voice Call Trigger")
    print()
    print("Usage:")
    print("  python trigger.py [agent_id] [reason...]")
    print("  python trigger.py --check")
    print("  python trigger.py --help")
    print()
    print("Arguments:")
    print("  agent_id   Agent personality to use (default: from .env)")
    print("  reason     Why the call is being made (free text)")
    print()
    print("Options:")
    print("  --check    Check if the pipeline is reachable, then exit")
    print("  --help     Show this message")
    print()
    print("Examples:")
    print('  python trigger.py assistant "deployment finished, need review"')
    print("  python trigger.py helper")
    print("  python trigger.py --check")


async def main() -> int:
    args = sys.argv[1:]

    if not args:
        return await trigger_call()

    if args[0] == "--help":
        print_usage()
        return 0

    if args[0] == "--check":
        healthy = await check_pipeline_health()
        if healthy:
            print("Pipeline is online and healthy.")
            return 0
        else:
            print(f"Pipeline is NOT reachable at {PIPELINE_HEALTH_URL}")
            return 1

    # Parse: trigger.py [agent_id] [reason...]
    agent_id = args[0]
    reason = " ".join(args[1:]) if len(args) > 1 else ""
    return await trigger_call(agent_id=agent_id, reason=reason)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
