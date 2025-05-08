from fuzzywuzzy import fuzz
import requests
import webbrowser
import subprocess
import json

# Komutları ayarlar.json'dan yükle
with open("ayarlar.json", "r", encoding="utf-8") as f:
    config = json.load(f)
commands = config.get("commands", {})

url = "http://192.168.1.11:5000/komut"  # Bilgisayar IP'si

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

# Örnek test
if __name__ == "__main__":
    metin = input("Komut gir: ")
    process_command(metin)
