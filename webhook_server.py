# Webhook va serverless deploy uchun asosiy sozlamalar
# Misol uchun: Flask yordamida webhook
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import os

TOKEN = os.getenv('BOT_TOKEN')
app = Flask(__name__)
tg_app = ApplicationBuilder().token(TOKEN).build()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), tg_app.bot)
    tg_app.process_update(update)
    return 'ok'

# Flask serverini ishga tushirish uchun:
# flask run --host=0.0.0.0 --port=8443
# yoki serverless platformaga deploy qilish uchun moslashtiring
