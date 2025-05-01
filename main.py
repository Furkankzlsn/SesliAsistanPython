import tkinter as tk
from tkinter import ttk, filedialog
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
import configparser
import webbrowser
import subprocess
import sys

# Import the border effect with QApplication
from PyQt5.QtWidgets import QApplication
import subprocess
import sys
import threading

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

# Global variable for border effect process - use subprocess instead of direct integration
border_effect_process = None

# Ayarlar için sınıf oluştur
class Settings:
    def __init__(self):
        self.config_file = "ayarlar.ini"
        self.config = configparser.ConfigParser()
        
        # Varsayılan değerler
        self.defaults = {
            "language": "tr",
            "voice_speed": "1.0",
            "voice_pitch": "1.0",
            "theme": "dark",
            "wake_word": "ceren",
            "passive_listening": "false"  # Yeni eklenen pasif dinleme ayarı
        }
        
        self.load()
        
        # Komut listesi bölümünü kontrol et
        if not self.config.has_section("Commands"):
            self.config.add_section("Commands")
            self.save()
    
    def load(self):
        # Ayarlar dosyası varsa yükle, yoksa varsayılanları kullan
        if os.path.exists(self.config_file):
            # UTF-8 kodlamasıyla dosyayı oku
            self.config.read(self.config_file, encoding='utf-8')
            if not self.config.has_section("Settings"):
                self.config.add_section("Settings")
                self.reset_to_defaults()
        else:
            self.config.add_section("Settings")
            self.reset_to_defaults()
    
    def save(self):
        # UTF-8 kodlamasıyla dosyaya yaz
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)
    
    def get(self, key):
        return self.config.get("Settings", key, fallback=self.defaults.get(key, ""))
    
    def set(self, key, value):
        if not self.config.has_section("Settings"):
            self.config.add_section("Settings")
        self.config.set("Settings", key, value)
    
    def reset_to_defaults(self):
        for key, value in self.defaults.items():
            self.set(key, value)
        self.save()
    
    def get_all_commands(self):
        """Tüm komutları bir sözlük olarak döndür"""
        if not self.config.has_section("Commands"):
            return {}
            
        commands = {}
        for key in self.config.options("Commands"):
            value = self.config.get("Commands", key)
            parts = value.split('|', 1) # komut türü|hedef
            if len(parts) == 2:
                commands[key] = {
                    "type": parts[0],
                    "target": parts[1]
                }
        return commands
    
    def add_command(self, keyword, cmd_type, target):
        """Yeni bir komut ekle"""
        if not self.config.has_section("Commands"):
            self.config.add_section("Commands")
        
        # Komut türü ve hedefi birlikte sakla
        value = f"{cmd_type}|{target}"
        self.config.set("Commands", keyword, value)
        self.save()
    
    def remove_command(self, keyword):
        """Komutu sil"""
        if self.config.has_section("Commands") and self.config.has_option("Commands", keyword):
            self.config.remove_option("Commands", keyword)
            self.save()

# Ayarlar penceresi sınıfı
class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.parent = parent
        self.settings = settings
        self.title("Ayarlar")
        self.geometry("500x500")  # Yükseklik arttırıldı (450->500)
        self.configure(bg=COLORS["bg_dark"])
        self.resizable(False, False)
        
        # Ayarlar değiştirildiğinde geçici olarak saklamak için
        self.temp_settings = {}
        for key in self.settings.defaults:
            self.temp_settings[key] = self.settings.get(key)
        
        self.create_widgets()
        
        # Pencere ortalama
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f'+{x}+{y}')
        
        # Modalı pencere olarak ayarla
        self.transient(parent)
        self.grab_set()
    
    def create_widgets(self):
        # Ana çerçeve
        main_frame = tk.Frame(self, bg=COLORS["bg_dark"], padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Başlık
        title_label = tk.Label(main_frame, text="Ayarlar", font=header_font, 
                               bg=COLORS["bg_dark"], fg=COLORS["text_primary"])
        title_label.pack(pady=(0, 20))
        
        # Ayarlar çerçevesi
        settings_frame = tk.Frame(main_frame, bg=COLORS["bg_medium"], padx=15, pady=15)
        settings_frame.pack(fill=tk.BOTH, expand=True)
        
        # Dil ayarları
        lang_frame = tk.Frame(settings_frame, bg=COLORS["bg_medium"])
        lang_frame.pack(fill=tk.X, pady=(0, 10))
        
        lang_label = tk.Label(lang_frame, text="Dil:", width=15, anchor="w",
                           font=default_font, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
        lang_label.pack(side=tk.LEFT)
        
        self.lang_var = tk.StringVar(value=self.temp_settings["language"])
        lang_combo = ttk.Combobox(lang_frame, textvariable=self.lang_var, 
                                 values=["tr", "en", "de", "fr", "es"], width=10)
        lang_combo.pack(side=tk.LEFT, padx=(0, 10))
        lang_combo.bind("<<ComboboxSelected>>", lambda e: self.update_temp_setting("language", self.lang_var.get()))
        
        # Ses hızı ayarı
        speed_frame = tk.Frame(settings_frame, bg=COLORS["bg_medium"])
        speed_frame.pack(fill=tk.X, pady=(0, 10))
        
        speed_label = tk.Label(speed_frame, text="Ses Hızı:", width=15, anchor="w",
                             font=default_font, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
        speed_label.pack(side=tk.LEFT)
        
        self.speed_var = tk.DoubleVar(value=float(self.temp_settings["voice_speed"]))
        speed_scale = ttk.Scale(speed_frame, from_=0.5, to=2.0, orient=tk.HORIZONTAL,
                               variable=self.speed_var, length=200)
        speed_scale.pack(side=tk.LEFT)
        speed_scale.bind("<ButtonRelease-1>", lambda e: self.update_temp_setting("voice_speed", str(self.speed_var.get())))
        
        speed_value = tk.Label(speed_frame, textvariable=self.speed_var,
                              width=4, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
        speed_value.pack(side=tk.LEFT, padx=(10, 0))
        
        # Tema ayarı
        theme_frame = tk.Frame(settings_frame, bg=COLORS["bg_medium"])
        theme_frame.pack(fill=tk.X, pady=(0, 10))
        
        theme_label = tk.Label(theme_frame, text="Tema:", width=15, anchor="w",
                             font=default_font, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
        theme_label.pack(side=tk.LEFT)
        
        self.theme_var = tk.StringVar(value=self.temp_settings["theme"])
        theme_combo = ttk.Combobox(theme_frame, textvariable=self.theme_var,
                                  values=["dark", "light"], width=10)
        theme_combo.pack(side=tk.LEFT)
        theme_combo.bind("<<ComboboxSelected>>", lambda e: self.update_temp_setting("theme", self.theme_var.get()))
        
        # Tetikleme kelimesi ayarı
        wake_frame = tk.Frame(settings_frame, bg=COLORS["bg_medium"])
        wake_frame.pack(fill=tk.X, pady=(0, 10))
        
        wake_label = tk.Label(wake_frame, text="Tetikleme Kelimesi:", width=15, anchor="w",
                            font=default_font, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
        wake_label.pack(side=tk.LEFT)
        
        self.wake_var = tk.StringVar(value=self.temp_settings["wake_word"])
        wake_entry = tk.Entry(wake_frame, textvariable=self.wake_var, width=20)
        wake_entry.pack(side=tk.LEFT)
        wake_entry.bind("<FocusOut>", lambda e: self.update_temp_setting("wake_word", self.wake_var.get()))
        
        # Pasif Dinleme Ayarı (YENİ)
        passive_frame = tk.Frame(settings_frame, bg=COLORS["bg_medium"])
        passive_frame.pack(fill=tk.X, pady=(0, 10))
        
        passive_label = tk.Label(passive_frame, text="Pasif Dinleme:", width=15, anchor="w",
                               font=default_font, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
        passive_label.pack(side=tk.LEFT)
        
        self.passive_var = tk.BooleanVar(value=self.temp_settings["passive_listening"].lower() == "true")
        passive_check = tk.Checkbutton(passive_frame, text="Aktif", variable=self.passive_var, 
                                      bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
                                      selectcolor=COLORS["bg_dark"], 
                                      command=lambda: self.update_temp_setting("passive_listening", str(self.passive_var.get()).lower()))
        passive_check.pack(side=tk.LEFT)
        
        # Butonlar çerçevesi
        button_frame = tk.Frame(main_frame, bg=COLORS["bg_dark"], pady=10)
        button_frame.pack(fill=tk.X)
        
        # Kaydet butonu
        save_button = RoundedButton(
            button_frame,
            text="Kaydet",
            command=self.save_settings,
            width=100,
            height=40,
            bg=BOOTSTRAP_COLORS["success"],
            hover_bg=BOOTSTRAP_COLORS["success_hover"],
            fg=COLORS["text_primary"]
        )
        save_button.pack(side=tk.RIGHT, padx=(10, 0))
        
        # İptal butonu
        cancel_button = RoundedButton(
            button_frame,
            text="İptal",
            command=self.destroy,
            width=100,
            height=40,
            bg=BOOTSTRAP_COLORS["danger"],
            hover_bg=BOOTSTRAP_COLORS["danger_hover"],
            fg=COLORS["text_primary"]
        )
        cancel_button.pack(side=tk.RIGHT)
        
    def update_temp_setting(self, key, value):
        self.temp_settings[key] = value
        
    def save_settings(self):
        # Detect wake word changes
        old_wake_word = settings.get("wake_word") 
        new_wake_word = self.temp_settings["wake_word"]
        wake_word_changed = old_wake_word != new_wake_word
        
        # Ayarları kaydet
        for key, value in self.temp_settings.items():
            self.settings.set(key, value)
        self.settings.save()
        
        # Pasif dinleme durumunu kontrol et ve gerekirse başlat/durdur
        old_passive = passive_listening_active
        new_passive = self.temp_settings["passive_listening"].lower() == "true"
        
        # Signal that we need to update UI elements
        window.after(100, update_ui_from_settings)
        
        # Pasif dinleme veya tetikleme kelimesi değiştiğinde güncelle
        if old_passive != new_passive or (wake_word_changed and passive_listening_active):
            window.after(200, update_passive_listening_state)
            
            # Wake word değiştiyse ve pasif dinleme aktifse yeni kelimeyi göster
            if wake_word_changed and passive_listening_active:
                result_text.set(f"Pasif dinleme aktif. '{new_wake_word}' diyerek beni çağırabilirsiniz.")
                
        self.destroy()

# Komut listesi penceresi
class CommandListDialog(tk.Toplevel):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.parent = parent
        self.settings = settings
        self.title("Komut Listesi")
        self.geometry("700x500")
        self.configure(bg=COLORS["bg_dark"])
        self.resizable(False, False)
        
        self.create_widgets()
        
        # Pencere ortalama
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f'+{x}+{y}')
        
        # Modalı pencere olarak ayarla
        self.transient(parent)
        self.grab_set()
        
    def create_widgets(self):
        # Ana çerçeve
        main_frame = tk.Frame(self, bg=COLORS["bg_dark"], padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Başlık ve Ekleme Butonu Satırı
        header_frame = tk.Frame(main_frame, bg=COLORS["bg_dark"])
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Başlık
        title_label = tk.Label(header_frame, text="Komut Listesi", font=header_font, 
                              bg=COLORS["bg_dark"], fg=COLORS["text_primary"])
        title_label.pack(side=tk.LEFT)
        
        # Ekleme butonu (yeşil + butonu)
        add_button = RoundedButton(
            header_frame,
            text="+",
            command=self.add_command,
            width=40,
            height=40,
            bg=BOOTSTRAP_COLORS["success"],
            hover_bg=BOOTSTRAP_COLORS["success_hover"],
            fg=COLORS["text_primary"]
        )
        add_button.pack(side=tk.RIGHT)
        
        # Komut listesi çerçevesi
        list_frame = tk.Frame(main_frame, bg=COLORS["bg_medium"], padx=15, pady=15)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Tablo başlığı
        header_frame = tk.Frame(list_frame, bg=COLORS["bg_light"])
        header_frame.pack(fill=tk.X, pady=(0, 2))
        
        tk.Label(header_frame, text="Anahtar Kelime", font=("Segoe UI", 12, "bold"), 
                width=15, bg=COLORS["bg_light"], fg=COLORS["text_primary"], padx=10, pady=5).pack(side=tk.LEFT)
        
        tk.Label(header_frame, text="Komut Türü", font=("Segoe UI", 12, "bold"), 
                width=12, bg=COLORS["bg_light"], fg=COLORS["text_primary"], padx=10, pady=5).pack(side=tk.LEFT)
        
        tk.Label(header_frame, text="Hedef", font=("Segoe UI", 12, "bold"), 
                bg=COLORS["bg_light"], fg=COLORS["text_primary"], padx=10, pady=5).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(header_frame, text="İşlem", font=("Segoe UI", 12, "bold"), 
                width=8, bg=COLORS["bg_light"], fg=COLORS["text_primary"], padx=10, pady=5).pack(side=tk.LEFT)
        
        # Scroll Frame
        self.canvas = tk.Canvas(list_frame, bg=COLORS["bg_medium"], highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=COLORS["bg_medium"])
        
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw", width=645)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True, padx=(0, 5))
        scrollbar.pack(side="right", fill="y")
        
        # Butonlar çerçevesi
        button_frame = tk.Frame(main_frame, bg=COLORS["bg_dark"], pady=10)
        button_frame.pack(fill=tk.X)
        
        # Kapat butonu
        close_button = RoundedButton(
            button_frame,
            text="Kapat",
            command=self.destroy,
            width=100,
            height=40,
            bg=BOOTSTRAP_COLORS["primary"],
            hover_bg=BOOTSTRAP_COLORS["primary_hover"],
            fg=COLORS["text_primary"]
        )
        close_button.pack(side=tk.RIGHT)
        
        # Komut listesini doldur
        self.load_commands()
    
    def load_commands(self):
        # Önce mevcut liste içeriğini temizle
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
            
        # Komutları getir
        commands = self.settings.get_all_commands()
        
        if not commands:
            # Komut yoksa bilgi mesajı göster
            empty_label = tk.Label(self.scroll_frame, text="Henüz komut eklenmemiş. Komut eklemek için + butonuna tıklayın.", 
                                 font=small_font, bg=COLORS["bg_medium"], fg=COLORS["text_secondary"],
                                 pady=20)
            empty_label.pack(fill=tk.X)
            return
            
        # Her komut için bir satır oluştur
        row_count = 0
        for keyword, details in commands.items():
            row_bg = COLORS["bg_medium"] if row_count % 2 == 0 else COLORS["bg_light"]
            row_frame = tk.Frame(self.scroll_frame, bg=row_bg)
            row_frame.pack(fill=tk.X, pady=1)
            
            # Anahtar kelime
            tk.Label(row_frame, text=keyword, width=15, anchor="w", 
                    bg=row_bg, fg=COLORS["text_primary"], padx=10, pady=5).pack(side=tk.LEFT)
            
            # Komut türü
            cmd_type_text = "URL Aç" if details["type"] == "url" else "Program Aç"
            tk.Label(row_frame, text=cmd_type_text, width=12, 
                    bg=row_bg, fg=COLORS["text_primary"], padx=10, pady=5).pack(side=tk.LEFT)
            
            # Hedef (URL/program yolu)
            target_text = details["target"]
            if len(target_text) > 40:  # Çok uzunsa kısalt
                target_text = target_text[:37] + "..."
            tk.Label(row_frame, text=target_text, anchor="w", 
                    bg=row_bg, fg=COLORS["text_primary"], padx=10, pady=5).pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            # Silme butonu
            delete_button = tk.Button(row_frame, text="Sil", bg=BOOTSTRAP_COLORS["danger"], 
                                     fg="white", bd=0, padx=5, pady=2,
                                     command=lambda kw=keyword: self.delete_command(kw))
            delete_button.pack(side=tk.LEFT, padx=10)
            
            row_count += 1
    
    def add_command(self):
        # Komut ekleme penceresini aç
        dialog = CommandAddDialog(self, self.settings)
        # Pencere kapanana kadar bekle
        self.wait_window(dialog)
        # Komut listesini yenile
        self.load_commands()
    
    def delete_command(self, keyword):
        # Silme onayı iste
        confirm = tk.messagebox.askyesno(
            "Komut Sil", 
            f"'{keyword}' komutunu silmek istediğinize emin misiniz?",
            parent=self
        )
        
        if confirm:
            self.settings.remove_command(keyword)
            self.load_commands()

# Komut ekleme diyaloğu
class CommandAddDialog(tk.Toplevel):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.parent = parent
        self.settings = settings
        self.title("Komut Ekle")
        self.geometry("500x300")
        self.configure(bg=COLORS["bg_dark"])
        self.resizable(False, False)
        
        # Komut türleri
        self.command_types = {
            "url": "Aç(url)",
            "exe": "Aç(.exe)"
        }
        
        self.target_frame = None  # Hedef giriş alanını tutacak değişken
        self.target_value = None  # Hedef değerini tutacak değişken
        
        self.create_widgets()
        
        # Pencere ortalama
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f'+{x}+{y}')
        
        # Modalı pencere olarak ayarla
        self.transient(parent)
        self.grab_set()
    
    def create_widgets(self):
        # Ana çerçeve
        main_frame = tk.Frame(self, bg=COLORS["bg_dark"], padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Başlık
        title_label = tk.Label(main_frame, text="Yeni Komut Ekle", font=("Segoe UI", 18, "bold"), 
                              bg=COLORS["bg_dark"], fg=COLORS["text_primary"])
        title_label.pack(pady=(0, 20))
        
        # Form alanı
        form_frame = tk.Frame(main_frame, bg=COLORS["bg_medium"], padx=15, pady=15)
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        # Anahtar kelime alanı
        keyword_frame = tk.Frame(form_frame, bg=COLORS["bg_medium"])
        keyword_frame.pack(fill=tk.X, pady=(0, 15))
        
        keyword_label = tk.Label(keyword_frame, text="Anahtar Kelime:", width=15, anchor="w",
                                font=default_font, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
        keyword_label.pack(side=tk.LEFT)
        
        self.keyword_var = tk.StringVar()
        keyword_entry = tk.Entry(keyword_frame, textvariable=self.keyword_var, width=30, font=default_font)
        keyword_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # Komut türü alanı
        type_frame = tk.Frame(form_frame, bg=COLORS["bg_medium"])
        type_frame.pack(fill=tk.X, pady=(0, 15))
        
        type_label = tk.Label(type_frame, text="Komut Türü:", width=15, anchor="w",
                             font=default_font, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
        type_label.pack(side=tk.LEFT)
        
        self.type_var = tk.StringVar()
        type_combo = ttk.Combobox(type_frame, textvariable=self.type_var, 
                                 values=list(self.command_types.values()), width=15, font=default_font)
        type_combo.pack(side=tk.LEFT)
        type_combo.current(0)  # İlk öğeyi seç
        type_combo.bind("<<ComboboxSelected>>", self.on_type_changed)
        
        # Hedef çerçevesi (Komut türüne göre dinamik olarak değişecek)
        self.target_container = tk.Frame(form_frame, bg=COLORS["bg_medium"])
        self.target_container.pack(fill=tk.X, pady=(0, 15))
        
        # İlk komut türü için hedef alanını oluştur
        self.on_type_changed(None)
        
        # Butonlar çerçevesi
        button_frame = tk.Frame(main_frame, bg=COLORS["bg_dark"], pady=10)
        button_frame.pack(fill=tk.X)
        
        # Kaydet butonu
        save_button = RoundedButton(
            button_frame,
            text="Kaydet",
            command=self.save_command,
            width=100,
            height=40,
            bg=BOOTSTRAP_COLORS["success"],
            hover_bg=BOOTSTRAP_COLORS["success_hover"],
            fg=COLORS["text_primary"]
        )
        save_button.pack(side=tk.RIGHT, padx=(10, 0))
        
        # İptal butonu
        cancel_button = RoundedButton(
            button_frame,
            text="İptal",
            command=self.destroy,
            width=100,
            height=40,
            bg=BOOTSTRAP_COLORS["danger"],
            hover_bg=BOOTSTRAP_COLORS["danger_hover"],
            fg=COLORS["text_primary"]
        )
        cancel_button.pack(side=tk.RIGHT)
    
    def on_type_changed(self, event):
        # Mevcut hedef alanını temizle
        if self.target_frame:
            self.target_frame.destroy()
        
        # Komut türüne göre uygun hedef alanını oluştur
        cmd_type = self.type_var.get()
        
        self.target_frame = tk.Frame(self.target_container, bg=COLORS["bg_medium"])
        self.target_frame.pack(fill=tk.X)
        
        if cmd_type == self.command_types["url"]:
            # URL giriş alanı
            target_label = tk.Label(self.target_frame, text="URL:", width=15, anchor="w",
                                  font=default_font, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
            target_label.pack(side=tk.LEFT)
            
            self.target_value = tk.StringVar()
            target_entry = tk.Entry(self.target_frame, textvariable=self.target_value, width=30, font=default_font)
            target_entry.pack(side=tk.LEFT)
            
        elif cmd_type == self.command_types["exe"]:
            # Dosya seçme alanı
            target_label = tk.Label(self.target_frame, text="Program:", width=15, anchor="w",
                                  font=default_font, bg=COLORS["bg_medium"], fg=COLORS["text_primary"])
            target_label.pack(side=tk.LEFT)
            
            self.target_value = tk.StringVar()
            target_entry = tk.Entry(self.target_frame, textvariable=self.target_value, width=20, font=default_font)
            target_entry.pack(side=tk.LEFT, padx=(0, 5))
            
            browse_button = tk.Button(self.target_frame, text="Gözat", command=self.browse_file,
                                    bg=COLORS["accent_blue"], fg="white", bd=0, padx=5, pady=2)
            browse_button.pack(side=tk.LEFT)
    
    def browse_file(self):
        # Dosya seçme diyaloğu
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Program Seç",
            filetypes=[("Çalıştırılabilir Dosyalar", "*.exe"), ("Tüm Dosyalar", "*.*")]
        )
        
        if file_path:
            self.target_value.set(file_path)
    
    def save_command(self):
        # Form verilerini kontrol et
        keyword = self.keyword_var.get().strip()
        cmd_type = self.type_var.get()
        
        if not keyword:
            tk.messagebox.showerror("Hata", "Anahtar kelime boş olamaz!", parent=self)
            return
        
        if len(keyword.split()) > 1:
            tk.messagebox.showerror("Hata", "Anahtar kelime boşluk içermemelidir!", parent=self)
            return
            
        target = self.target_value.get().strip() if self.target_value else ""
        
        if not target:
            tk.messagebox.showerror("Hata", "Hedef boş olamaz!", parent=self)
            return
        
        # Komut türünü belirle
        if cmd_type == self.command_types["url"]:
            cmd_type_key = "url"
            
            # URL doğrulaması
            if not target.startswith(("http://", "https://")):
                target = "https://" + target
                
        elif cmd_type == self.command_types["exe"]:
            cmd_type_key = "exe"
            
            # Dosya var mı kontrol et
            if not os.path.exists(target):
                tk.messagebox.showerror("Hata", "Belirtilen dosya bulunamadı!", parent=self)
                return
        
        # Komutu ayarlara ekle
        self.settings.add_command(keyword, cmd_type_key, target)
        
        # Pencereyi kapat
        self.destroy()

# Add helper function for TTS to avoid code duplication
def say_response(text, lang=None):
    """Text to speech helper function with settings"""
    if lang is None:
        lang = settings.get("language")
    
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

# Function to show border effect - using subprocess to avoid GUI framework conflicts
def show_border_effect():
    global border_effect_process
    
    # Close existing border effect if any
    hide_border_effect()
    
    try:
        # Launch border effect as a separate process
        print("Starting border effect...")
        border_effect_process = subprocess.Popen([sys.executable, "d:\\SesliAsistan\\border_effect.py", "--transparency", "0.9"])
        print(f"Border effect process started with PID: {border_effect_process.pid}")
    except Exception as e:
        print(f"Error launching border effect: {e}")

# Function to hide border effect
def hide_border_effect():
    global border_effect_process
    
    if border_effect_process is not None:
        try:
            print("Terminating border effect process...")
            border_effect_process.terminate()
            border_effect_process = None
        except Exception as e:
            print(f"Error closing border effect: {e}")

# Konuşmayı yazıya çeviren fonksiyon - iptal komutu desteği eklendi
def recognize():
    global is_listening
    rec = vosk.KaldiRecognizer(model, 16000)
    
    # Show border effect when listening starts
    print("Starting recognition and showing border effect")
    window.after(100, show_border_effect)  # Delay slightly to ensure UI is ready
    
    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                          channels=1, callback=callback):
        print("Dinlemeye başladı...")
        is_listening = True
        listening_label.config(text="Dinleniyor")
        status_indicator.config(bg="#facc15")  # Sarı ışık - dinliyor
        animate_listening()
        
        command_executed = False
        
        while is_listening:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "")
                if text:
                    print("Algılanan:", text)
                    result_text.set(text)
                    
                    # "iptal" kelimesini kontrol et - Yeni eklenen özellik
                    if "iptal" in text.lower():
                        # İptal komutu algılandı, dinlemeyi durdur
                        print("İptal komutu algılandı, dinleme durduruluyor...")
                        result_text.set("İşlem iptal edildi.")
                        window.after(0, lambda: say_response("İptal edildi", settings.get("language")))
                        is_listening = False
                        listening_label.config(text="")
                        status_indicator.config(bg="#6b7280")  # Gri ışık - iptal edildi
                        
                        # Hide border effect
                        window.after(0, hide_border_effect)
                        
                        # Eğer pasif dinleme aktifse, yeniden başlat
                        if settings.get("passive_listening").lower() == "true":
                            window.after(1000, start_passive_listening)
                        break
                    
                    # Komut kontrolü yap ve sonucu al
                    command_executed = process_command(text)
                    
                    # Komut algılamadıysa
                    if not command_executed:
                        # "Ne diyon lan" diye seslenip tekrar dinlemeye devam et
                        window.after(0, lambda: say_response("Ne diyon lan? Tekrar söyle", settings.get("language")))
                        print("Komut algılanmadı, dinlemeye devam ediliyor...")
                        continue
                    
                    # Komut algılandıysa dinlemeyi bitir
                    is_listening = False
                    listening_label.config(text="")
                    status_indicator.config(bg="#10b981")  # Yeşil ışık - tamamlandı
                    
                    # Hide border effect
                    window.after(0, hide_border_effect)
                    
                    window.after(2000, lambda: status_indicator.config(bg="#6b7280"))  # 2 saniye sonra gri ışığa dön
                    
                    # Eğer pasif dinleme aktifse, yeniden başlat
                    if settings.get("passive_listening").lower() == "true":
                        window.after(1000, start_passive_listening)
                    break

# Butona tıklayınca konuşmayı başlat
def start_recognition():
    # Eğer pasif dinleme aktifse geçici olarak durdur
    global passive_listening_active
    was_passive_active = passive_listening_active
    
    if was_passive_active:
        passive_listening_active = False
        # Pasif dinleme görsel göstergelerini güncelle
        passive_indicator.config(bg="#6b7280")
        passive_label.config(text="Pasif Dinleme: Bekleniyor", fg=COLORS["text_secondary"])
    
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
window.geometry("700x800")  # Genişlik ve yükseklik arttırıldı (600x700 -> 700x800)
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

# Ayarlar nesnesini oluştur (ve duplicates sil)
settings = Settings()

# Open settings dialog
def open_settings():
    dialog = SettingsDialog(window, settings)
    # Wait until dialog is closed
    window.wait_window(dialog)
    # Update UI elements that depend on settings
    update_ui_from_settings()

def update_ui_from_settings():
    # Update help text with current wake word
    new_help_text = """• Konuşmayı başlatmak için 'Konuşmayı Başlat' butonuna tıklayın.
• Algılanan metni duymak için 'Yazıyı Oku' butonuna tıklayın.
• Pasif dinleme modunda '{}' diyerek asistanı aktif edebilirsiniz.
• Dinleme sırasında "iptal" diyerek işlemi sonlandırabilirsiniz.
• Ayarlar butonundan pasif dinlemeyi açıp kapatabilirsiniz.
• Sarı ışık: Dinleniyor, Yeşil ışık: Tamamlandı, Mavi ışık: Pasif dinleme aktif""".format(settings.get("wake_word"))
    help_label.config(text=new_help_text)

# Function to update passive listening state based on settings
def update_passive_listening_state():
    global passive_listening_active
    should_be_active = settings.get("passive_listening").lower() == "true"
    
    # Pasif dinleme aktifse önce durdur (wake word değiştiği için)
    if passive_listening_active:
        passive_listening_active = False
        # Kısa bir bekleme ile yeniden başlatma için
        window.after(300, lambda: set_passive_listening(should_be_active))
    else:
        # Doğrudan ayarla
        set_passive_listening(should_be_active)

# Yardımcı fonksiyon - passive listening durumunu ayarlamak için
def set_passive_listening(should_be_active):
    global passive_listening_active
    
    if should_be_active and not passive_listening_active:
        # Pasif dinleme aktif edilecek
        if WAKE_WORD_AVAILABLE:
            start_passive_listening()
        else:
            result_text.set("Pasif dinleme için gerekli modüller yüklenmemiş. 'pip install pyaudio numpy' komutunu çalıştırın.")
    elif not should_be_active and passive_listening_active:
        # Pasif dinleme deaktif edilecek
        passive_listening_active = False
        passive_indicator.config(bg="#6b7280")
        passive_label.config(text="Pasif Dinleme: Kapalı", fg=COLORS["text_secondary"])

# Function to start passive listening
def start_passive_listening():
    global passive_listening_active
    
    if not WAKE_WORD_AVAILABLE:
        result_text.set("Pasif dinleme için gerekli modüller yüklenmemiş. 'pip install pyaudio numpy' komutunu çalıştırın.")
        return
    
    if not passive_listening_active and not is_listening:
        passive_listening_active = True
        passive_indicator.config(bg=COLORS["accent_blue"])
        passive_label.config(text="Pasif Dinleme: Aktif", fg=COLORS["accent_blue"])
        # Start passive listening in a thread
        threading.Thread(target=passive_listen_loop, daemon=True).start()

# Open command list dialog
def open_command_list():
    dialog = CommandListDialog(window, settings)
    # Wait until dialog is closed
    window.wait_window(dialog)

# Ana çerçeve oluştur
main_frame = tk.Frame(window, bg=COLORS["bg_dark"], padx=20, pady=20)
main_frame.pack(fill=tk.BOTH, expand=True)

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

# Buton çerçevesi için üst frame - should be placed at the top of the UI
top_button_frame = tk.Frame(main_frame, bg=COLORS["bg_dark"])
top_button_frame.pack(fill=tk.X, pady=(0, 10))

# Ayarlar butonu üst tarafa
settings_button = RoundedButton(
    top_button_frame, 
    text="Ayarlar", 
    command=open_settings,
    width=100, 
    height=40,
    bg=BOOTSTRAP_COLORS["dark"],
    hover_bg=BOOTSTRAP_COLORS["dark_hover"],
    fg=COLORS["text_primary"]
)
settings_button.pack(side=tk.RIGHT)

# Komut Listesi butonu
commands_button = RoundedButton(
    top_button_frame, 
    text="Komut Listesi", 
    command=open_command_list,
    width=120, 
    height=40,
    bg=BOOTSTRAP_COLORS["info"],
    hover_bg=BOOTSTRAP_COLORS["info_hover"],
    fg=COLORS["text_primary"]
)
commands_button.pack(side=tk.RIGHT, padx=(0, 10))

# Başlık Alanı
header_frame = RoundedFrame(main_frame, COLORS["accent_purple"], 660, 80, radius=15)  # Genişlik arttırıldı (560 -> 660)
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

output_frame = RoundedFrame(main_frame, COLORS["bg_medium"], 660, 200, radius=15)  # Genişlik arttırıldı (560 -> 660)
output_frame.pack(fill=tk.X, pady=(0, 25))

result_display = tk.Label(output_frame, textvariable=result_text, wraplength=500, 
                         font=default_font, bg=COLORS["bg_medium"], fg=COLORS["accent_cyan"],
                         justify=tk.LEFT, padx=15, pady=15)
result_display.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

# Buton alanı
button_frame = tk.Frame(main_frame, bg=COLORS["bg_dark"])
button_frame.pack(fill=tk.X, pady=10)

# Butonları oluştur - Pasif dinleme butonu kaldırıldı
start_button = RoundedButton(
    button_frame, 
    text="Konuşmayı Başlat", 
    command=start_recognition,
    width=275, 
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
    width=275, 
    height=50,
    bg=BOOTSTRAP_COLORS["primary"],
    hover_bg=BOOTSTRAP_COLORS["primary_hover"],
    fg=COLORS["text_primary"]
)
speak_button.pack(side=tk.LEFT, fill=tk.X, expand=True)  # Genişlik güncellendi

# Yardım ve bilgiler
help_frame = RoundedFrame(main_frame, COLORS["bg_light"], 660, 150, radius=15)  # Genişlik arttırıldı (560 -> 660)
help_frame.pack(fill=tk.X, pady=(25, 0))

# Help text with wake word from settings
help_text = """• Konuşmayı başlatmak için 'Konuşmayı Başlat' butonuna tıklayın.
• Algılanan metni duymak için 'Yazıyı Oku' butonuna tıklayın.
• Pasif dinleme modunda '{}' diyerek asistanı aktif edebilirsiniz.
• Dinleme sırasında "iptal" diyerek işlemi sonlandırabilirsiniz.
• Ayarlar butonundan pasif dinlemeyi açıp kapatabilirsiniz.
• Komut Listesi butonundan özel komutlar ekleyebilirsiniz.
• Sarı ışık: Dinleniyor, Yeşil ışık: Tamamlandı, Mavi ışık: Pasif dinleme aktif""".format(settings.get("wake_word"))

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
            
            wake_word = settings.get("wake_word")
            print(f"Pasif dinleme başlatıldı... ('{wake_word}' komutunu bekliyor)")
            result_text.set(f"Pasif dinleme aktif. '{wake_word}' diyerek beni çağırabilirsiniz.")
            
            # No border effect for passive listening until wake word is detected
            
            while passive_listening_active:
                data = passive_q.get()
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").lower()
                    print(f"Pasif dinleme duydu: {text}")
                    
                    # Wake word tespiti
                    if wake_word.lower() in text:
                        print(f"WAKE WORD ALGILANDI: {wake_word}")
                        result_text.set("Sizi dinliyorum...")
                        
                        # Show border effect when wake word detected - with delay
                        window.after(100, show_border_effect)
                        
                        # Sesli yanıt ver
                        window.after(0, lambda: say_response("Sizi dinliyorum", settings.get("language")))
                        
                        # Ses kaydını geçici olarak durdur, ana dinleme başlayacak
                        passive_listening_active = False
                        passive_indicator.config(bg="#6b7280")
                        passive_label.config(text="Pasif Dinleme: Bekleniyor", fg=COLORS["text_secondary"])
                        
                        # Ana dinlemeyi başlat (border effect already active)
                        window.after(1000, start_recognition)
                        break
                
    except Exception as e:
        print(f"Pasif dinleme başlatma hatası: {e}")
        result_text.set(f"Pasif dinleme başlatılamadı: {str(e)}")
        passive_listening_active = False
        passive_indicator.config(bg="#6b7280")
        passive_label.config(text="Pasif Dinleme: Hata", fg=BOOTSTRAP_COLORS["danger"])

# Komutları işle - boolean dönüş değeriyle güncellendi
def process_command(text):
    # Algılanan metindeki tüm kelimeleri ve komutları kontrol et
    words = text.lower().split()
    commands = settings.get_all_commands()
    
    for word in words:
        if word in commands:
            cmd = commands[word]
            execute_command(cmd["type"], cmd["target"])
            return True  # Komut başarıyla işlendi
    
    return False  # Hiçbir komut bulunamadı

# Komutu çalıştır
def execute_command(cmd_type, target):
    try:
        if cmd_type == "url":
            # URL aç
            webbrowser.open(target)
            result_text.set(f"Web sayfası açılıyor: {target}")
        
        elif cmd_type == "exe":
            # Program çalıştır
            subprocess.Popen(target)
            result_text.set(f"Program çalıştırılıyor: {os.path.basename(target)}")
    
    except Exception as e:
        result_text.set(f"Komut çalıştırılırken hata oluştu: {str(e)}")

# Uygulama başlatıldığında ayarlara göre pasif dinlemeyi otomatik başlat
def check_autostart_passive():
    if settings.get("passive_listening").lower() == "true":
        update_passive_listening_state()

# Ensure border effect is closed when application exits
def on_closing():
    print("Application closing, cleaning up resources...")
    hide_border_effect()
    window.destroy()

# Add window close handler
window.protocol("WM_DELETE_WINDOW", on_closing)

# Uygulama başlatıldığında çalışacak kodlar
window.after(1000, check_autostart_passive)
window.mainloop()
