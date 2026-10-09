import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.error import BadRequest, Forbidden, TimedOut, RetryAfter
from broadcast_update import campaign_state, deliver_campaign, save_state


class UpdateBroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_blocked_and_ambiguous_attempts_are_not_resent(self):
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=[
            SimpleNamespace(message_id=1), Forbidden("Bot was blocked by the user"), TimedOut(),
        ]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            report = await deliver_campaign(bot, {"1": {}, "2": {}, "3": {}}, "Update", path, delay=0)
            self.assertEqual(report, {"total": 3, "sent": 1, "blocked": 1, "uncertain": 1, "pending": 0})
            repeated = await deliver_campaign(bot, {"1": {}, "2": {}, "3": {}}, "Update", path, delay=0)
            self.assertEqual(repeated, report)
            self.assertEqual(bot.send_message.await_count, 3)
            self.assertEqual(json.loads(path.read_text())["deliveries"]["1"]["message_id"], 1)

    async def test_changed_message_cannot_reuse_same_campaign(self):
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            await deliver_campaign(bot, {"1": {}}, "Original update", path, delay=0)
            with self.assertRaisesRegex(ValueError, "differs"):
                await deliver_campaign(bot, {"1": {}}, "Changed update", path, delay=0)
            self.assertEqual(bot.send_message.await_count, 1)

    async def test_known_rate_limit_rejection_can_be_retried(self):
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=[
            RetryAfter(0), SimpleNamespace(message_id=7),
        ]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            report = await deliver_campaign(bot, {"1": {}}, "Update", path, delay=0)
            self.assertEqual(report["sent"], 1)
            self.assertEqual(bot.send_message.await_count, 2)

    async def test_bad_request_is_explicit_rejection_not_uncertain_network_delivery(self):
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=BadRequest("Chat not found")))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            report = await deliver_campaign(bot, {"1": {}}, "Update", path, delay=0)
            self.assertEqual(report["unavailable"], 1)
            self.assertNotIn("uncertain", report)

    async def test_legacy_rejected_attempt_can_be_retried_without_resending_success(self):
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=7)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = campaign_state({"1": {}, "2": {}}, "Update", path)
            state["deliveries"] = {
                "1": {"status": "sent", "message_id": 1},
                "2": {"status": "uncertain", "error": "BadRequest"},
            }
            save_state(path, state)
            report = await deliver_campaign(bot, {"1": {}, "2": {}}, "Update", path, delay=0)
            self.assertEqual(report["sent"], 2)
            bot.send_message.assert_awaited_once()
            self.assertEqual(bot.send_message.await_args.kwargs["chat_id"], 2)
