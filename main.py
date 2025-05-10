import threading
import sounddevice as sd
import queue
import vosk
import json
import os
from gtts import gTTS
import tempfile
import configparser
import webbrowser
import subprocess
import sys
import datetime
import re
import numpy as np
import random
import time
import hashlib
import logging
from settings import Settings
import concurrent.futures
import requests

url = "http://192.168.1.19:5000/endpoint"
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

from assistant_logic import say_response, generate_chat_response

from deneme import process_command

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('assistant.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

try:
    import pyaudio
    WAKE_WORD_AVAILABLE = True
except ImportError:
    WAKE_WORD_AVAILABLE = False
    logging.warning("Uyarı: Pasif dinleme için gerekli modüller yüklenmemiş. 'pip install pyaudio numpy' komutunu çalıştırın.")

q = queue.Queue()
passive_q = queue.Queue()

is_listening = False
passive_listening_active = False
is_speaking = False
app_running = True
border_effect_process = None
is_chatting = False

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'tts_cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
CACHE_TTL = 7 * 24 * 3600
_now = time.time()
for _file in os.listdir(CACHE_DIR):
    _path = os.path.join(CACHE_DIR, _file)
    if os.path.isfile(_path) and _now - os.path.getmtime(_path) > CACHE_TTL:
        try:
            os.remove(_path)
        except Exception:
            pass

tts_cache = {}

audio_input_device = None
audio_output_device = None

# ...UI-related classes and functions removed...

model_path = "models/vosk-model-small-tr-0.3"
if not os.path.exists(model_path):
    logging.error("Model bulunamadı. Lütfen 'models/vosk-model-small-tr-0.3' dizinine Türkçe modeli indiriniz.")
    exit(1)

model = vosk.Model(model_path)

model_path2 = "models/vosk-model-small-en-us-0.15"
if not os.path.exists(model_path2):
    logging.error("Model bulunamadı. Lütfen 'models/vosk-model-small-en-us-0.15' dizinine English modeli indiriniz.")
    exit(1)

model_en = vosk.Model(model_path2)

def callback(indata, frames, time, status):
    global is_speaking
    if status:
        logging.warning(f"Ses yakalama durumu: {status}")
    if is_speaking:
        return
    if indata is None or len(indata) == 0:
        logging.warning("Uyarı: Ses verisi boş geldi!")
        return
    try:
        q.put(bytes(indata))
    except Exception as e:
        logging.error(f"Callback hatası: {e}")

border_effect_active = False

def show_border_effect():
    global border_effect_process, border_effect_active
    if border_effect_active:
        return
    hide_border_effect()
    try:
        border_effect_process = subprocess.Popen([sys.executable, "border_effect.py", "--transparency", "0.9"])
        border_effect_active = True
    except Exception as e:
        logging.error(f"Error launching border effect: {e}")

def hide_border_effect():
    global border_effect_process, border_effect_active
    if border_effect_process is not None:
        try:
            logging.info("Terminating border effect process...")
            border_effect_process.terminate()
            border_effect_process = None
            border_effect_active = False
        except Exception as e:
            logging.error(f"Error closing border effect: {e}")
    else:
        border_effect_active = False

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
    if len(words) == 2:
        if words[0] in number_dict and words[1] in number_dict:
            tens = number_dict[words[0]]
            units = number_dict[words[1]]
            if tens % 10 == 0 and tens < 100 and units < 10:
                return tens + units
    return None

def stop_listening_and_cleanup():
    global is_listening, is_chatting
    logging.info("Dinleme sonlandırılıyor...")
    is_listening = False
    is_chatting = False
    try:
        sd.stop()
        start_passive_listening()
    except Exception as e:
        logging.error(f"Ses durdurma hatası: {e}")

def is_exit_command(query):
    exit_keywords = ["görüşürüz", "hoşça kal", "teşekkürler", "çıkış", "bay bay"]
    return any(keyword in query.lower() for keyword in exit_keywords)

def chat_mode():
    global is_listening, is_chatting
    logging.info("Sohbet modu başlatılıyor...")
    if is_chatting:
        logging.info("Zaten sohbet modundayız, tekrar başlatılmıyor.")
        return
    with q.mutex:
        q.queue.clear()
    try:
        rec = vosk.KaldiRecognizer(model, 16000)
        is_chatting = True
        is_listening = True
        say_response("Sohbet modu aktif. İstediğiniz zaman Görüşürüz veya Teşekkürler diyerek sonlandırabilirsiniz.")
        with sd.RawInputStream(device=audio_input_device, samplerate=16000, blocksize=8000, dtype='int16',
                              channels=1, callback=callback):
            logging.info("Sohbet modu başladı...")
            while is_chatting and is_listening:
                try:
                    data = q.get(timeout=0.1)
                except queue.Empty:
                    continue
                if not data:
                    continue
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "")
                    if text:
                        logging.info(f"Sohbet modunda algılanan: {text}")
                        chat_response, end_chat = generate_chat_response(text)
                        say_response(chat_response)
                        if end_chat:
                            logging.info("Sohbet sonlandırıldı.")
                            is_chatting = False
                            stop_listening_and_cleanup()
                            break
            if is_listening:
                stop_listening_and_cleanup()
    except Exception as e:
        logging.error(f"Sohbet modunda hata: {e}")
        import traceback; traceback.print_exc()
        is_chatting = False
        stop_listening_and_cleanup()

def recognize():
    global is_listening, is_chatting
    logging.info("Dinleme başlatılıyor...")
    rec = vosk.KaldiRecognizer(model, 16000)
    is_listening = True
    wait_for_yes_no = False
    wait_for_search = False
    with q.mutex:
        q.queue.clear()
    try:
        device_info = sd.query_devices(None, 'input')
        logging.info(f"Kullanılan mikrofon: {device_info['name']}")
        logging.info(f"Örnekleme Hızı: {device_info['default_samplerate']}")
        logging.info(f"Maksimum Giriş Kanalları: {device_info['max_input_channels']}")
        with sd.RawInputStream(device=audio_input_device, samplerate=16000, blocksize=8000, dtype='int16',
                              channels=1, callback=callback):
            logging.info("Mikrofon akışı başlatıldı, dinleniyor...")
            while is_listening:
                try:
                    data = q.get(timeout=0.1)
                except queue.Empty:
                    continue
                if not data:
                    continue
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "")
                    if text:
                        logging.info(f"Algılanan metin: {text}")
                        if wait_for_yes_no:
                            if "evet" in text.lower():
                                wait_for_yes_no = False
                                response = "Ne istersiniz?"
                                say_response(response)
                                continue
                            elif "hayır" in text.lower() or "hayir" in text.lower():
                                wait_for_yes_no = False
                                wake_word = settings.get("wake_word")
                                response = f"Görüşürüz, dilediğinde beni {wake_word} diyerek çağırabilirsin."
                                say_response(response)
                                stop_listening_and_cleanup()
                                break
                            else:
                                say_response("Lütfen evet veya hayır deyin.")
                                continue
                        if wait_for_search:
                            if "hayır" in text.lower() or "hayir" in text.lower():
                                wait_for_search = False
                                wake_word = settings.get("wake_word")
                                response = f"Tamamdır sadece Youtube açıyorum. Görüşürüz, dilediğinde beni {wake_word} diyerek çağırabilirsin."
                                data = {"result": "xxx", "cmd_type": "url", "target": "https://www.youtube.com/"}
                                try:
                                    response = requests.post(url, json=data)
                                except Exception as e:
                                    print("İstek gönderilirken hata oluştu:", e)
                                say_response(response)
                                stop_listening_and_cleanup()
                                break
                            else:
                                wait_for_search = False
                                wake_word = settings.get("wake_word")
                                response = f"Tamamdır, {text} aratıyorum. Görüşürüz, dilediğinde beni {wake_word} diyerek çağırabilirsin."
                                url2 = f"https://www.youtube.com/results?search_query={text}"
                                data = {"result": "xxx", "cmd_type": "url", "target": url2}
                                try:
                                    response = requests.post(url, json=data)
                                except Exception as e:
                                    print("İstek gönderilirken hata oluştu:", e)
                                say_response(response)
                                stop_listening_and_cleanup()
                                break
                        if "iptal" in text.lower() or "dur" in text.lower():
                            say_response("İptal edildi", settings.get("language"))
                            stop_listening_and_cleanup()
                            break
                        if any(x in text.lower() for x in ["sohbet", "konuş", "konuşalım"]):
                            chat_mode()
                            break
                        command_found = process_command(text)
                        command_keyword = text if command_found else None
                        command_keyword = None
                        for keyword in settings.get_all_commands():
                            if keyword in text.lower():
                                command_keyword = keyword
                                break
                        if not command_keyword:
                            for word in text.lower().split():
                                if word in settings.get_all_commands():
                                    command_keyword = word
                                    break
                        if command_found and command_keyword:
                            response = f"Tamamdır, {command_keyword} açıyorum. Başka bir işlem ister misiniz?"
                            say_response(response)
                            wait_for_yes_no = True
                            with q.mutex:
                                q.queue.clear()
                            continue
                        if "merhaba" in text.lower() or "selam" in text.lower():
                            with q.mutex:
                                q.queue.clear()
                            help_msg = "Merhaba! Nasılsınız? Size nasıl yardımcı olabilirim?"
                            executor.submit(say_response, help_msg)
                            time.sleep(0.5)
                            continue
                        if "video" in text.lower():
                            with q.mutex:
                                q.queue.clear()
                            help_msg = "İzlemek istediğin bir video var mı? Varsa söyle Youtube'da aratayım yoksa sadece aç diyebilirsin."
                            executor.submit(say_response, help_msg)
                            wait_for_search = True
                            time.sleep(0.5)
                            continue
                        if "nasılsın" in text.lower():
                            with q.mutex:
                                q.queue.clear()
                            help_msg = "Ben bir yapay zeka asistanıyım, duygularım yok ama size yardımcı olmak için buradayım!"
                            executor.submit(say_response, help_msg)
                            time.sleep(0.5)
                            continue
                        if "uyku modu" in text.lower():
                            with q.mutex:
                                q.queue.clear()
                            help_msg = "Bilgisayarınızı uyku moduna alıyorum."
                            executor.submit(say_response, help_msg)
                            def sleep_computer():
                                time.sleep(3)
                                data = {"result": "xxx", "cmd_type": "uyku modu", "target": "bilgisayarı uyku moduna al"}
                                try:
                                    response = requests.post(url, json=data)
                                except Exception as e:
                                    print("İstek gönderilirken hata oluştu:", e)
                            executor.submit(sleep_computer)
                            time.sleep(0.5)
                            stop_listening_and_cleanup()
                            break
                        if "bilgisayarı kapat" in text.lower():
                            with q.mutex:
                                q.queue.clear()
                            help_msg = "Tamamdır, bilgisayar kapanıyor. Görüşürüz!"
                            executor.submit(say_response, help_msg)
                            def shutdown_computer():
                                time.sleep(3)
                                data = {"result": "xxx", "cmd_type": "bilgisayarı kapat", "target": "bilgisayarı kapat"}
                                try:
                                    response = requests.post(url, json=data)
                                except Exception as e:
                                    print("İstek gönderilirken hata oluştu:", e)
                            executor.submit(shutdown_computer)
                            time.sleep(0.5)
                            stop_listening_and_cleanup()
                            break
                        help_msg = "Dediğinizi anlayamadım. Lütfen tekrar deneyin."
                        say_response(help_msg)
                        with q.mutex:
                            q.queue.clear()
                        continue
                elif random.randint(1, 500) == 1:
                    partial = json.loads(rec.PartialResult())
                    partial_text = partial.get("partial", "")
                    if partial_text:
                        logging.info(f"Kısmi algılama: {partial_text}")
    except Exception as e:
        logging.error(f"Ses yakalama hatası: {e}")
        import traceback; traceback.print_exc()
        stop_listening_and_cleanup()

def start_recognition():
    global passive_listening_active, is_listening
    logging.info("Manuel dinleme başlatılıyor...")
    was_passive_active = passive_listening_active
    if was_passive_active:
        passive_listening_active = False
    is_listening = False
    sd.stop()
    with q.mutex:
        q.queue.clear()
    time.sleep(0.5)
    is_listening = True
    executor.submit(recognize)

def passive_callback(indata, frames, time, status):
    global is_speaking
    if status:
        logging.warning(status)
    if is_speaking:
        return
    passive_q.put(bytes(indata))

def passive_listen_loop():
    global passive_listening_active
    logging.info("Pasif dinleme başlatılıyor...")
    try:
        rec = vosk.KaldiRecognizer(model_en, 16000, '["jarvis", "carviz", "çervis"]')
        with passive_q.mutex:
            passive_q.queue.clear()
        with sd.RawInputStream(device=audio_input_device, samplerate=16000, blocksize=8000, dtype='int16',
                              channels=1, callback=passive_callback):
            wake_word = settings.get("wake_word")
            logging.info(f"Pasif dinleme başlatıldı... ('{wake_word}' komutunu bekliyor)")
            while passive_listening_active:
                if passive_q.empty():
                    sd.sleep(10)
                    continue
                data = passive_q.get()
                if len(data) == 0:
                    continue
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").lower()
                    if text:
                        logging.info(f"Pasif dinleme duydu: {text}")
                        # Split recognized text into words and check for exact match
                        recognized_words = text.split()
                        if wake_word.lower() in recognized_words:
                            logging.info(f"WAKE WORD ALGILANDI: {wake_word}")
                            say_response("Sizi dinliyorum ne yapmak istersiniz?", settings.get("language"))
                            passive_listening_active = False
                            time.sleep(1.5)
                            start_recognition()
                            break
    except Exception as e:
        if not app_running:
            return
        logging.error(f"Pasif dinleme hatası: {e}")
        import traceback; traceback.print_exc()
        passive_listening_active = False

def apply_audio_device_settings():
    logging.info("Applying audio device settings...")
    global audio_input_device, audio_output_device
    try:
        default_input, default_output = sd.default.device
    except Exception:
        default_input = default_output = sd.default.device
    in_name = settings.get("input_device")
    out_name = settings.get("output_device")
    input_idx = default_input
    output_idx = default_output
    idx = 0
    while True:
        try:
            info = sd.query_devices(idx)
            if info.get("name") == in_name and info.get("max_input_channels", 0) > 0:
                input_idx = idx
            if info.get("name") == out_name and info.get("max_output_channels", 0) > 0:
                output_idx = idx
            idx += 1
        except Exception:
            break
    audio_input_device = input_idx
    audio_output_device = output_idx
    logging.info(f"Selected devices: input={audio_input_device}, output={audio_output_device}")

settings = Settings()

def check_autostart_passive():
    apply_audio_device_settings()
    if settings.get("passive_listening"):
        update_passive_listening_state()

def update_passive_listening_state():
    global passive_listening_active
    should_be_active = settings.get("passive_listening")
    if passive_listening_active:
        passive_listening_active = False
        time.sleep(0.3)
        set_passive_listening(should_be_active)
    else:
        set_passive_listening(should_be_active)

def set_passive_listening(should_be_active):
    global passive_listening_active
    if should_be_active and not passive_listening_active:
        if WAKE_WORD_AVAILABLE:
            start_passive_listening()
        else:
            logging.warning("Pasif dinleme için gerekli modüller yüklenmemiş.")
    elif not should_be_active and passive_listening_active:
        passive_listening_active = False

def start_passive_listening():
    global passive_listening_active
    if not WAKE_WORD_AVAILABLE:
        logging.warning("Pasif dinleme için gerekli modüller yüklenmemiş.")
        return
    if not passive_listening_active and not is_listening:
        passive_listening_active = True
        apply_audio_device_settings()
        executor.submit(passive_listen_loop)

def on_closing():
    global app_running, passive_listening_active, is_listening
    logging.info("Application closing, cleaning up resources...")
    app_running = False
    passive_listening_active = False
    is_listening = False
    try: sd.stop()
    except: pass
    hide_border_effect()

if __name__ == "__main__":
    check_autostart_passive()
    try:
        while app_running:
            time.sleep(1)
    except KeyboardInterrupt:
        on_closing()
