# Telegram Transliteration Bot

Bu bot lotin va kiril alifbolari o'rtasida matn transliteratsiyasini amalga oshiradi.

## Xususiyatlar
- /start: Botni ishga tushirish
- Matn yuborish: Lotin -> Kiril yoki Kiril -> Lotin
- /help: Yordam
- /export: Foydalanuvchilar ro'yxatini CSV sifatida yuklab olish (faqat admin)
- Kontakt ulashish: Telefon raqamini saqlash

## O'rnatish
1. Python 3.7+ o'rnating.
2. Kerakli paketlarni o'rnating:
   ```
   pip install python-telegram-bot transliterate
   ```
3. `token.txt` faylini yarating va bot tokenini qo'ying.
4. `users.json` va `translations.csv` fayllarini yarating (bo'sh).

## Ishga tushirish
```
cd Telegram_BOT
python first.py
```

## Fayllar
- `first.py`: Asosiy bot kodi
- `token.txt`: Bot tokeni
- `users.json`: Foydalanuvchilar ma'lumotlari
- `translations.csv`: Transliteratsiya loglari

## Admin
/export uchun admin ID ni kodda o'zgartiring.