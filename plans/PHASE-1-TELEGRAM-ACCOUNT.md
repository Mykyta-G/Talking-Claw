# Phase 1 — Telegram Userbot Account

> **Time:** 15 minutes
> **What:** Create a second Telegram account for the AI to make calls from.

The AI needs its own Telegram account to call you. You can't call yourself.

## Option A: TextNow (Free, US Number)

1. Grab any old phone (Android/iPhone), connect to WiFi
2. Install **TextNow** — you get a free US number
3. Install **Telegram** on the same phone
4. Sign up for Telegram using the TextNow number
5. Verification code arrives in TextNow app as SMS
6. Set a **2FA password**: Settings → Privacy → Two-Step Verification
7. Done. Old phone can be turned off.

**Keep-alive:** TextNow reclaims numbers after ~30 days of inactivity. Send one text per month from the TextNow app, or set up a cron job.

## Option B: Cheap SIM (More Reliable)

Buy a prepaid SIM for ~$5. More reliable than TextNow.

## Get Telegram API Credentials

1. Go to https://my.telegram.org
2. Log in with the new number
3. Go to "API development tools"
4. Create an application:
   - Title: `TalkingClaw`
   - Platform: `Other`
5. Save your **API ID** and **API Hash**

## What You Have After This Phase

```
A second Telegram account (the AI's "phone number")
API ID and API Hash for programmatic access
2FA password set
```

## Credentials to Save

```
TELEGRAM_API_ID=__________
TELEGRAM_API_HASH=__________
TELEGRAM_PHONE=+1__________
TELEGRAM_2FA_PASSWORD=__________
YOUR_TELEGRAM_USER_ID=__________
```

Find your user ID: message @userinfobot on Telegram.
