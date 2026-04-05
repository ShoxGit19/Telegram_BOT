# Inline mode uchun handler namunasi
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler
import uuid
from transliterate import to_cyrillic, to_latin

def inlinequery(update, context):
    query = update.inline_query.query
    if not query:
        return
    # Lotin yoki kiril aniqlash
    if any('а' <= c <= 'я' or 'А' <= c <= 'Я' for c in query):
        result = to_latin(query)
    else:
        result = to_cyrillic(query)
    results = [
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title="Transliteratsiya",
            input_message_content=InputTextMessageContent(result)
        )
    ]
    update.inline_query.answer(results)
