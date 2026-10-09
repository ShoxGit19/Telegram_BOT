# Telegram matn bot

O‘zbek lotin va kiril yozuvlari o‘rtasida transliteratsiya, UZ/RU/EN tarjima, TXT fayllar bilan ishlash, rasm va ovozdan matn olish uchun Telegram bot.

[Bot profil rasmi](assets/bot-avatar.png)

## Imkoniyatlar

- Lotin → kiril, kiril → lotin va avtomatik yo‘nalish.
- Oddiy matnni o‘zbek, rus va ingliz tillariga tarjima qilish.
- TXT faylni transliteratsiya yoki tanlangan tilga tarjima qilib, yana TXT faylda qaytarish.
- Surat va rasm fayllaridan matn olish; ovozli xabar va audioni matnga aylantirish.
- Natijalarni nusxalash, shaxsiy lug‘at, e/ye uchun muqobil variantlar va transliteratsiya tarixi.
- Ish tugaguncha yangilanadigan timer; tarjimada haqiqiy tezlikdan hisoblangan taxminiy qolgan vaqt.
- /start orqali foydalanuvchini ro‘yxatga olish va mavjud ma’lumotlarini yangilash.
- Inline rejim, doimiy menyu, admin statistikasi va CSV eksporti.
- Alohida skript orqali bir martalik yangilanish xabarini yuborish.

## Talablar va o‘rnatish

Python **3.10 yoki yuqori** kerak. Loyiha Python 3.14, `python-telegram-bot 22.8` va `googletrans 4.0.2` bilan tekshirilgan.

BotFather orqali bot yarating va tokenni oling. Tarjima, nutqni tanish va Telegram bilan aloqa uchun internet kerak. OCR uchun Python paketidan tashqari Tesseract dasturi ham o‘rnatiladi.

Repository’ni yuklang:

~~~bash
git clone https://github.com/ShoxGit19/Telegram_BOT.git
cd Telegram_BOT
~~~

### Windows / PowerShell

Python terminaldan ochiladigan qilib o‘rnatilgan bo‘lishi kerak. Yangi muhit yarating va paketlarni o‘rnating:

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install python-telegram-bot==22.8 python-dotenv googletrans==4.0.2 Pillow pytesseract SpeechRecognition imageio-ffmpeg Flask
Copy-Item .env.example .env
~~~

`.venv` yoki `.env` mavjud bo‘lsa, ularni qayta yaratish yoki ustidan nusxalash shart emas.

### Linux / macOS

~~~bash
python3 -m venv .venv
.venv/bin/python -m pip install python-telegram-bot==22.8 python-dotenv googletrans==4.0.2 Pillow pytesseract SpeechRecognition imageio-ffmpeg Flask
cp .env.example .env
~~~

Transliteratsiya uchun loyihadagi `transliterate.py` ishlatiladi; alohida `transliterate` paketini o‘rnatish kerak emas. Audio `imageio-ffmpeg` yordamida WAV formatiga o‘giriladi.

### Muhit sozlamalari

`.env` fayliga haqiqiy tokenni yozing:

~~~dotenv
BOT_TOKEN=your-telegram-bot-token-here
OCR_LANGUAGES=uzb+uzb_cyrl+rus+eng
~~~

Qo‘shimcha sozlamalar:

| Sozlama | Vazifasi |
| --- | --- |
| `TESSERACT_CMD` | Tesseract bajariladigan fayliga to‘liq yo‘l; avtomatik topilmasa belgilanadi. |
| `OCR_LANGUAGES` | OCR til paketlari. Bot mavjud paketlardan foydalanadi. |
| `WEBHOOK_MODE=1` | `first.py` ni polling o‘rniga webhook rejimida ishga tushiradi. |
| `PORT` | Webhook server porti; standart qiymat `8443`. |
| `WEBHOOK_SECRET` | Telegram `setWebhook` dagi `secret_token` bilan mos maxfiy qiymat. |

Admin amallari uchun `first.py` dagi `ADMIN_ID` ni o‘zingizning Telegram ID’ingizga moslang.

### Tesseract OCR

Windows’da:

~~~powershell
winget install --id UB-Mannheim.TesseractOCR --exact --source winget
~~~

`uzb`, `uzb_cyrl`, `rus` va `eng` til paketlarini Tesseract’ning `tessdata` papkasiga o‘rnating. Paketlar [Tesseract tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) repository’sida mavjud.

Bot Windows’da PATH, Program Files va foydalanuvchining `AppData/Local/Programs/Tesseract-OCR` papkasidan dasturni izlaydi. Boshqa manzil uchun `.env` da yo‘lni ko‘rsating:

~~~dotenv
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
~~~

Linux/macOS’da Tesseract va kerakli til paketlarini operatsion tizim paket menejeri orqali o‘rnating. Rasm sifati va mavjud til paketlari OCR natijasiga ta’sir qiladi.

## Ishga tushirish

Loyiha papkasidan bajaring.

Windows:

~~~powershell
.\.venv\Scripts\python.exe -B first.py
~~~

Linux/macOS:

~~~bash
.venv/bin/python -B first.py
~~~

`Ctrl+C` botni to‘xtatadi. Telegram’da `/start` yoki `/menu` yuboring. Bir token bilan bir vaqtning o‘zida bitta polling nusxasini ishlating.

## Foydalanish

Menyudan amalni tanlang, keyin shu amalga mos matn, rasm, ovoz yoki fayl yuboring. Boshqa amalga o‘tish uchun menyudan yangi amal tanlang.

| Amal | Tartibi va natijasi |
| --- | --- |
| Oddiy matn | Saqlangan yo‘nalish bo‘yicha transliteratsiya qilinadi. |
| 🔤 Lotin → Kiril / 🔠 Kiril → Lotin | Yo‘nalishni tanlang, keyin matn yuboring. |
| 🌐 Tarjima | Matn yuboring; UZ, RU va EN natijalari alohida qaytadi. |
| 📄 TXT fayl | Transliteratsiya yoki TXT tarjimasini tanlang, keyin fayl yuboring. |
| 🌐 TXT tarjima | Avval UZ/RU/EN tanlang, keyin TXT yuboring; tanlangan tilda TXT qaytadi. |
| 🖼 Rasm → matn | Surat yoki rasm fayli yuboring; topilgan matn qaytadi. |
| 🎙 Ovoz → matn | Ovozli xabar yoki audio yuboring; o‘zbekcha nutq taniladi. |
| ↔ Yo‘nalish | Avtomatik, lotin → kiril yoki kiril → lotin yo‘nalishini saqlang. |
| 📚 Lug‘at | Shaxsiy qoidalarni ko‘ring; qo‘shish/o‘chirish amallari ham menyuda bor. |
| 📜 Tarix / 💬 Fikr / 🌐 Til | Oxirgi transliteratsiyalar, fikr yuborish va interfeys tilini tanlash. |

### TXT fayllar

- **Transliteratsiya:** `TXT fayl → Transliteratsiya → fayl`. Natija: `transliterated.txt`.
- **Tarjima:** `TXT tarjima → UZ / RU / EN → fayl`. Natija: `translated_uz.txt`, `translated_ru.txt` yoki `translated_en.txt`.
- Amal tanlanmasdan yuborilgan TXT fayl saqlangan yo‘nalish bo‘yicha transliteratsiya qilinadi.
- Fayl UTF-8 formatida bo‘lishi kerak; UTF-8 BOM ham qabul qilinadi.
- Tarjima bo‘laklarga ajratiladi; asl satr ajratgichlari saqlanadi.

### Nusxalash va timer

Qisqa natijalarda `Nusxa olish` matnni clipboard’ga ko‘chiradi. Uzun natijalarda nusxalanadigan bo‘laklar chiqariladi. `Matnni olish` orqali matnni bosib ushlab ham nusxalash mumkin. Saqlangan natija xotiradan chiqib ketsa yoki bot qayta ishga tushsa, copy amali asl xabardagi matndan foydalanadi.

Tez tugagan ishda timer ko‘rinmaydi. Uzoq ishda haqiqiy o‘tgan vaqt yangilanadi. Tarjimada tugagan bo‘laklar tezligidan **taxminiy** qolgan vaqt hisoblanadi; tezlik o‘zgarsa taxmin ham yangilanadi. OCR va audioda tugash vaqti oldindan noma’lum bo‘lgani uchun o‘tgan vaqt ko‘rsatiladi.

### Shaxsiy lug‘at va inline rejim

~~~text
/dict_add Shaxzoda | Шахзода
/dict_list
/dict_remove Shaxzoda
~~~

Lug‘at qoidalari ikki yo‘nalishda ishlaydi; har bir foydalanuvchi 100 tagacha qoida saqlashi mumkin.

Inline rejim uchun BotFather’da `/setinline` ni yoqing. Keyin boshqa chatda `@bot_username matn` yozing va natijani tanlang.

## Buyruqlar

| Buyruq | Vazifasi |
| --- | --- |
| `/start` | Foydalanuvchini tekshirish/saqlash va menyuni ochish. |
| `/menu` | Kutilayotgan amalni bekor qilish va menyuni ochish. |
| `/help` | Yordam. |
| `/translate [matn]` | Matn tarjimasi; matn berilmasa keyingi xabarni kutadi. |
| `/txt_translate` | TXT tarjimasi uchun UZ/RU/EN tanlash. |
| `/ocr` / `/stt` | Rasm yoki audio kutish. |
| `/direction` / `/lang` | Transliteratsiya yo‘nalishi yoki interfeys tili. |
| `/dict_add` / `/dict_list` / `/dict_remove` | Shaxsiy lug‘at. |
| `/history` / `/feedback` | Transliteratsiya tarixi yoki fikr yuborish. |
| `/stats` / `/export` | Faqat admin uchun statistika va CSV eksporti. |

## Cheklovlar

| Ma’lumot | Chegara |
| --- | --- |
| Oddiy matn | 2 000 belgi. |
| TXT | 1 000 000 bayt va 100 000 belgi. |
| Rasm / audio | 20 000 000 bayt. |
| Matn so‘rovlari | 10 soniyada 8 ta. |
| Inline so‘rovlari | 10 soniyada 40 ta. |
| TXT / audio | Har biri uchun bir daqiqada 3 ta. |

Telegram’ning o‘z limitlari ham amal qiladi. Bot API orqali oddiy foydalanuvchiga `@username` bilan shaxsiy xabar yuborib bo‘lmaydi; botga ochiq chat ID kerak. Foydalanuvchi avval botga xabar yuborishi kerak. [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage), [botlar haqida](https://core.telegram.org/bots#how-do-bots-work).

## Foydalanuvchilar va saqlanadigan ma’lumotlar

`/start` har safar foydalanuvchi ID’sini `users.json` da tekshiradi. Yangi hisob qo‘shiladi; mavjud hisobning profili yangilanadi. Oldingi telefon raqami, birinchi ro‘yxatdan o‘tish vaqti va boshqa saqlangan maydonlar saqlanib qoladi.

Quyidagilar yoziladi:

- ID, ism-familiya, username, Telegram til kodi, bot va Premium belgisi.
- Telegram yuborgan `User` va `Chat` obyektlari; chat ID, turi va shaxsiy chat ID.
- Bot ID va username’i, birinchi/oxirgi `/start` vaqti, yangilanish vaqti va `/start` soni.
- Telefon raqami va kontakt ma’lumotlari — faqat foydalanuvchi o‘z kontaktini yuborsa.

`user_store.py` ma’lumotlarni vaqtinchalik faylga yozib, so‘ng asosiy faylni atomik almashtiradi. Buzilgan JSON ustidan yangi ma’lumot yozilmaydi.

| Fayl / papka | Mazmuni |
| --- | --- |
| `users.json` | Foydalanuvchilar reyestri; loyihaning asosiy papkasida. |
| `translations.csv` | Oddiy matn transliteratsiyalari tarixi. |
| `feedbacks.csv` | Fikr va takliflar. |
| `data/user_dictionaries.json` | Shaxsiy lug‘atlar. |
| `data/transliteration_preferences.json` | Saqlangan yo‘nalishlar. |
| `data/broadcast_bot_update_20261009_v1.json` | Bir martalik xabar yuborish natijalari. |

`.env`, foydalanuvchi fayllari, `data/` va loglar `.gitignore` da ko‘rsatilgan. Ularni public repository’ga qo‘shmang.

## Bir martalik yangilanish xabari

`broadcast_update.py` faqat tayyorlangan **2026-10-09 yangilanish kampaniyasi** uchun ishlaydi. Xabar: [announcements/bot-update-2026-10-09.html](announcements/bot-update-2026-10-09.html).

Avval yubormasdan ko‘ring:

~~~powershell
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -B broadcast_update.py
~~~

Barcha saqlangan foydalanuvchilarga yuborish:

~~~powershell
.\.venv\Scripts\python.exe -B broadcast_update.py --send
~~~

Har bir hisob natijasi alohida saqlanadi. Muvaffaqiyatli yuborilgan xabar takrorlanmaydi. Yetib borgan-bormagani noma’lum tarmoq xatosida avtomatik qayta yuborilmaydi. `Chat not found` va boshqa rad etishlar hisobotga yoziladi. Shu kampaniyaning xabar matni o‘zgarsa, skript takror yuborishdan saqlanish uchun to‘xtaydi.

## Webhook

Windows’da:

~~~powershell
.\.venv\Scripts\python.exe -B webhook_server.py
~~~

Linux/macOS’da:

~~~bash
.venv/bin/python -B webhook_server.py
~~~

`POST /webhook` Telegram yangilanishlarini qabul qiladi. Telegram ilovasi bitta doimiy event loop’da ishga tushiriladi va yangilanishlar navbatga qo‘yiladi.

Public HTTPS manzilni Telegram’ning `setWebhook` metodi orqali alohida ro‘yxatdan o‘tkazish kerak; serverni ishga tushirish buni avtomatik bajarmaydi. `WEBHOOK_SECRET` ishlatilsa, `setWebhook` uchun ayni qiymatni `secret_token` sifatida yuboring. Polling’ga qaytishdan oldin webhook’ni o‘chiring.

## Testlar

Windows:

~~~powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
~~~

Linux/macOS:

~~~bash
.venv/bin/python -B -m unittest discover -s tests -v
~~~

Testlar copy, TXT tarjimasi, OCR xabar oqimi, timer, webhook, bir martalik yuborish va foydalanuvchilarni saqlashni tekshiradi. Tashqi tarjima/Telegram so‘rovlari mock qilinadi; testlar haqiqiy foydalanuvchilarga xabar yubormaydi.

## Loyiha tuzilishi

~~~text
first.py                 Asosiy bot va handlerlar
transliterate.py         Lotin/kiril konvertori
transliteration_tools.py Shaxsiy lug‘at, yo‘nalish va variantlar
extra_features.py        Tarjima, Tesseract OCR va audio tanish
inline_handler.py        Inline transliteratsiya
lang_support.py          Interfeys tilidagi xabarlar
request_guard.py         So‘rov tezligi cheklovlari
user_store.py            Foydalanuvchi va kontaktlarni saqlash
webhook_server.py        Flask webhook
broadcast_update.py      Bir martalik yangilanish xabari
announcements/           Tayyor xabar matni
assets/                  Bot profil rasmi va dizayn prompti
tests/                   Avtomatik tekshiruvlar
.env.example             Muhit sozlamalari namunasi
~~~

`git_push.sh` dagi `/home/ec2-user/Telegram_BOT` manzili EC2 muhiti uchun yozilgan. Boshqa muhitda ishlatishdan oldin shu manzilni moslang.

## Ko‘p uchraydigan muammolar

- **BOT_TOKEN topilmadi:** `.env` dagi qiymatni va faylning loyiha papkasida ekanini tekshiring.
- **Python topilmadi:** Python’ni terminal PATH’iga qo‘shing yoki mavjud `.venv` ichidagi Python’dan foydalaning.
- **Rasmdan matn olinmadi:** Tesseract yo‘li, til paketlari va surat aniqligini tekshiring.
- **TXT o‘qilmadi:** faylni UTF-8 formatida saqlang; hajm va belgilar chegarasini tekshiring.
- **Tarjima/audio xizmati javob bermadi:** internet va xizmat mavjudligini tekshiring; keyin qayta urinib ko‘ring.
- **Conflict yoki bot javobi uzilmoqda:** shu token bilan boshqa polling nusxasi ishlamayotganini tekshiring.
- **Chat not found:** saqlangan ID hozirgi bot uchun ochiq chatga tegishli emas; foydalanuvchi aynan shu botga `/start` yuborishi kerak.
