import json
import os
import re
import tempfile
from pathlib import Path

from transliterate import to_cyrillic, to_latin

DATA_FILE = Path(__file__).resolve().parent / "data" / "user_dictionaries.json"
PREFERENCES_FILE = Path(__file__).resolve().parent / "data" / "transliteration_preferences.json"
LATIN_TERM = re.compile(r"^[A-Za-z][A-Za-z '’‘ʻʼ-]{0,79}$")
CYRILLIC_TERM = re.compile(r"^[А-Яа-яЁёЎўҚқҒғҲҳ][А-Яа-яЁёЎўҚқҒғҲҳ '’‘ʻʼ-]{0,79}$")
DIRECTIONS = {"auto", "latin_to_cyrillic", "cyrillic_to_latin"}


def _load_all_dictionaries():
    try:
        with DATA_FILE.open("r", encoding="utf-8") as dictionary_file:
            data = json.load(dictionary_file)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Lug'at fayli formati noto'g'ri")
    return data


def _save_all_dictionaries(dictionaries):
    _save_json(DATA_FILE, dictionaries)


def _save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix="user_dictionaries_",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump(data, temporary_file, ensure_ascii=False, indent=2)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def get_user_direction(user_id):
    try:
        with PREFERENCES_FILE.open("r", encoding="utf-8") as preferences_file:
            preferences = json.load(preferences_file)
    except FileNotFoundError:
        return "auto"
    direction = preferences.get(str(user_id), "auto")
    return direction if direction in DIRECTIONS else "auto"


def set_user_direction(user_id, direction):
    if direction not in DIRECTIONS:
        raise ValueError("Noto'g'ri transliteratsiya yo'nalishi")
    try:
        with PREFERENCES_FILE.open("r", encoding="utf-8") as preferences_file:
            preferences = json.load(preferences_file)
    except FileNotFoundError:
        preferences = {}
    preferences[str(user_id)] = direction
    _save_json(PREFERENCES_FILE, preferences)


def get_user_dictionary(user_id):
    dictionaries = _load_all_dictionaries()
    entries = dictionaries.get(str(user_id), {})
    if not isinstance(entries, dict):
        return {}
    return entries


def add_dictionary_entry(user_id, latin, cyrillic):
    latin = latin.strip()
    cyrillic = cyrillic.strip()
    if not LATIN_TERM.fullmatch(latin) or not CYRILLIC_TERM.fullmatch(cyrillic):
        raise ValueError("Lotin va kiril yozuvini tekshiring; faqat so'z yoki ibora kiriting.")

    dictionaries = _load_all_dictionaries()
    entries = dictionaries.setdefault(str(user_id), {})
    if not isinstance(entries, dict):
        entries = {}
        dictionaries[str(user_id)] = entries

    for existing in list(entries):
        if existing.casefold() == latin.casefold():
            del entries[existing]
    if len(entries) >= 100:
        raise ValueError("Shaxsiy lug'atda eng ko'pi bilan 100 ta qoida saqlash mumkin.")

    entries[latin] = cyrillic
    _save_all_dictionaries(dictionaries)


def remove_dictionary_entry(user_id, latin):
    dictionaries = _load_all_dictionaries()
    entries = dictionaries.get(str(user_id), {})
    if not isinstance(entries, dict):
        return False

    for existing in list(entries):
        if existing.casefold() == latin.strip().casefold():
            del entries[existing]
            if not entries:
                dictionaries.pop(str(user_id), None)
            _save_all_dictionaries(dictionaries)
            return True
    return False


def _contains_cyrillic(text):
    return any("А" <= character <= "я" or character in "ЁёЎўҚқҒғҲҳ" for character in text)


def _match_case(source, replacement):
    if source.isupper():
        return replacement.upper()
    if source.istitle():
        return replacement.title()
    return replacement


def _apply_dictionary(text, entries, direction):
    if not entries:
        return to_cyrillic(text) if direction == "latin_to_cyrillic" else to_latin(text)

    if direction == "latin_to_cyrillic":
        pairs = {source.casefold(): target for source, target in entries.items()}
        source_terms = list(entries)
        converter = to_cyrillic
    else:
        pairs = {target.casefold(): source for source, target in entries.items()}
        source_terms = list(entries.values())
        converter = to_latin

    unique_terms = sorted(set(source_terms), key=len, reverse=True)
    if not unique_terms:
        return converter(text)
    pattern = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(term) for term in unique_terms) + r")(?!\w)",
        re.IGNORECASE,
    )

    converted_parts = []
    previous_end = 0
    for match in pattern.finditer(text):
        converted_parts.append(converter(text[previous_end:match.start()]))
        replacement = pairs[match.group().casefold()]
        converted_parts.append(_match_case(match.group(), replacement))
        previous_end = match.end()
    converted_parts.append(converter(text[previous_end:]))
    return "".join(converted_parts)


def transliterate_for_user(text, direction="auto", dictionary=None):
    if direction not in DIRECTIONS:
        direction = "auto"
    if direction == "auto":
        direction = "cyrillic_to_latin" if _contains_cyrillic(text) else "latin_to_cyrillic"
    return _apply_dictionary(text, dictionary or {}, direction)


def transliteration_candidates(text, direction="auto", dictionary=None):
    dictionary = dictionary or {}
    if direction not in DIRECTIONS:
        direction = "auto"
    if direction == "auto":
        direction = "cyrillic_to_latin" if _contains_cyrillic(text) else "latin_to_cyrillic"

    primary = transliterate_for_user(text, direction, dictionary)
    candidates = [primary]
    if direction != "latin_to_cyrillic":
        return candidates

    dictionary_terms = {term.casefold() for term in dictionary}
    vowels = "aeiou"
    for word_match in re.finditer(r"[A-Za-z][A-Za-z'’‘ʻʼ]*", text):
        word = word_match.group()
        if word.casefold() in dictionary_terms:
            continue
        lowered_word = word.lower()
        position = 0
        while position < len(word):
            preceding_vowel = position == 0 or lowered_word[position - 1] in vowels
            if preceding_vowel and lowered_word.startswith("ye", position):
                original = word[position:position + 2]
                replacement = _match_case(original, "e")
            elif preceding_vowel and lowered_word[position] == "e":
                original = word[position]
                replacement = _match_case(original, "ye")
            else:
                position += 1
                continue

            alternative_word = word[:position] + replacement + word[position + len(original):]
            alternative_text = (
                text[:word_match.start()]
                + alternative_word
                + text[word_match.end():]
            )
            alternative = transliterate_for_user(alternative_text, direction, dictionary)
            if alternative not in candidates:
                candidates.append(alternative)
                if len(candidates) == 3:
                    return candidates
            position += len(original)
    return candidates
