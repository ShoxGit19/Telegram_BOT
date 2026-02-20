import logging
import json
import datetime
import csv
import io
import os
import re
import asyncio  # ✅ Qo‘shildi

from transliterate import to_cyrillic, to_latin
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ADMIN ID ni o'zgartiring (o'zingizning Telegram ID)
ADMIN_ID = 6954909676

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
    # Agar foydalanuvchi feedback yuborishi kutilayotgan bo'lsa, feedback sifatida saqlaymiz
    if context.user_data.get('awaiting_feedback'):
        feedback_text = update.message.text
        user = update.effective_user
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

    kirilgan_matn = update.message.text or ""
    user = update.effective_user
    user_name = user.username or user.first_name or "Foydalanuvchi"
    user_id = str(user.id)
    try:
        # Yangi: kiril bor-yo'qligini aniqlash uchun contains_cyrillic dan foydalanamiz
        if contains_cyrillic(kirilgan_matn):
            javob = to_latin(kirilgan_matn)
        else:
            javob = to_cyrillic(kirilgan_matn)

        # Tarjima saqlash
        os.makedirs('data', exist_ok=True)
        with open('translations.csv', 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([user_id, kirilgan_matn, javob, datetime.datetime.now().isoformat()])

        # Monospaced format - HTML <pre>
        await update.message.reply_text(f"{user_name} siz kiritgan so'z:\n<pre>{javob}</pre>", parse_mode='HTML')
        await update.message.reply_text("Yana so'z kiring:")
    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await update.message.reply_text("Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Yordam\n\n"
        "Bu bot Lotin ↔ Kiril transliteratsiya qiladi.\n\n"
        "📌 Buyruqlar:\n"
        "/start — Boshlash\n"
        "/history — Oxirgi tarjimalar\n"
        "/feedback — Fikr bildirish\n"
        "/help — Yordam\n\n"
        "✍️ Istalgan matn yuboring — bot avtomatik aylantirib beradi."
    )

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

    try:
        with open('token.txt', 'r', encoding='utf-8') as f:
            token = f.read().strip()
    except FileNotFoundError:
        logger.error("token.txt fayli topilmadi")
        exit(1)

    app = ApplicationBuilder().token(token).build()

    # ✅ Qo‘shildi: bot ishga tushganda 5 soniyadan keyin broadcast (faqat 1 marta)
    
    # Commandlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("feedback", feedback_start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("export", export_users))

    # Contact va matn handlerlari
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, matn_olish))

    app.run_polling()
