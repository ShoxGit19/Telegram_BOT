# Telegram Transliteration Bot

Bu Telegram bot o‘zbek lotin va kiril alifbolari o‘rtasida tezkor va avtomatik transliteratsiya amalga oshiradi. Foydalanuvchi yuborgan matn bir zumda boshqa yozuv tizimiga aylantiriladi.

---

## Asosiy imkoniyatlar

- Lotin → Kiril o‘girish
- Kiril → Lotin o‘girish
- Matnni avtomatik aniqlash va mos yozuvga aylantirish
- Foydalanuvchilar ma’lumotlarini saqlash
- Tarjima tarixini CSV formatda yozib borish
- Telefon raqamni qabul qilish va saqlash
- Real vaqt rejimida ishlash

---

## Texnologiyalar

- Python 3.7+
- python-telegram-bot
- transliterate
- JSON va CSV orqali ma’lumot saqlash

---

## O‘rnatish

1. Python 3.7 yoki undan yuqori versiyasini o‘rnating.

2. Repository’ni yuklab oling:

   git clone https://github.com/ShoxGit19/Telegram_BOT.git
   cd Telegram_BOT

3. Virtual environment yaratish tavsiya etiladi:

   python3 -m venv .venv
   source .venv/bin/activate

4. Kerakli paketlarni o‘rnating:

   pip install python-telegram-bot transliterate

5. token.txt fayl yarating va ichiga bot tokenini yozing.

6. Quyidagi fayllar mavjudligiga ishonch hosil qiling (bo‘sh bo‘lishi mumkin):
   - users.json
   - translations.csv

---

## Ishga tushirish

   python3 first.py

Bot ishga tushgandan so‘ng Telegram orqali foydalanish mumkin bo‘ladi.

---

## Loyihaning tuzilishi

- first.py — asosiy bot kodi
- transliterate.py — transliteratsiya logikasi
- token.txt — bot tokeni
- users.json — foydalanuvchilar ma’lumotlari
- translations.csv — tarjimalar logi
- feedbacks.csv — foydalanuvchi xabarlari

---

## Ishlash printsipi

Bot foydalanuvchi yuborgan matndagi yozuv tizimini avtomatik aniqlaydi va uni boshqa alifboga o‘giradi. Barcha transliteratsiyalar log sifatida saqlanadi. Ma’lumotlar JSON va CSV fayllarda lokal tarzda saqlanadi.
