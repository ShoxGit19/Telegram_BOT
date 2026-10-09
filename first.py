import logging
import json
import datetime
import csv
import html
import io
import os
import re
import asyncio  # ✅ Qo‘shildi
import subprocess  # ✅ Qo‘shildi: git auto push uchun
import tempfile
import uuid
import time
import math
import threading
from pathlib import Path
from dotenv import load_dotenv
from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, MessageEntity, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, InlineQueryHandler, MessageHandler, filters, ContextTypes
from speech_recognition import RequestError, UnknownValueError
from telegram.error import TelegramError

# Qo‘shimcha imkoniyatlar va modullar
from extra_features import translate_text, translation_chunk_count, ocr_image, speech_to_text
from inline_handler import inlinequery
from lang_support import LANGUAGES, get_lang, set_lang
from request_guard import is_rate_limited
from user_store import USERS_FILE, register_user, save_user_contact
from transliteration_tools import (
    DIRECTIONS,
    add_dictionary_entry,
    get_user_dictionary,
    get_user_direction,
    remove_dictionary_entry,
    set_user_direction,
    transliteration_candidates,
    transliterate_for_user,
)

# ADMIN ID ni o'zgartiring (o'zingizning Telegram ID)
ADMIN_ID = 6954909676
logger = logging.getLogger("dastur_loglari")
MAX_TEXT_CHARS = 2000
MAX_TEXT_FILE_BYTES = 1_000_000
MAX_TEXT_FILE_CHARS = 100_000
MAX_AUDIO_FILE_BYTES = 20_000_000
PROGRESS_UPDATE_SECONDS = 1
MENU_ACTIONS = {
    "🔤 Lotin → Kiril": "latin_to_cyrillic",
    "🔠 Kiril → Lotin": "cyrillic_to_latin",
    "🌐 Tarjima": "translate",
    "🎙 Ovoz → matn": "voice",
    "🖼 Rasm → matn": "image",
    "📄 TXT fayl": "text_file",
    "🌐 TXT tarjima": "txt_translate",
    "↔ Yo'nalish": "direction_menu",
    "🌐 Til": "language_menu",
    "💬 Fikr": "feedback",
    "📚 Lug'at": "dictionary_list",
    "➕ Lug'at qo'shish": "dictionary_add",
    "➖ Lug'at o'chirish": "dictionary_remove",
    "📊 Statistika": "stats",
    "📤 Export": "export",
}


def main_menu_markup(is_admin=False):
    keyboard = [
        ["🔤 Lotin → Kiril", "🔠 Kiril → Lotin"],
        ["🌐 Tarjima", "🎙 Ovoz → matn"],
        ["🖼 Rasm → matn", "📄 TXT fayl"],
        ["🌐 TXT tarjima"],
        ["↔ Yo'nalish", "🌐 Til"],
        ["💬 Fikr", "📜 Tarix"],
        ["📚 Lug'at", "➕ Lug'at qo'shish"],
        ["➖ Lug'at o'chirish", "❔ Yordam"],
    ]
    if is_admin:
        keyboard.append(["📊 Statistika", "📤 Export"])
    keyboard.append(["🏠 Menyu"])
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Amalni tanlang yoki matn yuboring",
    )


async def show_main_menu(message, text="Kerakli amalni tanlang:"):
    sender = getattr(message, "from_user", None)
    is_admin = bool(sender and sender.id == ADMIN_ID)
    await message.reply_text(text, reply_markup=main_menu_markup(is_admin))


def clear_pending_actions(user_data):
    for key in ("selected_action", "awaiting_translation", "awaiting_feedback", "awaiting_dictionary_action", "txt_translate_target"):
        user_data.pop(key, None)


def resolve_txt_file_mode(user_data):
    target_lang = user_data.get("txt_translate_target")
    if target_lang in {"uz", "ru", "en"}:
        return {"mode": "translate", "target_lang": target_lang}
    return {"mode": "transliterate"}


class ProcessingProgress:
    def __init__(self, total_steps):
        self.total_steps = max(0, int(total_steps))
        self.completed_steps = 0
        self._lock = threading.Lock()

    def advance(self):
        with self._lock:
            self.completed_steps = min(self.total_steps, self.completed_steps + 1)

    def snapshot(self):
        with self._lock:
            return self.completed_steps, self.total_steps


def processing_status_text(status, elapsed, progress=None):
    elapsed = max(0, elapsed)
    lines = [status, f"O'tgan vaqt: {int(elapsed)} soniya"]
    if progress is not None:
        completed, total = progress.snapshot()
        if total:
            lines.append(f"Tayyor: {completed}/{total} bo'lak")
            if 0 < completed < total:
                remaining = max(1, math.ceil(elapsed / completed * (total - completed)))
                lines.append(f"Taxminan qolgan vaqt: {remaining} soniya")
            elif completed == total:
                lines.append("Natija yakunlanmoqda...")
    return "\n".join(lines)


async def run_with_countdown(message, operation, status="Tayyorlanmoqda", progress=None):
    # Keep the public helper name for callers, but time actual work, not a fixed countdown.
    started = time.monotonic()
    operation_task = asyncio.create_task(asyncio.to_thread(operation))
    progress_message = None
    progress_enabled = True
    try:
        while True:
            done, _ = await asyncio.wait({operation_task}, timeout=PROGRESS_UPDATE_SECONDS)
            if done:
                return operation_task.result()
            if not progress_enabled:
                continue
            text = processing_status_text(status, time.monotonic() - started, progress)
            try:
                if progress_message is None:
                    progress_message = await message.reply_text(text)
                else:
                    await progress_message.edit_text(text)
            except TelegramError:
                # A blocked edit or a deleted status message must not abort the operation.
                logger.debug("Progress xabarini yangilab bo'lmadi", exc_info=True)
                progress_enabled = False
    except asyncio.CancelledError:
        operation_task.cancel()
        raise
    finally:
        if progress_message is not None:
            try:
                await progress_message.delete()
            except TelegramError:
                logger.debug("Progress xabarini o'chirib bo'lmadi", exc_info=True)


# Start xabari
START_MESSAGE = (
    "👋 Assalomu alaykum!\n\n"
    "Quyidagi menyudan kerakli amalni tanlang. Bot keyingi yuborgan ma'lumotingizni shu amal bilan bajaradi.\n\n"
    "Oddiy matn yuborsangiz, saqlangan yo'nalish bo'yicha transliteratsiya qilinadi."
)

# ✅ Qo‘shildi: Ramazon broadcast xabari (HTML)
RAMAZON_MESSAGE = (
    "🌙 <b>Ramazon muborak!</b>\n\n"
    "Ramazoningiz barakali o‘tsin. 🤲\n"
    "Ibodatlarni qiynalmay ado etish nasib qilsin.\n"
    "Duolaringiz ijobat bo‘lsin! ✨\n\n"
    "Ramazon sabab ishlarimiz yanada rejali va intizomli bo‘lsin.\n\n"
    "🕌 <b>Ayyom muborak!</b>"
)

# ✅ Qo‘shildi: bir marta yuborilgani uchun flag
SENT_FLAGS_FILE = "data/sent_flags.json"
RAMAZON_FLAG_KEY = "ramazon_broadcast_sent_v1"
def git_auto_push():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Auto update data"], check=True)
        subprocess.run(["git", "push"], check=True)
    except Exception as e:
        logger.error(f"Git push xatolik: {e}")


# Helper functions
def remove_emojis(text):
    """
    Berilgan matndan emoji va boshqa ruxsat etilmagan belgilarni olib tashlaydi.
    (Soddalashtirilgan: lotin/raqam/underscore/bo'shliq va kiril harflaridan boshqa hamma belgilar o'chiriladi.)
    """
    if text is None:
        return ""
    return re.sub(r'[^\w\sА-Яа-яЁё]', '', text)

def contains_cyrillic(text):
    """
    Matnda kiril harflari borligini tekshiradi (emoji va ortiqcha belgilar olib tashlanganidan keyin).
    """
    clean = remove_emojis(text)
    return bool(re.search('[А-Яа-яЁё]', clean))


# ✅ Qo‘shildi: flaglarni yuklash/saqlash
def load_sent_flags():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(SENT_FLAGS_FILE):
        return {}
    try:
        with open(SENT_FLAGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_sent_flags(flags: dict):
    os.makedirs("data", exist_ok=True)
    with open(SENT_FLAGS_FILE, "w", encoding="utf-8") as f:
        json.dump(flags, f, indent=4, ensure_ascii=False)


# ✅ Qo‘shildi: bot ishga tushganda hamma eski userlarga yuborish
async def broadcast_ramazon_to_all_users(context: ContextTypes.DEFAULT_TYPE):
    """
    Bot ishga tushganda users.json dagi hamma userlarga Ramazon xabarini yuboradi.
    Takror yubormaslik uchun data/sent_flags.json da flag saqlaydi.
    """
    flags = load_sent_flags()
    if flags.get(RAMAZON_FLAG_KEY) is True:
        return  # avval yuborilgan bo'lsa, qayta yubormaydi

    # users.json o'qish
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except FileNotFoundError:
        users = {}
    except Exception as e:
        logger.error(f"users.json o'qishda xatolik: {e}")
        users = {}

    if not users:
        flags[RAMAZON_FLAG_KEY] = True
        save_sent_flags(flags)
        return

    success, failed = 0, 0
    for uid in users.keys():
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=RAMAZON_MESSAGE,
                parse_mode="HTML"
            )
            success += 1
            await asyncio.sleep(0.05)  # flood limitdan saqlanish uchun
        except Exception as e:
            failed += 1
            logger.warning(f"Broadcast yuborilmadi uid={uid}, xatolik={e}")

    flags[RAMAZON_FLAG_KEY] = True
    save_sent_flags(flags)

    logger.info(f"Ramazon broadcast yakunlandi. success={success}, failed={failed}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_pending_actions(context.user_data)
    context.user_data.pop("awaiting_feedback", None)
    try:
        await asyncio.to_thread(
            register_user, update.effective_user, update.effective_chat,
            bot_id=context.bot.id, bot_username=context.bot.username,
        )
    except Exception:
        logger.exception("Foydalanuvchi ma'lumotlarini saqlashda xatolik")
        await update.message.reply_text("Ma'lumotlaringizni saqlab bo'lmadi. Keyinroq /start ni qayta yuboring.")

    await show_main_menu(update.message, START_MESSAGE)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_pending_actions(context.user_data)
    await show_main_menu(update.message)

async def matn_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    input_text = update.message.text or ""

    if input_text in MENU_ACTIONS:
        action = MENU_ACTIONS[input_text]
        clear_pending_actions(context.user_data)
        if action == "direction_menu":
            context.user_data.pop("selected_action", None)
            await direction_command(update, context)
            return
        if action == "language_menu":
            context.user_data.pop("selected_action", None)
            await lang_command(update, context)
            return
        if action == "feedback":
            context.user_data.pop("selected_action", None)
            context.user_data["awaiting_feedback"] = True
            await update.message.reply_text("Fikr yoki taklifingizni keyingi xabarda yozing.", reply_markup=main_menu_markup(user.id == ADMIN_ID))
            return
        if action == "dictionary_list":
            context.user_data.pop("selected_action", None)
            await dictionary_list_command(update, context)
            return
        if action in ("dictionary_add", "dictionary_remove"):
            context.user_data.pop("selected_action", None)
            context.user_data["awaiting_dictionary_action"] = action
            if action == "dictionary_add":
                prompt = "Lotincha va kirillcha juftlikni yuboring. Namuna: Shaxzoda | Шахзода"
            else:
                prompt = "O'chiriladigan lotincha so'zni yuboring."
            await update.message.reply_text(prompt, reply_markup=main_menu_markup(user.id == ADMIN_ID))
            return
        if action == "stats":
            await stats(update, context)
            return
        if action == "export":
            await export_users(update, context)
            return
        context.user_data["selected_action"] = action
        if action == "txt_translate":
            await prompt_txt_translation_language(update.message, context)
            return
        if action == "text_file":
            context.user_data.pop("txt_translate_target", None)
            await prompt_txt_file_action(update, context)
            return
        prompts = {
            "latin_to_cyrillic": "Lotincha matnni yuboring. Men uni kirillga o'giraman.",
            "cyrillic_to_latin": "Kirillcha matnni yuboring. Men uni lotinga o'giraman.",
            "translate": "Tarjima qilinadigan matnni yuboring.",
            "voice": "Ovozli xabar yoki audio fayl yuboring.",
            "image": "Matni olinadigan rasmni yuboring.",
        }
        await update.message.reply_text(prompts[action], reply_markup=main_menu_markup(user.id == ADMIN_ID))
        return
    if input_text == "📜 Tarix":
        clear_pending_actions(context.user_data)
        await history(update, context)
        return
    if input_text == "❔ Yordam":
        clear_pending_actions(context.user_data)
        await help_command(update, context)
        return
    if input_text == "🏠 Menyu":
        clear_pending_actions(context.user_data)
        await show_main_menu(update.message)
        return
    if is_rate_limited(user.id, "chat", limit=8, window_seconds=10):
        await update.message.reply_text("So'rovlar juda tez kelyapti. 10 soniyadan keyin davom eting.")
        return
    if len(input_text) > MAX_TEXT_CHARS:
        await update.message.reply_text(f"Matn juda uzun. Eng ko'pi bilan {MAX_TEXT_CHARS} ta belgi yuboring.")
        return

    # Agar foydalanuvchi feedback yuborishi kutilayotgan bo'lsa, feedback sifatida saqlaymiz
    if context.user_data.get('awaiting_feedback'):
        feedback_text = input_text
        user_id = str(user.id)
        user_name = user.username or user.first_name or "Foydalanuvchi"
        try:
            os.makedirs('data', exist_ok=True)
            with open('feedbacks.csv', 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([user_id, user_name, feedback_text, datetime.datetime.now().isoformat()])
            context.user_data.pop('awaiting_feedback', None)
            await update.message.reply_text("Fikringiz qabul qilindi. Rahmat!")
        except Exception as e:
            logger.error(f"Feedback saqlashda xatolik: {e}")
            await update.message.reply_text("Fikrni saqlashda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")
        return

    dictionary_action = context.user_data.pop("awaiting_dictionary_action", None)
    if dictionary_action == "dictionary_add":
        if "|" not in input_text:
            await update.message.reply_text("Namuna format: Shaxzoda | Шахзода")
            context.user_data["awaiting_dictionary_action"] = dictionary_action
            return
        latin, cyrillic = input_text.split("|", maxsplit=1)
        try:
            add_dictionary_entry(user.id, latin, cyrillic)
            await update.message.reply_text("Lug'at qoidasi saqlandi.", reply_markup=main_menu_markup(user.id == ADMIN_ID))
        except ValueError as error:
            await update.message.reply_text(str(error))
            context.user_data["awaiting_dictionary_action"] = dictionary_action
        return
    if dictionary_action == "dictionary_remove":
        try:
            removed = remove_dictionary_entry(user.id, input_text)
            response = "Lug'at qoidasi o'chirildi." if removed else "Bu qoida lug'atingizda topilmadi."
            await update.message.reply_text(response, reply_markup=main_menu_markup(user.id == ADMIN_ID))
        except Exception:
            logger.exception("Shaxsiy lug'at qoidasini o'chirishda xatolik")
            await update.message.reply_text("Lug'at qoidasini o'chirib bo'lmadi.")
        return

    selected_action = context.user_data.get("selected_action")
    if selected_action == "voice":
        await update.message.reply_text("Ovozli xabar yoki audio fayl yuboring.", reply_markup=main_menu_markup())
        return
    if selected_action == "image":
        await update.message.reply_text("Rasm yuboring.", reply_markup=main_menu_markup())
        return
    if selected_action in {"text_file_choose", "text_file_language"}:
        await update.message.reply_text("Avval yuqoridagi tugmalardan amal va tarjima tilini tanlang.")
        return
    if selected_action == "text_file":
        await update.message.reply_text(".txt fayl yuboring.", reply_markup=main_menu_markup(update.effective_user.id == ADMIN_ID))
        return

    if context.user_data.pop("awaiting_translation", False) or selected_action == "translate":
        context.user_data.pop("selected_action", None)
        await send_translation_results(update.message, input_text, context.user_data)
        return

    kirilgan_matn = input_text
    user_name = user.username or user.first_name or "Foydalanuvchi"
    user_id = str(user.id)
    try:
        direction = selected_action if selected_action in {
            "latin_to_cyrillic",
            "cyrillic_to_latin",
        } else get_user_direction(user.id)
        if direction in {"latin_to_cyrillic", "cyrillic_to_latin"}:
            context.user_data.pop("selected_action", None)
        dictionary = get_user_dictionary(user.id)
        candidates = await run_with_countdown(
            update.message,
            lambda: transliteration_candidates(kirilgan_matn, direction, dictionary),
            status="Matn o'girilmoqda...",
        )
        javob = candidates[0]

        # Tarjima saqlash
        os.makedirs('data', exist_ok=True)
        with open('translations.csv', 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([user_id, kirilgan_matn, javob, datetime.datetime.now().isoformat()])

        # Monospaced format - HTML <pre>
        result_buttons = []
        if len(candidates) > 1:
            choices = context.user_data.setdefault("transliteration_choices", {})
            choice_id = uuid.uuid4().hex[:8]
            choices[choice_id] = candidates[1:]
            while len(choices) > 5:
                choices.pop(next(iter(choices)))
            result_buttons.extend(
                [InlineKeyboardButton(
                    f"Variant {index + 1}: {' '.join(candidate.split())[:40]}",
                    callback_data=f"translit:{choice_id}:{index}",
                )]
                for index, candidate in enumerate(candidates[1:])
            )
        await send_copyable_text(
            update.message, javob, context.user_data,
            label=f"{user_name}, natija:", extra_buttons=result_buttons,
        )
    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await update.message.reply_text("Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")


async def transliteration_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        _, choice_id, index_text = query.data.split(":", maxsplit=2)
        index = int(index_text)
        alternatives = context.user_data.get("transliteration_choices", {}).pop(choice_id, None)
        if alternatives is None or index < 0 or index >= len(alternatives):
            raise ValueError("Tanlov eskirgan")
    except (ValueError, TypeError):
        await query.answer("Bu variant eskirgan. Matnni qayta yuboring.", show_alert=True)
        return
    await query.answer("Variant tanlandi.")
    text = alternatives[index]
    await query.edit_message_text(
        f"<pre>{html.escape(text)}</pre>", parse_mode="HTML",
        reply_markup=copy_result_markup(text, context.user_data),
    )


def copy_result_markup(text, user_data, extra_buttons=None):
    buttons = list(extra_buttons or [])
    if not text:
        return InlineKeyboardMarkup(buttons) if buttons else None
    results = user_data.setdefault("copy_results", {})
    result_id = uuid.uuid4().hex[:12]
    results[result_id] = text
    while len(results) > 10:
        results.pop(next(iter(results)))
    if len(text.encode("utf-16-le")) // 2 <= 256:
        buttons.append([InlineKeyboardButton(
            "📋 Nusxa olish", copy_text=CopyTextButton(text=text),
        )])
    buttons.append([InlineKeyboardButton(
        "📄 Matnni olish" if len(text.encode("utf-16-le")) // 2 <= 256 else "📋 Nusxa olish",
        callback_data=f"copy:{result_id}",
    )])
    return InlineKeyboardMarkup(buttons)


def copy_chunks(text):
    chunk, size = [], 0
    for character in text:
        units = 2 if ord(character) > 0xFFFF else 1
        if size + units > 256:
            yield "".join(chunk)
            chunk, size = [], 0
        chunk.append(character)
        size += units
    if chunk:
        yield "".join(chunk)


async def send_copyable_text(message, text, user_data, label=None, extra_buttons=None):
    if not text.strip():
        await message.reply_text("Matn topilmadi. Aniqroq rasm yoki matn yuboring.")
        return
    if label:
        await message.reply_text(label)
    if len(text) > 12000:
        await message.reply_document(
            document=io.BytesIO(text.encode("utf-8")), filename="result.txt",
            caption="To'liq matn TXT faylda.",
        )
        text = text[:1800]
    for offset in range(0, len(text), 1800):
        part = text[offset:offset + 1800]
        await message.reply_text(
            f"<pre>{html.escape(part)}</pre>", parse_mode="HTML",
            reply_markup=copy_result_markup(
                part, user_data, extra_buttons if offset == 0 else None,
            ),
        )


async def copy_result_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    result_id = (query.data or "").partition(":")[2]
    text = context.user_data.get("copy_results", {}).get(result_id)
    if text is None:
        # The original Telegram message survives restarts and cache eviction.
        parse_entities = getattr(query.message, "parse_entities", None)
        if callable(parse_entities):
            entities = parse_entities(types=[MessageEntity.PRE, MessageEntity.CODE])
            text = "\n".join(entities.values()) or None
    if text is None:
        await query.answer("Bu xabarda nusxalanadigan matn topilmadi. Matnni qayta yuboring.", show_alert=True)
        return
    await query.answer()
    await query.message.reply_text(
        "Quyidagi matnni bosib ushlab nusxalang yoki har bir bo'lakdagi Nusxa olish tugmasini bosing."
    )
    for part in copy_chunks(text):
        await query.message.reply_text(
            f"<pre>{html.escape(part)}</pre>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "📋 Nusxa olish", copy_text=CopyTextButton(text=part),
            )]]),
        )


async def prompt_txt_file_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["selected_action"] = "text_file_choose"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔤 Transliteratsiya", callback_data="txt_action:transliterate")],
        [InlineKeyboardButton("🌐 TXT tarjima", callback_data="txt_action:translate")],
    ])
    await update.message.reply_text("TXT fayl uchun amalni tanlang:", reply_markup=keyboard)


def txt_translation_language_markup():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇺🇿 UZ", callback_data="txt_action:translate:uz"),
        InlineKeyboardButton("🇷🇺 RU", callback_data="txt_action:translate:ru"),
        InlineKeyboardButton("🇬🇧 EN", callback_data="txt_action:translate:en"),
    ]])


async def prompt_txt_translation_language(message, context, edit=False):
    context.user_data["selected_action"] = "text_file_language"
    context.user_data.pop("txt_translate_target", None)
    respond = message.edit_text if edit else message.reply_text
    await respond(
        "TXT faylni qaysi tilga tarjima qilay: UZ, RU yoki EN?",
        reply_markup=txt_translation_language_markup(),
    )


async def txt_file_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    if data == "txt_action:translate":
        clear_pending_actions(context.user_data)
        await query.answer()
        await prompt_txt_translation_language(query.message, context, edit=True)
        return
    if data in {"txt_action:translate:uz", "txt_action:translate:ru", "txt_action:translate:en"}:
        target_lang = data.rsplit(":", 1)[1]
        clear_pending_actions(context.user_data)
        context.user_data["selected_action"] = "text_file"
        context.user_data["txt_translate_target"] = target_lang
        await query.answer(f"Tanlandi: {target_lang.upper()}")
        await query.edit_message_text(
            f"TXT faylni yuboring. Uni {target_lang.upper()} tiliga tarjima qilib, .txt fayl qaytaraman."
        )
        return
    if data != "txt_action:transliterate":
        await query.answer("Noto'g'ri amal yoki til.", show_alert=True)
        return
    clear_pending_actions(context.user_data)
    context.user_data["selected_action"] = "text_file"
    await query.answer("Transliteratsiya tanlandi.")
    await query.edit_message_text("TXT faylni yuboring. Men uni lotin/kirilga o'girib, .txt fayl qaytaraman.")


async def txt_translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_pending_actions(context.user_data)
    await prompt_txt_translation_language(update.message, context)


async def txt_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    selected_action = context.user_data.get("selected_action")
    is_image_document = bool(
        (document.mime_type and document.mime_type.startswith("image/"))
        or Path(document.file_name or "").suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    )
    if is_image_document and selected_action in (None, "image"):
        await ocr_command(update, context)
        return
    if selected_action in {"text_file_choose", "text_file_language"}:
        await update.message.reply_text("Avval TXT amalini va tarjima tilini tanlang, keyin faylni yuboring.")
        return
    if selected_action not in (None, "text_file"):
        prompts = {
            "voice": "Tanlangan amal ovozdan matn olish. Ovozli xabar yuboring.",
            "translate": "Tarjima uchun oddiy matn yuboring.",
            "latin_to_cyrillic": "Lotincha matn yuboring.",
            "cyrillic_to_latin": "Kirillcha matn yuboring.",
        }
        await update.message.reply_text(prompts.get(selected_action, "Tanlangan amal uchun kerakli ma'lumotni yuboring."), reply_markup=main_menu_markup())
        return
    if is_rate_limited(update.effective_user.id, "file", limit=3, window_seconds=60):
        await update.message.reply_text("Fayllar juda tez yuborildi. Bir daqiqadan keyin qayta urinib ko'ring.")
        return
    filename = document.file_name or ""
    if not filename.lower().endswith(".txt"):
        await update.message.reply_text("Faqat .txt fayl yuboring.")
        return
    if document.file_size is not None and document.file_size > MAX_TEXT_FILE_BYTES:
        await update.message.reply_text("Fayl hajmi 1 MB dan oshmasligi kerak.")
        return
    try:
        telegram_file = await document.get_file()
        with tempfile.TemporaryDirectory(prefix="telegram_translit_") as temporary_directory:
            source_path = Path(temporary_directory) / "source.txt"
            result_path = Path(temporary_directory) / "processed.txt"
            await telegram_file.download_to_drive(custom_path=source_path)
            if source_path.stat().st_size > MAX_TEXT_FILE_BYTES:
                await update.message.reply_text("Fayl hajmi 1 MB dan oshmasligi kerak.")
                return
            source_text = source_path.read_bytes().decode("utf-8-sig")
            if len(source_text) > MAX_TEXT_FILE_CHARS:
                await update.message.reply_text("Faylda eng ko'pi bilan 100 000 ta belgi bo'lishi mumkin.")
                return

            if not source_text.strip():
                await update.message.reply_text("TXT fayl bo'sh. Matnli fayl yuboring.")
                return
            mode = resolve_txt_file_mode(context.user_data)
            if mode["mode"] == "translate":
                target_lang = mode["target_lang"]
                progress = ProcessingProgress(translation_chunk_count(source_text))
                result_text = await run_with_countdown(
                    update.message,
                    lambda: asyncio.run(translate_text(source_text, src="auto", dest=target_lang, on_progress=progress.advance)),
                    status=f"TXT {target_lang.upper()} tiliga tarjima qilinmoqda...",
                    progress=progress,
                )
                filename_output = f"translated_{target_lang}.txt"
                caption = f"Tarjima ({target_lang.upper()}) tayyor."
            else:
                user_id = update.effective_user.id
                result_text = transliterate_for_user(
                    source_text,
                    get_user_direction(user_id),
                    get_user_dictionary(user_id),
                )
                filename_output = "transliterated.txt"
                caption = "Transliteratsiya tayyor."

            result_path.write_bytes(result_text.encode("utf-8"))
            with result_path.open("rb") as result_file:
                await update.message.reply_document(
                    document=result_file,
                    filename=filename_output,
                    caption=caption,
                )
        context.user_data.pop("selected_action", None)
        context.user_data.pop("txt_translate_target", None)
    except UnicodeDecodeError:
        await update.message.reply_text("Fayl UTF-8 matn formatida bo'lishi kerak.")
    except Exception:
        logger.exception("TXT faylni qayta ishlashda xatolik")
        await update.message.reply_text("Faylni qayta ishlashda xatolik yuz berdi.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        LANGUAGES[get_lang(context.user_data)]['help'] +
        "\n\n📌 Buyruqlar:\n"
        "/start — Boshlash\n"
        "/menu — Asosiy menyuni ochish\n"
        "/history — Oxirgi tarjimalar\n"
        "/feedback — Fikr bildirish\n"
        "/help — Yordam\n"
        "/translate — Tarjima (EN/RU ↔ UZ)\n"
        "/ocr — Rasm matnini tanib olish\n"
        "/stt — Audio matnini tanib olish\n"
        "/lang — Tilni o‘zgartirish\n"
        "/direction — Transliteratsiya yo‘nalishini tanlash\n"
        "/dict_add Lotin | Кирилл — Shaxsiy lug'atga qoida qo'shish\n"
        "/dict_list — Shaxsiy lug'atni ko'rish\n"
        "/dict_remove Lotin — Lug'at qoidasini o'chirish\n"
        "\n✍️ Istalgan matn yuboring — bot avtomatik aylantirib beradi."
    )


async def direction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("↔ Avto", callback_data="direction:auto"),
            InlineKeyboardButton("A → К", callback_data="direction:latin_to_cyrillic"),
            InlineKeyboardButton("К → A", callback_data="direction:cyrillic_to_latin"),
        ],
    ])
    await update.message.reply_text("Transliteratsiya yo'nalishini tanlang:", reply_markup=keyboard)


async def direction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    direction = query.data.partition(":")[2]
    if direction not in DIRECTIONS:
        await query.answer("Noto'g'ri yo'nalish.", show_alert=True)
        return
    try:
        set_user_direction(query.from_user.id, direction)
    except Exception:
        logger.exception("Transliteratsiya yo'nalishini saqlashda xatolik")
        await query.answer("Yo'nalishni saqlab bo'lmadi.", show_alert=True)
        return
    labels = {
        "auto": "Avtomatik aniqlash",
        "latin_to_cyrillic": "Lotin → Kiril",
        "cyrillic_to_latin": "Kiril → Lotin",
    }
    await query.answer("Yo'nalish saqlandi.")
    await query.edit_message_text(f"Tanlangan yo'nalish: {labels[direction]}")


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = query.data.partition(":")[2]
    if lang not in LANGUAGES:
        await query.answer("Noto'g'ri til.", show_alert=True)
        return
    set_lang(context.user_data, lang)
    await query.answer("Til saqlandi.")
    await query.edit_message_text(LANGUAGES[lang]['start'])


async def dictionary_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = " ".join(context.args)
    if "|" not in value:
        await update.message.reply_text("Namuna: /dict_add Shaxzoda | Шахзода")
        return
    latin, cyrillic = value.split("|", maxsplit=1)
    try:
        add_dictionary_entry(update.effective_user.id, latin, cyrillic)
        await update.message.reply_text("Qoida saqlandi va ikki yo'nalishda ham ishlaydi.")
    except ValueError as error:
        await update.message.reply_text(str(error))
    except Exception:
        logger.exception("Shaxsiy lug'atni saqlashda xatolik")
        await update.message.reply_text("Lug'at qoidasini saqlab bo'lmadi.")


async def dictionary_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        entries = get_user_dictionary(update.effective_user.id)
    except Exception:
        logger.exception("Shaxsiy lug'atni o'qishda xatolik")
        await update.message.reply_text("Lug'atni o'qib bo'lmadi.")
        return
    if not entries:
        await update.message.reply_text("Shaxsiy lug'atingiz hozircha bo'sh.")
        return
    lines = [f"{latin} → {cyrillic}" for latin, cyrillic in list(entries.items())[:20]]
    remaining = len(entries) - len(lines)
    if remaining:
        lines.append(f"... va yana {remaining} ta qoida")
    await update.message.reply_text("Shaxsiy lug'atingiz:\n" + "\n".join(lines))


async def dictionary_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    latin = " ".join(context.args).strip()
    if not latin:
        await update.message.reply_text("O'chirish uchun lotincha so'zni yozing: /dict_remove Shaxzoda")
        return
    try:
        removed = remove_dictionary_entry(update.effective_user.id, latin)
    except Exception:
        logger.exception("Shaxsiy lug'at qoidasini o'chirishda xatolik")
        await update.message.reply_text("Lug'at qoidasini o'chirib bo'lmadi.")
        return
    if removed:
        await update.message.reply_text("Qoida o'chirildi.")
    else:
        await update.message.reply_text("Bunday qoida lug'atingizda topilmadi.")

# --- Tarjima qo‘shimcha imkoniyati ---
async def _translate_all_languages(text, progress=None):
    translations = []
    for language in ("uz", "ru", "en"):
        translations.append(await translate_text(
            text, dest=language, on_progress=progress.advance if progress is not None else None,
        ))
    return translations


async def send_translation_results(message, text, user_data=None):
    try:
        progress = ProcessingProgress(translation_chunk_count(text) * 3)
        translations = await run_with_countdown(
            message,
            lambda: asyncio.run(_translate_all_languages(text, progress)),
            status="Tarjima qilinmoqda...",
            progress=progress,
        )
        for label, translated in zip(("UZ", "RU", "EN"), translations):
            await send_copyable_text(message, translated, user_data if user_data is not None else {}, label=f"{label}:")
    except Exception:
        logger.exception("Tarjima qilishda xatolik")
        await message.reply_text("Tarjima xatoligi yuz berdi. Keyinroq qayta urinib ko'ring.")


async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        clear_pending_actions(context.user_data)
        context.user_data["selected_action"] = "translate"
        context.user_data["awaiting_translation"] = True
        await update.message.reply_text(
            "Tarjima qilinadigan matnni yuboring.",
            reply_markup=main_menu_markup(),
        )
        return
    text = ' '.join(args)
    clear_pending_actions(context.user_data)
    await send_translation_results(update.message, text, context.user_data)

# --- OCR qo‘shimcha imkoniyati ---
async def ocr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    photos = update.message.photo
    selected_action = context.user_data.get("selected_action")
    if selected_action not in (None, "image"):
        await update.message.reply_text("Tanlangan amal uchun mos ma'lumot yuboring yoki menyudan boshqa amalni tanlang.", reply_markup=main_menu_markup())
        return
    if not document and not photos:
        context.user_data["selected_action"] = "image"
        await update.message.reply_text("Matni olinadigan rasmni yuboring.", reply_markup=main_menu_markup(update.effective_user.id == ADMIN_ID))
        return
    try:
        image_file = document if document else photos[-1]
        if document and document.mime_type and not document.mime_type.startswith("image/") and Path(document.file_name or "").suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            await update.message.reply_text("Faqat rasm faylini yuboring.")
            return
        if image_file.file_size is not None and image_file.file_size > MAX_AUDIO_FILE_BYTES:
            await update.message.reply_text("Rasm hajmi 20 MB dan oshmasligi kerak.")
            return
        telegram_file = await image_file.get_file()
        with tempfile.TemporaryDirectory(prefix="telegram_ocr_") as temporary_directory:
            file_path = Path(temporary_directory) / "image-upload"
            await telegram_file.download_to_drive(custom_path=file_path)
            if file_path.stat().st_size > MAX_AUDIO_FILE_BYTES:
                await update.message.reply_text("Rasm hajmi 20 MB dan oshmasligi kerak.")
                return
            text = await run_with_countdown(
                update.message,
                lambda: ocr_image(str(file_path)),
                status="Rasmdagi matn aniqlanmoqda...",
            )
        await send_copyable_text(update.message, text, context.user_data, label="Rasmdan olingan matn:")
        context.user_data.pop("selected_action", None)
    except ValueError as error:
        await update.message.reply_text(str(error))
    except Exception:
        logger.exception("OCR faylni qayta ishlashda xatolik")
        await update.message.reply_text("Rasmni o'qib bo'lmadi. Rasm formati va Tesseract o'rnatilganini tekshiring.")

# --- STT qo‘shimcha imkoniyati ---
async def stt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_action = context.user_data.get("selected_action")
    if selected_action not in (None, "voice"):
        await update.message.reply_text("Tanlangan amal uchun mos ma'lumot yuboring yoki menyudan boshqa amalni tanlang.", reply_markup=main_menu_markup())
        return
    if not update.message.voice and not update.message.audio:
        context.user_data["selected_action"] = "voice"
        await update.message.reply_text("Ovozli xabar yoki audio fayl yuboring.", reply_markup=main_menu_markup(update.effective_user.id == ADMIN_ID))
        return
    audio = update.message.voice or update.message.audio
    if audio.file_size is not None and audio.file_size > MAX_AUDIO_FILE_BYTES:
        await update.message.reply_text("Audio hajmi 20 MB dan oshmasligi kerak.")
        return
    if is_rate_limited(update.effective_user.id, "audio", limit=3, window_seconds=60):
        await update.message.reply_text("Audio juda ko'p yuborildi. Bir daqiqadan keyin qayta urinib ko'ring.")
        return

    try:
        telegram_file = await audio.get_file()
        with tempfile.TemporaryDirectory(prefix="telegram_stt_") as temporary_directory:
            file_path = Path(temporary_directory) / "incoming-audio.ogg"
            await telegram_file.download_to_drive(custom_path=file_path)
            if file_path.stat().st_size > MAX_AUDIO_FILE_BYTES:
                await update.message.reply_text("Audio hajmi 20 MB dan oshmasligi kerak.")
                return
            text = await run_with_countdown(
                update.message,
                lambda: speech_to_text(str(file_path), lang="uz-UZ"),
                status="Ovoz matnga aylantirilmoqda...",
            )
        if not text.strip():
            await update.message.reply_text("Audiodan matn aniqlanmadi.")
            context.user_data.pop("selected_action", None)
            return
        await send_copyable_text(update.message, text, context.user_data, label="Audio matni:")
        context.user_data.pop("selected_action", None)
    except UnknownValueError:
        await update.message.reply_text("Audiodagi nutqni aniqlay olmadim. Iltimos, aniqroq yozuv yuboring.")
    except RequestError:
        await update.message.reply_text("Nutqni aniqlash xizmati hozir ishlamayapti. Keyinroq urinib ko'ring.")
    except ValueError as error:
        await update.message.reply_text(str(error))
    except Exception:
        logger.exception("Audio matnga aylantirishda xatolik")
        await update.message.reply_text("Audioni qayta ishlashda xatolik yuz berdi.")

# --- Tilni o‘zgartirish ---
async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="language:uz"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="language:ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="language:en"),
    ]])
    await update.message.reply_text(
        LANGUAGES[get_lang(context.user_data)]['choose_lang'],
        reply_markup=keyboard,
    )

async def lang_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = update.message.text.lower()
    if lang in LANGUAGES:
        set_lang(context.user_data, lang)
        await update.message.reply_text(LANGUAGES[lang]['start'])
    else:
        await update.message.reply_text("Noto‘g‘ri til tanlandi.")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        return
    if contact.user_id != update.effective_user.id:
        await update.message.reply_text("Faqat o'zingizning kontaktingizni yuboring.")
        return
    try:
        saved = await asyncio.to_thread(save_user_contact, update.effective_user.id, contact)
        if saved:
            await update.message.reply_text("Kontakt saqlandi. Rahmat!")
        else:
            await update.message.reply_text("Avval /start ni bosing, keyin kontaktingizni yuboring.")
    except Exception:
        logger.exception("Kontakt saqlashda xatolik")
        await update.message.reply_text("Kontaktni saqlab bo'lmadi. Keyinroq qayta urinib ko'ring.")

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin uchun: users.csv, feedbacks.csv va users_with_feedbacks.csv ni yuboradi.
    users_with_feedbacks.csv har bir feedback uchun bitta qator beradi, unda
    user ma'lumotlari (phone va hokazo) ham bo'ladi.
    """
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return

    # Yuklash va tayyorlash
    try:
        # users.json o'qish
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
        except FileNotFoundError:
            users = {}

        # feedbacks.csv o'qish
        feedbacks = []
        if os.path.exists('feedbacks.csv'):
            with open('feedbacks.csv', 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    # format: [user_id, user_name, feedback_text, ts]
                    if len(row) >= 4:
                        feedbacks.append({
                            'user_id': row[0],
                            'user_name': row[1],
                            'feedback_text': row[2],
                            'ts': row[3]
                        })

        # translations.csv ham kerak bo'lsa, uni alohida yuborish
        translations_exist = os.path.exists('translations.csv')

        # Prepare users.csv
        users_buf = io.StringIO()
        users_writer = csv.writer(users_buf)
        users_writer.writerow(['User ID', 'First Name', 'Last Name', 'Username', 'Phone', 'First Start'])
        for uid, data in users.items():
            users_writer.writerow([
                uid,
                data.get('first_name', ''),
                data.get('last_name', ''),
                data.get('username', ''),
                data.get('phone', ''),
                data.get('first_start', '')
            ])
        users_buf.seek(0)

        # Prepare feedbacks.csv (if mavjud bo'lsa, shunchaki yuborish)
        feedbacks_buf = io.StringIO()
        feedbacks_writer = csv.writer(feedbacks_buf)
        feedbacks_writer.writerow(['User ID', 'User Name', 'Feedback', 'Timestamp'])
        for fdb in feedbacks:
            feedbacks_writer.writerow([fdb['user_id'], fdb['user_name'], fdb['feedback_text'], fdb['ts']])
        feedbacks_buf.seek(0)

        # Prepare merged users_with_feedbacks.csv
        merged_buf = io.StringIO()
        merged_writer = csv.writer(merged_buf)
        merged_writer.writerow([
            'User ID', 'First Name', 'Last Name', 'Username', 'Phone', 'First Start',
            'Feedback', 'Feedback Timestamp'
        ])
        # Agar feedbacklar mavjud bo'lsa, har bir feedback uchun user ma'lumotini yozamiz
        if feedbacks:
            for fdb in feedbacks:
                uid = fdb['user_id']
                u = users.get(uid, {})
                merged_writer.writerow([
                    uid,
                    u.get('first_name', ''),
                    u.get('last_name', ''),
                    u.get('username', ''),
                    u.get('phone', ''),
                    u.get('first_start', ''),
                    fdb['feedback_text'],
                    fdb['ts']
                ])
        else:
            # feedback bo'lmasa, users ni bo'sh feedback bilan yozamiz (shu bilan admin uchun hamma users ko'rinadi)
            for uid, u in users.items():
                merged_writer.writerow([
                    uid,
                    u.get('first_name', ''),
                    u.get('last_name', ''),
                    u.get('username', ''),
                    u.get('phone', ''),
                    u.get('first_start', ''),
                    '',
                    ''
                ])
        merged_buf.seek(0)

        # Yuborish: bir nechta fayl birma-bir yuboriladi
        await update.message.reply_document(document=users_buf, filename='users.csv', caption="Foydalanuvchilar ro'yxati")
        await update.message.reply_document(document=feedbacks_buf, filename='feedbacks.csv', caption="Fikrlar ro'yxati")
        await update.message.reply_document(document=merged_buf, filename='users_with_feedbacks.csv', caption="Foydalanuvchilar va ularning feedbacklari (birlashtirilgan)")

        # Agar translations.csv mavjud bo'lsa, uni ham yuboramiz
        if translations_exist:
            with open('translations.csv', 'rb') as tf:
                await update.message.reply_document(document=tf, filename='translations.csv', caption="Tarjimalar (raw)")
    except Exception as e:
        logger.error(f"Export xatolik: {e}")
        await update.message.reply_text("Export qilishda xatolik yuz berdi.")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    try:
        with open('translations.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = [r for r in reader if len(r) >= 4 and r[0] == user_id]
        if not rows:
            await update.message.reply_text("Sizning tarjimalaringiz topilmadi.")
            return
        last = rows[-10:]
        lines = []
        for r in last:
            ts = r[3] if len(r) > 3 else ''
            orig = r[1] if len(r) > 1 else ''
            trans = r[2] if len(r) > 2 else ''
            lines.append(f"[{ts}] {orig} -> {trans}")
        await update.message.reply_text("Sizning oxirgi tarjimalaringiz:\n\n" + "\n".join(lines))
    except FileNotFoundError:
        await update.message.reply_text("Hech qanday tarjima topilmadi.")
    except Exception as e:
        logger.error(f"History o'qishda xatolik: {e}")
        await update.message.reply_text("Tarixni olishda xatolik yuz berdi.")

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_pending_actions(context.user_data)
    context.user_data['awaiting_feedback'] = True
    await update.message.reply_text("Iltimos, fikringizni yozing. Yozganingiz keyingi xabarda saqlanadi.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return
    try:
        users_count = 0
        translations_count = 0
        feedbacks_count = 0
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
            users_count = len(users)
        except FileNotFoundError:
            users_count = 0
        try:
            with open('translations.csv', 'r', encoding='utf-8') as f:
                translations_count = sum(1 for _ in f)
        except FileNotFoundError:
            translations_count = 0
        try:
            with open('feedbacks.csv', 'r', encoding='utf-8') as f:
                feedbacks_count = sum(1 for _ in f)
        except FileNotFoundError:
            feedbacks_count = 0

        text = (
            f"📊 Statistikalar:\n\n"
            f"Foydalanuvchilar soni: {users_count}\n"
            f"Umumiy tarjimalar soni: {translations_count}\n"
            f"Fikrlar soni: {feedbacks_count}\n"
            f"Oxirgi yangilanish: {datetime.datetime.now().isoformat()}"
        )
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Stats xatolik: {e}")
        await update.message.reply_text("Statistikani olishda xatolik yuz berdi.")


def build_application(token=None):
    load_dotenv(Path(__file__).resolve().parent / ".env")
    token = token or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN .env faylida sozlanmagan")
    app = ApplicationBuilder().token(token).build()
    # Commandlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("feedback", feedback_start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("export", export_users))

    # Qo‘shimcha imkoniyatlar
    app.add_handler(CommandHandler("translate", translate_command))
    app.add_handler(CommandHandler("txt_translate", txt_translate_command))
    app.add_handler(CommandHandler("ocr", ocr_command))
    app.add_handler(CommandHandler("stt", stt_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("direction", direction_command))
    app.add_handler(CommandHandler("dict_add", dictionary_add_command))
    app.add_handler(CommandHandler("dict_list", dictionary_list_command))
    app.add_handler(CommandHandler("dict_remove", dictionary_remove_command))
    app.add_handler(CallbackQueryHandler(direction_callback, pattern=r"^direction:"))
    app.add_handler(CallbackQueryHandler(language_callback, pattern=r"^language:"))
    app.add_handler(CallbackQueryHandler(copy_result_callback, pattern=r"^copy:"))
    app.add_handler(CallbackQueryHandler(txt_file_action_callback, pattern=r"^txt_action:"))
    app.add_handler(CallbackQueryHandler(transliteration_choice_callback, pattern=r"^translit:"))

    # Contact va matn handlerlari
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, stt_command))
    app.add_handler(MessageHandler(filters.PHOTO, ocr_command))
    app.add_handler(MessageHandler(filters.Document.ALL, txt_file_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, matn_olish))

    # Inline mode
    app.add_handler(InlineQueryHandler(inlinequery))

    return app


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = build_application()
    if os.getenv("WEBHOOK_MODE") == "1":
        from webhook_server import create_app
        create_app(app).run(host="0.0.0.0", port=int(os.getenv("PORT", "8443")))
    else:
        app.run_polling()
