from telegram import InlineQueryResultArticle, InputTextMessageContent
import uuid

from request_guard import is_rate_limited
from transliteration_tools import get_user_dictionary, get_user_direction, transliterate_for_user

MAX_INLINE_QUERY_CHARS = 1000


async def inlinequery(update, context):
    inline_query = update.inline_query
    text = inline_query.query.strip()
    if not text:
        await inline_query.answer([], cache_time=0, is_personal=True)
        return

    user_id = inline_query.from_user.id
    rate_limited = is_rate_limited(
        user_id,
        "inline",
        limit=40,
        window_seconds=10,
    )
    if len(text) > MAX_INLINE_QUERY_CHARS or rate_limited:
        await inline_query.answer([], cache_time=5, is_personal=True)
        return

    direction = get_user_direction(user_id)
    dictionary = get_user_dictionary(user_id)
    result = transliterate_for_user(text, direction, dictionary)
    results = [
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title="Transliteratsiya",
            input_message_content=InputTextMessageContent(result)
        )
    ]
    await inline_query.answer(results, cache_time=0, is_personal=True)
