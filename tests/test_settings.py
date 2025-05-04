import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import os
import json
import configparser
import pytest
from settings import Settings, SettingsSchema

def test_default_settings(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings = Settings(file_path=str(settings_file))
    # Defaults from schema
    assert settings.get("language") == "tr"
    assert isinstance(settings.get("passive_listening"), bool)

    # JSON file created
    assert os.path.exists(settings_file)

    # Commands default should be empty
    assert settings.get_all_commands() == {}


def test_set_invalid_language(tmp_path):
    settings = Settings(file_path=str(tmp_path / "settings.json"))
    # language must be 2-letter code
    with pytest.raises(Exception):
        settings.set("language", "invalid_lang")


def test_add_remove_command(tmp_path):
    settings = Settings(file_path=str(tmp_path / "settings.json"))
    # Add command and verify
    settings.add_command("testcmd", "url", "http://example.com")
    cmds = settings.get_all_commands()
    assert "testcmd" in cmds
    assert cmds["testcmd"]["type"] == "url"
    assert cmds["testcmd"]["target"] == "http://example.com"
    # Remove command and verify
    settings.remove_command("testcmd")
    assert "testcmd" not in settings.get_all_commands()