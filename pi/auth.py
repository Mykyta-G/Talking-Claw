"""
Talking-Claw -- One-time Pyrogram authentication.

Run this ONCE interactively to create the session file.
You will need the phone number, verification code, and optional 2FA password.

Usage:
    cd pi/
    cp .env.example .env   # fill in your credentials
    python auth.py

After success, a .session file is created. Do NOT run this while caller.py is active.
"""

import asyncio
import sys

from pyrogram import Client

from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    SESSION_PATH,
)


async def main() -> None:
    print("=" * 50)
    print("Talking-Claw -- Telegram Authentication")
    print("=" * 50)
    print()
    print("This will create a Pyrogram session file.")
    print("You need:")
    print("  1. The AI's Telegram phone number")
    print("  2. Access to receive the verification code")
    print("  3. The 2FA password (if set)")
    print()

    app = Client(
        name=SESSION_PATH,
        api_id=TELEGRAM_API_ID,
        api_hash=TELEGRAM_API_HASH,
    )

    async with app:
        me = await app.get_me()
        print()
        print(f"Authenticated as: {me.first_name} (ID: {me.id})")
        print(f"Session saved to: {SESSION_PATH}.session")
        print()
        print("You can now run caller.py. Do NOT run auth.py again")
        print("while the caller is active -- only one process can")
        print("use a session file at a time.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nAuthentication failed: {exc}")
        sys.exit(1)
