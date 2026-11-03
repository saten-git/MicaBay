import os
import json
import time
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QTimer, QThread

WEATHER_FILE = os.path.join(os.path.dirname(__file__), "weather_cache.json")

class WeatherWorker(QThread):
    weather_fetched = Signal(dict)

    def __init__(self, settings_service):
        super().__init__()
        self.settings = settings_service

    def run(self):
        # Attempt to fetch real weather data if network is available
        import urllib.request
        data = None
        try:
            # 1. Try IP geolocation for lat/lon
            req = urllib.request.Request("http://ip-api.com/json", headers={"User-Agent": "MicaBay/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                geo = json.loads(resp.read().decode())
                lat = geo.get("lat")
                lon = geo.get("lon")
                city = geo.get("city", "Local Weather")

                # 2. Fetch Open-Meteo current weather
                url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                req2 = urllib.request.Request(url, headers={"User-Agent": "MicaBay/1.0"})
                with urllib.request.urlopen(req2, timeout=3) as resp2:
                    w = json.loads(resp2.read().decode())
                    cw = w.get("current_weather", {})
                    temp = round(cw.get("temperature", 22))
                    w_code = cw.get("weathercode", 2)
                    data = {
                        "temp": temp,
                        "w_code": w_code,
                        "city": city
                    }
        except Exception:
            pass

        if data:
            self.weather_fetched.emit(data)


class WeatherService(QObject):
    weather_updated = Signal(dict)

    def __init__(self, settings_service=None):
        super().__init__()
        self.settings = settings_service

        # Seed defaults matching user's exact live taskbar: 21°C, Partly cloudy, Humid
        self.temp = self.settings.get("weather_temp", 21) if self.settings else 21
        self.condition = self.settings.get("weather_condition", "Partly cloudy") if self.settings else "Partly cloudy"
        self.humidity_desc = self.settings.get("weather_humidity_desc", "Humid") if self.settings else "Humid"
        self.city = self.settings.get("weather_city", "Local Weather") if self.settings else "Local Weather"
        self.high = 26
        self.low = 18
        self.humidity = 78

        self._load_cache()

        # Worker for periodic non-blocking background fetch
        self.worker = None
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.fetch_update)
        self.refresh_timer.start(900000)  # Refresh every 15 minutes

        # Check every 60s for day/night icon switch
        self.icon_timer = QTimer(self)
        self.icon_timer.timeout.connect(self._check_time_icon)
        self.icon_timer.start(60000)

        # Trigger initial fetch if network available
        QTimer.singleShot(1500, self.fetch_update)

    def _get_icon(self, condition: str = None) -> str:
        hour = datetime.now().hour
        is_night = (hour >= 19 or hour < 6)

        c = (condition or self.condition).lower()
        if "rain" in c or "shower" in c or "drizzle" in c:
            return "🌧️"
        elif "thunder" in c or "storm" in c:
            return "⛈️"
        elif "snow" in c:
            return "🌨️"
        elif "fog" in c or "mist" in c:
            return "🌫️"
        elif "partly" in c or "scattered" in c or "few clouds" in c or "humid" in c:
            return "🌙☁️" if is_night else "⛅"
        elif "cloud" in c or "overcast" in c:
            return "☁️"
        else:  # Clear
            return "🌙" if is_night else "☀️"

    def _check_time_icon(self):
        self.weather_updated.emit(self.get_data())

    def get_data(self) -> dict:
        unit = self.settings.get("weather_unit", "°C") if self.settings else "°C"
        icon = self._get_icon()
        return {
            "temp": self.temp,
            "temp_str": f"{self.temp}{unit}",
            "condition": self.condition,
            "humidity_desc": self.humidity_desc,
            "icon": icon,
            "city": self.city,
            "high": self.high,
            "low": self.low,
            "humidity": self.humidity
        }

    def set_temp(self, temp: int):
        self.temp = temp
        if self.settings:
            self.settings.set("weather_temp", temp)
        self._save_cache()
        self.weather_updated.emit(self.get_data())

    def set_condition(self, cond: str):
        self.condition = cond
        if self.settings:
            self.settings.set("weather_condition", cond)
        self._save_cache()
        self.weather_updated.emit(self.get_data())

    def set_humidity_desc(self, desc: str):
        self.humidity_desc = desc
        if self.settings:
            self.settings.set("weather_humidity_desc", desc)
        self._save_cache()
        self.weather_updated.emit(self.get_data())

    def fetch_update(self):
        if not self.worker or not self.worker.isRunning():
            self.worker = WeatherWorker(self.settings)
            self.worker.weather_fetched.connect(self._on_worker_data)
            self.worker.start()

    def _on_worker_data(self, data: dict):
        self.temp = data.get("temp", self.temp)
        if "city" in data:
            self.city = data["city"]

        code = data.get("w_code", 2)
        if code == 0:
            self.condition = "Clear"
        elif code in (1, 2):
            self.condition = "Partly cloudy"
        elif code == 3:
            self.condition = "Overcast"
        elif code in (45, 48):
            self.condition = "Foggy"
        elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
            self.condition = "Rain"
        elif code in (71, 73, 75, 85, 86):
            self.condition = "Snow"
        elif code in (95, 96, 99):
            self.condition = "Thunderstorm"

        self._save_cache()
        self.weather_updated.emit(self.get_data())

    def _load_cache(self):
        if os.path.exists(WEATHER_FILE):
            try:
                with open(WEATHER_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.temp = data.get("temp", self.temp)
                    self.condition = data.get("condition", self.condition)
                    self.city = data.get("city", self.city)
                    self.high = data.get("high", self.high)
                    self.low = data.get("low", self.low)
                    self.humidity = data.get("humidity", self.humidity)
            except Exception:
                pass

    def _save_cache(self):
        try:
            with open(WEATHER_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "temp": self.temp,
                    "condition": self.condition,
                    "city": self.city,
                    "high": self.high,
                    "low": self.low,
                    "humidity": self.humidity
                }, f)
        except Exception:
            pass
