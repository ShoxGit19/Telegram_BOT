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
- Inline rejimda transliteratsiya
- Foydalanuvchi tanlaydigan transliteratsiya yo'nalishi
- Har bir foydalanuvchi uchun shaxsiy lug'at
- `.txt` faylni transliteratsiya qilib yangi fayl sifatida qaytarish
- Noaniq `e/ye` yozilishlari uchun muqobil variant tanlash
- Matn, inline so'rov va fayl hajmiga qarshi cheklovlar
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

   pip install python-telegram-bot transliterate python-dotenv

5. `.env.example` faylidan `.env` nusxa yarating va `BOT_TOKEN` qiymatini o'zingiz kiriting. `.env` va bot ishlashida yaratiladigan foydalanuvchi ma'lumotlarini GitHub'ga yubormang.

6. `.env` faylini hech qachon public repository'ga commit qilmang.

---

## Ishga tushirish

   python3 first.py

Bot ishga tushgandan so‘ng Telegram orqali foydalanish mumkin bo‘ladi.

## Yangi imkoniyatlar

- Inline rejimni BotFather'da `/setinline` buyrug'i bilan yoqing. So'ng Telegram chatida `@bot_username matn` yozing.
- `/direction` orqali avtomatik aniqlash, lotin → kiril yoki kiril → lotin yo'nalishini tanlang. Tanlov qayta ishga tushgandan keyin ham saqlanadi.
- `/dict_add Shaxzoda | Шахзода` bilan shaxsiy qoida qo'shing. Qoida ikkala yo'nalishda ham ishlaydi.
- `/dict_list` shaxsiy qoidalarni ko'rsatadi, `/dict_remove Shaxzoda` esa o'chiradi.
- `.txt` fayl yuboring; bot transliteratsiya qilingan `transliterated.txt` faylini qaytaradi. Fayl 1 MB va 100 000 belgigacha bo'lishi mumkin.
- `e/ye` noaniq holatlarida asosiy natijaga qo'shimcha variant tugmalari chiqadi.
- Matn xabari 2 000 belgi, inline so'rov 1 000 belgi bilan cheklangan. Chatda 10 soniyada 8 ta matn, inline rejimda 10 soniyada 40 ta so'rov va bir daqiqada 3 ta faylga ruxsat beriladi.
- Lug'at va transliteratsiya sozlamalari `data/` ichida saqlanadi; bu papka `.gitignore` bilan GitHub'dan chetda.

---

## Loyihaning tuzilishi

- first.py — asosiy bot kodi
- transliterate.py — transliteratsiya logikasi
- .env — maxfiy bot tokeni (faqat lokal, Git'dan chetda)
- users.json — foydalanuvchilar ma’lumotlari
- translations.csv — tarjimalar logi
- feedbacks.csv — foydalanuvchi xabarlari

---

## Ishlash printsipi

Bot foydalanuvchi yuborgan matndagi yozuv tizimini avtomatik aniqlaydi va uni boshqa alifboga o‘giradi. Barcha transliteratsiyalar log sifatida saqlanadi. Ma’lumotlar JSON va CSV fayllarda lokal tarzda saqlanadi.
