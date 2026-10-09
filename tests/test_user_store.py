import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from telegram import User, Chat, Contact
import first
import user_store


class UserStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "users.json"
        self.patcher = patch.object(user_store, "USERS_FILE", self.path)
        self.patcher.start()
        self.user = User(123, "Ali", False, last_name="Test", username="ali_test",
                         language_code="uz", is_premium=True)
        self.chat = Chat(123, "private", first_name="Ali", username="ali_test")

    def tearDown(self):
        self.patcher.stop()
        self.directory.cleanup()

    def test_new_start_saves_received_metadata_and_usable_chat_id(self):
        record, is_new = user_store.register_user(
            self.user, self.chat, bot_id=999, bot_username="example_bot",
        )
        self.assertTrue(is_new)
        saved = json.loads(self.path.read_text(encoding="utf-8"))["123"]
        self.assertEqual(saved["telegram_user"], json.loads(self.user.to_json()))
        self.assertEqual(saved["telegram_chat"], json.loads(self.chat.to_json()))
        self.assertEqual(saved["private_chat_id"], 123)
        self.assertEqual(saved["bot_id"], 999)
        self.assertEqual(saved["start_count"], 1)
        self.assertEqual(saved["phone"], "")
        self.assertTrue(saved["is_premium"])
        self.assertEqual(saved["first_start"], saved["last_start"])

    def test_existing_start_updates_profile_without_losing_old_fields_or_other_users(self):
        self.path.write_text(json.dumps({
            "123": {"first_start": "2025-01-01", "phone": "+998000000000", "custom_field": "keep"},
            "456": {"first_name": "Other"},
        }), encoding="utf-8")
        record, is_new = user_store.register_user(self.user, self.chat)
        self.assertFalse(is_new)
        self.assertEqual(record["first_start"], "2025-01-01")
        self.assertEqual(record["phone"], "+998000000000")
        self.assertEqual(record["custom_field"], "keep")
        changed = User(123, "New name", False, username="changed")
        user_store.register_user(changed, self.chat)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 2)
        self.assertEqual(data["123"]["username"], "changed")
        self.assertEqual(data["123"]["start_count"], 2)
        self.assertEqual(data["456"], {"first_name": "Other"})

    def test_shared_own_contact_is_preserved_on_later_start(self):
        user_store.register_user(self.user, self.chat)
        contact = Contact("+998000000000", "Ali", user_id=123)
        self.assertTrue(user_store.save_user_contact(123, contact))
        record, _ = user_store.register_user(self.user, self.chat)
        self.assertEqual(record["phone"], contact.phone_number)
        self.assertEqual(record["contact"], json.loads(contact.to_json()))

    def test_someone_elses_contact_cannot_modify_user_record(self):
        user_store.register_user(self.user, self.chat)
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            user_store.save_user_contact(123, Contact("+998000000001", "Other", user_id=456))
        self.assertEqual(self.path.read_bytes(), original)

    def test_corrupt_database_is_not_overwritten(self):
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            user_store.register_user(self.user, self.chat)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{broken")

    def test_parallel_registration_keeps_every_record(self):
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(lambda uid: user_store.register_user(
                User(uid, "Test", False), Chat(uid, "private"),
            ), range(100, 115)))
        self.assertEqual(len(json.loads(self.path.read_text(encoding="utf-8"))), 15)


class StartHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_registers_then_opens_menu_for_existing_or_new_user(self):
        user = User(123, "Ali", False)
        chat = Chat(123, "private")
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=user, effective_chat=chat, message=message)
        context = SimpleNamespace(
            user_data={"selected_action": "image"},
            bot=SimpleNamespace(id=999, username="example_bot"),
        )
        for is_new in (True, False):
            with patch.object(first, "register_user", return_value=({}, is_new)) as register, patch.object(first, "show_main_menu", new=AsyncMock()) as menu:
                await first.start(update, context)
                register.assert_called_once_with(user, chat, bot_id=999, bot_username="example_bot")
                menu.assert_awaited_once_with(message, first.START_MESSAGE)
        self.assertNotIn("selected_action", context.user_data)
