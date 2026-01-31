from telegram import Update
import logging
from transliterate import to_cyrillic, to_latin
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import json
import datetime
import csv
import io
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    try:
        with open('users.json', 'r') as f:
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
        with open('users.json', 'w') as f:
            json.dump(users, f, indent=4)
    keyboard = [[InlineKeyboardButton("Kontaktni ulashish", request_contact=True)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Assalomu aleykom! Bu bot lotin va kiril alifbolari o'rtasida matn transliteratsiyasini amalga oshiradi.\n\nMenga lotin yoki kiril so'zlarini yoki matnlarini kiritasiz. Matn kiriting:", reply_markup=reply_markup)
    
async def matn_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kirilgan_matn = update.message.text  # Foydalanuvchi kiritgan matn
    user = update.effective_user
    user_name = user.username or user.first_name or "Foydalanuvchi"
    user_id = str(update.effective_user.id)
    try:
        if kirilgan_matn.isascii():
            javob = to_cyrillic(kirilgan_matn)
        else:
            javob = to_latin(kirilgan_matn)
        # Auto save
        with open('translations.csv', 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([user_id, kirilgan_matn, javob, datetime.datetime.now().isoformat()])
        monospace_text = f'```\n{javob}\n```'  # Matnni Monospace formatida qayta ishlash
        await update.message.reply_text(f"{user_name} siz kiritgan so'z:\n{monospace_text}", parse_mode='MarkdownV2') 
        await update.message.reply_text("Yana so'z kiring:")
    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await update.message.reply_text("Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")
    
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Demak siz tushunmadingiz: /start tugmasini bosib va istalgan matin yoki so'z kiriting ")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = str(update.effective_user.id)
    if contact and contact.user_id == update.effective_user.id:
        try:
            with open('users.json', 'r') as f:
                users = json.load(f)
            if user_id in users:
                users[user_id]['phone'] = contact.phone_number
                with open('users.json', 'w') as f:
                    json.dump(users, f, indent=4)
            await update.message.reply_text("Kontakt saqlandi. Rahmat!")
        except FileNotFoundError:
            await update.message.reply_text("Xatolik.")

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat admin uchun (sizning ID ni qo'ying)
    admin_id = 123456789  # O'zingizning Telegram ID ni qo'ying
    if update.effective_user.id != admin_id:
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return
    try:
        with open('users.json', 'r') as f:
            users = json.load(f)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['User ID', 'First Name', 'Last Name', 'Username', 'Phone', 'First Start'])
        for uid, data in users.items():
            writer.writerow([uid, data['first_name'], data['last_name'], data['username'], data['phone'], data['first_start']])
        output.seek(0)
        await update.message.reply_document(document=output, filename='users.csv', caption='Foydalanuvchilar ro\'yxati')
    except FileNotFoundError:
        await update.message.reply_text("Hech kim start bermagan.")



if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    logger = logging.getLogger("dastur_loglari")
    logger.setLevel(logging.DEBUG)
    try:
        with open('token.txt', 'r') as f:
            token = f.read().strip()
    except FileNotFoundError:
        logger.error("token.txt fayli topilmadi")
        exit(1)
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, matn_olish))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(CommandHandler("help",help))
    app.add_handler(CommandHandler("export", export_users))
    app.run_polling()