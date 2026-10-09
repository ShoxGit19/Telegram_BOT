"""Explicit one-time update announcement. Preview by default; send only with --send."""
import argparse
import asyncio
import hashlib
import json
import os
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError

ROOT = Path(__file__).resolve().parent
MESSAGE_FILE = ROOT / "announcements" / "bot-update-2026-10-09.html"
STATE_FILE = ROOT / "data" / "broadcast_bot_update_20261009_v1.json"
CAMPAIGN_ID = "bot_update_20261009_v1"


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers / antivirus may briefly hold the destination open.
        for attempt in range(10):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.1)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def campaign_state(users, text, path):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("campaign") != CAMPAIGN_ID or state.get("message_sha256") != digest:
            raise ValueError("Campaign or message differs; refusing to send duplicates.")
        # Repair legacy classification: BadRequest is a subclass of NetworkError,
        # but an explicit rejection proves that no message was delivered.
        for delivery in state["deliveries"].values():
            if delivery.get("status") == "uncertain" and delivery.get("error") == "BadRequest":
                delivery["status"] = "retryable_rejected"
        save_state(path, state)
        return state
    recipients = list(dict.fromkeys(str(int(uid)) for uid in users if str(uid).isdigit() and int(uid) > 0))
    state = {
        "campaign": CAMPAIGN_ID, "message_sha256": digest,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "recipients": recipients, "deliveries": {},
    }
    save_state(path, state)
    return state


def summary(state):
    counts = Counter(entry["status"] for entry in state["deliveries"].values())
    return {"total": len(state["recipients"]), **dict(counts),
            "pending": len(state["recipients"]) - len(state["deliveries"])}


async def deliver_campaign(bot, users, text, state_path, delay=0.1):
    state = campaign_state(users, text, state_path)
    for index, uid in enumerate(state["recipients"], start=1):
        # Includes interrupted/uncertain attempts: never automatically resend them.
        if uid in state["deliveries"] and state["deliveries"][uid]["status"] != "retryable_rejected":
            continue
        delivery = {"status": "sending", "started_at": datetime.now(timezone.utc).isoformat()}
        state["deliveries"][uid] = delivery
        save_state(state_path, state)
        for attempt in range(3):
            try:
                response = await bot.send_message(
                    chat_id=int(uid), text=text, parse_mode="HTML",
                    read_timeout=30, write_timeout=30, connect_timeout=15,
                )
                delivery.update(status="sent", message_id=response.message_id)
                break
            except RetryAfter as error:
                if attempt == 2:
                    delivery.update(status="rate_limited", error="RetryAfter")
                    break
                seconds = error.retry_after.total_seconds() if hasattr(error.retry_after, "total_seconds") else float(error.retry_after)
                while seconds > 0:
                    pause = min(seconds + 0.1, 30)
                    print("Telegram rate limit: waiting before retry.", flush=True)
                    await asyncio.sleep(pause)
                    seconds -= pause
            except Forbidden as error:
                reason = str(error).lower()
                status = "blocked" if "blocked" in reason else "deactivated" if "deactivated" in reason else "forbidden"
                delivery.update(status=status, error=type(error).__name__)
                break
            except BadRequest as error:
                reason = str(error)
                status = "unavailable" if "chat not found" in reason.lower() else "rejected"
                delivery.update(status=status, error="BadRequest", reason=reason)
                break
            except NetworkError as error:
                # The request may have reached Telegram; do not risk a duplicate.
                delivery.update(status="uncertain", error=type(error).__name__)
                break
            except TelegramError as error:
                delivery.update(status="failed", error=type(error).__name__)
                break
        delivery["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state_path, state)
        if index % 10 == 0:
            print(json.dumps(summary(state)), flush=True)
        await asyncio.sleep(delay)
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state_path, state)
    return summary(state)


async def send():
    load_dotenv(ROOT / ".env")
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing.")
    text = MESSAGE_FILE.read_text(encoding="utf-8")
    if not text.strip() or len(text) > 4096:
        raise ValueError("Announcement must contain 1..4096 characters.")
    users = json.loads((ROOT / "users.json").read_text(encoding="utf-8"))
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = STATE_FILE.with_suffix(".lock")
    # A second process must never send the same campaign in parallel.
    with lock_path.open("x", encoding="utf-8") as lock:
        lock.write(str(os.getpid()))
    try:
        async with Bot(token) as bot:
            result = await deliver_campaign(bot, users, text, STATE_FILE)
        print("FINAL " + json.dumps(result), flush=True)
    finally:
        lock_path.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Send the prepared message once to all stored users.")
    args = parser.parse_args()
    if args.send:
        asyncio.run(send())
    else:
        text = MESSAGE_FILE.read_text(encoding="utf-8")
        users = json.loads((ROOT / "users.json").read_text(encoding="utf-8"))
        print("Preview only; no messages sent.")
        print("Recipients:", len(users), "Message characters:", len(text))
        print(text)


if __name__ == "__main__":
    main()
