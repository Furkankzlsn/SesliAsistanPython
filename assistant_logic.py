import os
import sys
import json
import random
import subprocess
import time
import hashlib
import logging
import queue
import requests
import sounddevice as sd
import vosk
from gtts import gTTS
import webbrowser
import numpy as np
from rapidfuzz import fuzz

from settings import Settings
url = "http://192.168.1.19:5000/endpoint"

# Initialize settings and queues
settings = Settings()
q = queue.Queue()
passive_q = queue.Queue()
with open("ayarlar.json", "r", encoding="utf-8") as f:
    config = json.load(f)
commands = config.get("commands", {})
# State flags
tts_cache = {}

# Ensure cache directory exists
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'tts_cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def play_audio(filepath):
    """
    Raspberry Pi ve diğer platformlarda playsound yerine subprocess ile ses dosyası oynatır.
    """
    import shutil
    import subprocess

    # Önce mpg123 var mı kontrol et (MP3 için)
    if shutil.which("mpg123"):
        subprocess.run(["mpg123", "-q", filepath])
    # Eğer yoksa aplay ile (WAV için)
    elif shutil.which("aplay"):
        subprocess.run(["aplay", filepath])
    # MacOS için afplay
    elif shutil.which("afplay"):
        subprocess.run(["afplay", filepath])
    else:
        raise RuntimeError("Ses oynatıcı bulunamadı (mpg123, aplay veya afplay gereklidir)")

# Text-to-speech helper with caching
def say_response(text, lang=None):
    """Text-to-speech helper function with caching."""
    # Compute cache key
    if lang is None:
        lang = settings.get("language")
    key = hashlib.md5((text + lang).encode('utf-8')).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{key}.mp3")
    # Generate if not cached
    if key not in tts_cache or not os.path.exists(cache_path):
        tts = gTTS(text=text, lang=lang)
        tts.save(cache_path)
        tts_cache[key] = cache_path
    # Play and cleanup
    play_audio(tts_cache[key])
    try:
        os.remove(cache_path)
    except Exception:
        pass
    tts_cache.pop(key, None)

# Chat response generator
def generate_chat_response(query):
    """Generate a simple AI chat response based on the query."""
    # Exit check
    exit_keywords = ["görüşürüz", "hoşça kal", "teşekkürler", "çıkış", "bay bay"]
    if any(keyword in query.lower() for keyword in exit_keywords):
        responses = [
            "Görüşürüz! İyi günler!",
            "Hoşça kalın! Tekrar görüşmek üzere!",
            "Teşekkür ederim, başka bir zaman görüşürüz.",
            "İyi günler! Başka bir sorunuz olursa beni çağırabilirsiniz."
        ]
        return random.choice(responses), True
    # Greetings
    greetings = ["merhaba", "selam", "hey", "nasılsın"]
    if any(g in query.lower() for g in greetings):
        return random.choice([
            "Merhaba! Size nasıl yardımcı olabilirim?",
            "Selam! Bugün ne yapmak istersiniz?"
        ]), False
    # Default
    return random.choice([
        "Anladım, başka nasıl yardımcı olabilirim?",
        "Devam edin, sizi dinliyorum."
    ]), False

# Command processing with fuzzy matching
def process_command(text, threshold=75):
    text_lower = text.lower()

    for keyword, details in commands.items():
        if keyword in text_lower:
            send_command(details)
            return keyword

    best_keyword = None
    best_score = 0
    for keyword, details in commands.items():
        score = fuzz.ratio(text_lower, keyword)
        if score > best_score:
            best_keyword, best_score = keyword, score

    if best_score >= threshold:
        send_command(commands[best_keyword])
        return best_keyword
    else:
        print("Komut eşleşmedi")
    return None

def send_command(details):
    try:
        data = {"cmd_type": details["type"], "target": details["target"]}
        response = requests.post(url, json=data)
        print("Sunucudan yanıt:", response.json())
    except Exception as e:
        print("İstek gönderilirken hata:", e)


# Add Turkish number conversion helper
def turkish_number_to_digit(text):
    number_dict = {
        'sıfır': 0, 'bir': 1, 'iki': 2, 'üç': 3, 'dört': 4, 
        'beş': 5, 'altı': 6, 'yedi': 7, 'sekiz': 8, 'dokuz': 9,
        'on': 10, 'yirmi': 20, 'otuz': 30, 'kırk': 40, 'elli': 50, 
        'altmış': 60, 'yetmiş': 70, 'seksen': 80, 'doksan': 90,
        'yüz': 100, 'bin': 1000
    }
    text = text.lower()
    if text in number_dict:
        return number_dict[text]
    if text.isdigit():
        return int(text)
    words = text.split()
    if len(words) == 2 and words[0] in number_dict and words[1] in number_dict:
        tens, units = number_dict[words[0]], number_dict[words[1]]
        if tens % 10 == 0 and tens < 100 and units < 10:
            return tens + units
    return None

# Add cleanup listening state helper
def stop_listening_and_cleanup():
    global is_listening, is_chatting
    logging.info("Dinleme sonlandırılıyor...")
    is_listening = False
    is_chatting = False
    try:
        sd.stop()
    except Exception as e:
        logging.error(f"Ses durdurma hatası: {e}")
    return

# Add exit command checker
def is_exit_command(query):
    exit_keywords = ["görüşürüz", "hoşça kal", "teşekkürler", "çıkış", "bay bay"]
    return any(keyword in query.lower() for keyword in exit_keywords)