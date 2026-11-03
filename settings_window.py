import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QStackedWidget, QScrollArea
)
from appearance_settings_widget import AppearanceSettingsWidget

class SettingsWindow(QWidget):
    def __init__(self, settings_service, parent=None):
        super().__init__(parent)
        self.settings_service = settings_service
        self.setWindowTitle("MicaBay Settings")
        self.resize(840, 590)
        self.setMinimumSize(780, 520)

        # Apply dark mica theme
        self.setStyleSheet("""
            QWidget {
                background: #0c0c0e;
                color: #ffffff;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---------------------------------------------------------
        # LEFT SIDEBAR (Screenshot 2: Navigation)
        # ---------------------------------------------------------
        sidebar = QFrame()
        sidebar.setFixedWidth(210)
        sidebar.setStyleSheet("""
            QFrame {
                background: #111114;
                border-right: 1px solid rgba(255, 255, 255, 0.07);
            }
        """)
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(14, 16, 14, 16)
        s_layout.setSpacing(6)

        # Logo & App Title
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        logo_lbl = QLabel()
        logo_path = os.path.join(os.path.dirname(__file__), "micabay_logo.jpg")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(26, 26, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
        else:
            logo_lbl.setText("🫧")
            logo_lbl.setStyleSheet("font-size: 18px;")

        name_lbl = QLabel("MicaBay")
        name_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #ffffff;")
        brand_row.addWidget(logo_lbl)
        brand_row.addWidget(name_lbl)
        brand_row.addStretch()
        s_layout.addLayout(brand_row)

        sub_lbl = QLabel("Free & Open Source")
        sub_lbl.setStyleSheet("color: #00d2ff; font-size: 10px; font-weight: 600; margin-bottom: 6px;")
        s_layout.addWidget(sub_lbl)

        # Search Bar (Screenshot 2)
        search_box = QLineEdit()
        search_box.setPlaceholderText("Search              Ctrl K")
        search_box.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 6px 10px;
                color: #8e8e93;
                font-size: 11px;
            }
        """)
        s_layout.addWidget(search_box)
        s_layout.addSpacing(6)

        # Nav Buttons
        self.nav_buttons = {}
        nav_items = [
            ("⚙️", "General", 0),
            ("🔲", "Notch", 1),
            ("🎨", "Appearance", 2),
            ("📱", "Modules", 3),
            ("🔔", "Live Activities", 4),
            ("🛡️", "Privacy", 5),
            ("ℹ️", "About", 6)
        ]

        for icon, label, idx in nav_items:
            btn = QPushButton(f"  {icon}   {label}")
            btn.setFixedHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #9e9ea6;
                    text-align: left;
                    font-size: 12px;
                    font-weight: 500;
                    border-radius: 8px;
                    padding-left: 8px;
                    border: none;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.06);
                    color: #ffffff;
                }
            """)
            btn.clicked.connect(lambda _, i=idx, l=label: self._switch_page(i, l))
            self.nav_buttons[label] = btn
            s_layout.addWidget(btn)

        s_layout.addStretch()
        main_layout.addWidget(sidebar)

        # ---------------------------------------------------------
        # RIGHT CONTENT AREA (Screenshots 2, 3, 4)
        # ---------------------------------------------------------
        self.stack = QStackedWidget()

        # Page 0: General
        self.stack.addWidget(self._create_general_page())

        # Page 1: Notch
        self.stack.addWidget(self._create_notch_page())

        # Page 2: Appearance (Surface & Edge light)
        self.appearance_page = AppearanceSettingsWidget(self.settings_service, self)
        self.stack.addWidget(self.appearance_page)

        # Page 3: Modules (Screenshots 2, 3, 4!)
        self.stack.addWidget(self._create_modules_page())

        # Page 4: Live Activities
        self.stack.addWidget(self._create_live_activities_page())

        # Page 5: Privacy
        self.stack.addWidget(self._create_privacy_page())

        # Page 6: About
        self.stack.addWidget(self._create_about_page())

        main_layout.addWidget(self.stack, 1)

        # Default select Appearance or Modules
        self._switch_page(2, "Appearance")

    def _switch_page(self, index: int, label: str):
        self.stack.setCurrentIndex(index)
        for name, btn in self.nav_buttons.items():
            if name == label:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.12);
                        color: #ffffff;
                        text-align: left;
                        font-size: 12px;
                        font-weight: 700;
                        border-radius: 8px;
                        padding-left: 8px;
                        border: none;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #9e9ea6;
                        text-align: left;
                        font-size: 12px;
                        font-weight: 500;
                        border-radius: 8px;
                        padding-left: 8px;
                        border: none;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.06);
                        color: #ffffff;
                    }
                """)

    # -------------------------------------------------------------
    # MODULES PAGE (Exact UI from Screenshots 2, 3, 4!)
    # -------------------------------------------------------------
    def _create_modules_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(16)

        # Title
        t_lbl = QLabel("Modules")
        t_lbl.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: 800;")
        s_lbl = QLabel("Choose what lives in your notch. Drag to reorder.")
        s_lbl.setStyleSheet("color: #8e8e93; font-size: 12px; margin-bottom: 6px;")
        layout.addWidget(t_lbl)
        layout.addWidget(s_lbl)

        # ESSENTIALS
        layout.addWidget(self._create_section_label("ESSENTIALS"))
        essentials = [
            ("Home", "Now playing, your next event and quick stats", "blue", True),
            ("System", "CPU, memory, disk and battery", "cyan", True),
            ("Timers", "Pomodoro, countdown, stopwatch and water", "orange", True),
            ("Weather", "Now, hourly and five-day forecast", "sky", True),
            ("Clock", "World clocks, digital or analog", "yellow", True),
            ("Calendar", "Agenda, festivals and reminders", "pink", False),
        ]
        for name, desc, color_key, enabled in essentials:
            layout.addLayout(self._create_module_row(name, desc, color_key, enabled))

        layout.addSpacing(10)

        # PRODUCTIVITY (Screenshot 3)
        layout.addWidget(self._create_section_label("PRODUCTIVITY"))
        productivity = [
            ("Clipboard", "Everything you copied, searchable", "purple", True),
            ("Notes", "Quick notes that stay with the notch", "yellow", True),
            ("File Shelf", "Park files and drag them anywhere", "teal", True),
            ("Mica Drop", "Share with your phone on your private network", "violet", True),
            ("Units", "Length, weight, temperature and more", "purple", True),
            ("Links", "Bookmarks and quick web searches", "coral", True),
            ("Message", "Flash your own text on the notch", "pink", True),
        ]
        for name, desc, color_key, enabled in productivity:
            layout.addLayout(self._create_module_row(name, desc, color_key, enabled))

        layout.addSpacing(10)

        # INSIGHTS (Screenshot 4)
        layout.addWidget(self._create_section_label("INSIGHTS"))
        insights = [
            ("Screen Time", "Where your day went, app by app", "magenta", True),
            ("Analytics", "Website visitors, pages and sources", "emerald", False),
            ("AI Coding", "Claude Code, Gemini and Codex usage", "slate", False),
            ("Revenue", "Sales and license revenue at a glance", "lime", False)
        ]
        for name, desc, color_key, enabled in insights:
            layout.addLayout(self._create_module_row(name, desc, color_key, enabled))

        scroll.setWidget(content)
        return scroll

    def _create_section_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #636366; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; margin-top: 4px;")
        return lbl

    def _create_module_row(self, name, desc, color_key, enabled):
        row = QHBoxLayout()
        row.setSpacing(12)

        # Icon with colored background
        icon_box = QLabel()
        icon_box.setFixedSize(32, 32)
        color_map = {
            "blue": "#0a84ff",
            "cyan": "#00d2ff",
            "orange": "#ff9f0a",
            "sky": "#64d2ff",
            "yellow": "#ffd60a",
            "pink": "#ff375f",
            "purple": "#bf5af2",
            "teal": "#30d158",
            "violet": "#af52de",
            "coral": "#ff6961",
            "magenta": "#da70d6",
            "emerald": "#34c759",
            "slate": "#8e8e93",
            "lime": "#a4de02"
        }
        bg = color_map.get(color_key, "#3a3a3c")
        icon_box.setStyleSheet(f"background: {bg}; border-radius: 8px;")
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Text
        v_box = QVBoxLayout()
        v_box.setSpacing(2)
        t_lbl = QLabel(name)
        t_lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: 600;")
        d_lbl = QLabel(desc)
        d_lbl.setStyleSheet("color: #8e8e93; font-size: 11px;")
        v_box.addWidget(t_lbl)
        v_box.addWidget(d_lbl)

        # Toggle Switch
        toggle_btn = QPushButton("ON" if enabled else "OFF")
        toggle_btn.setFixedSize(50, 26)
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_toggle(toggle_btn, enabled)

        def on_click():
            new_val = (toggle_btn.text() == "OFF")
            toggle_btn.setText("ON" if new_val else "OFF")
            self._style_toggle(toggle_btn, new_val)
            self.settings_service.set(f"module_{name.lower().replace(' ', '_')}", new_val)

        toggle_btn.clicked.connect(on_click)

        row.addWidget(icon_box)
        row.addLayout(v_box)
        row.addStretch()
        row.addWidget(toggle_btn)
        return row

    def _style_toggle(self, btn, is_on):
        if is_on:
            btn.setStyleSheet("""
                QPushButton {
                    background: #ffffff;
                    color: #000000;
                    border-radius: 13px;
                    font-size: 10px;
                    font-weight: 800;
                    border: none;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: #242428;
                    color: #71717a;
                    border-radius: 13px;
                    font-size: 10px;
                    font-weight: 700;
                    border: none;
                }
            """)

    # -------------------------------------------------------------
    # NOTCH PAGE (Screenshot 2: Visibility & Style)
    # -------------------------------------------------------------
    def _create_notch_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(16)

        t_lbl = QLabel("Notch Style & Placement")
        t_lbl.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 800;")
        layout.addWidget(t_lbl)

        layout.addWidget(self._create_section_label("STYLE"))
        styles = [
            ("Notch", "Grows seamlessly out of the top screen edge", "notch"),
            ("Island", "A floating pill just below the screen edge", "island"),
            ("Line", "A minimalist slim line along the top edge", "line")
        ]
        s_layout = QHBoxLayout()
        for title, desc, key in styles:
            btn = QPushButton(f"{title}\n{desc}")
            btn.setFixedHeight(75)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            is_active = (self.settings_service.get("notch_style", "notch") == key)
            border = "2px solid #ffffff" if is_active else "1px solid rgba(255, 255, 255, 0.1)"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #141418;
                    color: #ffffff;
                    border: {border};
                    border-radius: 10px;
                    padding: 8px;
                    text-align: left;
                    font-size: 11px;
                }}
            """)
            btn.clicked.connect(lambda _, k=key: self.settings_service.set("notch_style", k))
            s_layout.addWidget(btn)
        layout.addLayout(s_layout)

        layout.addSpacing(10)
        layout.addWidget(self._create_section_label("BEHAVIOR"))
        
        row_open = QHBoxLayout()
        ro_lbl = QLabel("Opens on")
        ro_lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: 600;")
        ro_sub = QLabel("Hover to peek, click on purpose")
        ro_sub.setStyleSheet("color: #8e8e93; font-size: 11px;")
        v_ro = QVBoxLayout()
        v_ro.addWidget(ro_lbl)
        v_ro.addWidget(ro_sub)

        btn_hover = QPushButton("Hover")
        btn_click = QPushButton("Click")
        for b in (btn_hover, btn_click):
            b.setFixedSize(70, 30)
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        curr_op = self.settings_service.get("opens_on", "click")
        btn_click.setStyleSheet("background: #ffffff; color: #000; border-radius: 6px; font-weight: 700;" if curr_op == "click" else "background: #242428; color: #8e8e93; border-radius: 6px;")
        btn_hover.setStyleSheet("background: #ffffff; color: #000; border-radius: 6px; font-weight: 700;" if curr_op == "hover" else "background: #242428; color: #8e8e93; border-radius: 6px;")

        btn_hover.clicked.connect(lambda: self.settings_service.set("opens_on", "hover"))
        btn_click.clicked.connect(lambda: self.settings_service.set("opens_on", "click"))

        row_open.addLayout(v_ro)
        row_open.addStretch()
        row_open.addWidget(btn_hover)
        row_open.addWidget(btn_click)
        layout.addLayout(row_open)

        layout.addStretch()
        return content

    # -------------------------------------------------------------
    # GENERAL PAGE
    # -------------------------------------------------------------
    def _create_general_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(16)

        t_lbl = QLabel("General Settings")
        t_lbl.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 800;")
        layout.addWidget(t_lbl)

        layout.addLayout(self._create_toggle_item("Launch on Windows startup", "Start MicaBay automatically when you log in", True))
        layout.addLayout(self._create_toggle_item("Hide in fullscreen", "Automatically tuck away when gaming or watching movies", True))
        layout.addLayout(self._create_toggle_item("Show events over apps", "Briefly peek for volume, track changes and copy events", True))

        layout.addStretch()
        return content

    def _create_toggle_item(self, title, sub, default):
        row = QHBoxLayout()
        v = QVBoxLayout()
        t = QLabel(title)
        t.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: 600;")
        s = QLabel(sub)
        s.setStyleSheet("color: #8e8e93; font-size: 11px;")
        v.addWidget(t)
        v.addWidget(s)

        btn = QPushButton("ON" if default else "OFF")
        btn.setFixedSize(50, 26)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_toggle(btn, default)
        btn.clicked.connect(lambda: (btn.setText("OFF" if btn.text() == "ON" else "ON"), self._style_toggle(btn, btn.text() == "ON")))

        row.addLayout(v)
        row.addStretch()
        row.addWidget(btn)
        return row

    def _create_toggle_setting(self, title, sub, key, default=True):
        row = QHBoxLayout()
        v = QVBoxLayout()
        v.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: 600;")
        s = QLabel(sub)
        s.setStyleSheet("color: #8e8e93; font-size: 11px;")
        v.addWidget(t)
        v.addWidget(s)

        is_on = self.settings_service.get(key, default)
        btn = QPushButton("ON" if is_on else "OFF")
        btn.setFixedSize(50, 26)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_toggle(btn, is_on)

        def on_click():
            new_val = (btn.text() == "OFF")
            btn.setText("ON" if new_val else "OFF")
            self._style_toggle(btn, new_val)
            self.settings_service.set(key, new_val)

        btn.clicked.connect(on_click)

        row.addLayout(v)
        row.addStretch()
        row.addWidget(btn)
        return row

    def _create_live_activities_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(14)

        t = QLabel("Live Activities & Animations")
        t.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 800;")
        s = QLabel("Smart contextual alerts, animation speeds and background monitoring.")
        s.setStyleSheet("color: #8e8e93; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(t)
        layout.addWidget(s)

        # -------------------------------------------------------------
        # 1. ANIMATION SPEED
        # -------------------------------------------------------------
        layout.addWidget(self._create_section_label("ANIMATION SPEED"))
        speeds = [
            ("Snappy", "Crisp 180ms fast response", "snappy"),
            ("Smooth", "Balanced 240ms natural spring", "smooth"),
            ("Relaxed", "Gentle 320ms fluid transitions", "relaxed")
        ]
        sp_layout = QHBoxLayout()
        curr_speed = self.settings_service.get("animation_speed", "smooth")
        self.speed_buttons = {}

        def select_speed(key):
            self.settings_service.set("animation_speed", key)
            for k, b in self.speed_buttons.items():
                active = (k == key)
                border = "2px solid #ffffff" if active else "1px solid rgba(255, 255, 255, 0.1)"
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: #141418;
                        color: #ffffff;
                        border: {border};
                        border-radius: 10px;
                        padding: 8px;
                        text-align: left;
                        font-size: 11px;
                    }}
                """)

        for title, desc, key in speeds:
            btn = QPushButton(f"{title}\n{desc}")
            btn.setFixedHeight(70)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            active = (key == curr_speed)
            border = "2px solid #ffffff" if active else "1px solid rgba(255, 255, 255, 0.1)"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #141418;
                    color: #ffffff;
                    border: {border};
                    border-radius: 10px;
                    padding: 8px;
                    text-align: left;
                    font-size: 11px;
                }}
            """)
            btn.clicked.connect(lambda _, k=key: select_speed(k))
            self.speed_buttons[key] = btn
            sp_layout.addWidget(btn)
        layout.addLayout(sp_layout)

        layout.addSpacing(6)

        # -------------------------------------------------------------
        # 2. CONTEXTUAL ACTIVITIES
        # -------------------------------------------------------------
        layout.addWidget(self._create_section_label("SMART CONTEXTUAL ALERTS"))
        layout.addLayout(self._create_toggle_setting("Download Progress", "Show live download transfer speed and progress in notch", "enable_download_alerts", True))
        layout.addLayout(self._create_toggle_setting("Microphone In-Use Indicator", "Briefly indicate when an application is accessing the microphone", "enable_mic_indicator", True))
        layout.addLayout(self._create_toggle_setting("Screenshot Confirmation", "Display an island confirmation when a screenshot is captured", "enable_screenshot_toast", True))
        layout.addLayout(self._create_toggle_setting("Battery & Power Alerts", "Show alerts when charger is connected or battery is low", "enable_battery_alerts", True))
        layout.addLayout(self._create_toggle_setting("Volume HUD", "Display sleek volume level slider on volume key changes", "enable_volume_hud", True))

        layout.addSpacing(6)

        # -------------------------------------------------------------
        # 3. SYSTEM HARDWARE SENSORS
        # -------------------------------------------------------------
        layout.addWidget(self._create_section_label("HARDWARE SENSORS"))
        layout.addLayout(self._create_toggle_setting("GPU Utilization Monitoring", "Poll native 3D engine utilization percentage", "enable_gpu_monitor", True))
        layout.addLayout(self._create_toggle_setting("Network Throughput Monitoring", "Track live upload and download bandwidth rates", "enable_net_monitor", True))

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _create_privacy_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 24)
        t = QLabel("Privacy & Security")
        t.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 800;")
        desc = QLabel("MicaBay operates 100% offline. Zero telemetry, zero cloud logging, zero tracking.\nYour clipboard history and notes are saved strictly on your local PC.")
        desc.setStyleSheet("color: #a0a0ab; font-size: 12px; line-height: 1.6;")
        layout.addWidget(t)
        layout.addWidget(desc)
        layout.addStretch()
        return content

    def _create_about_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(12)

        t = QLabel("About MicaBay")
        t.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: 800;")
        v = QLabel("Version 1.0.0 (Windows 64-bit)")
        v.setStyleSheet("color: #00d2ff; font-size: 12px; font-weight: 600;")
        
        info = QLabel("MicaBay is a lightweight, free, and open-source Dynamic Notch utility\nengineered for Windows 10 and Windows 11 with PySide6 and WinRT SMTC.\n\nEnjoy pure productivity without paywalls.")
        info.setStyleSheet("color: #b0b0ba; font-size: 12px; line-height: 1.7;")

        layout.addWidget(t)
        layout.addWidget(v)
        layout.addWidget(info)
        layout.addStretch()
        return content
