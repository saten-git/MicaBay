import os
import time
from datetime import datetime
from PySide6.QtCore import Qt, Signal, QTimer, QRectF
from PySide6.QtGui import QFont, QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QStackedWidget
)
from circular_gauge import CircularGauge
from weekly_bars import WeeklyBarsWidget
from appearance_settings_widget import AppearanceSettingsWidget

class DashboardWidget(QWidget):
    close_requested = Signal()
    pin_toggled = Signal(bool)
    shelf_requested = Signal()
    settings_requested = Signal()

    def __init__(self, clipboard_service, system_service, settings_service, weather_service=None, parent=None):
        super().__init__(parent)
        self.clipboard_service = clipboard_service
        self.system_service = system_service
        self.settings_service = settings_service
        self.weather_service = weather_service
        self.is_pinned = False

        # Pomodoro Focus state
        self.focus_seconds = 25 * 60
        self.focus_running = False
        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self._tick_focus)

        self._init_ui()

        # Connect service updates
        self.system_service.stats_updated.connect(self._on_stats_updated)
        self.clipboard_service.history_updated.connect(self._on_clipboard_updated)
        if self.weather_service:
            self.weather_service.weather_updated.connect(self._on_weather_updated)
            self._on_weather_updated(self.weather_service.get_data())

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 14)
        main_layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. Header Bar (Matches Exact Vayli Screenshot)
        # -------------------------------------------------------------
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        # App Logo (Rounded Squircle with Notch Icon)
        self.logo_btn = QPushButton("🫧")
        self.logo_btn.setFixedSize(28, 28)
        self.logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_btn.setStyleSheet("""
            QPushButton {
                background: #1c1c22;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #ffffff;
                font-size: 13px;
                padding: 0;
            }
            QPushButton:hover {
                background: #25252e;
            }
        """)
        self.logo_btn.clicked.connect(self._show_home)

        # "Home" Title
        self.home_btn = QPushButton("Home")
        self.home_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.home_btn.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: 700;
                color: #ffffff;
                background: transparent;
                border: none;
                padding: 0 4px;
            }
            QPushButton:hover {
                color: #d0d0d8;
            }
        """)
        self.home_btn.clicked.connect(self._show_home)

        sep_lbl = QLabel("|")
        sep_lbl.setStyleSheet("color: #3e3e48; font-size: 14px; font-weight: 500;")

        # "Monday, 2 Nov" Date
        now_dt = datetime.now()
        date_str = now_dt.strftime("%A, %d %b").replace(" 0", " ")
        self.date_lbl = QLabel(date_str)
        self.date_lbl.setStyleSheet("color: #8e8e98; font-size: 13px; font-weight: 500;")

        header_layout.addWidget(self.logo_btn)
        header_layout.addWidget(self.home_btn)
        header_layout.addWidget(sep_lbl)
        header_layout.addWidget(self.date_lbl)
        header_layout.addStretch()

        # Right Header Elements: Battery | ✏️ | ⚙️ | ✕
        self.bat_lbl = QLabel("72% 🔋")
        self.bat_lbl.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600; padding-right: 8px;")

        btn_style = """
            QPushButton {
                background: #1c1c22;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                color: #ffffff;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #282832;
            }
        """

        self.edit_btn = QPushButton("✏️")
        self.edit_btn.setFixedSize(28, 28)
        self.edit_btn.setToolTip("Customize Dashboard")
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setStyleSheet(btn_style)

        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setStyleSheet(btn_style)
        self.settings_btn.clicked.connect(self.settings_requested.emit)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setToolTip("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #1c1c22;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                color: #ffffff;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(240, 60, 60, 0.6);
            }
        """)
        close_btn.clicked.connect(self.close_requested.emit)

        header_layout.addWidget(self.bat_lbl)
        header_layout.addWidget(self.edit_btn)
        header_layout.addWidget(self.settings_btn)
        header_layout.addWidget(close_btn)
        main_layout.addLayout(header_layout)

        # -------------------------------------------------------------
        # 2. Main Content Stack
        # -------------------------------------------------------------
        self.content_stack = QStackedWidget(self)

        # Page 0: Cards Grid (2 Rows x 3 Columns)
        self.cards_page = QWidget()
        grid = QGridLayout(self.cards_page)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        # -------------------------------------------------------------
        # CARD 1: SCREEN TIME (Top-Left)
        # -------------------------------------------------------------
        self.card_screen = self._create_card()
        cs_layout = QVBoxLayout(self.card_screen)
        cs_layout.setContentsMargins(14, 12, 14, 12)
        cs_layout.setSpacing(3)

        cs_head = QLabel("📊  SCREEN TIME")
        cs_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")

        self.screen_time_val = QLabel("1h")
        self.screen_time_val.setStyleSheet("color: #ffffff; font-size: 30px; font-weight: 800; margin-top: 1px;")

        app_row = QHBoxLayout()
        app_row.setSpacing(6)
        app_dot = QLabel("🔹")
        app_dot.setStyleSheet("font-size: 10px; background: transparent;")
        self.screen_top_app = QLabel("Antigravity IDE · 26m")
        self.screen_top_app.setStyleSheet("color: #9e9ea8; font-size: 11px; font-weight: 500;")
        app_row.addWidget(app_dot)
        app_row.addWidget(self.screen_top_app)
        app_row.addStretch()

        self.weekly_bars = WeeklyBarsWidget()

        cs_layout.addWidget(cs_head)
        cs_layout.addWidget(self.screen_time_val)
        cs_layout.addLayout(app_row)
        cs_layout.addStretch()
        cs_layout.addWidget(self.weekly_bars)
        grid.addWidget(self.card_screen, 0, 0)

        # -------------------------------------------------------------
        # CARD 2: SYSTEM (Top-Middle, Donut Progress Rings)
        # -------------------------------------------------------------
        self.card_system = self._create_card()
        sys_layout = QVBoxLayout(self.card_system)
        sys_layout.setContentsMargins(14, 12, 14, 12)
        sys_layout.setSpacing(4)

        sys_head = QLabel("⚙️  SYSTEM")
        sys_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")

        gauges_layout = QHBoxLayout()
        gauges_layout.setSpacing(8)
        gauges_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cpu_gauge = CircularGauge("CPU")
        self.ram_gauge = CircularGauge("RAM")
        self.disk_gauge = CircularGauge("DISK")
        gauges_layout.addWidget(self.cpu_gauge)
        gauges_layout.addWidget(self.ram_gauge)
        gauges_layout.addWidget(self.disk_gauge)

        sys_layout.addWidget(sys_head)
        sys_layout.addLayout(gauges_layout)
        grid.addWidget(self.card_system, 0, 1)

        # -------------------------------------------------------------
        # CARD 3: WEATHER (Top-Right)
        # -------------------------------------------------------------
        self.card_weather = self._create_card()
        w_layout = QVBoxLayout(self.card_weather)
        w_layout.setContentsMargins(14, 12, 14, 12)
        w_layout.setSpacing(4)

        w_head = QLabel("🌤️  WEATHER")
        w_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")

        w_row = QHBoxLayout()
        w_row.setSpacing(10)
        w_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.weather_icon = QLabel("🌙☁️")
        self.weather_icon.setStyleSheet("font-size: 26px; background: transparent;")

        w_col = QVBoxLayout()
        w_col.setSpacing(2)
        w_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.weather_title = QLabel("22°C · Partly cloudy")
        self.weather_title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 700;")

        self.weather_sub = QLabel("Local Weather · H: 26° L: 18°")
        self.weather_sub.setStyleSheet("color: #8a8a96; font-size: 11px;")

        w_col.addWidget(self.weather_title)
        w_col.addWidget(self.weather_sub)

        w_row.addWidget(self.weather_icon)
        w_row.addLayout(w_col)
        w_row.addStretch()

        w_layout.addWidget(w_head)
        w_layout.addSpacing(2)
        w_layout.addLayout(w_row)
        w_layout.addStretch()
        grid.addWidget(self.card_weather, 0, 2)

        # -------------------------------------------------------------
        # CARD 4: FOCUS (Bottom-Left)
        # -------------------------------------------------------------
        self.card_focus = self._create_card()
        f_layout = QVBoxLayout(self.card_focus)
        f_layout.setContentsMargins(14, 12, 14, 12)
        f_layout.setSpacing(4)

        f_head = QLabel("⏱️  FOCUS")
        f_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")

        f_row = QHBoxLayout()
        f_info_v = QVBoxLayout()
        f_info_v.setSpacing(2)

        self.focus_val = QLabel("25:00")
        self.focus_val.setStyleSheet("color: #ffffff; font-size: 30px; font-weight: 800;")

        self.focus_state_lbl = QLabel("Ready")
        self.focus_state_lbl.setStyleSheet("color: #7a7a85; font-size: 12px;")
        f_info_v.addWidget(self.focus_val)
        f_info_v.addWidget(self.focus_state_lbl)

        # Circular Play Button (Dark circle with white triangle)
        self.focus_play_btn = QPushButton("▶")
        self.focus_play_btn.setFixedSize(38, 38)
        self.focus_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.focus_play_btn.setStyleSheet("""
            QPushButton {
                background: #25252d;
                color: #ffffff;
                font-size: 13px;
                border-radius: 19px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                font-weight: 700;
            }
            QPushButton:hover {
                background: #33333e;
            }
        """)
        self.focus_play_btn.clicked.connect(self._toggle_focus)

        f_row.addLayout(f_info_v)
        f_row.addStretch()
        f_row.addWidget(self.focus_play_btn)

        f_layout.addWidget(f_head)
        f_layout.addStretch()
        f_layout.addLayout(f_row)
        grid.addWidget(self.card_focus, 1, 0)

        # -------------------------------------------------------------
        # CARD 5: CLIPBOARD (Bottom-Middle)
        # -------------------------------------------------------------
        self.card_clip = self._create_card()
        clip_layout = QVBoxLayout(self.card_clip)
        clip_layout.setContentsMargins(14, 12, 14, 10)
        clip_layout.setSpacing(6)

        clip_head = QLabel("📄  CLIPBOARD")
        clip_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")
        clip_layout.addWidget(clip_head)

        self.clip_list_layout = QVBoxLayout()
        self.clip_list_layout.setSpacing(6)
        clip_layout.addLayout(self.clip_list_layout)
        clip_layout.addStretch()
        grid.addWidget(self.card_clip, 1, 1)

        # Populate initial clipboard samples matching screenshot
        self._populate_mock_clipboard()

        # -------------------------------------------------------------
        # CARD 6: NOTES (Bottom-Right)
        # -------------------------------------------------------------
        self.card_notes = self._create_card()
        notes_layout = QVBoxLayout(self.card_notes)
        notes_layout.setContentsMargins(14, 12, 14, 10)
        notes_layout.setSpacing(6)

        notes_head = QLabel("🗒️  NOTES")
        notes_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")

        self.note_status = QLabel("No notes yet")
        self.note_status.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 600; margin-top: 2px;")

        note_row = QHBoxLayout()
        note_row.setSpacing(6)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Write a note...")
        self.note_input.setStyleSheet("""
            QLineEdit {
                background: #202026;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 8px;
                padding: 6px 10px;
                color: #ffffff;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(255, 255, 255, 0.22);
            }
        """)
        self.note_input.returnPressed.connect(self._save_note)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(26, 26)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #80808a;
                font-size: 18px;
                font-weight: 600;
                border: none;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        add_btn.clicked.connect(self._save_note)

        note_row.addWidget(self.note_input)
        note_row.addWidget(add_btn)

        notes_layout.addWidget(notes_head)
        notes_layout.addWidget(self.note_status)
        notes_layout.addStretch()
        notes_layout.addLayout(note_row)
        grid.addWidget(self.card_notes, 1, 2)

        self.content_stack.addWidget(self.cards_page)

        # Page 1: Appearance Settings
        self.settings_page = AppearanceSettingsWidget(self.settings_service, self)
        self.content_stack.addWidget(self.settings_page)

        main_layout.addWidget(self.content_stack)

        # -------------------------------------------------------------
        # 3. Bottom Floating Dock (Exact Vayli Screenshot Icons)
        # -------------------------------------------------------------
        dock_container = QHBoxLayout()
        dock_pill = QFrame()
        dock_pill.setStyleSheet("""
            QFrame {
                background: #151519;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 22px;
            }
        """)
        dock_layout = QHBoxLayout(dock_pill)
        dock_layout.setContentsMargins(8, 4, 8, 4)
        dock_layout.setSpacing(6)

        # 14 Dock Icons
        dock_spec = [
            ("⌂", "Home", self._show_home, True),
            ("⚙️", "System", None, False),
            ("📋", "Clipboard", None, False),
            ("📝", "Notes", None, False),
            ("⏱️", "Focus", None, False),
            ("📁", "Shelf", self.shelf_requested.emit, False),
            ("🗄️", "Drawer", None, False),
            ("⛅", "Weather", None, False),
            ("🕒", "Clock", None, False),
            ("📏", "Tools", None, False),
            ("🔗", "Links", None, False),
            ("🗂️", "Windows", None, False),
            ("📊", "Screen Time", None, False),
            ("|", "Separator", None, False),
            ("+", "Add", None, False)
        ]

        self.dock_buttons = {}
        for icon, name, handler, is_active in dock_spec:
            if icon == "|":
                s = QLabel("|")
                s.setStyleSheet("color: #383842; font-size: 13px; font-weight: 500;")
                dock_layout.addWidget(s)
                continue

            btn = QPushButton(icon)
            btn.setFixedSize(30, 30)
            btn.setToolTip(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

            if is_active:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #ffffff;
                        color: #0c0c0e;
                        border-radius: 10px;
                        font-size: 15px;
                        font-weight: 800;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #7a7a85;
                        border-radius: 10px;
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.08);
                        color: #ffffff;
                    }
                """)

            if handler:
                btn.clicked.connect(handler)
            self.dock_buttons[name] = btn
            dock_layout.addWidget(btn)

        dock_container.addStretch()
        dock_container.addWidget(dock_pill)
        dock_container.addStretch()
        main_layout.addLayout(dock_container)

    def _create_card(self):
        card = QFrame()
        card.setFixedHeight(136)
        card.setStyleSheet("""
            QFrame {
                background: #111114;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 16px;
            }
        """)
        return card

    def _show_home(self):
        self.content_stack.setCurrentWidget(self.cards_page)
        if "Home" in self.dock_buttons:
            self.dock_buttons["Home"].setStyleSheet("background: #ffffff; color: #0c0c0e; border-radius: 10px; font-size: 15px; font-weight: 800;")

    def _toggle_focus(self):
        self.focus_running = not self.focus_running
        if self.focus_running:
            self.focus_play_btn.setText("⏸")
            self.focus_state_lbl.setText("Focusing...")
            self.focus_timer.start(1000)
        else:
            self.focus_play_btn.setText("▶")
            self.focus_state_lbl.setText("Ready")
            self.focus_timer.stop()

    def _tick_focus(self):
        if self.focus_seconds > 0:
            self.focus_seconds -= 1
            m = self.focus_seconds // 60
            s = self.focus_seconds % 60
            self.focus_val.setText(f"{m:02d}:{s:02d}")
        else:
            self.focus_timer.stop()
            self.focus_running = False
            self.focus_play_btn.setText("▶")
            self.focus_state_lbl.setText("Session Done! 🎉")

    def _save_note(self):
        text = self.note_input.text().strip()
        if text:
            self.note_status.setText(text)
            self.note_input.clear()

    def _on_stats_updated(self, stats: dict):
        self.cpu_gauge.set_value(stats["cpu"])
        self.ram_gauge.set_value(stats["ram"])
        self.disk_gauge.set_value(stats["disk"])

        self.screen_time_val.setText(stats["screen_time_total"])
        self.screen_top_app.setText(stats["top_app_str"])

        bat = stats["battery"]
        self.bat_lbl.setText(f"{bat}% 🔋")

    def _on_weather_updated(self, data: dict):
        icon = data.get("icon", "🌙☁️")
        temp = data.get("temp_str", "21°C")
        cond = data.get("condition", "Partly cloudy")
        humid = data.get("humidity_desc", "Humid")
        city = data.get("city", "Local Weather")
        h = data.get("high", 26)
        l = data.get("low", 18)
        hum_pct = data.get("humidity", 78)

        self.weather_icon.setText(icon)
        self.weather_title.setText(f"{temp} · {cond} ({humid})")
        self.weather_sub.setText(f"{city} · Humidity {hum_pct}% · H: {h}° L: {l}°")

    def _populate_mock_clipboard(self):
        # Initial clipboard items matching screenshot
        mock_items = [
            {"title": "Image · 1041 × 162", "time": "29m"},
            {"title": "Image · 583 × 342", "time": "29m"}
        ]
        self._render_clip_items(mock_items)

    def _render_clip_items(self, items: list):
        while self.clip_list_layout.count():
            item = self.clip_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for it in items[:2]:
            row = QFrame()
            row.setFixedHeight(34)
            row.setStyleSheet("""
                QFrame {
                    background: transparent;
                    border: none;
                }
            """)
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(0, 2, 0, 2)
            r_layout.setSpacing(8)

            # Mini Thumbnail Squircle
            thumb = QLabel("🖼️")
            thumb.setFixedSize(26, 26)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setStyleSheet("""
                background: #23232a;
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                font-size: 11px;
            """)

            title_lbl = QLabel(it["title"])
            title_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

            time_lbl = QLabel(it.get("time", "now"))
            time_lbl.setStyleSheet("color: #7a7a85; font-size: 11px; background: transparent;")

            cp_btn = QPushButton("⧉")
            cp_btn.setFixedSize(22, 22)
            cp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cp_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #7a7a85;
                    border: none;
                    font-size: 12px;
                }
                QPushButton:hover {
                    color: #ffffff;
                }
            """)

            r_layout.addWidget(thumb)
            r_layout.addWidget(title_lbl, 1)
            r_layout.addWidget(time_lbl)
            r_layout.addWidget(cp_btn)
            self.clip_list_layout.addWidget(row)

    def _on_clipboard_updated(self, history: list):
        if not history:
            return
        formatted = []
        for h in history[:2]:
            if h["type"] == "image":
                title = f"Image · {h.get('detail', 'Image')}"
            else:
                title = h.get("detail", "Text")
                if len(title) > 20:
                    title = title[:18] + "..."
            formatted.append({"title": title, "time": "now"})
        self._render_clip_items(formatted)
