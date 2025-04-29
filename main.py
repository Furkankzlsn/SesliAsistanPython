import tkinter as tk
from tkinter import ttk
import threading
import sounddevice as sd
import queue
import vosk
import json
import os
from gtts import gTTS
from playsound import playsound
import tempfile
from PIL import Image, ImageTk
import io
import base64

# Check for optional packages
try:
    import pyaudio
    import numpy as np
    WAKE_WORD_AVAILABLE = True
except ImportError:
    WAKE_WORD_AVAILABLE = False
    print("Uyarı: Pasif dinleme için gerekli modüller yüklenmemiş. 'pip install pyaudio numpy' komutunu çalıştırın.")

# Ses verisini almak için bir kuyruk oluştur
q = queue.Queue()
# Pasif dinleme için ayrı bir kuyruk oluştur
passive_q = queue.Queue()

# Dinleme durumunu takip etmek için global değişken
is_listening = False
passive_listening_active = False

# Add helper function for TTS to avoid code duplication
def say_response(text, lang="tr"):
    """Text to speech helper function"""
    tts = gTTS(text=text, lang=lang)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        temp_file = f.name
    tts.save(temp_file)
    playsound(temp_file)
    try:
        os.remove(temp_file)  # MP3 çaldıktan sonra temizle
    except:
        pass

# Update speak_text function to use the helper
def speak_text():
    text = result_text.get()
    if text:
        say_response(text)

# Model yükleme
model_path = "models/vosk-model-small-tr-0.3"
if not os.path.exists(model_path):
    print("Model bulunamadı. Lütfen 'models/vosk-model-small-tr-0.3' dizinine Türkçe modeli indiriniz.")
    exit(1)

model = vosk.Model(model_path)

# Mikrofon callback fonksiyonu
def callback(indata, frames, time, status):
    if status:
        print(status)
    q.put(bytes(indata))

# Konuşmayı yazıya çeviren fonksiyon
def recognize():
    global is_listening
    rec = vosk.KaldiRecognizer(model, 16000)
    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                          channels=1, callback=callback):
        print("Dinlemeye başladı...")
        is_listening = True
        listening_label.config(text="Dinleniyor")
        status_indicator.config(bg="#facc15")  # Sarı ışık - dinliyor
        animate_listening()
        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "")
                if text:
                    print("Algılanan:", text)
                    result_text.set(text)
                    is_listening = False
                    listening_label.config(text="")
                    status_indicator.config(bg="#10b981")  # Yeşil ışık - tamamlandı
                    window.after(2000, lambda: status_indicator.config(bg="#6b7280"))  # 2 saniye sonra gri ışığa dön
                    break

# Butona tıklayınca konuşmayı başlat
def start_recognition():
    threading.Thread(target=recognize, daemon=True).start()

# "Dinleniyor..." animasyonu
def animate_listening():
    if not is_listening:
        return
    
    current = listening_label.cget("text")
    if "..." in current:
        listening_label.config(text="Dinleniyor")
    else:
        listening_label.config(text=current + ".")
    
    if is_listening:
        window.after(500, animate_listening)

# Hover efekti eklemek için fonksiyon
def on_enter(e):
    e.widget['background'] = e.widget.hover_color

def on_leave(e):
    e.widget['background'] = e.widget.normal_color

# Yuvarlak köşeli çerçeve için özel sınıf
class RoundedFrame(tk.Canvas):
    def __init__(self, parent, bg, width, height, radius=20, **kwargs):
        super().__init__(parent, width=width, height=height, bg=bg, 
                         highlightthickness=0, **kwargs)
        self._create_rounded_rect(0, 0, width, height, radius, fill=bg, outline=bg)
        
    def _create_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius, y1,
                 x2-radius, y1,
                 x2, y1,
                 x2, y1+radius,
                 x2, y2-radius,
                 x2, y2,
                 x2-radius, y2,
                 x1+radius, y2,
                 x1, y2,
                 x1, y2-radius,
                 x1, y1+radius,
                 x1, y1]
        return self.create_polygon(points, **kwargs, smooth=True)

# Özel yuvarlak buton sınıfı oluşturalım
class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command, width=200, height=40, 
                 radius=20, bg="#0d6efd", hover_bg="#0b5ed7", fg="#ffffff", 
                 font=("Segoe UI", 12, "bold"), **kwargs):
        super().__init__(parent, width=width, height=height, 
                         bg=parent["bg"], highlightthickness=0, **kwargs)
        self.text = text
        self.command = command
        self.radius = radius
        self.bg = bg
        self.hover_bg = hover_bg
        self.fg = fg
        self.font = font
        self.width_val = width
        self.height_val = height
        
        # Buton durumu
        self.active = False
        
        # Configure event binding
        self.bind("<Configure>", self._on_configure)
        
        # Olaylar
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        
        # Initial draw (delay slightly to ensure widget is created)
        self.after(10, lambda: self._draw_button(bg))
        
    def _on_configure(self, event):
        # Update stored dimensions when widget is resized
        self.width_val = event.width
        self.height_val = event.height
        self._draw_button(self.bg)
        
    def _draw_button(self, bg_color):
        # Eski çizimleri temizle
        self.delete("all")
        
        # Use stored dimensions instead of winfo calls
        w = self.width_val
        h = self.height_val
        
        # Yuvarlak köşeli dikdörtgen
        self.create_rounded_rect(0, 0, w, h, 
                                self.radius, fill=bg_color, outline=bg_color)
        
        # Metin
        text_x = w / 2
        text_y = h / 2
        self.create_text(text_x, text_y, text=self.text, fill=self.fg, 
                        font=self.font)
    
    def create_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius, y1,
                 x2-radius, y1,
                 x2, y1,
                 x2, y1+radius,
                 x2, y2-radius,
                 x2, y2,
                 x2-radius, y2,
                 x1+radius, y2,
                 x1, y2,
                 x1, y2-radius,
                 x1, y1+radius,
                 x1, y1]
        return self.create_polygon(points, **kwargs, smooth=True)
    
    def _on_enter(self, event):
        self._draw_button(self.hover_bg)
        
    def _on_leave(self, event):
        self._draw_button(self.bg)
        
    def _on_press(self, event):
        self.active = True
        self._draw_button(self.hover_bg)
        
    def _on_release(self, event):
        if self.active:
            self.active = False
            self._draw_button(self.bg)
            if self.command:
                self.command()

# ---- Tkinter Arayüzü ----
window = tk.Tk()
window.title("Sesli Asistan")
window.geometry("600x650")
window.configure(bg="#0d1117")  # Koyu arka plan

# Stil tanımlamaları
COLORS = {
    "bg_dark": "#0d1117",
    "bg_medium": "#161b22",
    "bg_light": "#21262d",
    "text_primary": "#ffffff",
    "text_secondary": "#c9d1d9",
    "accent_blue": "#3b82f6",
    "accent_blue_hover": "#60a5fa",
    "accent_green": "#238636",
    "accent_green_hover": "#2ea043",
    "accent_cyan": "#00ffea",
    "accent_yellow": "#facc15",
    "accent_purple": "#8b5cf6",
    "border": "#30363d"
}

result_text = tk.StringVar()

# Genel Font
default_font = ("Segoe UI", 14)
header_font = ("Segoe UI", 24, "bold")
small_font = ("Segoe UI", 12)
button_font = ("Segoe UI", 14, "bold")

# Ana çerçeve oluştur
main_frame = tk.Frame(window, bg=COLORS["bg_dark"], padx=20, pady=20)
main_frame.pack(fill=tk.BOTH, expand=True)

# Başlık Alanı
header_frame = RoundedFrame(main_frame, COLORS["accent_purple"], 560, 80, radius=15)
header_frame.pack(pady=(0, 20), fill=tk.X)

title_label = tk.Label(header_frame, text="SESLİ ASİSTAN", font=header_font, 
                      bg=COLORS["accent_purple"], fg=COLORS["text_primary"])
title_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

# Durum göstergesi
status_frame = tk.Frame(main_frame, bg=COLORS["bg_dark"])
status_frame.pack(fill=tk.X, pady=(0, 15))

status_indicator = tk.Label(status_frame, text="", width=2, height=2, bg="#6b7280")
status_indicator.pack(side=tk.LEFT, padx=(0, 10))

listening_label = tk.Label(status_frame, text="", font=small_font, 
                          bg=COLORS["bg_dark"], fg=COLORS["accent_yellow"])
listening_label.pack(side=tk.LEFT)

# Pasif dinleme durumu için gösterge
passive_status_frame = tk.Frame(main_frame, bg=COLORS["bg_dark"])
passive_status_frame.pack(fill=tk.X, pady=(0, 10))

passive_indicator = tk.Label(passive_status_frame, text="", width=2, height=2, bg="#6b7280")
passive_indicator.pack(side=tk.LEFT, padx=(0, 10))

passive_label = tk.Label(passive_status_frame, text="Pasif Dinleme: Kapalı", font=small_font, 
                        bg=COLORS["bg_dark"], fg=COLORS["text_secondary"])
passive_label.pack(side=tk.LEFT)

# Çıktı alanı
output_label = tk.Label(main_frame, text="Algılanan Konuşma:", 
                       font=("Segoe UI", 16, "bold"), bg=COLORS["bg_dark"], 
                       fg=COLORS["text_primary"])
output_label.pack(anchor=tk.W, pady=(0, 5))

output_frame = RoundedFrame(main_frame, COLORS["bg_medium"], 560, 200, radius=15)
output_frame.pack(fill=tk.X, pady=(0, 25))

result_display = tk.Label(output_frame, textvariable=result_text, wraplength=500, 
                         font=default_font, bg=COLORS["bg_medium"], fg=COLORS["accent_cyan"],
                         justify=tk.LEFT, padx=15, pady=15)
result_display.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

# Buton alanı
button_frame = tk.Frame(main_frame, bg=COLORS["bg_dark"])
button_frame.pack(fill=tk.X, pady=10)

# Bootstrap benzeri renkler
BOOTSTRAP_COLORS = {
    "primary": "#0d6efd",  # Mavi
    "primary_hover": "#0b5ed7",
    "success": "#198754",  # Yeşil
    "success_hover": "#157347",
    "info": "#0dcaf0",     # Açık mavi
    "info_hover": "#31d2f2",
    "warning": "#ffc107",  # Sarı
    "warning_hover": "#ffca2c",
    "danger": "#dc3545",   # Kırmızı
    "danger_hover": "#bb2d3b",
    "dark": "#212529",     # Koyu gri
    "dark_hover": "#424649"
}

def toggle_passive_listening():
    global passive_listening_active
    
    if not WAKE_WORD_AVAILABLE:
        result_text.set("Pasif dinleme için gerekli modüller yüklenmemiş. 'pip install pyaudio numpy' komutunu çalıştırın.")
        return
        
    passive_listening_active = not passive_listening_active
    
    if passive_listening_active:
        passive_indicator.config(bg=COLORS["accent_blue"])
        passive_label.config(text="Pasif Dinleme: Açık", fg=COLORS["accent_blue"])
        # Start passive listening in a thread
        threading.Thread(target=passive_listen_loop, daemon=True).start()
    else:
        passive_indicator.config(bg="#6b7280")
        passive_label.config(text="Pasif Dinleme: Kapalı", fg=COLORS["text_secondary"])

# Butonları oluştur - Fix button alignment with proper padding
start_button = RoundedButton(
    button_frame, 
    text="Konuşmayı Başlat", 
    command=start_recognition,
    width=170, 
    height=50,
    bg=BOOTSTRAP_COLORS["success"],
    hover_bg=BOOTSTRAP_COLORS["success_hover"],
    fg=COLORS["text_primary"]
)
start_button.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)

speak_button = RoundedButton(
    button_frame, 
    text="Yazıyı Oku", 
    command=speak_text,
    width=170, 
    height=50,
    bg=BOOTSTRAP_COLORS["primary"],
    hover_bg=BOOTSTRAP_COLORS["primary_hover"],
    fg=COLORS["text_primary"]
)
speak_button.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)  # Add right padding

# Add passive listening toggle button
passive_button = RoundedButton(
    button_frame, 
    text="Pasif Dinleme", 
    command=toggle_passive_listening,
    width=170, 
    height=50,
    bg=BOOTSTRAP_COLORS["info"],
    hover_bg=BOOTSTRAP_COLORS["info_hover"],
    fg=COLORS["text_primary"]
)
passive_button.pack(side=tk.LEFT, fill=tk.X, expand=True)  # Remove right padding (it's the last button)

# Yardım ve bilgiler
help_frame = RoundedFrame(main_frame, COLORS["bg_light"], 560, 150, radius=15)
help_frame.pack(fill=tk.X, pady=(25, 0))

help_text = """• Konuşmayı başlatmak için 'Konuşmayı Başlat' butonuna tıklayın.
• Algılanan metni duymak için 'Yazıyı Oku' butonuna tıklayın.
• Pasif dinleme modunda 'Bilgisayar' diyerek asistanı aktif edebilirsiniz.
• Sarı ışık: Dinleniyor, Yeşil ışık: Tamamlandı, Mavi ışık: Pasif dinleme aktif"""

help_label = tk.Label(help_frame, text=help_text, font=small_font,
                     bg=COLORS["bg_light"], fg=COLORS["text_secondary"],
                     justify=tk.LEFT, padx=15, pady=15)
help_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

# Alt bilgi
footer = tk.Label(main_frame, text="© 2025 Sesli Asistan v1.0", 
                 font=("Segoe UI", 9), bg=COLORS["bg_dark"], fg=COLORS["text_secondary"])
footer.pack(pady=(20, 0))

# Pasif dinleme için ses callback fonksiyonu
def passive_callback(indata, frames, time, status):
    if status:
        print(status)
    passive_q.put(bytes(indata))

def passive_listen_loop():
    global passive_listening_active
    
    try:
        # Vosk modelini kullan
        rec = vosk.KaldiRecognizer(model, 16000)
        
        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                              channels=1, callback=passive_callback):
            
            print("Pasif dinleme başlatıldı... ('Bilgisayar' komutunu bekliyor)")
            result_text.set("Pasif dinleme aktif. 'Bilgisayar' diyerek beni çağırabilirsiniz.")
            
            while passive_listening_active:
                data = passive_q.get()
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").lower()
                    print(f"Pasif dinleme duydu: {text}")
                    
                    # Wake word tespiti - 'bilgisayar' kelimesi var mı?
                    if "bilgisayar" in text:
                        print("WAKE WORD ALGILANDI: Bilgisayar")
                        result_text.set("Sizi dinliyorum...")
                        
                        # Sesli yanıt ver
                        window.after(0, lambda: say_response("Sizi dinliyorum"))
                        
                        # Ses kaydını durdur çünkü başka bir kod dinlemeye başlayacak
                        passive_listening_active = False
                        passive_indicator.config(bg="#6b7280")
                        passive_label.config(text="Pasif Dinleme: Kapalı", fg=COLORS["text_secondary"])
                        
                        # Kısa bir duraklama ile ana dinlemeyi başlat
                        window.after(1000, start_recognition)  # Ana thread'de dinlemeyi başlat
                        break
                
    except Exception as e:
        print(f"Pasif dinleme başlatma hatası: {e}")
        result_text.set(f"Pasif dinleme başlatılamadı: {str(e)}")
        passive_listening_active = False
        passive_indicator.config(bg="#6b7280")
        passive_label.config(text="Pasif Dinleme: Hata", fg=BOOTSTRAP_COLORS["danger"])
    finally:
        # Temizleme
        passive_indicator.config(bg="#6b7280")
        passive_label.config(text="Pasif Dinleme: Kapalı", fg=COLORS["text_secondary"])

# Başlangıçta pasif dinlemeyi açma
# Numpy gerekli - import ekleyelim
try:
    import numpy as np
except ImportError:
    print("Numpy bulunamadı. 'pip install numpy' komutunu çalıştırın.")

# Pasif dinlemeyi otomatik başlatmıyoruz, kullanıcının manuel olarak açması gerekiyor
window.mainloop()