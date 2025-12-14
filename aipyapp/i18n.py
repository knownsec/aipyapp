#!/usr/bin/env python
# -*- coding: utf-8 -*-

import locale
import csv
from importlib import resources
import os
import ctypes
import platform

from loguru import logger

def get_system_language() -> str:
    """
    Get the current runtime environment language code (e.g., 'en', 'zh').
    Supports Windows, macOS, Linux.
    Returns lowercase language code, defaults to 'en' if unable to determine.
    """
    language_code = 'en' # Default to English

    try:
        if platform.system() == "Windows":
            # Windows: Use GetUserDefaultUILanguage or GetSystemDefaultUILanguage
            # https://learn.microsoft.com/en-us/windows/win32/intl/language-identifiers
            windll = ctypes.windll.kernel32
            # GetUserDefaultUILanguage returns the current user's UI language ID
            lang_id = windll.GetUserDefaultUILanguage()
            # Convert language ID to standard language code (e.g., 1033 -> en, 2052 -> zh)
            # Primary language ID is in the low 10 bits
            primary_lang_id = lang_id & 0x3FF
            if primary_lang_id == 0x04: # zh - Chinese
                language_code = 'zh'
            elif primary_lang_id == 0x09: # en - English
                language_code = 'en'
            # Additional language ID mappings can be added as needed
            # Reference: https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-lcid/a9eac961-e77d-41a6-90a5-ce1a8b0cdb9c

        elif platform.system() == "Darwin": # macOS
            # macOS: Prefer using locale.getlocale()
            language, encoding = locale.getlocale()
            if language:
                language_code = language.split('_')[0].lower()
            else:
                # Fallback: Read environment variables
                lang_env = os.environ.get('LANG')
                if lang_env:
                    language_code = lang_env.split('_')[0].lower()

        else: # Linux/Unix
            # Linux/Unix: Prefer using locale.getlocale()
            language, encoding = locale.getlocale()
            if language:
                language_code = language.split('_')[0].lower()
            else:
                # Fallback: Read environment variables LANG or LANGUAGE
                lang_env = os.environ.get('LANG') or os.environ.get('LANGUAGE')
                if lang_env:
                    language_code = lang_env.split('_')[0].lower()

        # Normalize common Chinese language codes
        if language_code.startswith('zh'):
            language_code = 'zh'

    except Exception:
        # If any error occurs, fallback to default value 'en'
        pass # Use default 'en'

    return language_code

class Translator:
    def __init__(self, lang=None):
        self.lang = lang
        self.messages = {}
        self.log = logger.bind(src='i18n')

    def get_lang(self):
        return self.lang

    def set_lang(self, lang=None):
        """Set the current language."""
        if not lang:
            lang = get_system_language()
            self.log.info(f"No language specified, using system language: {lang}")

        if lang != self.lang:
            if self.lang: self.log.info(f"Switching language from {self.lang} to: {lang}")
            else: self.log.info(f"Setting language to: {lang}")
            self.lang = lang
            self.load_messages()

    def load_messages(self):
        try:
            with resources.open_text('aipyapp.res', 'locales.csv') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.messages[row['en']] = None if self.lang=='en' else row.get(self.lang)
        except Exception as e:
            self.log.error(f"Error loading translations: {e}")

    def translate(self, key, *args):
        if not self.lang:
            self.set_lang()

        if self.lang == 'en':
            msg = key
        else:
            msg = self.messages.get(key)
            if not msg:
                self.log.error(f"Translation not found for key: {key}")
                msg = key
        return msg.format(*args) if args else msg   

translator = Translator()
T = translator.translate
get_lang = translator.get_lang
set_lang = translator.set_lang
