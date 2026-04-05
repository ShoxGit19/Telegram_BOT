# Tarjima va qo'shimcha imkoniyatlar uchun kutubxonalar
# pip install googletrans==4.0.0-rc1 pytesseract pillow SpeechRecognition

from googletrans import Translator
from PIL import Image
import pytesseract
import speech_recognition as sr

# Tarjima funksiyasi
def translate_text(text, src='auto', dest='uz'):
    translator = Translator()
    result = translator.translate(text, src=src, dest=dest)
    return result.text

# OCR funksiyasi (rasmdan matn)
def ocr_image(image_path, lang='uzb'):
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang=lang)
    return text

# STT funksiyasi (audio -> matn)
def speech_to_text(audio_path, lang='uz-UZ'):
    r = sr.Recognizer()
    with sr.AudioFile(audio_path) as source:
        audio = r.record(source)
    text = r.recognize_google(audio, language=lang)
    return text
