import asyncio
import html
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock, patch

from PIL import Image
from telegram import Message
import extra_features
import first
from webhook_server import create_app


def message_mock(**attrs):
    return SimpleNamespace(
        reply_text=AsyncMock(), reply_document=AsyncMock(),
        edit_text=AsyncMock(), **attrs,
    )


class CopyTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_copy_preserves_all_characters_and_valid_button_lengths(self):
        text = ("<hello>& \U0001f600 \u0441\u0430\u043b\u043e\u043c\n" * 90)
        user_data = {}
        markup = first.copy_result_markup(text, user_data)
        query = SimpleNamespace(
            data=markup.inline_keyboard[-1][0].callback_data,
            message=message_mock(), answer=AsyncMock(),
        )
        await first.copy_result_callback(
            SimpleNamespace(callback_query=query), SimpleNamespace(user_data=user_data),
        )
        calls = query.message.reply_text.await_args_list[1:]
        copied = []
        for call in calls:
            button = call.kwargs["reply_markup"].inline_keyboard[0][0]
            part = button.copy_text.text
            self.assertLessEqual(len(part.encode("utf-16-le")) // 2, 256)
            self.assertEqual(call.args[0], f"<pre>{html.escape(part)}</pre>")
            copied.append(part)
        self.assertEqual("".join(copied), text)

    async def test_ocr_length_result_is_split_and_html_escaped(self):
        message = message_mock()
        text = "<x>&\U0001f600" * 1000
        await first.send_copyable_text(message, text, {})
        result = "".join(
            html.unescape(call.args[0][5:-6])
            for call in message.reply_text.await_args_list
        )
        self.assertEqual(result, text)
        self.assertTrue(all(call.kwargs["reply_markup"] for call in message.reply_text.await_args_list))

    async def test_short_result_has_native_copy_and_manual_fallback(self):
        markup = first.copy_result_markup("salom", {})
        self.assertEqual(markup.inline_keyboard[0][0].copy_text.text, "salom")
        self.assertTrue(markup.inline_keyboard[1][0].callback_data.startswith("copy:"))


    async def test_copy_survives_restart_and_recovers_exact_text_from_message_entities(self):
        text = "\U0001f600 <hello> & \u0421\u0430\u043b\u043e\u043c\n" * 30
        original = Message.de_json({
            "message_id": 1, "date": 0,
            "chat": {"id": 100, "type": "private"},
            "text": "Result:\n" + text,
            "entities": [{
                "type": "pre", "offset": 8,
                "length": len(text.encode("utf-16-le")) // 2,
            }],
        }, None)
        message = message_mock(parse_entities=original.parse_entities)
        query = SimpleNamespace(data="copy:previous-session", message=message, answer=AsyncMock())
        await first.copy_result_callback(
            SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
        )
        copied = "".join(
            call.kwargs["reply_markup"].inline_keyboard[0][0].copy_text.text
            for call in message.reply_text.await_args_list[1:]
        )
        self.assertEqual(copied, text)

    async def test_copy_without_saved_result_or_entities_answers_with_alert(self):
        query = SimpleNamespace(
            data="copy:missing", message=message_mock(), answer=AsyncMock(),
        )
        await first.copy_result_callback(
            SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
        )
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])
        query.message.reply_text.assert_not_awaited()


class TxtFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_menu_translation_prompts_for_language_first(self):
        message = message_mock(text="\U0001f310 TXT tarjima")
        context = SimpleNamespace(user_data={})
        await first.matn_olish(
            SimpleNamespace(message=message, effective_user=SimpleNamespace(id=100)), context,
        )
        self.assertEqual(context.user_data["selected_action"], "text_file_language")
        buttons = message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard[0]
        self.assertEqual([b.callback_data for b in buttons], [
            "txt_action:translate:uz", "txt_action:translate:ru", "txt_action:translate:en",
        ])

    async def test_translation_menu_then_language(self):
        context = SimpleNamespace(user_data={"txt_translate_target": "en"})
        query = SimpleNamespace(
            data="txt_action:translate", answer=AsyncMock(),
            message=message_mock(), edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        await first.txt_file_action_callback(update, context)
        self.assertEqual(context.user_data["selected_action"], "text_file_language")
        self.assertNotIn("txt_translate_target", context.user_data)
        for language in ("uz", "ru", "en"):
            query.data = f"txt_action:translate:{language}"
            await first.txt_file_action_callback(update, context)
            self.assertEqual(first.resolve_txt_file_mode(context.user_data), {
                "mode": "translate", "target_lang": language,
            })
        first.clear_pending_actions(context.user_data)
        self.assertEqual(first.resolve_txt_file_mode(context.user_data), {"mode": "transliterate"})

    async def test_upload_before_language_selection_does_not_transliterate(self):
        document = SimpleNamespace(mime_type="text/plain", file_name="input.txt", get_file=AsyncMock())
        message = message_mock(document=document)
        await first.txt_file_handler(
            SimpleNamespace(message=message),
            SimpleNamespace(user_data={"selected_action": "text_file_language"}),
        )
        document.get_file.assert_not_awaited()
        message.reply_text.assert_awaited_once()

    async def test_translated_utf8_file_uses_selected_language_and_resets_state(self):
        for language in ("uz", "ru", "en"):
            with self.subTest(language=language):
                source = "\ufeffHello world!\nSecond line."
                translated = "\u0421\u0430\u043b\u043e\u043c\nTarjima."
                async def download(custom_path):
                    Path(custom_path).write_bytes(source.encode("utf-8"))
                document = SimpleNamespace(
                    mime_type="text/plain", file_name="input.txt", file_size=100,
                    get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=download)),
                )
                received = {}
                async def reply_document(document, filename, caption):
                    received["content"] = document.read()
                    received["filename"] = filename
                message = message_mock(document=document)
                message.reply_document.side_effect = reply_document
                context = SimpleNamespace(user_data={
                    "selected_action": "text_file", "txt_translate_target": language,
                })
                update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=100))
                with patch.object(first, "translate_text", new=AsyncMock(return_value=translated)) as translate, patch.object(first, "is_rate_limited", return_value=False):
                    await first.txt_file_handler(update, context)
                translate.assert_awaited_once_with("Hello world!\nSecond line.", src="auto", dest=language, on_progress=ANY)
                self.assertEqual(received["filename"], f"translated_{language}.txt")
                self.assertEqual(received["content"].decode("utf-8"), translated)
                self.assertEqual(context.user_data, {})

    async def test_image_document_without_image_mime_routes_to_ocr(self):
        message = message_mock(document=SimpleNamespace(mime_type="application/octet-stream", file_name="scan.PNG"))
        update = SimpleNamespace(message=message)
        context = SimpleNamespace(user_data={})
        with patch.object(first, "ocr_command", new=AsyncMock()) as ocr:
            await first.txt_file_handler(update, context)
        ocr.assert_awaited_once_with(update, context)


    async def test_photo_ocr_downloads_and_returns_copyable_text(self):
        image = io.BytesIO()
        Image.new("RGB", (100, 50), "white").save(image, format="PNG")
        async def download(custom_path):
            Path(custom_path).write_bytes(image.getvalue())
        photo = SimpleNamespace(
            file_size=len(image.getvalue()),
            get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=download)),
        )
        message = message_mock(document=None, photo=[photo])
        context = SimpleNamespace(user_data={"selected_action": "image"})
        update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=100))
        with patch.object(first, "ocr_image", return_value="Salom <dunyo>") as ocr:
            await first.ocr_command(update, context)
        ocr.assert_called_once()
        call = message.reply_text.await_args_list[-1]
        self.assertEqual(call.args[0], "<pre>Salom &lt;dunyo&gt;</pre>")
        self.assertEqual(call.kwargs["reply_markup"].inline_keyboard[0][0].copy_text.text, "Salom <dunyo>")
        self.assertNotIn("selected_action", context.user_data)


class TranslationTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_txt_uses_small_requests_and_preserves_separators(self):
        text = "  Hello world. " * 900 + "\r\n\r\n\tSecond line.  \n"
        translator = SimpleNamespace(
            translate=AsyncMock(side_effect=lambda text, **kwargs: SimpleNamespace(text=text.upper(), src="en")),
        )
        manager = AsyncMock()
        manager.__aenter__.return_value = translator
        with patch.object(extra_features, "Translator", return_value=manager):
            result = await extra_features.translate_text(text, dest="ru")
        self.assertEqual(result, text.upper())
        self.assertGreater(translator.translate.await_count, 1)
        for call in translator.translate.await_args_list:
            self.assertLessEqual(len(call.args[0]), extra_features.TRANSLATION_CHUNK_CHARS)
            self.assertEqual(call.kwargs["dest"], "ru")
        self.assertEqual(translator.translate.await_args_list[1].kwargs["src"], "en")


class OcrTests(unittest.TestCase):
    def test_missing_uzbek_pack_falls_back_to_installed_english(self):
        image = io.BytesIO()
        Image.new("RGBA", (100, 50), "white").save(image, format="PNG")
        image.seek(0)
        with patch.object(extra_features, "configure_tesseract"), patch.dict(os.environ, {"OCR_LANGUAGES": "uzb+rus+eng"}), patch.object(extra_features.pytesseract, "get_languages", return_value=["eng", "osd"]), patch.object(extra_features.pytesseract, "image_to_string", return_value=" Hello ") as ocr:
            self.assertEqual(extra_features.ocr_image(image), "Hello")
        self.assertEqual(ocr.call_args.kwargs["lang"], "eng")
        self.assertEqual(ocr.call_args.kwargs["timeout"], 60)
        self.assertEqual(ocr.call_args.args[0].mode, "L")

    def test_missing_tesseract_gives_actionable_error(self):
        with patch.object(extra_features, "configure_tesseract"), patch.object(extra_features.pytesseract, "get_languages", side_effect=extra_features.pytesseract.TesseractNotFoundError()):
            with self.assertRaisesRegex(ValueError, "TESSERACT_CMD"):
                extra_features.ocr_image("unused.png")


class WebhookTests(unittest.TestCase):
    def test_persistent_application_initializes_once_and_enqueues_updates(self):
        application = SimpleNamespace(
            bot=Mock(), initialize=AsyncMock(), start=AsyncMock(),
            stop=AsyncMock(), shutdown=AsyncMock(),
            update_queue=SimpleNamespace(put=AsyncMock()),
        )
        app = create_app(application)
        try:
            with patch.dict(os.environ, {"WEBHOOK_SECRET": ""}):
                client = app.test_client()
                self.assertEqual(client.post("/webhook", json={}).status_code, 400)
                self.assertEqual(client.post("/webhook", json={"update_id": 1}).status_code, 200)
                self.assertEqual(client.post("/webhook", json={"update_id": 2}).status_code, 200)
            application.initialize.assert_awaited_once()
            application.start.assert_awaited_once()
            self.assertEqual(application.update_queue.put.await_count, 2)
            self.assertEqual(application.update_queue.put.await_args_list[1].args[0].update_id, 2)
        finally:
            app.extensions["telegram_shutdown"]()
        application.stop.assert_awaited_once()
        application.shutdown.assert_awaited_once()

    def test_configured_webhook_secret_rejects_other_requests(self):
        application = SimpleNamespace(bot=Mock())
        app = create_app(application)
        try:
            with patch.dict(os.environ, {"WEBHOOK_SECRET": "test-secret"}):
                self.assertEqual(app.test_client().post("/webhook", json={"update_id": 1}).status_code, 403)
        finally:
            app.extensions["telegram_shutdown"]()


if __name__ == "__main__":
    unittest.main()
