import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from telegram.error import TelegramError

import first
import extra_features


class TimerTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_work_does_not_show_timer(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        result = await first.run_with_countdown(message, lambda: "ready")
        self.assertEqual(result, "ready")
        message.reply_text.assert_not_awaited()

    async def test_timer_keeps_updating_after_five_seconds_until_actual_completion(self):
        release = threading.Event()
        progress_message = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=progress_message))
        async def edit(text):
            if "20 soniya" in text:
                release.set()
        progress_message.edit_text.side_effect = edit
        def operation():
            if not release.wait(timeout=2):
                raise TimeoutError("Timer stopped before work completed")
            return "ready"
        fake_clock = SimpleNamespace(monotonic=Mock(side_effect=[100, 101, 110, 120]))
        with patch.object(first, "PROGRESS_UPDATE_SECONDS", 0.01), patch.object(first, "time", fake_clock):
            result = await first.run_with_countdown(message, operation)
        self.assertEqual(result, "ready")
        self.assertIn("1 soniya", message.reply_text.await_args.args[0])
        self.assertIn("10 soniya", progress_message.edit_text.await_args_list[0].args[0])
        self.assertIn("20 soniya", progress_message.edit_text.await_args_list[1].args[0])
        progress_message.delete.assert_awaited_once()

    async def test_progress_edit_failure_does_not_abort_work(self):
        release = threading.Event()
        async def failing_edit(text):
            release.set()
            raise TelegramError("Status message removed")
        progress_message = SimpleNamespace(edit_text=AsyncMock(side_effect=failing_edit), delete=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=progress_message))
        def operation():
            if not release.wait(timeout=2):
                raise TimeoutError("Status was never updated")
            return "ready"
        with patch.object(first, "PROGRESS_UPDATE_SECONDS", 0.01):
            self.assertEqual(await first.run_with_countdown(message, operation), "ready")
        progress_message.delete.assert_awaited_once()

    async def test_timer_is_removed_when_processing_fails(self):
        release = threading.Event()
        progress_message = SimpleNamespace(
            edit_text=AsyncMock(side_effect=lambda text: release.set()), delete=AsyncMock(),
        )
        message = SimpleNamespace(reply_text=AsyncMock(return_value=progress_message))
        def operation():
            release.wait(timeout=2)
            raise ValueError("Processing failed")
        with patch.object(first, "PROGRESS_UPDATE_SECONDS", 0.01):
            with self.assertRaisesRegex(ValueError, "Processing failed"):
                await first.run_with_countdown(message, operation)
        progress_message.delete.assert_awaited_once()

    def test_remaining_time_uses_actual_chunk_speed_and_revises_for_slow_work(self):
        progress = first.ProcessingProgress(4)
        initial = first.processing_status_text("Translating", 1, progress)
        self.assertNotIn("Taxminan qolgan vaqt", initial)
        progress.advance()
        self.assertIn("30 soniya", first.processing_status_text("Translating", 10, progress))
        self.assertIn("90 soniya", first.processing_status_text("Translating", 30, progress))
        progress.advance()
        progress.advance()
        text = first.processing_status_text("Translating", 12, progress)
        self.assertIn("3/4", text)
        self.assertIn("4 soniya", text)
        progress.advance()
        self.assertIn("Natija yakunlanmoqda", first.processing_status_text("Translating", 15, progress))
        self.assertNotIn("Taxminan qolgan vaqt", first.processing_status_text("Translating", 15, progress))

    async def test_translation_reports_only_finished_nonempty_chunks(self):
        text = "Hello\r\n\r\nWorld " + "word " * 1600
        completed = Mock()
        translator = SimpleNamespace(
            translate=AsyncMock(side_effect=lambda text, **kwargs: SimpleNamespace(text=text.upper(), src="en")),
        )
        manager = AsyncMock()
        manager.__aenter__.return_value = translator
        with patch.object(extra_features, "Translator", return_value=manager):
            result = await extra_features.translate_text(text, dest="uz", on_progress=completed)
        self.assertEqual(result, text.upper())
        self.assertEqual(completed.call_count, extra_features.translation_chunk_count(text))
        self.assertEqual(completed.call_count, translator.translate.await_count)

    async def test_failed_translation_is_not_counted_as_finished(self):
        completed = Mock()
        manager = AsyncMock()
        manager.__aenter__.return_value = SimpleNamespace(
            translate=AsyncMock(side_effect=RuntimeError("Network error")),
        )
        with patch.object(extra_features, "Translator", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "Network error"):
                await extra_features.translate_text("Hello", on_progress=completed)
        completed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
