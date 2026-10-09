"""Atomic registration of user/chat metadata received from Telegram."""
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

USERS_FILE = Path(__file__).resolve().parent / "users.json"
_LOCK = threading.RLock()


def _load_users():
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("users.json must contain an object; existing data was not overwritten.")
    return data


def _save_users(data):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=USERS_FILE.parent,
            prefix="users_", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=4)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(10):
            try:
                os.replace(temporary, USERS_FILE)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.1)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def register_user(user, chat=None, *, bot_id=None, bot_username=None):
    now = datetime.now(timezone.utc).isoformat()
    user_data = json.loads(user.to_json())
    chat_data = json.loads(chat.to_json()) if chat is not None else None
    user_id = str(user.id)
    with _LOCK:
        users = _load_users()
        is_new = user_id not in users
        existing = users.get(user_id, {})
        if not isinstance(existing, dict):
            raise ValueError("Existing user record is invalid; data was not overwritten.")
        record = dict(existing)
        record.update(
            user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=user.username or "",
            language_code=user_data.get("language_code"),
            is_bot=user.is_bot,
            is_premium=user_data.get("is_premium", False),
            telegram_user=user_data,
            last_start=now,
            updated_at=now,
            start_count=int(record.get("start_count", 0)) + 1,
        )
        record.setdefault("phone", "")
        record.setdefault("first_start", now)
        if chat_data is not None:
            record.update(chat_id=chat.id, chat_type=chat.type, telegram_chat=chat_data)
            if chat.type == "private":
                record["private_chat_id"] = chat.id
        if bot_id is not None:
            record["bot_id"] = bot_id
        if bot_username is not None:
            record["bot_username"] = bot_username
        users[user_id] = record
        _save_users(users)
        return dict(record), is_new


def save_user_contact(user_id, contact):
    if contact.user_id != user_id:
        raise ValueError("Only the user's own shared contact may be saved.")
    with _LOCK:
        users = _load_users()
        record = users.get(str(user_id))
        if not isinstance(record, dict):
            return False
        record["phone"] = contact.phone_number
        record["contact"] = json.loads(contact.to_json())
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_users(users)
        return True
