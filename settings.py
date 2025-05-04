import os
import json
import logging
import configparser
from pydantic import BaseModel, ValidationError, validator
from typing import Literal, Dict

"""
Settings management using JSON storage and pydantic schema validation.
Supports typed settings and command entries.
"""

class SettingsSchema(BaseModel):
    language: str = "tr"
    voice_speed: float = 1.0
    voice_pitch: float = 1.0
    theme: Literal["dark", "light"] = "dark"
    wake_word: str = "ceren"
    passive_listening: bool = False
    input_device: str = ""
    output_device: str = ""
    commands: Dict[str, Dict[str, str]] = {}

    @validator('language')
    def check_language_length(cls, v):
        if not v or len(v) not in (2,):
            raise ValueError('language must be 2-letter code')
        return v

    class Config:
        validate_assignment = True

class Settings:
    def __init__(self, file_path: str = "ayarlar.json"):
        self.config_file = file_path
        # ini_file located in the same directory as config_file
        ini_dir = os.path.dirname(os.path.abspath(file_path)) or os.getcwd()
        self.ini_file = os.path.join(ini_dir, "ayarlar.ini")
        self.load()

    def load(self):
        # Migrate from INI if JSON not exists but INI exists
        if not os.path.exists(self.config_file) and os.path.exists(self.ini_file):
            try:
                cp = configparser.ConfigParser()
                cp.read(self.ini_file, encoding='utf-8')
                data = {}
                # Settings
                for key in ["language","voice_speed","voice_pitch","theme","wake_word","passive_listening","input_device","output_device"]:
                    if cp.has_option("Settings", key):
                        data[key] = cp.get("Settings", key)
                # Type conversions
                data["voice_speed"] = float(data.get("voice_speed", 1.0))
                data["voice_pitch"] = float(data.get("voice_pitch", 1.0))
                data["passive_listening"] = data.get("passive_listening", "false").lower() == "true"
                # Commands
                cmds = {}
                if cp.has_section("Commands"):
                    for k in cp.options("Commands"):
                        t,v = cp.get("Commands", k).split('|',1)
                        cmds[k] = {"type": t, "target": v}
                data["commands"] = cmds
                self.schema = SettingsSchema.parse_obj(data)
                self.save()
            except Exception as e:
                logging.error(f"Migration error: {e}")
                self.schema = SettingsSchema()
                self.save()
            return
        if os.path.exists(self.config_file):
            try:
                data = json.load(open(self.config_file, encoding='utf-8'))
                self.schema = SettingsSchema.parse_obj(data)
            except (json.JSONDecodeError, ValidationError) as e:
                logging.error(f"Settings load error: {e}, resetting to defaults")
                self.schema = SettingsSchema()
                self.save()
        else:
            self.schema = SettingsSchema()
            self.save()

    def save(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.schema.dict(), f, ensure_ascii=False, indent=4)

    def get(self, key: str):
        return getattr(self.schema, key)

    def set(self, key: str, value):
        try:
            setattr(self.schema, key, value)
            self.save()
        except ValidationError as e:
            logging.error(f"Invalid setting {key}={value}: {e}")
            raise

    def get_all_commands(self):
        return self.schema.commands.copy()

    def add_command(self, keyword: str, cmd_type: str, target: str):
        self.schema.commands[keyword] = {"type": cmd_type, "target": target}
        self.save()

    def remove_command(self, keyword: str):
        if keyword in self.schema.commands:
            self.schema.commands.pop(keyword)
            self.save()