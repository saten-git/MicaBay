import math
import time
from datetime import datetime
from PySide6.QtCore import (
    Qt, QTimer, QRectF, QPointF, QSize, QVariantAnimation, QEasingCurve,
    QEvent
)
from PySide6.QtGui import (
    QPainter, QColor, QPainterPath, QPen, QRadialGradient, QLinearGradient, QBrush
)
from PySide6.QtWidgets import QWidget, QApplication

from compact_bar import CompactBar
from dashboard_widget import DashboardWidget
from shelf_widget import FileShelfWidget
from settings_window import SettingsWindow
from color_extractor import extract_dominant_color

COMPACT_STATES = (
    "MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD", "DOWNLOAD",
    "MIC_ACTIVE", "BATTERY_ALERT", "GREETING", "NOTIFICATION_TOAST",
    "NET_SPEED", "CPU_RAM", "WEATHER", "DATE", "NOTIFICATIONS"
)

class NotchWindow(QWidget):
    def __init__(self, media_service, clipboard_service, system_service, settings_service, volume_service, weather_service=None, notification_service=None):
        super().__init__()
        self.media_service = media_service
        self.clipboard_service = clipboard_service
        self.system_service = system_service
        self.settings_service = settings_service
        self.volume_service = volume_service
        self.weather_service = weather_service
        self.notification_service = notification_service

        # States: "MEDIA", "COPY_TOAST", "VOLUME_HUD", "IDLE", "EXPANDED", "SHELF", "NOTIFICATION_TOAST", "NET_SPEED"
        self.current_state = "IDLE"
        self.previous_compact_state = "IDLE"
        self.is_pinned = False

        # Visual Geometry constants
        self.margin = 20
        self.ear_w = 11
        self.ear_h = 7
        self.corner_r = 13

        # Base pill dimensions
        placement = self.settings_service.get("placement", "top")
        self.base_pill_w = self.settings_service.get("pill_width", 270)
        self.cur_w = self._get_scaled_width()
        self.cur_h = 42 if placement == "full_taskbar" else 28  # default slim height for idle

        # Light animation phases
        self.light_time = 0.0
        self.comet_pos = 0.0
        self.light_timer = QTimer(self)
        self.light_timer.timeout.connect(self._animate_light)
        self.light_timer.start(24)

        # Hover auto-collapse timer (for opens_on == "hover")
        self.hover_leave_timer = QTimer(self)
        self.hover_leave_timer.setSingleShot(True)
        self.hover_leave_timer.timeout.connect(self._on_hover_leave_timeout)

        # Volume HUD timer (auto dismiss after 1.8s)
        self.vol_hud_timer = QTimer(self)
        self.vol_hud_timer.setSingleShot(True)
        self.vol_hud_timer.timeout.connect(self._end_volume_hud)

        # Dynamic album art color
        self.music_color = QColor(255, 255, 255)

        # Copy toast timer
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self._end_copy_toast)

        # Battery alert timer
        self.battery_alert_timer = QTimer(self)
        self.battery_alert_timer.setSingleShot(True)
        self.battery_alert_timer.timeout.connect(self._end_battery_alert)
        self.battery_alert_data = {"title": "Charger Connected", "is_charging": True, "pct": 100}

        # Real-time incoming notification toast timer (holds for 5 seconds)
        self.notification_toast_timer = QTimer(self)
        self.notification_toast_timer.setSingleShot(True)
        self.notification_toast_timer.timeout.connect(self._end_notification_toast)

        # Activity states
        self.download_data = {"active": False}
        self.mic_data = {"active": False}
        self.system_stats = {}
        self.notification_data = {"count": 0, "display_text": "No notifications"}
        if self.notification_service:
            try:
                self.notification_data = self.notification_service.get_data()
            except Exception:
                pass

        # Media & Download rotation timer (alternates every 5s when both active)
        self.rotation_timer = QTimer(self)
        self.rotation_timer.timeout.connect(self._rotate_media_download)

        # Apple-style cursive greeting typewriter (on first load / login)
        self.is_greeting_active = True
        hour = datetime.now().hour
        if 5 <= hour < 12:
            self.greeting_full_text = "Good morning"
        elif 12 <= hour < 17:
            self.greeting_full_text = "Good afternoon"
        else:
            self.greeting_full_text = "Good evening"

        self.greeting_char_idx = 0
        self.typewriter_timer = QTimer(self)
        self.typewriter_timer.setInterval(100)  # 100ms per character
        self.typewriter_timer.timeout.connect(self._on_typewriter_tick)

        self.greeting_hold_timer = QTimer(self)
        self.greeting_hold_timer.setSingleShot(True)
        self.greeting_hold_timer.setInterval(5500)  # Hold greeting for at least 5.5s
        self.greeting_hold_timer.timeout.connect(self._finish_greeting)

        # Smooth size animation
        self.size_anim = QVariantAnimation(self)
        self.size_anim.setDuration(240)
        self.size_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.size_anim.valueChanged.connect(self._on_size_anim_frame)

        self.media_data = {
            "has_media": False,
            "display_text": "",
            "is_playing": False,
            "thumbnail": None
        }

        self._last_expand_time = 0.0

        # Automatic focus loss & outside click detector for expanded dashboard
        self.outside_click_timer = QTimer(self)
        self.outside_click_timer.setInterval(75)  # Responsive 75ms check
        self.outside_click_timer.timeout.connect(self._check_expanded_focus_loss)

        # Persistent topmost keeper timer (ensures Live Pill stays above Windows Taskbar Shell_TrayWnd)
        self.topmost_keeper_timer = QTimer(self)
        self.topmost_keeper_timer.setInterval(400)  # Responsive 400ms assertion
        self.topmost_keeper_timer.timeout.connect(self._tick_topmost_keeper)
        self.topmost_keeper_timer.start()

        self._init_window()
        self._build_components()
        self._connect_signals()

        self.setAcceptDrops(True)
        self.is_greeting_active = True
        self.current_state = "GREETING"
        self._switch_state("GREETING")
        self.compact_bar.show_greeting("")
        self._sync_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_layout()
        if self.settings_service.get("placement", "top") in ("taskbar", "full_taskbar"):
            self._ensure_topmost()
        if not getattr(self, "_has_started_greeting_on_show", False):
            self._has_started_greeting_on_show = True
            try:
                import ctypes
                ctypes.windll.wtsapi32.WTSRegisterSessionNotification(int(self.winId()), 0)
            except Exception:
                pass
            self._greeting_startup_timer = QTimer(self)
            self._greeting_startup_timer.setSingleShot(True)
            self._greeting_startup_timer.timeout.connect(self._start_greeting)
            self._greeting_startup_timer.start(100)

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)

        # Allow UIPI messages for Drag & Drop from Windows Explorer
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.ChangeWindowMessageFilter(0x0233, 1)  # WM_DROPFILES
            user32.ChangeWindowMessageFilter(0x004A, 1)  # WM_COPYDATA
            user32.ChangeWindowMessageFilter(0x0049, 1)  # WM_COPYGLOBALDATA
            if hasattr(user32, "ChangeWindowMessageFilterEx"):
                hwnd = int(self.winId())
                user32.ChangeWindowMessageFilterEx(hwnd, 0x0233, 1, None)
                user32.ChangeWindowMessageFilterEx(hwnd, 0x004A, 1, None)
                user32.ChangeWindowMessageFilterEx(hwnd, 0x0049, 1, None)
        except Exception:
            pass

    def _ensure_topmost(self):
        """Re-asserts topmost z-order over Windows Shell_TrayWnd taskbar without taking focus."""
        try:
            import ctypes
            import ctypes.wintypes
            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [
                ctypes.wintypes.HWND,
                ctypes.wintypes.HWND,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_uint
            ]
            user32.SetWindowPos.restype = ctypes.wintypes.BOOL
            hwnd = int(self.winId())

            # Attach ownership to Shell_TrayWnd if on taskbar so Windows User32 naturally keeps it above
            placement = self.settings_service.get("placement", "top")
            if placement in ("taskbar", "full_taskbar") and not getattr(self, "_has_set_tray_owner", False):
                tray_hwnd = user32.FindWindowW("Shell_TrayWnd", None)
                if tray_hwnd:
                    SetWindowLongPtr = user32.SetWindowLongPtrW if hasattr(user32, "SetWindowLongPtrW") else user32.SetWindowLongW
                    SetWindowLongPtr(hwnd, -8, tray_hwnd)  # GWLP_HWNDPARENT = -8
                    self._has_set_tray_owner = True

            HWND_TOPMOST = ctypes.wintypes.HWND(-1)
            # SWP_NOSIZE (0x0001) | SWP_NOMOVE (0x0002) | SWP_NOACTIVATE (0x0010) | SWP_SHOWWINDOW (0x0040)
            user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0010 | 0x0040
            )
        except Exception:
            pass

    def _build_components(self):
        self.compact_bar = CompactBar(self, self.weather_service, self.media_service)
        self.compact_bar.set_placement(self.settings_service.get("placement", "top"))
        self.compact_bar.setGeometry(self.margin, 0, self.cur_w, self.cur_h)

        self.dashboard_widget = DashboardWidget(
            self.clipboard_service, self.system_service, self.settings_service, self.weather_service, self
        )
        self.dashboard_widget.close_requested.connect(self.collapse)
        self.dashboard_widget.pin_toggled.connect(self._on_pin_toggled)
        self.dashboard_widget.shelf_requested.connect(self.open_shelf)
        self.dashboard_widget.settings_requested.connect(self.open_settings)
        self.dashboard_widget.hide()

        self.settings_window = SettingsWindow(self.settings_service)

        self.shelf_widget = FileShelfWidget(self)
        self.shelf_widget.close_requested.connect(self.collapse)
        self.shelf_widget.hide()

    def _connect_signals(self):
        self.media_service.media_updated.connect(self._on_media_updated)
        self.clipboard_service.item_copied.connect(self._on_clipboard_copied)
        self.system_service.stats_updated.connect(self._on_stats_updated)
        self.system_service.battery_event.connect(self._on_battery_event)
        self.system_service.download_activity_changed.connect(self._on_download_activity_changed)
        self.system_service.mic_activity_changed.connect(self._on_mic_activity_changed)
        self.volume_service.volume_changed.connect(self._on_volume_changed)
        self.settings_service.settings_changed.connect(self._on_settings_changed)
        self.compact_bar.elastic_size_requested.connect(self._on_elastic_size_requested)
        if self.weather_service:
            self.weather_service.weather_updated.connect(self._on_weather_updated)
        if self.notification_service:
            self.notification_service.notifications_updated.connect(self._on_notifications_updated)
            self.notification_service.notification_toast_requested.connect(self._on_new_notification)

    def _on_new_notification(self, notif: dict):
        if not self.settings_service.get("enable_notification_alerts", True):
            return
        if self.current_state in ("EXPANDED", "SHELF"):
            return

        if self.current_state in COMPACT_STATES and self.current_state != "NOTIFICATION_TOAST":
            self.previous_compact_state = self.current_state

        app_name = notif.get("app", "Notification")
        title = notif.get("title", "")
        body = notif.get("body", "")
        if title and title != app_name:
            msg_text = f"{title}: {body}" if body else title
        else:
            msg_text = body or notif.get("display_text", "New message")

        icon = notif.get("icon", "💬")

        # 1. Update toast UI first so currentWidget is notification_toast_page
        self.compact_bar.show_notification_toast(app_name, msg_text, icon)

        # 2. Switch window state to NOTIFICATION_TOAST
        self._switch_state("NOTIFICATION_TOAST")

        # 3. Halt rotation timer during notification toast so nothing overrides it
        if hasattr(self, "rotation_timer") and self.rotation_timer.isActive():
            self.rotation_timer.stop()

        # 4. Directly display incoming notification for guaranteed full 5 seconds
        self.notification_toast_timer.start(5000)

    def _end_notification_toast(self):
        if self.current_state == "NOTIFICATION_TOAST":
            fallback = self.previous_compact_state if hasattr(self, "previous_compact_state") and self.previous_compact_state in COMPACT_STATES else self._get_active_fallback_state()
            self._switch_state(fallback)
            self._update_rotation_timer()

    def _on_elastic_size_requested(self, optimal_w: int):
        if self.settings_service.get("placement", "top") == "full_taskbar":
            return
        if self.current_state in COMPACT_STATES:
            if int(self.cur_w) != optimal_w:
                self._animate_size(optimal_w, 42)

    def _on_weather_updated(self, data: dict):
        self.weather_data = data
        self.compact_bar.update_weather(data)
        if self.current_state == "WEATHER":
            self.compact_bar.update_weather_page_data(data)
        self.update()

    def _on_notifications_updated(self, data: dict):
        self.notification_data = data
        if self.current_state == "NOTIFICATIONS":
            self.compact_bar.update_notification_data(data.get("count", 0), data.get("display_text", "No notifications"))

    def _get_scaled_width(self):
        placement = self.settings_service.get("placement", "top")
        if placement == "full_taskbar":
            max_b = self.settings_service.get("full_taskbar_width", 505)
            return max(200, max_b - 36)
        scale = self.settings_service.get("notch_scale", 90) / 100.0
        w_enabled = self.settings_service.get("weather_enabled", True)
        base = self.settings_service.get("pill_width", 270)
        if placement == "taskbar" and w_enabled:
            # Expand to comfortably display weather + media across the whole taskbar section
            base = max(base, 335)
        return int(base * scale)

    def _animate_light(self):
        speed_mode = self.settings_service.get("edge_light_speed", "normal")
        speed_factor = 0.6 if speed_mode == "slow" else (1.5 if speed_mode == "fast" else 1.0)

        self.light_time += 0.045 * speed_factor
        self.comet_pos = (self.comet_pos + 0.014 * speed_factor) % 1.0
        self.update()

    def _on_stats_updated(self, stats: dict):
        self.system_stats = stats
        self.compact_bar.update_battery(stats.get("battery", 95), stats.get("is_charging", False))
        if self.current_state == "NET_SPEED":
            self.compact_bar.update_net_speed_data(stats.get("net_down_str", "0 KB/s"), stats.get("net_up_str", "0 KB/s"))
        elif self.current_state == "CPU_RAM":
            self.compact_bar.update_cpu_ram_data(stats.get("cpu", 0), stats.get("ram", 0))

    def _on_volume_changed(self, pct: int, is_muted: bool):
        if not self.settings_service.get("enable_volume_hud", True) or getattr(self, "is_greeting_active", False):
            return
        if self.current_state in COMPACT_STATES:
            if self.current_state != "VOLUME_HUD":
                self.previous_compact_state = self.current_state

            self._switch_state("VOLUME_HUD")
            self.compact_bar.show_volume(pct, is_muted, self._get_active_glow_color())
            timeout_ms = self.settings_service.get("volume_hud_timeout", 1800)
            self.vol_hud_timer.start(timeout_ms)

    def _end_volume_hud(self):
        if self.current_state == "VOLUME_HUD":
            self._switch_state(self._get_active_fallback_state())

    def _on_battery_event(self, event: dict):
        if not self.settings_service.get("enable_battery_alerts", True) or getattr(self, "is_greeting_active", False) or self.current_state == "NOTIFICATION_TOAST":
            return
        ev_type = event.get("type")
        pct = event.get("pct", 100)
        if ev_type == "charging_started":
            self.battery_alert_data = {"title": "Charger Connected", "is_charging": True, "pct": pct}
            if self.current_state not in ("EXPANDED", "SHELF", "GREETING", "NOTIFICATION_TOAST"):
                self._switch_state("BATTERY_ALERT")
                self.battery_alert_timer.start(3000)
        elif ev_type == "low_battery":
            self.battery_alert_data = {"title": "Low Battery Warning", "is_charging": False, "pct": pct}
            if self.current_state not in ("EXPANDED", "SHELF", "GREETING", "NOTIFICATION_TOAST"):
                self._switch_state("BATTERY_ALERT")
                self.battery_alert_timer.start(3500)

    def _end_battery_alert(self):
        if self.current_state == "BATTERY_ALERT":
            self._switch_state(self._get_active_fallback_state())

    def _on_download_activity_changed(self, dl_info: dict):
        self.download_data = dl_info
        if not self.settings_service.get("enable_download_alerts", True) or getattr(self, "is_greeting_active", False) or self.current_state == "NOTIFICATION_TOAST":
            return
        self._update_rotation_timer()
        if self.current_state not in ("EXPANDED", "SHELF", "COPY_TOAST", "VOLUME_HUD", "BATTERY_ALERT", "GREETING", "NOTIFICATION_TOAST"):
            self._switch_state(self._get_active_fallback_state())

    def _on_mic_activity_changed(self, mic_info: dict):
        self.mic_data = mic_info
        if not self.settings_service.get("enable_mic_indicator", True) or getattr(self, "is_greeting_active", False) or self.current_state == "NOTIFICATION_TOAST":
            return
        if self.current_state not in ("EXPANDED", "SHELF", "COPY_TOAST", "VOLUME_HUD", "BATTERY_ALERT", "GREETING", "NOTIFICATION_TOAST"):
            self._switch_state(self._get_active_fallback_state())

    def _get_active_rotation_cycle(self) -> list:
        cycle = []
        has_media = self.media_data.get("has_media", False)
        has_dl = self.download_data.get("active", False) and self.settings_service.get("enable_download_alerts", True)

        # Priority 2: Active tasks
        if has_media:
            cycle.append("MEDIA")
        if has_dl:
            cycle.append("DOWNLOAD")

        # Priority 3: Normal Live Pill info (Time & Battery + Live Net Speed)
        # Note: CPU/RAM, Date, separate Weather, and Notification bell icon removed per user directive
        if self.settings_service.get("enable_net_speed_pill", True):
            cycle.append("NET_SPEED")
        if self.settings_service.get("enable_time_battery_pill", True):
            cycle.append("IDLE")

        # Fallback if everything disabled: ensure at least IDLE is present
        if not cycle:
            cycle.append("IDLE")

        return cycle

    def _update_rotation_timer(self):
        if getattr(self, "is_greeting_active", False) or self.current_state in ("EXPANDED", "SHELF", "NOTIFICATION_TOAST"):
            if hasattr(self, "rotation_timer") and self.rotation_timer.isActive():
                self.rotation_timer.stop()
            return
        cycle = self._get_active_rotation_cycle()
        interval_ms = int(self.settings_service.get("rotation_interval_sec", 5) * 1000)
        if len(cycle) >= 2:
            if not self.rotation_timer.isActive() or self.rotation_timer.interval() != interval_ms:
                self.rotation_timer.start(interval_ms)
        else:
            if self.rotation_timer.isActive():
                self.rotation_timer.stop()

    def _rotate_media_download(self):
        # Rotate between active activities and normal pill info every 5 seconds
        if getattr(self, "is_greeting_active", False):
            return
        if self.current_state in ("EXPANDED", "SHELF", "VOLUME_HUD", "COPY_TOAST", "BATTERY_ALERT", "NOTIFICATION_TOAST"):
            return

        cycle = self._get_active_rotation_cycle()
        if len(cycle) < 2:
            self.rotation_timer.stop()
            self._switch_state(self._get_active_fallback_state())
            return

        try:
            curr_idx = cycle.index(self.current_state)
            next_idx = (curr_idx + 1) % len(cycle)
        except ValueError:
            next_idx = 0

        next_state = cycle[next_idx]
        self._switch_state(next_state)

    def _get_active_fallback_state(self) -> str:
        cycle = self._get_active_rotation_cycle()
        if cycle:
            if self.current_state in cycle:
                return self.current_state
            return cycle[0]
        if self.mic_data.get("active", False) and self.settings_service.get("enable_mic_indicator", True):
            return "MIC_ACTIVE"
        return "IDLE"

    def _start_greeting(self):
        hour = datetime.now().hour
        if 5 <= hour < 12:
            self.greeting_full_text = "Good morning"
        elif 12 <= hour < 17:
            self.greeting_full_text = "Good afternoon"
        else:
            self.greeting_full_text = "Good evening"

        self.greeting_char_idx = 0
        self.is_greeting_active = True
        if hasattr(self, "rotation_timer") and self.rotation_timer.isActive():
            self.rotation_timer.stop()

        self._switch_state("GREETING")
        self.compact_bar.show_greeting("")
        self.typewriter_timer.start(100)  # Steady 100ms per character typewriter pace

    def _on_typewriter_tick(self):
        if not getattr(self, "is_greeting_active", False):
            self.typewriter_timer.stop()
            return

        self.greeting_char_idx += 1
        typed = self.greeting_full_text[:self.greeting_char_idx]
        self.compact_bar.show_greeting(typed)

        if self.greeting_char_idx >= len(self.greeting_full_text):
            self.typewriter_timer.stop()
            self.greeting_hold_timer.start(5500)  # Hold on taskbar for at least 5.5 seconds once fully typed

    def _finish_greeting(self):
        if hasattr(self, "_greeting_startup_timer") and self._greeting_startup_timer.isActive():
            self._greeting_startup_timer.stop()
        if hasattr(self, "typewriter_timer") and self.typewriter_timer.isActive():
            self.typewriter_timer.stop()
        if hasattr(self, "greeting_hold_timer") and self.greeting_hold_timer.isActive():
            self.greeting_hold_timer.stop()
        self.is_greeting_active = False
        self._switch_state(self._get_active_fallback_state())
        self._update_rotation_timer()

    def _on_settings_changed(self, settings: dict):
        placement = settings.get("placement", "top")
        w_enabled = settings.get("weather_enabled", True)
        self.compact_bar.set_weather_visible(w_enabled)
        self.compact_bar.set_placement(placement)

        if placement == "full_taskbar":
            max_b = settings.get("full_taskbar_width", 505)
            optimal_w = self.compact_bar.update_elastic_layout(max_b)
            if self.current_state not in ("EXPANDED", "SHELF"):
                self._animate_size(optimal_w, 42)
        else:
            self.base_pill_w = settings.get("pill_width", 270)
            target_w = self._get_scaled_width()
            if self.current_state == "MEDIA":
                self._animate_size(target_w, 35)
            elif self.current_state == "IDLE":
                idle_base = 325 if (placement == "taskbar" and w_enabled) else 225
                idle_w = int(idle_base * (settings.get("notch_scale", 90) / 100.0))
                self._animate_size(idle_w, 28)
        self._sync_layout()
        self._update_rotation_timer()
        self.update()

    def _on_media_updated(self, data: dict):
        self.media_data = data
        has_media = data["has_media"]
        is_playing = data["is_playing"]

        if data["thumbnail"]:
            self.music_color = extract_dominant_color(data["thumbnail"])
        else:
            self.music_color = QColor(255, 255, 255)

        if getattr(self, "is_greeting_active", False) or self.current_state == "NOTIFICATION_TOAST":
            return

        self.compact_bar.show_media(
            data["display_text"],
            data["thumbnail"],
            is_playing
        )

        self._update_rotation_timer()

        if self.current_state not in ("EXPANDED", "COPY_TOAST", "VOLUME_HUD", "BATTERY_ALERT", "SHELF", "GREETING", "NOTIFICATION_TOAST"):
            self._switch_state(self._get_active_fallback_state())
            if self.settings_service.get("placement", "top") == "full_taskbar":
                max_b = self.settings_service.get("full_taskbar_width", 505)
                optimal_w = self.compact_bar.update_elastic_layout(max_b)
                self._animate_size(optimal_w, 42)

    def _on_clipboard_copied(self, item: dict):
        if self.current_state == "NOTIFICATION_TOAST":
            return
        preview = item["preview"]
        is_img = (item.get("type") == "image")
        icon = "📸" if is_img else "📋"
        text = "Screenshot Captured" if is_img else f"Copied · {preview}"

        self.compact_bar.show_toast(icon, text)

        if self.current_state in ("MEDIA", "IDLE", "DOWNLOAD", "MIC_ACTIVE"):
            self.previous_compact_state = self.current_state

        self._switch_state("COPY_TOAST")
        self.toast_timer.start(2500)

    def _end_copy_toast(self):
        if self.current_state == "COPY_TOAST":
            self._switch_state(self._get_active_fallback_state())

    def _switch_state(self, state: str):
        self.current_state = state
        if state in ("EXPANDED", "SHELF"):
            if hasattr(self, "outside_click_timer") and not self.outside_click_timer.isActive():
                self.outside_click_timer.start(75)
        else:
            if hasattr(self, "outside_click_timer") and self.outside_click_timer.isActive():
                self.outside_click_timer.stop()
            if self.settings_service.get("placement", "top") in ("taskbar", "full_taskbar"):
                self._ensure_topmost()

        scale = self.settings_service.get("notch_scale", 90) / 100.0
        placement = self.settings_service.get("placement", "top")
        is_full_tb = (placement == "full_taskbar")

        if state == "MEDIA":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            self.compact_bar.show_media(
                self.media_data.get("display_text", ""),
                self.media_data.get("thumbnail"),
                self.media_data.get("is_playing", False)
            )
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                target_w = self._get_scaled_width()
                self._animate_size(target_w, 35)

        elif state == "VOLUME_HUD":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            self.compact_bar.stack.setCurrentWidget(self.compact_bar.volume_page)
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(250 * scale), 30)

        elif state == "COPY_TOAST":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            self.compact_bar.stack.setCurrentWidget(self.compact_bar.toast_page)
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(240 * scale), 30)

        elif state == "DOWNLOAD":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            dl = self.download_data
            self.compact_bar.show_download(
                dl.get("filename", "File"),
                dl.get("size_mb", 0.0),
                dl.get("speed_str", "0 KB/s")
            )
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(260 * scale), 32)

        elif state == "MIC_ACTIVE":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            self.compact_bar.show_mic_status(self.mic_data.get("app", ""))
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(240 * scale), 30)

        elif state == "BATTERY_ALERT":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            ba = self.battery_alert_data
            self.compact_bar.show_battery_alert(
                ba.get("title", "Battery"),
                ba.get("is_charging", True),
                ba.get("pct", 100)
            )
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(250 * scale), 30)

        elif state == "NOTIFICATION_TOAST":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(280 * scale), 32)

        elif state == "GREETING":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                fm = self.compact_bar.greeting_lbl.fontMetrics()
                w_greet = fm.horizontalAdvance(getattr(self, "greeting_full_text", "Good morning")) + 60
                self._animate_size(int(max(w_greet, 200) * scale), 32)

        elif state == "IDLE":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            self.compact_bar.show_idle()
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                w_enabled = self.settings_service.get("weather_enabled", True)
                idle_base = 325 if (placement == "taskbar" and w_enabled) else 225
                idle_w = int(idle_base * scale)
                self._animate_size(idle_w, 28)

        elif state == "NET_SPEED":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            st = getattr(self, "system_stats", {})
            self.compact_bar.show_net_speed(st.get("net_down_str", "0 KB/s"), st.get("net_up_str", "0 KB/s"))
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(240 * scale), 28)

        elif state == "CPU_RAM":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            st = getattr(self, "system_stats", {})
            self.compact_bar.show_cpu_ram(st.get("cpu", 0), st.get("ram", 0))
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(215 * scale), 28)

        elif state == "WEATHER":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            wd = getattr(self.compact_bar, "current_weather_data", None) or {}
            self.compact_bar.show_weather_page(
                wd.get("temp_str", "22°C"),
                wd.get("condition", "Partly cloudy"),
                wd.get("icon", "🌙☁️")
            )
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(245 * scale), 28)

        elif state == "DATE":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            self.compact_bar.show_date_page()
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(235 * scale), 28)

        elif state == "NOTIFICATIONS":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            nd = getattr(self, "notification_data", {}) or {}
            self.compact_bar.show_notification_page(
                nd.get("count", 0),
                nd.get("display_text", "No notifications")
            )
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self.cur_w = full_w
                self.cur_h = 42
                self._sync_layout()
            else:
                self._animate_size(int(200 * scale), 28)

        elif state == "EXPANDED":
            self.compact_bar.hide()
            self.shelf_widget.hide()
            self.dashboard_widget.show()
            self._animate_size(760, 480)

        elif state == "SHELF":
            self.compact_bar.hide()
            self.dashboard_widget.hide()
            self.shelf_widget.show()
            self._animate_size(500, 300)

    def _get_anim_duration(self, is_expanding: bool) -> int:
        mode = self.settings_service.get("animation_speed", "smooth")
        if mode == "snappy":
            return 170 if is_expanding else 130
        elif mode == "relaxed":
            return 320 if is_expanding else 250
        else: # smooth
            return 240 if is_expanding else 190

    def _animate_size(self, target_w, target_h):
        # Guard: never shrink expanded or shelf panels back to compact height
        if self.current_state in ("EXPANDED", "SHELF") and target_h < 150:
            return
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.size_anim.stop()
        if int(self.cur_w) == target_w and int(self.cur_h) == target_h:
            self._sync_layout()
            self.update()
            return

        is_expanding = (target_h > self.cur_h or target_w > self.cur_w)
        dur = self._get_anim_duration(is_expanding)
        self.size_anim.setDuration(dur)
        if is_expanding:
            self.size_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        else:
            self.size_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.size_anim.setStartValue(QSize(int(self.cur_w), int(self.cur_h)))
        self.size_anim.setEndValue(QSize(target_w, target_h))
        self.size_anim.start()

    def _on_size_anim_frame(self, val: QSize):
        self.cur_w = val.width()
        self.cur_h = val.height()
        self._sync_layout()
        self._update_rotation_timer()
        self.update()

    def _sync_layout(self):
        style = self.settings_service.get("notch_style", "notch")
        placement = self.settings_service.get("placement", "top")
        is_full_tb = (placement == "full_taskbar")
        is_bottom = (placement in ("taskbar", "full_taskbar") and self.current_state in COMPACT_STATES)

        screen = QApplication.primaryScreen().geometry()

        if self.current_state in COMPACT_STATES:
            if is_full_tb:
                # FULL TASKBAR: Flush across full space till Start button, without pill
                max_b = self.settings_service.get("full_taskbar_width", 505)
                safe_max_w = max(200, max_b - 36)
                full_w = safe_max_w
                full_h = int(self.cur_h)
                x = 0
                y = int(screen.y() + screen.height() - full_h - 3) # Vertically centered inside taskbar
                self.setGeometry(x, y, full_w, full_h)
                self.compact_bar.setGeometry(0, 0, full_w, full_h)
                self.compact_bar.setFixedWidth(full_w)
                self._ensure_topmost()
            elif is_bottom:
                total_w = int(self.cur_w + 2 * self.margin)
                total_h = int(self.cur_h)
                user_x = self.settings_service.get("taskbar_x_offset", 250)
                x = int(screen.x() + user_x - total_w / 2.0)
                gap = 6 if style == "island" else 0
                y = int(screen.y() + screen.height() - total_h - gap)
                self.setGeometry(x, y, total_w, total_h)
                self.compact_bar.setGeometry(self.margin, 0, self.cur_w, self.cur_h)
                self._ensure_topmost()
            else:
                total_w = int(self.cur_w + 2 * self.margin)
                total_h = int(self.cur_h)
                top_gap = 8 if style == "island" else 0
                x = int(screen.x() + (screen.width() - total_w) / 2.0)
                y = int(screen.y() + top_gap)
                self.setGeometry(x, y, total_w, total_h)
                self.compact_bar.setGeometry(self.margin, 0, self.cur_w, self.cur_h)

        elif self.current_state in ("EXPANDED", "SHELF"):
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            total_w = int(self.cur_w + 2 * self.margin)
            total_h = int(self.cur_h)
            x = int(screen.x() + (screen.width() - total_w) / 2.0)
            if placement in ("taskbar", "full_taskbar"):
                y = int(screen.y() + screen.height() - total_h - 58)
            else:
                y = int(screen.y())

            self.setGeometry(x, y, total_w, total_h)
            if self.current_state == "EXPANDED":
                self.dashboard_widget.setGeometry(self.margin, 6, self.cur_w, self.cur_h - 10)
            elif self.current_state == "SHELF":
                self.shelf_widget.setGeometry(self.margin, 6, self.cur_w, self.cur_h - 10)

    def expand_dashboard(self):
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._last_expand_time = time.time()
        if self.current_state in COMPACT_STATES:
            self.previous_compact_state = self._get_active_fallback_state()
        if hasattr(self, "rotation_timer") and self.rotation_timer.isActive():
            self.rotation_timer.stop()
        if hasattr(self, "typewriter_timer") and self.typewriter_timer.isActive():
            self.typewriter_timer.stop()
        if hasattr(self, "greeting_hold_timer") and self.greeting_hold_timer.isActive():
            self.greeting_hold_timer.stop()
        if hasattr(self, "_greeting_startup_timer") and self._greeting_startup_timer.isActive():
            self._greeting_startup_timer.stop()
        self.is_greeting_active = False
        self._switch_state("EXPANDED")
        if hasattr(self, "outside_click_timer"):
            self.outside_click_timer.start(75)
        self.raise_()
        self.activateWindow()
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        except Exception:
            pass

    def open_shelf(self):
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._last_expand_time = time.time()
        if hasattr(self, "rotation_timer") and self.rotation_timer.isActive():
            self.rotation_timer.stop()
        if hasattr(self, "outside_click_timer") and self.outside_click_timer.isActive():
            self.outside_click_timer.stop()
        self._switch_state("SHELF")
        self.raise_()
        self.activateWindow()

    def open_settings(self):
        if self.settings_window.isMinimized():
            self.settings_window.showNormal()
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def collapse(self):
        if hasattr(self, "outside_click_timer"):
            self.outside_click_timer.stop()
        target = self.previous_compact_state if self.previous_compact_state not in ("EXPANDED", "SHELF") else self._get_active_fallback_state()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._switch_state(target)
        self._sync_layout()
        if self.settings_service.get("placement", "top") in ("taskbar", "full_taskbar"):
            self._ensure_topmost()
        self._update_rotation_timer()

    def _on_pin_toggled(self, pinned: bool):
        self.is_pinned = pinned

    def _tick_topmost_keeper(self):
        """Periodically re-asserts topmost z-order over Windows Shell_TrayWnd taskbar while compact."""
        if self.settings_service.get("placement", "top") in ("taskbar", "full_taskbar") and self.current_state in COMPACT_STATES:
            self._ensure_topmost()

    def _check_expanded_focus_loss(self):
        """Monitors focus loss and clicks outside while dashboard is open."""
        if self.current_state != "EXPANDED":
            if hasattr(self, "outside_click_timer") and self.outside_click_timer.isActive():
                self.outside_click_timer.stop()
            return

        if getattr(self, "is_pinned", False):
            return

        if time.time() - getattr(self, "_last_expand_time", 0.0) < 0.35:
            return

        if QApplication.activePopupWidget() is not None:
            return

        # 1. Native Windows Foreground / Focus Check
        try:
            import ctypes
            user32 = ctypes.windll.user32
            fg = user32.GetForegroundWindow()
            if fg != 0:
                self_hwnd = int(self.winId())
                settings_hwnd = (
                    int(self.settings_window.winId())
                    if hasattr(self, "settings_window") and self.settings_window.isVisible()
                    else 0
                )
                root_fg = user32.GetAncestor(fg, 2)
                owner_fg = user32.GetAncestor(fg, 3)
                is_our_window = (
                    fg == self_hwnd
                    or (root_fg != 0 and root_fg == self_hwnd)
                    or (owner_fg != 0 and owner_fg == self_hwnd)
                    or (settings_hwnd != 0 and (fg == settings_hwnd or root_fg == settings_hwnd or owner_fg == settings_hwnd))
                )
                if not is_our_window:
                    self.collapse()
                    return
        except Exception:
            pass

        # 2. Native Windows Outside Click Check
        try:
            import ctypes
            user32 = ctypes.windll.user32
            l_down = (user32.GetAsyncKeyState(0x01) & 0x8000) != 0
            r_down = (user32.GetAsyncKeyState(0x02) & 0x8000) != 0
            if l_down or r_down:
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                pt = POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                geom = self.geometry()
                inside_self = geom.contains(pt.x, pt.y)
                inside_settings = (
                    hasattr(self, "settings_window")
                    and self.settings_window.isVisible()
                    and self.settings_window.geometry().contains(pt.x, pt.y)
                )
                if not inside_self and not inside_settings:
                    self.collapse()
                    return
        except Exception:
            pass

        # 3. Qt application focus fallback
        if not self.isActiveWindow():
            if not (hasattr(self, "settings_window") and self.settings_window.isActiveWindow()):
                self.collapse()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if time.time() - getattr(self, "_last_expand_time", 0.0) < 0.35:
                return
            if not getattr(self, "is_pinned", False) and self.current_state == "EXPANDED":
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    fg = user32.GetForegroundWindow()
                    self_hwnd = int(self.winId())
                    settings_hwnd = (
                        int(self.settings_window.winId())
                        if hasattr(self, "settings_window") and self.settings_window.isVisible()
                        else 0
                    )
                    root_fg = user32.GetAncestor(fg, 2)
                    owner_fg = user32.GetAncestor(fg, 3)
                    is_our_window = (
                        fg == self_hwnd
                        or (root_fg != 0 and root_fg == self_hwnd)
                        or (owner_fg != 0 and owner_fg == self_hwnd)
                        or (settings_hwnd != 0 and (fg == settings_hwnd or root_fg == settings_hwnd or owner_fg == settings_hwnd))
                    )
                    if fg != 0 and not is_our_window:
                        self.collapse()
                        return
                except Exception:
                    pass
                if not self.isActiveWindow():
                    if not (hasattr(self, "settings_window") and self.settings_window.isActiveWindow()):
                        self.collapse()
        super().changeEvent(event)

    def enterEvent(self, event):
        self.hover_leave_timer.stop()
        if self.settings_service.get("placement", "top") in ("taskbar", "full_taskbar"):
            self._ensure_topmost()
        if self.settings_service.get("opens_on", "click") == "hover":
            if self.current_state in COMPACT_STATES:
                self.expand_dashboard()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        if self.settings_service.get("opens_on", "click") == "hover":
            if self.current_state == "EXPANDED" and not self.is_pinned:
                grace_ms = 850 if self.settings_service.get("placement", "top") in ("taskbar", "full_taskbar") else 350
                self.hover_leave_timer.start(grace_ms)
        super().leaveEvent(event)

    def _on_hover_leave_timeout(self):
        if not self.underMouse() and not self.is_pinned and self.current_state == "EXPANDED":
            self.collapse()

    def wheelEvent(self, event):
        if self.current_state in COMPACT_STATES:
            delta = event.angleDelta().y()
            step = 5 if delta > 0 else -5
            curr_scale = self.settings_service.get("notch_scale", 90)
            new_scale = max(70, min(130, curr_scale + step))
            if new_scale != curr_scale:
                self.settings_service.set("notch_scale", new_scale)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.current_state in COMPACT_STATES:
                self.expand_dashboard()
                event.accept()
                return
        super().mousePressEvent(event)

    def _get_path_point(self, u, x1, x2, h):
        placement = self.settings_service.get("placement", "top")
        is_bottom = (placement == "taskbar" and self.current_state in COMPACT_STATES)

        ew = self.ear_w if self.current_state not in ("IDLE", "VOLUME_HUD") else 9
        eh = self.ear_h if self.current_state not in ("IDLE", "VOLUME_HUD") else 6
        cr = self.corner_r if self.current_state not in ("IDLE", "VOLUME_HUD") else 11
        cr = min(cr, h / 2.0)
        x_mid = (x1 + x2) / 2.0

        style = self.settings_service.get("notch_style", "notch")
        if style == "island" and self.current_state in COMPACT_STATES:
            r = h / 2.0
            if u <= 0.4:
                ang = math.pi / 2.0 + (u / 0.4) * (math.pi / 2.0)
                cx = x1 + r
                cy = r
                return QPointF(cx + r * math.cos(ang), cy - r * math.sin(ang))
            elif u <= 0.7:
                ang = math.pi + ((u - 0.4) / 0.3) * (math.pi / 2.0)
                cx = x1 + r
                cy = h - r
                return QPointF(cx + r * math.cos(ang), cy - r * math.sin(ang))
            else:
                k = (u - 0.7) / 0.3
                bx = x1 + r
                return QPointF(bx + k * (x_mid - bx), h)

        if u <= 0.2:
            k = u / 0.2
            x = (x1 - ew) + k * ew
            y = (1.0 - math.cos(k * math.pi / 2)) * eh
        elif u <= 0.6:
            k = (u - 0.2) / 0.4
            x = x1
            y = eh + k * (h - cr - eh)
        elif u <= 0.8:
            k = (u - 0.6) / 0.2
            ang = math.pi + k * (math.pi / 2)
            cx = x1 + cr
            cy = h - cr
            x = cx + cr * math.cos(ang)
            y = cy - cr * math.sin(ang)
        else:
            k = (u - 0.8) / 0.2
            bx = x1 + cr
            x = bx + k * (x_mid - bx)
            y = h

        # If on taskbar at bottom, reflect vertically: y' = h - y!
        if is_bottom:
            return QPointF(x, h - y)
        return QPointF(x, y)

    def make_notch_path(self, w, h):
        style = self.settings_service.get("notch_style", "notch")
        placement = self.settings_service.get("placement", "top")
        is_bottom = (placement == "taskbar" and self.current_state in COMPACT_STATES)

        x1 = self.margin
        x2 = self.margin + w

        path = QPainterPath()

        if self.current_state in ("EXPANDED", "SHELF"):
            path.addRoundedRect(QRectF(x1, 0, w, h), 20, 20)
            return path

        if style == "island" and self.current_state in COMPACT_STATES:
            r = min(self.corner_r, h / 2.0)
            path.addRoundedRect(QRectF(x1, 0, w, h), r, r)
            return path

        elif style == "line" and self.current_state in COMPACT_STATES:
            if is_bottom:
                path.moveTo(x1, h)
                path.lineTo(x1, 4)
                path.quadTo(QPointF(x1, 0), QPointF(x1 + 4, 0))
                path.lineTo(x2 - 4, 0)
                path.quadTo(QPointF(x2, 0), QPointF(x2, 4))
                path.lineTo(x2, h)
                path.closeSubpath()
                return path
            else:
                path.moveTo(x1, 0)
                path.lineTo(x1, h - 4)
                path.quadTo(QPointF(x1, h), QPointF(x1 + 4, h))
                path.lineTo(x2 - 4, h)
                path.quadTo(QPointF(x2, h), QPointF(x2, h - 4))
                path.lineTo(x2, 0)
                path.closeSubpath()
                return path

        # Default S-Curve Notch
        ew = self.ear_w if self.current_state not in ("IDLE", "VOLUME_HUD") else 9
        placement = self.settings_service.get("placement", "top")
        is_bottom = (placement == "taskbar" and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"))
        eh = self.ear_h if self.current_state not in ("IDLE", "VOLUME_HUD") else 6
        cr = self.corner_r if self.current_state not in ("IDLE", "VOLUME_HUD") else 11

        if is_bottom:
            # REVERSED NOTCH DESIGN: Emerging from bottom bezel / taskbar!
            path.moveTo(x1 - ew, h)
            path.cubicTo(
                QPointF(x1 - ew * 0.4, h),
                QPointF(x1, h - eh * 0.4),
                QPointF(x1, h - eh)
            )
            path.lineTo(x1, cr)
            path.quadTo(QPointF(x1, 0), QPointF(x1 + cr, 0))
            path.lineTo(x2 - cr, 0)
            path.quadTo(QPointF(x2, 0), QPointF(x2, cr))
            path.lineTo(x2, h - eh)
            path.cubicTo(
                QPointF(x2, h - eh * 0.4),
                QPointF(x2 + ew * 0.4, h),
                QPointF(x2 + ew, h)
            )
            path.lineTo(x1 - ew, h)
            path.closeSubpath()
            return path
        else:
            # Standard top notch emerging from top bezel
            path.moveTo(x1 - ew, 0)
            path.cubicTo(
                QPointF(x1 - ew * 0.4, 0),
                QPointF(x1, eh * 0.4),
                QPointF(x1, eh)
            )
            path.lineTo(x1, h - cr)
            path.quadTo(QPointF(x1, h), QPointF(x1 + cr, h))
            path.lineTo(x2 - cr, h)
            path.quadTo(QPointF(x2, h), QPointF(x2, h - cr))
            path.lineTo(x2, eh)
            path.cubicTo(
                QPointF(x2, eh * 0.4),
                QPointF(x2 + ew * 0.4, 0),
                QPointF(x2 + ew, 0)
            )
            path.lineTo(x1 - ew, 0)
            path.closeSubpath()
            return path

    def _get_active_glow_color(self):
        match_cover = self.settings_service.get("match_music_color", False)
        if match_cover and self.current_state == "MEDIA" and self.media_data.get("has_media", False):
            return self.music_color

        hex_c = self.settings_service.get("edge_light_color", "#ffffff")
        return QColor(hex_c)

    def paintEvent(self, event):
        placement = self.settings_service.get("placement", "top")
        if placement == "full_taskbar" and self.current_state in COMPACT_STATES:
            # Full Taskbar mode: "without pill and center H and V aligned"
            # Fill alpha=1 so Windows hit-testing delivers all clicks to this window,
            # while remaining 100% visually invisible to the human eye ("without pill").
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.cur_w
        h = self.cur_h
        x1 = self.margin
        x2 = self.margin + w
        x_mid = (x1 + x2) / 2.0

        path = self.make_notch_path(w, h)

        edge_light_on = self.settings_service.get("edge_light_enabled", True)
        effect_mode = self.settings_service.get("edge_light_effect", "twin_comets")
        intensity_pct = self.settings_service.get("edge_light_intensity", 80) / 100.0
        outline_on = self.settings_service.get("outline_enabled", True)
        outline_w = self.settings_service.get("outline_width", 1)
        soft_edge = self.settings_service.get("soft_edge", "Medium")

        active_color = self._get_active_glow_color()

        ew = self.ear_w if self.current_state not in ("IDLE", "VOLUME_HUD") else 9
        placement = self.settings_service.get("placement", "top")
        is_bottom = (placement == "taskbar" and self.current_state in COMPACT_STATES)

        # -------------------------------------------------------------
        # 1. Glass Effect & Edge-to-Center Transparency Fill
        # 0% is solid opaque glass. As transparency increases (0 to 100),
        # transparency creeps from the edges inward to the center with
        # increasing penetration range and increasing edge transparency!
        # -------------------------------------------------------------
        trans_pct = self.settings_service.get("glass_transparency", 0) / 100.0  # 0.0 to 1.0

        if trans_pct <= 0.001:
            # 0% transparency: Solid rich dark glass
            painter.fillPath(path, QColor(10, 10, 14, 255))
        else:
            # Edge-to-center transparency
            edge_alpha = int(255 * (1.0 - trans_pct))
            center_alpha = int(255 - trans_pct * 95)  # remains dark glass at center (down to ~160)

            # Penetration range expands from edges toward center (up to 0.48 at trans=1.0)
            penetration = 0.48 * trans_pct
            s_left = penetration
            s_right = 1.0 - penetration

            h_grad = QLinearGradient(x1 - ew, 0, x2 + ew, 0)
            c_edge = QColor(10, 11, 16, edge_alpha)
            c_center = QColor(10, 11, 16, center_alpha)

            h_grad.setColorAt(0.0, c_edge)
            if s_left > 0.01:
                h_grad.setColorAt(s_left, c_center)
            h_grad.setColorAt(0.5, c_center)
            if s_right < 0.99:
                h_grad.setColorAt(s_right, c_center)
            h_grad.setColorAt(1.0, c_edge)

            painter.fillPath(path, QBrush(h_grad))

            # Vertical bottom edge transparency fade
            if trans_pct > 0.15:
                v_fade = QLinearGradient(0, 0, 0, h)
                v_fade.setColorAt(0.0, QColor(0, 0, 0, 0))
                v_fade.setColorAt(max(0.0, 1.0 - trans_pct * 0.45), QColor(0, 0, 0, 0))
                v_fade.setColorAt(1.0, QColor(10, 11, 16, int(edge_alpha * 0.4)))
                painter.fillPath(path, QBrush(v_fade))

        # -------------------------------------------------------------
        # Glass Specular Refraction Highlight (Top curved glass reflection)
        # -------------------------------------------------------------
        spec_h = min(11.0, h * 0.42)
        spec_grad = QLinearGradient(0, 0, 0, spec_h)
        spec_alpha = int(32 + 28 * trans_pct)
        spec_grad.setColorAt(0.0, QColor(255, 255, 255, spec_alpha))
        spec_grad.setColorAt(0.45, QColor(255, 255, 255, int(spec_alpha * 0.35)))
        spec_grad.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.save()
        painter.setClipPath(path)
        painter.fillRect(QRectF(x1 - ew - 5, 0, w + 2 * ew + 10, spec_h), QBrush(spec_grad))
        painter.restore()

        # -------------------------------------------------------------
        # 2. Low-Height Baseline Equalizer (Clean White Micro-Ticks)
        # Spans across the bottom width from left to right with low height profile
        # -------------------------------------------------------------
        if self.current_state == "MEDIA" and self.media_data.get("has_media", False):
            base_y = h - 3.2
            start_x = x1 + 16
            end_x = x2 - 16
            spacing = 5.2
            num_ticks = max(8, int((end_x - start_x) / spacing))
            t = time.time() * 4.4
            is_playing = self.media_data.get("is_playing", False)

            painter.setPen(Qt.PenStyle.NoPen)
            for i in range(num_ticks):
                tx = start_x + i * spacing
                ratio = i / float(num_ticks - 1)  # 0 to 1

                # Parabolic envelope: grounded at ends (~1.2px), rising subtly in center
                env = 4.0 * ratio * (1.0 - ratio)  # 0 at edges, 1.0 at center

                if is_playing:
                    # Organic audio frequencies with low height profile (~3.8px max)
                    wave = abs(math.sin(i * 0.46 + t)) * 0.55 + abs(math.cos(i * 0.74 - t * 0.85)) * 0.45
                    tick_h = 1.2 + env * (0.6 + wave * 2.2)  # subtle low height (1.2px to ~3.8px)
                    tick_alpha = int(140 + 115 * (0.35 + 0.65 * env * wave))
                else:
                    # Resting micro ticks when paused
                    tick_h = 1.2 + env * 0.4
                    tick_alpha = 90

                c_tick = QColor(255, 255, 255, tick_alpha)
                painter.setBrush(QBrush(c_tick))
                # Grounded at base_y, extending upwards
                painter.drawRoundedRect(QRectF(tx - 0.8, base_y - tick_h, 1.6, tick_h), 0.8, 0.8)

        # 3. Hairline Outline
        if outline_on:
            trans_pct = self.settings_service.get("glass_transparency", 0) / 100.0
            rim_alpha = int(55 + 40 * trans_pct)
            hairline_pen = QPen(QColor(255, 255, 255, rim_alpha), float(outline_w))
            painter.setPen(hairline_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # 4. Tapered Line Comets
        if edge_light_on and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
            cr_r = active_color.red()
            cr_g = active_color.green()
            cr_b = active_color.blue()

            # Twin comets
            if effect_mode == "twin_comets":
                u_head = (1.0 - math.cos(self.light_time)) / 2.0
                tail_len = 0.22
                num_segs = 14
                beam_alpha = int(255 * intensity_pct)

                for side in (-1, 1):
                    prev_pt = None
                    for step in range(num_segs + 1):
                        ratio = step / float(num_segs)
                        u = max(0.0, u_head - (1.0 - ratio) * tail_len)
                        pt_base = self._get_path_point(u, x1, x2, h)
                        pt = pt_base if side == 1 else QPointF(2 * x_mid - pt_base.x(), pt_base.y())

                        if prev_pt is not None:
                            thick = 1.0 + 2.4 * (ratio ** 1.5)
                            alpha = int(beam_alpha * (0.15 + 0.85 * (ratio ** 1.8)))
                            pen = QPen(QColor(cr_r, cr_g, cr_b, alpha), thick, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                            painter.setPen(pen)
                            painter.drawLine(prev_pt, pt)
                        prev_pt = pt

                if u_head > 0.88:
                    mid_flash = (u_head - 0.88) / 0.12
                    f_alpha = int(210 * mid_flash * intensity_pct)
                    flash_y = 0.0 if is_bottom else float(h)
                    g_mid = QRadialGradient(x_mid, flash_y, 8)
                    g_mid.setColorAt(0.0, QColor(255, 255, 255, f_alpha))
                    g_mid.setColorAt(0.5, QColor(cr_r, cr_g, cr_b, int(f_alpha * 0.5)))
                    g_mid.setColorAt(1.0, QColor(cr_r, cr_g, cr_b, 0))
                    painter.setBrush(QBrush(g_mid))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(QPointF(x_mid, flash_y), 8, 2.5)

            # Single comet
            elif effect_mode == "comet":
                u_head = self.comet_pos
                tail_len = 0.20
                num_segs = 16
                beam_alpha = int(255 * intensity_pct)

                prev_pt = None
                for step in range(num_segs + 1):
                    ratio = step / float(num_segs)
                    u_norm = (u_head - (1.0 - ratio) * tail_len) % 1.0
                    
                    if u_norm <= 0.5:
                        u_sub = u_norm * 2.0
                        pt = self._get_path_point(u_sub, x1, x2, h)
                    else:
                        u_sub = 1.0 - (u_norm - 0.5) * 2.0
                        p_orig = self._get_path_point(u_sub, x1, x2, h)
                        pt = QPointF(2 * x_mid - p_orig.x(), p_orig.y())

                    if prev_pt is not None:
                        thick = 1.0 + 2.5 * (ratio ** 1.5)
                        alpha = int(beam_alpha * (0.15 + 0.85 * (ratio ** 1.8)))
                        pen = QPen(QColor(cr_r, cr_g, cr_b, alpha), thick, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                        painter.setPen(pen)
                        painter.drawLine(prev_pt, pt)
                    prev_pt = pt

            # Breathe
            elif effect_mode == "breathe":
                pulse = (math.sin(self.light_time) + 1.0) / 2.0
                b_alpha = int((80 + 150 * pulse) * intensity_pct)
                b_pen = QPen(QColor(cr_r, cr_g, cr_b, b_alpha), 1.8)
                painter.setPen(b_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            if self.current_state != "SHELF":
                self.open_shelf()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if paths:
                self.shelf_widget.add_paths(paths)
                if self.current_state != "SHELF":
                    self.open_shelf()
                event.acceptProposedAction()

    def nativeEvent(self, eventType, message):
        try:
            import ctypes
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(message.__int__())
            # WM_NCHITTEST = 0x0084
            if msg.message == 0x0084:
                return True, 1  # HTCLIENT: delivers all mouse clicks & drag-drops to this window
            # WM_WTSSESSION_CHANGE = 0x02B1
            if msg.message == 0x02B1:
                # WTS_SESSION_UNLOCK = 0x8, WTS_SESSION_LOGON = 0x5
                if msg.wParam in (0x8, 0x5):
                    QTimer.singleShot(400, self._start_greeting)
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        try:
            if hasattr(self, 'rotation_timer'):
                self.rotation_timer.stop()
            if hasattr(self, 'typewriter_timer'):
                self.typewriter_timer.stop()
            if hasattr(self, 'greeting_hold_timer'):
                self.greeting_hold_timer.stop()
            try:
                import ctypes
                ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(int(self.winId()))
            except Exception:
                pass
            if hasattr(self, 'system_service'):
                self.system_service.stop()
            if hasattr(self, 'media_service'):
                self.media_service.stop()
        except Exception:
            pass
        super().closeEvent(event)

