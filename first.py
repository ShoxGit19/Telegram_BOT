import logging, json, datetime, csv, io, os, re
from transliterate import to_cyrillic, to_latin
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

ADMIN_ID = 6954909676

START_MESSAGE = (
    "👋 Assalomu alaykum!\n\n"
    "Bu bot Lotin ↔ Kiril transliteratsiya qiladi.\n\n"
    "✍️ Matn yuboring — men darhol aylantirib beraman.\n\n"
    "📌 Buyruqlar:\n"
    "/help — Yordam\n"
    "/history — Oxirgi tarjimalar\n"
    "/feedback — Fikr bildirish\n"
)

def remove_noise(text):
    return re.sub(r'[^\w\sА-Яа-яЁё]', '', text)

def contains_cyrillic(text):
    return bool(re.search('[А-Яа-яЁё]', remove_noise(text)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user=update.effective_user
    uid=str(user.id)

    try:
        users=json.load(open("users.json",encoding="utf8"))
    except:
        users={}

    if uid not in users:
        users[uid]={
            "first":user.first_name,
            "last":user.last_name,
            "username":user.username,
            "joined":datetime.datetime.now().isoformat()
        }
        json.dump(users,open("users.json","w",encoding="utf8"),indent=2,ensure_ascii=False)

    await update.message.reply_text(START_MESSAGE)

async def matn_olish(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if context.user_data.get("fb"):
        os.makedirs("data",exist_ok=True)
        csv.writer(open("feedbacks.csv","a",newline="",encoding="utf8")).writerow([
            update.effective_user.id,
            update.message.text,
            datetime.datetime.now().isoformat()
        ])
        context.user_data.pop("fb")
        return await update.message.reply_text("Rahmat! Fikr saqlandi.")

    text=update.message.text

    result = to_latin(text) if contains_cyrillic(text) else to_cyrillic(text)

    os.makedirs("data",exist_ok=True)
    csv.writer(open("translations.csv","a",newline="",encoding="utf8")).writerow([
        update.effective_user.id,
        text,
        result,
        datetime.datetime.now().isoformat()
    ])

    await update.message.reply_text(f"<pre>{result}</pre>",parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Yordam\n\n"
        "/start — Boshlash\n"
        "/history — Oxirgi tarjimalar\n"
        "/feedback — Fikr bildirish\n"
        "/help — Yordam"
    )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=str(update.effective_user.id)
    try:
        rows=[r for r in csv.reader(open("translations.csv",encoding="utf8")) if r[0]==uid]
    except:
        rows=[]

    if not rows:
        return await update.message.reply_text("Tarjima topilmadi.")

    msg="🕘 Oxirgi tarjimalar:\n\n"
    for r in rows[-10:]:
        msg+=f"{r[1]} → {r[2]}\n"

    await update.message.reply_text(msg)

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fb"]=True
    await update.message.reply_text("✍️ Fikringizni yozing:")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    users=len(json.load(open("users.json"))) if os.path.exists("users.json") else 0
    trans=sum(1 for _ in open("translations.csv")) if os.path.exists("translations.csv") else 0
    feeds=sum(1 for _ in open("feedbacks.csv")) if os.path.exists("feedbacks.csv") else 0

    await update.message.reply_text(f"📊 Stats\nUsers:{users}\nTranslations:{trans}\nFeedbacks:{feeds}")

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    await update.message.reply_document(open("users.json","rb"))

if __name__=="__main__":
    logging.basicConfig(level=logging.INFO)
    token=open("token.txt").read().strip()

    app=ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("help",help_command))
    app.add_handler(CommandHandler("history",history))
    app.add_handler(CommandHandler("feedback",feedback))
    app.add_handler(CommandHandler("stats",stats))
    app.add_handler(CommandHandler("export",export))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,matn_olish))

    print("BOT RUNNING...")
    app.run_polling()
