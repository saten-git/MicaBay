import json
import os
from PySide6.QtCore import QObject, Signal

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")

DEFAULT_SETTINGS = {
    # Edge light settings (Screenshot 1)
    "edge_light_enabled": True,
    "edge_light_effect": "twin_comets",  # "comet", "twin_comets", "breathe"
    "edge_light_color": "#ffffff",
    "match_music_color": True,            # Auto-match music cover art color!
    "edge_light_intensity": 80,           # 20 to 100%
    "edge_light_speed": "normal",         # "slow", "normal", "fast"

    # Surface & Style settings (Screenshots 2 & 3)
    "placement": "full_taskbar",          # "top", "taskbar", "full_taskbar"
    "taskbar_x_offset": 250,              # horizontal offset along taskbar
    "full_taskbar_width": 605,            # width from left screen edge to Start button
    "notch_style": "notch",               # "notch", "island", "line"
    "notch_scale": 90,                    # 70% to 130%
    "pill_width": 270,                    # base width before scale
    "glass_transparency": 0,              # 0 to 100% (edge to center transparency)
    "opens_on": "click",                  # "hover", "click"
    "outline_enabled": True,
    "outline_width": 1,
    "shadow_level": "Deep",
    "soft_edge": "Medium",

    # Weather settings (Integrated cloud/weather into pill)
    "weather_enabled": True,              # Integrate weather directly into notch pill
    "weather_temp": 22,
    "weather_condition": "Partly cloudy",
    "weather_unit": "°C",
    "weather_city": "Local Weather"
}

class SettingsService(QObject):
    settings_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.data = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
            except Exception:
                pass

    def save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()
        self.settings_changed.emit(self.data)
