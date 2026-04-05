# Multi-language interfeys uchun
# Foydalanuvchi tilini aniqlash va javoblarni moslashtirish

LANGUAGES = {
    'uz': {
        'start': "👋 Assalomu alaykum!",
        'help': "ℹ️ Yordam\n\nBu bot Lotin ↔ Kiril transliteratsiya qiladi.",
        'choose_lang': "Tilni tanlang:",
    },
    'ru': {
        'start': "👋 Здравствуйте!",
        'help': "ℹ️ Помощь\n\nЭтот бот выполняет транслитерацию латиницы и кириллицы.",
        'choose_lang': "Выберите язык:",
    },
    'en': {
        'start': "👋 Hello!",
        'help': "ℹ️ Help\n\nThis bot transliterates Latin and Cyrillic alphabets.",
        'choose_lang': "Choose your language:",
    }
}

def get_lang(user_data):
    return user_data.get('lang', 'uz')

def set_lang(user_data, lang):
    user_data['lang'] = lang
