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
from pathlib import Path
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes

# Qo‘shimcha imkoniyatlar va modullar
from extra_features import translate_text, ocr_image, speech_to_text
from inline_handler import inlinequery
from lang_support import LANGUAGES, get_lang, set_lang
from request_guard import is_rate_limited
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

try:
    from flask import Flask, request
except ImportError:
    Flask = None
    request = None

# ADMIN ID ni o'zgartiring (o'zingizning Telegram ID)
ADMIN_ID = 6954909676
MAX_TEXT_CHARS = 2000
MAX_TEXT_FILE_BYTES = 1_000_000
MAX_TEXT_FILE_CHARS = 100_000

# Start xabari
START_MESSAGE = (
    "👋 Assalomu alaykum!\n\n"
    "Bu Telegram bot lotin va kiril alifbolari o‘rtasida tezkor transliteratsiya qiladi.\n\n"
    "✍️ Istalgan matn yuboring — bot avtomatik tarzda aylantirib beradi.\n\n"
    "📌 Imkoniyatlar:\n"
    "• Lotin ↔ Kiril tarjima\n"
    "• /history — oxirgi yuborgan tarjimalaringizni ko‘rish\n"
    "• /feedback — bot haqida fikr yoki taklif yuborish\n"
    "• Tezkor va bepul foydalanish\n\n"
    "🚀 Dasturchi: @gaybullayeev19"
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
        with open("users.json", "r", encoding="utf-8") as f:
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
    user = update.effective_user
    user_id = str(user.id)
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
    except FileNotFoundError:
        users = {}

    if user_id not in users:
        users[user_id] = {
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'username': user.username or '',
            'phone': '',
            'first_start': datetime.datetime.now().isoformat()
        }
        with open('users.json', 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4, ensure_ascii=False)

    await update.message.reply_text(START_MESSAGE)

async def matn_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    input_text = update.message.text or ""
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

    kirilgan_matn = input_text
    user_name = user.username or user.first_name or "Foydalanuvchi"
    user_id = str(user.id)
    try:
        direction = get_user_direction(user.id)
        dictionary = get_user_dictionary(user.id)
        candidates = transliteration_candidates(kirilgan_matn, direction, dictionary)
        javob = candidates[0]

        # Tarjima saqlash
        os.makedirs('data', exist_ok=True)
        with open('translations.csv', 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([user_id, kirilgan_matn, javob, datetime.datetime.now().isoformat()])

        # Monospaced format - HTML <pre>
        reply_markup = None
        if len(candidates) > 1:
            choices = context.user_data.setdefault("transliteration_choices", {})
            choice_id = uuid.uuid4().hex[:8]
            choices[choice_id] = candidates[1:]
            while len(choices) > 5:
                choices.pop(next(iter(choices)))
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"Variant {index + 1}: {' '.join(candidate.split())[:40]}",
                    callback_data=f"translit:{choice_id}:{index}",
                )]
                for index, candidate in enumerate(candidates[1:])
            ])
        prompt = "Boshqa variantni tanlang:" if reply_markup else "Yana so'z kiriting."
        await update.message.reply_text(
            f"{html.escape(user_name)} siz kiritgan so'z:\n<pre>{html.escape(javob)}</pre>\n{prompt}",
            parse_mode='HTML',
            reply_markup=reply_markup,
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
    await query.edit_message_text(f"<pre>{html.escape(alternatives[index])}</pre>", parse_mode="HTML")


async def txt_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
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
            result_path = Path(temporary_directory) / "transliterated.txt"
            await telegram_file.download_to_drive(custom_path=source_path)
            if source_path.stat().st_size > MAX_TEXT_FILE_BYTES:
                await update.message.reply_text("Fayl hajmi 1 MB dan oshmasligi kerak.")
                return
            source_text = source_path.read_text(encoding="utf-8-sig")
            if len(source_text) > MAX_TEXT_FILE_CHARS:
                await update.message.reply_text("Faylda eng ko'pi bilan 100 000 ta belgi bo'lishi mumkin.")
                return

            user_id = update.effective_user.id
            result_text = transliterate_for_user(
                source_text,
                get_user_direction(user_id),
                get_user_dictionary(user_id),
            )
            result_path.write_text(result_text, encoding="utf-8")
            with result_path.open("rb") as result_file:
                await update.message.reply_document(
                    document=result_file,
                    filename="transliterated.txt",
                    caption="Transliteratsiya tayyor.",
                )
    except UnicodeDecodeError:
        await update.message.reply_text("Fayl UTF-8 matn formatida bo'lishi kerak.")
    except Exception:
        logger.exception("TXT faylni transliteratsiya qilishda xatolik")
        await update.message.reply_text("Faylni qayta ishlashda xatolik yuz berdi.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        LANGUAGES[get_lang(context.user_data)]['help'] +
        "\n\n📌 Buyruqlar:\n"
        "/start — Boshlash\n"
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
        [InlineKeyboardButton("Avtomatik", callback_data="direction:auto")],
        [InlineKeyboardButton("Lotin → Kiril", callback_data="direction:latin_to_cyrillic")],
        [InlineKeyboardButton("Kiril → Lotin", callback_data="direction:cyrillic_to_latin")],
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
async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Tarjima uchun matn yuboring: /translate <matn>")
        return
    text = ' '.join(args)
    try:
        # EN/RU -> UZ
        translated = translate_text(text, dest='uz')
        await update.message.reply_text(f"UZ: {translated}")
        # UZ -> RU
        translated_ru = translate_text(text, dest='ru')
        await update.message.reply_text(f"RU: {translated_ru}")
        # UZ -> EN
        translated_en = translate_text(text, dest='en')
        await update.message.reply_text(f"EN: {translated_en}")
    except Exception as e:
        await update.message.reply_text(f"Tarjima xatoligi: {e}")

# --- OCR qo‘shimcha imkoniyati ---
async def ocr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("Rasm yuboring yoki /ocr buyrug‘ini rasm bilan birga yuboring.")
        return
    file = await update.message.document.get_file()
    file_path = f"temp_{update.message.document.file_name}"
    await file.download_to_drive(file_path)
    try:
        text = ocr_image(file_path)
        await update.message.reply_text(f"Rasmdan matn: {text}")
    except Exception as e:
        await update.message.reply_text(f"OCR xatoligi: {e}")
    finally:
        os.remove(file_path)

# --- STT qo‘shimcha imkoniyati ---
async def stt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.voice and not update.message.audio:
        await update.message.reply_text("Audio yuboring yoki /stt buyrug‘ini audio bilan birga yuboring.")
        return
    audio = update.message.voice or update.message.audio
    file = await audio.get_file()
    file_path = f"temp_{audio.file_id}.ogg"
    await file.download_to_drive(file_path)
    try:
        text = speech_to_text(file_path)
        await update.message.reply_text(f"Audio matni: {text}")
    except Exception as e:
        await update.message.reply_text(f"STT xatoligi: {e}")
    finally:
        os.remove(file_path)

# --- Tilni o‘zgartirish ---
from telegram import ReplyKeyboardMarkup
async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["uz", "ru", "en"]]
    await update.message.reply_text(
        LANGUAGES['uz']['choose_lang'],
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
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
    user_id = str(update.effective_user.id)
    if contact and contact.user_id == update.effective_user.id:
        try:
            try:
                with open('users.json', 'r', encoding='utf-8') as f:
                    users = json.load(f)
            except FileNotFoundError:
                users = {}
            if user_id in users:
                users[user_id]['phone'] = contact.phone_number
                with open('users.json', 'w', encoding='utf-8') as f:
                    json.dump(users, f, indent=4, ensure_ascii=False)
            await update.message.reply_text("Kontakt saqlandi. Rahmat!")
        except Exception as e:
            logger.error(f"Kontakt saqlashda xatolik: {e}")
            await update.message.reply_text("Xatolik yuz berdi.")

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
            with open('users.json', 'r', encoding='utf-8') as f:
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
            with open('users.json', 'r', encoding='utf-8') as f:
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


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    logger = logging.getLogger("dastur_loglari")
    logger.setLevel(logging.DEBUG)

    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN .env faylida sozlanmagan")
        exit(1)

    from telegram.ext import InlineQueryHandler
    app = ApplicationBuilder().token(token).build()

    # Commandlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("feedback", feedback_start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("export", export_users))

    # Qo‘shimcha imkoniyatlar
    app.add_handler(CommandHandler("translate", translate_command))
    app.add_handler(CommandHandler("ocr", ocr_command))
    app.add_handler(CommandHandler("stt", stt_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("direction", direction_command))
    app.add_handler(CommandHandler("dict_add", dictionary_add_command))
    app.add_handler(CommandHandler("dict_list", dictionary_list_command))
    app.add_handler(CommandHandler("dict_remove", dictionary_remove_command))
    app.add_handler(CallbackQueryHandler(direction_callback, pattern=r"^direction:"))
    app.add_handler(CallbackQueryHandler(transliteration_choice_callback, pattern=r"^translit:"))
    app.add_handler(MessageHandler(filters.Regex("^(uz|ru|en)$"), lang_choice))

    # Contact va matn handlerlari
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.Document.ALL, txt_file_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, matn_olish))

    # Inline mode
    app.add_handler(InlineQueryHandler(inlinequery))

    # Webhook/serverless uchun Flask
    if Flask is not None and os.getenv('WEBHOOK_MODE') == '1':
        flask_app = Flask(__name__)
        @flask_app.route('/webhook', methods=['POST'])
        def webhook():
            update = Update.de_json(request.get_json(force=True), app.bot)
            app.process_update(update)
            return 'ok'
        flask_app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8443)))
    else:
        app.run_polling()
