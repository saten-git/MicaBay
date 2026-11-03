import math
import time
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

class NotchWindow(QWidget):
    def __init__(self, media_service, clipboard_service, system_service, settings_service, volume_service, weather_service=None):
        super().__init__()
        self.media_service = media_service
        self.clipboard_service = clipboard_service
        self.system_service = system_service
        self.settings_service = settings_service
        self.volume_service = volume_service
        self.weather_service = weather_service

        # States: "MEDIA", "COPY_TOAST", "VOLUME_HUD", "IDLE", "EXPANDED", "SHELF"
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

        # Smooth size animation
        self.size_anim = QVariantAnimation(self)
        self.size_anim.setDuration(220)
        self.size_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.size_anim.valueChanged.connect(self._on_size_anim_frame)

        self.media_data = {
            "has_media": False,
            "display_text": "",
            "is_playing": False,
            "thumbnail": None
        }

        self._last_expand_time = 0.0

        self._init_window()
        self._build_components()
        self._connect_signals()

        self.setAcceptDrops(True)
        self._switch_state("IDLE")
        self._sync_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_layout()
        if self.settings_service.get("placement", "top") in ("taskbar", "full_taskbar"):
            self._ensure_topmost()

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

    def _ensure_topmost(self):
        """Re-asserts topmost z-order over Windows Shell_TrayWnd taskbar without taking focus."""
        try:
            import ctypes
            hwnd = int(self.winId())
            # HWND_TOPMOST = -1
            # SWP_NOSIZE (0x0001) | SWP_NOMOVE (0x0002) | SWP_NOACTIVATE (0x0010) | SWP_SHOWWINDOW (0x0040)
            ctypes.windll.user32.SetWindowPos(
                hwnd, -1, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0010 | 0x0040
            )
        except Exception:
            pass

    def _build_components(self):
        self.compact_bar = CompactBar(self, self.weather_service)
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
        self.shelf_widget.hide()

    def _connect_signals(self):
        self.media_service.media_updated.connect(self._on_media_updated)
        self.clipboard_service.item_copied.connect(self._on_clipboard_copied)
        self.system_service.stats_updated.connect(self._on_stats_updated)
        self.volume_service.volume_changed.connect(self._on_volume_changed)
        self.settings_service.settings_changed.connect(self._on_settings_changed)
        self.compact_bar.elastic_size_requested.connect(self._on_elastic_size_requested)
        if self.weather_service:
            self.weather_service.weather_updated.connect(self._on_weather_updated)

    def _on_elastic_size_requested(self, optimal_w: int):
        if self.settings_service.get("placement", "top") == "full_taskbar":
            if self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
                if int(self.cur_w) != optimal_w:
                    self._animate_size(optimal_w, 42)

    def _on_weather_updated(self, data: dict):
        self.update()

    def _get_scaled_width(self):
        placement = self.settings_service.get("placement", "top")
        if placement == "full_taskbar":
            max_b = self.settings_service.get("full_taskbar_width", 505)
            if hasattr(self, "compact_bar"):
                return self.compact_bar.update_elastic_layout(max_b)
            return min(460, max_b - 14)
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
        self.compact_bar.update_battery(stats.get("battery", 95), stats.get("is_charging", False))

    def _on_volume_changed(self, pct: int, is_muted: bool):
        # Trigger Volume HUD when volume keys or slider changes
        if self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
            if self.current_state != "VOLUME_HUD":
                self.previous_compact_state = self.current_state

            self._switch_state("VOLUME_HUD")
            self.compact_bar.show_volume(pct, is_muted, self._get_active_glow_color())
            self.vol_hud_timer.start(1800)  # auto dismiss after 1.8s

    def _end_volume_hud(self):
        if self.current_state == "VOLUME_HUD":
            target = "MEDIA" if self.media_data.get("has_media", False) else "IDLE"
            self._switch_state(target)

    def _on_settings_changed(self, settings: dict):
        placement = settings.get("placement", "top")
        w_enabled = settings.get("weather_enabled", True)
        self.compact_bar.set_weather_visible(w_enabled)
        self.compact_bar.set_placement(placement)

        if placement == "full_taskbar":
            max_b = settings.get("full_taskbar_width", 505)
            optimal_w = self.compact_bar.update_elastic_layout(max_b)
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
        self.update()

    def _on_media_updated(self, data: dict):
        self.media_data = data
        has_media = data["has_media"]
        is_playing = data["is_playing"]

        if data["thumbnail"]:
            self.music_color = extract_dominant_color(data["thumbnail"])
        else:
            self.music_color = QColor(255, 255, 255)

        self.compact_bar.show_media(
            data["display_text"],
            data["thumbnail"],
            is_playing
        )

        if self.current_state not in ("EXPANDED", "COPY_TOAST", "VOLUME_HUD", "SHELF"):
            if has_media:
                self._switch_state("MEDIA")
            else:
                self._switch_state("IDLE")
        elif self.settings_service.get("placement", "top") == "full_taskbar":
            max_b = self.settings_service.get("full_taskbar_width", 505)
            optimal_w = self.compact_bar.update_elastic_layout(max_b)
            self._animate_size(optimal_w, 42)

    def _on_clipboard_copied(self, item: dict):
        preview = item["preview"]
        icon = "🖼️" if item["type"] == "image" else "📋"
        text = f"Copied · {preview}"

        self.compact_bar.show_toast(icon, text)

        if self.current_state in ("MEDIA", "IDLE"):
            self.previous_compact_state = self.current_state

        self._switch_state("COPY_TOAST")
        self.toast_timer.start(2500)

    def _end_copy_toast(self):
        if self.current_state == "COPY_TOAST":
            target = "MEDIA" if self.media_data.get("has_media", False) else "IDLE"
            self._switch_state(target)

    def _switch_state(self, state: str):
        self.current_state = state
        scale = self.settings_service.get("notch_scale", 90) / 100.0
        placement = self.settings_service.get("placement", "top")
        is_full_tb = (placement == "full_taskbar")

        if state == "MEDIA":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            self.compact_bar.stack.setCurrentWidget(self.compact_bar.media_page)
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self._animate_size(full_w, 42)
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
                self._animate_size(full_w, 42)
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
                self._animate_size(full_w, 42)
            else:
                self._animate_size(int(240 * scale), 30)

        elif state == "IDLE":
            self.compact_bar.show()
            self.dashboard_widget.hide()
            self.shelf_widget.hide()
            self.compact_bar.show_idle()
            if is_full_tb:
                max_b = self.settings_service.get("full_taskbar_width", 505)
                full_w = self.compact_bar.update_elastic_layout(max_b)
                self._animate_size(full_w, 42)
            else:
                w_enabled = self.settings_service.get("weather_enabled", True)
                idle_base = 325 if (placement == "taskbar" and w_enabled) else 225
                idle_w = int(idle_base * scale)
                self._animate_size(idle_w, 28)

        elif state == "EXPANDED":
            self.compact_bar.hide()
            self.shelf_widget.hide()
            self.dashboard_widget.show()
            self._animate_size(760, 450)

        elif state == "SHELF":
            self.compact_bar.hide()
            self.dashboard_widget.hide()
            self.shelf_widget.show()
            self._animate_size(500, 300)

    def _animate_size(self, target_w, target_h):
        self.size_anim.stop()
        if int(self.cur_w) == target_w and int(self.cur_h) == target_h:
            self._sync_layout()
            self.update()
            return
        self.size_anim.setStartValue(QSize(int(self.cur_w), int(self.cur_h)))
        self.size_anim.setEndValue(QSize(target_w, target_h))
        self.size_anim.start()

    def _on_size_anim_frame(self, val: QSize):
        self.cur_w = val.width()
        self.cur_h = val.height()
        self._sync_layout()
        self.update()

    def _sync_layout(self):
        style = self.settings_service.get("notch_style", "notch")
        placement = self.settings_service.get("placement", "top")
        is_full_tb = (placement == "full_taskbar")
        is_bottom = (placement in ("taskbar", "full_taskbar") and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"))

        screen = QApplication.primaryScreen().geometry()

        if self.current_state in ("MEDIA", "COPY_TOAST", "VOLUME_HUD", "IDLE"):
            if is_full_tb:
                # FULL TASKBAR: Flush across full space till Start button, without pill
                full_w = int(self.cur_w)
                full_h = int(self.cur_h)
                x = 0
                y = int(screen.y() + screen.height() - full_h - 3) # Vertically centered inside taskbar
                self.setGeometry(x, y, full_w, full_h)
                self.compact_bar.setGeometry(0, 0, full_w, full_h)
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
        self._last_expand_time = time.time()
        if self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
            self.previous_compact_state = "MEDIA" if self.media_data["has_media"] else "IDLE"
        self._switch_state("EXPANDED")
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
        target = self.previous_compact_state if self.previous_compact_state != "EXPANDED" else ("MEDIA" if self.media_data["has_media"] else "IDLE")
        self._switch_state(target)

    def _on_pin_toggled(self, pinned: bool):
        self.is_pinned = pinned

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            # Prevent instant re-collapse if dashboard was expanded within the last 500ms
            if time.time() - getattr(self, "_last_expand_time", 0.0) < 0.5:
                return
            if not self.isActiveWindow() and not self.is_pinned and self.current_state in ("EXPANDED", "SHELF"):
                if not (hasattr(self, "settings_window") and self.settings_window.isActiveWindow()):
                    self.collapse()
        super().changeEvent(event)

    def enterEvent(self, event):
        self.hover_leave_timer.stop()
        if self.settings_service.get("placement", "top") in ("taskbar", "full_taskbar"):
            self._ensure_topmost()
        if self.settings_service.get("opens_on", "click") == "hover":
            if self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
                self.expand_dashboard()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.settings_service.get("opens_on", "click") == "hover":
            if self.current_state in ("EXPANDED", "SHELF") and not self.is_pinned:
                grace_ms = 850 if self.settings_service.get("placement", "top") in ("taskbar", "full_taskbar") else 350
                self.hover_leave_timer.start(grace_ms)
        super().leaveEvent(event)

    def _on_hover_leave_timeout(self):
        if not self.underMouse() and not self.is_pinned and self.current_state in ("EXPANDED", "SHELF"):
            self.collapse()

    def wheelEvent(self, event):
        if self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
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
            if self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
                self.expand_dashboard()
                event.accept()
                return
        super().mousePressEvent(event)

    def _get_path_point(self, u, x1, x2, h):
        placement = self.settings_service.get("placement", "top")
        is_bottom = (placement == "taskbar" and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"))

        ew = self.ear_w if self.current_state not in ("IDLE", "VOLUME_HUD") else 9
        placement = self.settings_service.get("placement", "top")
        is_bottom = (placement == "taskbar" and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"))
        eh = self.ear_h if self.current_state not in ("IDLE", "VOLUME_HUD") else 6
        cr = self.corner_r if self.current_state not in ("IDLE", "VOLUME_HUD") else 11
        cr = min(cr, h / 2.0)
        x_mid = (x1 + x2) / 2.0

        style = self.settings_service.get("notch_style", "notch")
        if style == "island" and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
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
        is_bottom = (placement == "taskbar" and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"))

        x1 = self.margin
        x2 = self.margin + w

        path = QPainterPath()

        if self.current_state in ("EXPANDED", "SHELF"):
            path.addRoundedRect(QRectF(x1, 0, w, h), 20, 20)
            return path

        if style == "island" and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
            r = min(self.corner_r, h / 2.0)
            path.addRoundedRect(QRectF(x1, 0, w, h), r, r)
            return path

        elif style == "line" and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"):
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
        if placement == "full_taskbar" and self.current_state in ("MEDIA", "IDLE", "VOLUME_HUD", "COPY_TOAST"):
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
        is_bottom = (placement == "taskbar" and self.current_state in ("MEDIA", "IDLE", "COPY_TOAST", "VOLUME_HUD"))

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

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if paths:
            self.shelf_widget.add_paths(paths)
            event.acceptProposedAction()
