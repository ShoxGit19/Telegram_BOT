# Tarjima va qo'shimcha imkoniyatlar uchun kutubxonalar
# pip install googletrans==4.0.2 pytesseract pillow SpeechRecognition

from googletrans import Translator
from PIL import Image, ImageOps
import pytesseract
import speech_recognition as sr
import subprocess
import tempfile
from pathlib import Path
import imageio_ffmpeg
import os
import re
import shutil

TRANSLATION_CHUNK_CHARS = 3500


def translation_segments(text):
    for line in re.split(r"(\r\n|\r|\n)", text):
        if not line.strip():
            yield False, line
            continue
        while line:
            if not line.strip():
                yield False, line
                break
            leading = len(line) - len(line.lstrip())
            if leading:
                yield False, line[:leading]
                line = line[leading:]
            end = min(len(line), TRANSLATION_CHUNK_CHARS)
            if end < len(line):
                boundary = max(line.rfind(" ", 0, end + 1), line.rfind("\t", 0, end + 1))
                if boundary > 0:
                    end = boundary
            part, line = line[:end], line[end:]
            content = part.rstrip()
            if content:
                yield True, content
            if len(content) < len(part):
                yield False, part[len(content):]


def translation_chunk_count(text):
    return sum(needs_translation for needs_translation, _ in translation_segments(text))


async def translate_text(text, src="auto", dest="uz", on_progress=None):
    if dest not in {"uz", "ru", "en"}:
        raise ValueError("Tarjima tili UZ, RU yoki EN bo'lishi kerak.")
    if not text.strip():
        return text
    async with Translator(raise_exception=True) as translator:
        parts = []
        detected_src = src
        for needs_translation, part in translation_segments(text):
            if not needs_translation:
                parts.append(part)
                continue
            result = await translator.translate(part, src=detected_src, dest=dest)
            if not result.text or not result.text.strip():
                raise ValueError("Tarjima xizmati bo'sh javob qaytardi.")
            parts.append(result.text)
            if detected_src == "auto" and getattr(result, "src", None):
                detected_src = result.src
            if on_progress is not None:
                on_progress()
        return "".join(parts)


def configure_tesseract():
    configured = os.getenv("TESSERACT_CMD")
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured
        return
    executable = shutil.which("tesseract")
    if not executable and os.name == "nt":
        for directory in (
            Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR",
            Path(os.getenv("LOCALAPPDATA", ".")) / "Programs" / "Tesseract-OCR",
            Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Tesseract-OCR",
        ):
            candidate = directory / "tesseract.exe"
            if candidate.is_file():
                executable = str(candidate)
                break
    if executable:
        pytesseract.pytesseract.tesseract_cmd = executable


def ocr_image(image_path, lang=None):
    configure_tesseract()
    try:
        available = set(pytesseract.get_languages(config=""))
        requested = (lang or os.getenv("OCR_LANGUAGES", "uzb+uzb_cyrl+rus+eng")).split("+")
        languages = [language for language in requested if language in available]
        if not languages:
            languages = [language for language in ("eng", "rus", "uzb", "uzb_cyrl") if language in available]
        if not languages:
            raise ValueError("Tesseract uchun UZ, RU yoki EN til paketini o'rnating.")
        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source)
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
            image = ImageOps.autocontrast(ImageOps.grayscale(image))
            if max(image.size) < 1600:
                image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
            return pytesseract.image_to_string(image, lang="+".join(languages), timeout=60).strip()
    except pytesseract.TesseractNotFoundError as error:
        raise ValueError(
            "Rasmdan matn olish uchun serverga Tesseract OCR o'rnatilishi kerak. "
            "TESSERACT_CMD sozlamasida tesseract.exe yo'lini ko'rsating."
        ) from error


# STT funksiyasi (audio -> matn)
def speech_to_text(audio_path, lang='uz-UZ'):
    r = sr.Recognizer()
    with tempfile.TemporaryDirectory(prefix="telegram_stt_") as temporary_directory:
        wav_path = Path(temporary_directory) / "converted.wav"
        try:
            subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-nostdin",
                    "-y",
                    "-i",
                    str(audio_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-f",
                    "wav",
                    str(wav_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError("Audio faylni WAV formatiga aylantirib bo'lmadi.") from error

        with sr.AudioFile(str(wav_path)) as source:
            audio = r.record(source)
    text = r.recognize_google(audio, language=lang)
    return text
