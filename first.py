from telegram import Update
import logging
import requests
from transliterate import to_cyrillic, to_latin
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    javob=await update.message.reply_text("Assalomu aleykom startni bosganingizdan hursandman!!\n Menga lotin yoki кирил so'zlarini yoki matnlarini kiritasiz\n Matn kiriting: ")
    
async def matn_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kirilgan_matn = update.message.text  # Foydalanuvchi kiritgan matn
    if kirilgan_matn.isascii():
        javob=to_cyrillic(kirilgan_matn)
        
    else:
        javob=to_latin(kirilgan_matn)
    #text = javob  # Foydalanuvchi yuborgan matn
    monospace_text = f'```\n{javob}\n```'  # Matnni Monospace formatida qayta ishlash
    await update.message.reply_text(monospace_text, parse_mode='MarkdownV2') 
    await update.message.reply_text("Yana so'z kiring:")  # MarkdownV2 rejimida yubori
    #await update.message.reply_text(javob, parse_mode='MarkdownV2')
    #await update.message.reply_text(f"Siz kiritgan matn: '{javob}' \n Yana matn kiring:")
    ##await update.message.reply_copy(f"Siz kiritgan matn: {javob} \n Yana matn kiring:")
    #async def javob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Demak siz tushunmadingiz: /start tugmasini bosib va istalgan matin yoki so'z kiriting ")



if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    logger = logging.getLogger("dastur_loglari")
    logger.setLevel(logging.DEBUG)
    app = ApplicationBuilder().token("7999620884:AAEmh5wQNWiEG4uCYIWDF5gj9hfAq-9F9zE").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, matn_olish))
    app.add_handler(CommandHandler("help",help))
    app.run_polling()