import os
import configparser

class Settings:
    def __init__(self):
        self.config_file = "ayarlar.ini"
        self.config = configparser.ConfigParser()
        # Default settings
        self.defaults = {
            "language": "tr",
            "voice_speed": "1.0",
            "voice_pitch": "1.0",
            "theme": "dark",
            "wake_word": "ceren",
            "passive_listening": "false",
            "input_device": "",
            "output_device": ""
        }
        self.load()
        # Ensure Commands section exists
        if not self.config.has_section("Commands"):
            self.config.add_section("Commands")
            self.save()

    def load(self):
        if os.path.exists(self.config_file):
            self.config.read(self.config_file, encoding='utf-8')
            if not self.config.has_section("Settings"):
                self.config.add_section("Settings")
                self.reset_to_defaults()
        else:
            self.config.add_section("Settings")
            self.reset_to_defaults()

    def save(self):
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
        if not self.config.has_section("Commands"):
            return {}
        commands = {}
        for key in self.config.options("Commands"):
            value = self.config.get("Commands", key)
            parts = value.split('|', 1)
            if len(parts) == 2:
                commands[key] = {"type": parts[0], "target": parts[1]}
        return commands

    def add_command(self, keyword, cmd_type, target):
        if not self.config.has_section("Commands"):
            self.config.add_section("Commands")
        self.config.set("Commands", keyword, f"{cmd_type}|{target}")
        self.save()

    def remove_command(self, keyword):
        if self.config.has_section("Commands") and self.config.has_option("Commands", keyword):
            self.config.remove_option("Commands", keyword)
            self.save()