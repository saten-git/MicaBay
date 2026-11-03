import os
import time
import subprocess
from datetime import datetime
from PySide6.QtCore import Qt, Signal, QTimer, QRectF
from PySide6.QtGui import QFont, QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QStackedWidget, QSlider, QSizePolicy
)
from circular_gauge import CircularGauge
from weekly_bars import WeeklyBarsWidget
from appearance_settings_widget import AppearanceSettingsWidget
from audio_visualizer import EqualizerBarsWidget
from battery_glyph import BatteryGlyphWidget

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

        # Services from parent notch window
        self.media_service = getattr(parent, "media_service", None)
        self.volume_service = getattr(parent, "volume_service", None)

        # Pomodoro Focus state
        self.focus_seconds = 25 * 60
        self.focus_running = False
        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self._tick_focus)

        # Stopwatch state
        self.stopwatch_running = False
        self.stopwatch_elapsed_ms = 0
        self.stopwatch_last_time = 0.0
        self.stopwatch_timer = QTimer(self)
        self.stopwatch_timer.timeout.connect(self._tick_stopwatch)

        # Microphone mute state
        self.is_mic_muted = False

        self._init_ui()

        # Connect service updates
        self.system_service.stats_updated.connect(self._on_stats_updated)
        self.clipboard_service.history_updated.connect(self._on_clipboard_updated)
        if self.weather_service:
            self.weather_service.weather_updated.connect(self._on_weather_updated)
            self._on_weather_updated(self.weather_service.get_data())

        if self.media_service:
            self.media_service.media_updated.connect(self._on_media_updated)
        if self.volume_service:
            self.volume_service.volume_changed.connect(self._on_volume_changed)
            self.volume_service.mic_mute_changed.connect(self._on_mic_mute_changed)
            self.is_mic_muted = self.volume_service.is_microphone_muted()
            self._update_mic_btn_ui(self.is_mic_muted)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 10, 16, 12)
        main_layout.setSpacing(8)

        # -------------------------------------------------------------
        # 1. Header Bar (MicaBay Dashboard Header)
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
        self.edit_btn.clicked.connect(self._show_settings)

        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setStyleSheet(btn_style)
        self.settings_btn.clicked.connect(self._show_settings)

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
        # CARD 1: MEDIA CONTROLS & SCREEN TIME (Top-Left)
        # -------------------------------------------------------------
        self.card_screen = self._create_card()
        c1_layout = QVBoxLayout(self.card_screen)
        c1_layout.setContentsMargins(12, 10, 12, 10)
        c1_layout.setSpacing(4)

        c1_header = QHBoxLayout()
        self.c1_title_lbl = QLabel("🎵  NOW PLAYING")
        self.c1_title_lbl.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")

        self.c1_toggle_btn = QPushButton("Stats ⮂")
        self.c1_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c1_toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #00d2ff;
                font-size: 9px;
                font-weight: 600;
                border: none;
                padding: 0 4px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        self.c1_toggle_btn.clicked.connect(self._toggle_c1_mode)

        c1_header.addWidget(self.c1_title_lbl)
        c1_header.addStretch()
        c1_header.addWidget(self.c1_toggle_btn)
        c1_layout.addLayout(c1_header)

        self.c1_stack = QStackedWidget(self.card_screen)

        # Page 0: Media Player
        page_media = QWidget()
        pm_layout = QVBoxLayout(page_media)
        pm_layout.setContentsMargins(0, 0, 0, 0)
        pm_layout.setSpacing(6)

        m_info_row = QHBoxLayout()
        m_info_row.setSpacing(8)

        self.media_thumb_lbl = QLabel("🎵")
        self.media_thumb_lbl.setFixedSize(32, 32)
        self.media_thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.media_thumb_lbl.setStyleSheet("background: #222228; border-radius: 6px; font-size: 14px;")

        m_text_col = QVBoxLayout()
        m_text_col.setSpacing(1)
        self.media_title_lbl = QLabel("No Media Playing")
        self.media_title_lbl.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 700; background: transparent;")
        self.media_artist_lbl = QLabel("MicaBay Media")
        self.media_artist_lbl.setStyleSheet("color: #8a8a96; font-size: 10px; background: transparent;")
        m_text_col.addWidget(self.media_title_lbl)
        m_text_col.addWidget(self.media_artist_lbl)

        self.media_eq_bars = EqualizerBarsWidget()

        m_info_row.addWidget(self.media_thumb_lbl)
        m_info_row.addLayout(m_text_col, 1)
        m_info_row.addWidget(self.media_eq_bars)
        pm_layout.addLayout(m_info_row)

        # Controls & Volume Row
        m_ctrl_row = QHBoxLayout()
        m_ctrl_row.setSpacing(6)

        btn_ctrl_style = """
            QPushButton {
                background: #1f1f26;
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 11px;
                font-size: 9px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #2c2c36;
            }
        """

        self.media_prev_btn = QPushButton("⏮")
        self.media_prev_btn.setFixedSize(24, 22)
        self.media_prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.media_prev_btn.setStyleSheet(btn_ctrl_style)
        self.media_prev_btn.clicked.connect(lambda: self.media_service.prev_track() if self.media_service else None)

        self.media_play_btn = QPushButton("▶")
        self.media_play_btn.setFixedSize(26, 22)
        self.media_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.media_play_btn.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                color: #0c0c0e;
                border: none;
                border-radius: 11px;
                font-size: 10px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #d8d8e0;
            }
        """)
        self.media_play_btn.clicked.connect(lambda: self.media_service.play_pause() if self.media_service else None)

        self.media_next_btn = QPushButton("⏭")
        self.media_next_btn.setFixedSize(24, 22)
        self.media_next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.media_next_btn.setStyleSheet(btn_ctrl_style)
        self.media_next_btn.clicked.connect(lambda: self.media_service.next_track() if self.media_service else None)

        self.vol_mute_btn = QPushButton("🔊")
        self.vol_mute_btn.setFixedSize(22, 22)
        self.vol_mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_mute_btn.setStyleSheet("background: transparent; border: none; font-size: 11px;")
        self.vol_mute_btn.clicked.connect(self._toggle_speaker_mute)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.setFixedHeight(16)
        self.vol_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #24242c;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #00d2ff;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
        """)
        self.vol_slider.valueChanged.connect(self._on_vol_slider_moved)

        m_ctrl_row.addWidget(self.media_prev_btn)
        m_ctrl_row.addWidget(self.media_play_btn)
        m_ctrl_row.addWidget(self.media_next_btn)
        m_ctrl_row.addWidget(self.vol_mute_btn)
        m_ctrl_row.addWidget(self.vol_slider)
        pm_layout.addLayout(m_ctrl_row)

        self.c1_stack.addWidget(page_media)

        # Page 1: Screen Time
        page_screen = QWidget()
        ps_layout = QVBoxLayout(page_screen)
        ps_layout.setContentsMargins(0, 0, 0, 0)
        ps_layout.setSpacing(2)

        self.screen_time_val = QLabel("1h")
        self.screen_time_val.setStyleSheet("color: #ffffff; font-size: 26px; font-weight: 800;")

        app_row = QHBoxLayout()
        app_row.setSpacing(6)
        app_dot = QLabel("🔹")
        app_dot.setStyleSheet("font-size: 9px; background: transparent;")
        self.screen_top_app = QLabel("Antigravity IDE · 26m")
        self.screen_top_app.setStyleSheet("color: #9e9ea8; font-size: 10px; font-weight: 500;")
        app_row.addWidget(app_dot)
        app_row.addWidget(self.screen_top_app)
        app_row.addStretch()

        self.weekly_bars = WeeklyBarsWidget()

        ps_layout.addWidget(self.screen_time_val)
        ps_layout.addLayout(app_row)
        ps_layout.addStretch()
        ps_layout.addWidget(self.weekly_bars)

        self.c1_stack.addWidget(page_screen)
        c1_layout.addWidget(self.c1_stack)
        grid.addWidget(self.card_screen, 0, 0)

        # -------------------------------------------------------------
        # CARD 2: SYSTEM PERFORMANCE (Top-Middle, 4 Circular Gauges)
        # -------------------------------------------------------------
        self.card_system = self._create_card()
        sys_layout = QVBoxLayout(self.card_system)
        sys_layout.setContentsMargins(10, 10, 10, 10)
        sys_layout.setSpacing(3)

        sys_head = QLabel("⚙️  SYSTEM PERFORMANCE")
        sys_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")

        gauges_layout = QHBoxLayout()
        gauges_layout.setSpacing(4)
        gauges_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cpu_gauge = CircularGauge("CPU", gauge_size=38)
        self.ram_gauge = CircularGauge("RAM", gauge_size=38)
        self.gpu_gauge = CircularGauge("GPU", gauge_size=38)
        self.disk_gauge = CircularGauge("DISK", gauge_size=38)
        gauges_layout.addWidget(self.cpu_gauge)
        gauges_layout.addWidget(self.ram_gauge)
        gauges_layout.addWidget(self.gpu_gauge)
        gauges_layout.addWidget(self.disk_gauge)

        sys_layout.addWidget(sys_head)
        sys_layout.addLayout(gauges_layout)
        grid.addWidget(self.card_system, 0, 1)

        # -------------------------------------------------------------
        # CARD 3: BATTERY & NETWORK (Top-Right)
        # -------------------------------------------------------------
        self.card_weather = self._create_card()
        w_layout = QVBoxLayout(self.card_weather)
        w_layout.setContentsMargins(12, 10, 12, 10)
        w_layout.setSpacing(5)

        w_head = QLabel("🔋  POWER & NETWORK")
        w_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")
        w_layout.addWidget(w_head)

        # Battery Row
        bat_row = QHBoxLayout()
        bat_row.setSpacing(8)
        self.bat_glyph = BatteryGlyphWidget()
        self.bat_pct_lbl = QLabel("95% ⚡")
        self.bat_pct_lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: 700;")
        self.bat_state_lbl = QLabel("Plugged In · Fast Charging")
        self.bat_state_lbl.setStyleSheet("color: #8a8a96; font-size: 10px;")
        bat_row.addWidget(self.bat_glyph)
        bat_row.addWidget(self.bat_pct_lbl)
        bat_row.addWidget(self.bat_state_lbl)
        bat_row.addStretch()
        w_layout.addLayout(bat_row)

        # Network Speeds Row
        net_row = QHBoxLayout()
        net_row.setSpacing(8)
        self.net_down_lbl = QLabel("↓ 0 KB/s")
        self.net_down_lbl.setStyleSheet("color: #00d2ff; font-size: 12px; font-weight: 700;")
        self.net_up_lbl = QLabel("↑ 0 KB/s")
        self.net_up_lbl.setStyleSheet("color: #a0a0ab; font-size: 11px; font-weight: 600;")
        self.net_sub_lbl = QLabel("Bandwidth I/O")
        self.net_sub_lbl.setStyleSheet("color: #6a6a75; font-size: 10px;")
        net_row.addWidget(self.net_down_lbl)
        net_row.addWidget(self.net_up_lbl)
        net_row.addWidget(self.net_sub_lbl)
        net_row.addStretch()
        w_layout.addLayout(net_row)

        # Weather / Environment Row
        env_row = QHBoxLayout()
        env_row.setSpacing(6)
        self.weather_icon = QLabel("🌙☁️")
        self.weather_icon.setStyleSheet("font-size: 13px; background: transparent;")
        self.weather_title = QLabel("22°C · Partly cloudy")
        self.weather_title.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600;")
        env_row.addWidget(self.weather_icon)
        env_row.addWidget(self.weather_title)
        env_row.addStretch()
        w_layout.addLayout(env_row)
        grid.addWidget(self.card_weather, 0, 2)

        # -------------------------------------------------------------
        # CARD 4: PRODUCTIVITY TOOLS (Bottom-Left: Pomodoro & Stopwatch)
        # -------------------------------------------------------------
        self.card_focus = self._create_card()
        f_layout = QVBoxLayout(self.card_focus)
        f_layout.setContentsMargins(14, 10, 14, 10)
        f_layout.setSpacing(4)

        f_header = QHBoxLayout()
        self.prod_title_lbl = QLabel("⏱️  POMODORO")
        self.prod_title_lbl.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")

        self.prod_mode_btn = QPushButton("Stopwatch ⮂")
        self.prod_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prod_mode_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ff9f0a;
                font-size: 9px;
                font-weight: 600;
                border: none;
                padding: 0 4px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        self.prod_mode_btn.clicked.connect(self._toggle_prod_mode)

        f_header.addWidget(self.prod_title_lbl)
        f_header.addStretch()
        f_header.addWidget(self.prod_mode_btn)
        f_layout.addLayout(f_header)

        self.prod_stack = QStackedWidget(self.card_focus)

        # Page 0: Pomodoro
        page_pomo = QWidget()
        pomo_layout = QHBoxLayout(page_pomo)
        pomo_layout.setContentsMargins(0, 0, 0, 0)
        pomo_layout.setSpacing(8)

        pomo_info_v = QVBoxLayout()
        pomo_info_v.setSpacing(2)
        self.focus_val = QLabel("25:00")
        self.focus_val.setStyleSheet("color: #ffffff; font-size: 28px; font-weight: 800;")
        self.focus_state_lbl = QLabel("Ready")
        self.focus_state_lbl.setStyleSheet("color: #7a7a85; font-size: 11px;")
        pomo_info_v.addWidget(self.focus_val)
        pomo_info_v.addWidget(self.focus_state_lbl)

        pomo_ctrl_row = QHBoxLayout()
        pomo_ctrl_row.setSpacing(6)
        self.focus_reset_btn = QPushButton("↺")
        self.focus_reset_btn.setFixedSize(28, 28)
        self.focus_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.focus_reset_btn.setStyleSheet("""
            QPushButton {
                background: #1f1f26;
                color: #888892;
                font-size: 12px;
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QPushButton:hover {
                color: #ffffff;
                background: #2a2a34;
            }
        """)
        self.focus_reset_btn.clicked.connect(self._reset_focus)

        self.focus_play_btn = QPushButton("▶")
        self.focus_play_btn.setFixedSize(36, 36)
        self.focus_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.focus_play_btn.setStyleSheet("""
            QPushButton {
                background: #25252d;
                color: #ffffff;
                font-size: 13px;
                border-radius: 18px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                font-weight: 700;
            }
            QPushButton:hover {
                background: #33333e;
            }
        """)
        self.focus_play_btn.clicked.connect(self._toggle_focus)
        pomo_ctrl_row.addWidget(self.focus_reset_btn)
        pomo_ctrl_row.addWidget(self.focus_play_btn)

        pomo_layout.addLayout(pomo_info_v)
        pomo_layout.addStretch()
        pomo_layout.addLayout(pomo_ctrl_row)
        self.prod_stack.addWidget(page_pomo)

        # Page 1: Stopwatch
        page_sw = QWidget()
        sw_layout = QHBoxLayout(page_sw)
        sw_layout.setContentsMargins(0, 0, 0, 0)
        sw_layout.setSpacing(8)

        sw_info_v = QVBoxLayout()
        sw_info_v.setSpacing(2)
        self.stopwatch_val = QLabel("00:00.0")
        self.stopwatch_val.setStyleSheet("color: #ffffff; font-size: 26px; font-weight: 800;")
        self.stopwatch_state_lbl = QLabel("Stopped")
        self.stopwatch_state_lbl.setStyleSheet("color: #7a7a85; font-size: 11px;")
        sw_info_v.addWidget(self.stopwatch_val)
        sw_info_v.addWidget(self.stopwatch_state_lbl)

        sw_ctrl_row = QHBoxLayout()
        sw_ctrl_row.setSpacing(6)
        self.stopwatch_reset_btn = QPushButton("↺")
        self.stopwatch_reset_btn.setFixedSize(28, 28)
        self.stopwatch_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stopwatch_reset_btn.setStyleSheet("""
            QPushButton {
                background: #1f1f26;
                color: #888892;
                font-size: 12px;
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QPushButton:hover {
                color: #ffffff;
                background: #2a2a34;
            }
        """)
        self.stopwatch_reset_btn.clicked.connect(self._reset_stopwatch)

        self.stopwatch_play_btn = QPushButton("▶")
        self.stopwatch_play_btn.setFixedSize(36, 36)
        self.stopwatch_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stopwatch_play_btn.setStyleSheet("""
            QPushButton {
                background: #25252d;
                color: #ffffff;
                font-size: 13px;
                border-radius: 18px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                font-weight: 700;
            }
            QPushButton:hover {
                background: #33333e;
            }
        """)
        self.stopwatch_play_btn.clicked.connect(self._toggle_stopwatch)
        sw_ctrl_row.addWidget(self.stopwatch_reset_btn)
        sw_ctrl_row.addWidget(self.stopwatch_play_btn)

        sw_layout.addLayout(sw_info_v)
        sw_layout.addStretch()
        sw_layout.addLayout(sw_ctrl_row)
        self.prod_stack.addWidget(page_sw)

        f_layout.addWidget(self.prod_stack)
        grid.addWidget(self.card_focus, 1, 0)

        # -------------------------------------------------------------
        # CARD 5: QUICK ACTIONS & APP LAUNCHER (Bottom-Middle)
        # -------------------------------------------------------------
        self.card_actions = self._create_card()
        act_layout = QVBoxLayout(self.card_actions)
        act_layout.setContentsMargins(12, 10, 12, 10)
        act_layout.setSpacing(6)

        act_head = QLabel("⚡  QUICK ACTIONS")
        act_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")
        act_layout.addWidget(act_head)

        btn_act_style = """
            QPushButton {
                background: #1b1b21;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #ffffff;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 6px;
            }
            QPushButton:hover {
                background: #262630;
                border-color: rgba(255, 255, 255, 0.16);
            }
        """

        # Row 1: System Shortcuts (Snip, Win+V, Mic Mute)
        r1 = QHBoxLayout()
        r1.setSpacing(6)

        self.act_snip_btn = QPushButton("📸 Snip")
        self.act_snip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_snip_btn.setStyleSheet(btn_act_style)
        self.act_snip_btn.clicked.connect(self._trigger_screenshot)

        self.act_clip_btn = QPushButton("📋 Win+V")
        self.act_clip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_clip_btn.setStyleSheet(btn_act_style)
        self.act_clip_btn.clicked.connect(self._open_clipboard_win_v)

        self.act_mic_btn = QPushButton("🎙️ Mic")
        self.act_mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_mic_btn.setStyleSheet(btn_act_style)
        self.act_mic_btn.clicked.connect(self._toggle_mic_mute)

        r1.addWidget(self.act_snip_btn)
        r1.addWidget(self.act_clip_btn)
        r1.addWidget(self.act_mic_btn)
        act_layout.addLayout(r1)

        # Row 2: Quick Launchers (Calc, Terminal, Tasks, Explorer)
        r2 = QHBoxLayout()
        r2.setSpacing(6)

        self.act_calc_btn = QPushButton("🧮 Calc")
        self.act_calc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_calc_btn.setStyleSheet(btn_act_style)
        self.act_calc_btn.clicked.connect(lambda: self._launch_app("calc.exe"))

        self.act_term_btn = QPushButton("⚡ Term")
        self.act_term_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_term_btn.setStyleSheet(btn_act_style)
        self.act_term_btn.clicked.connect(lambda: self._launch_app("powershell.exe"))

        self.act_task_btn = QPushButton("📊 Tasks")
        self.act_task_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_task_btn.setStyleSheet(btn_act_style)
        self.act_task_btn.clicked.connect(lambda: self._launch_app("taskmgr.exe"))

        self.act_file_btn = QPushButton("📁 Files")
        self.act_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_file_btn.setStyleSheet(btn_act_style)
        self.act_file_btn.clicked.connect(lambda: self._launch_app("explorer.exe"))

        r2.addWidget(self.act_calc_btn)
        r2.addWidget(self.act_term_btn)
        r2.addWidget(self.act_task_btn)
        r2.addWidget(self.act_file_btn)
        act_layout.addLayout(r2)

        grid.addWidget(self.card_actions, 1, 1)

        # -------------------------------------------------------------
        # CARD 6: CLIPBOARD & NOTES (Bottom-Right)
        # -------------------------------------------------------------
        self.card_notes = self._create_card()
        notes_layout = QVBoxLayout(self.card_notes)
        notes_layout.setContentsMargins(12, 10, 12, 10)
        notes_layout.setSpacing(5)

        notes_head = QLabel("📄  CLIPBOARD & NOTES")
        notes_head.setStyleSheet("color: #888892; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")
        notes_layout.addWidget(notes_head)

        self.clip_list_layout = QVBoxLayout()
        self.clip_list_layout.setSpacing(4)
        notes_layout.addLayout(self.clip_list_layout)
        self._populate_mock_clipboard()

        note_row = QHBoxLayout()
        note_row.setSpacing(6)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Write a note...")
        self.note_input.setStyleSheet("""
            QLineEdit {
                background: #202026;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 8px;
                padding: 4px 8px;
                color: #ffffff;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(255, 255, 255, 0.22);
            }
        """)
        self.note_input.returnPressed.connect(self._save_note)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(24, 24)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #80808a;
                font-size: 16px;
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
        notes_layout.addLayout(note_row)

        grid.addWidget(self.card_notes, 1, 2)

        self.content_stack.addWidget(self.cards_page)

        # Page 1: Appearance Settings
        self.settings_page = AppearanceSettingsWidget(self.settings_service, self)
        self.content_stack.addWidget(self.settings_page)

        main_layout.addWidget(self.content_stack)

        # -------------------------------------------------------------
        # 3. Bottom Floating Dock (MicaBay Floating Dock)
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
            ("⚙️", "System", self._show_settings, False),
            ("📋", "Clipboard", self._on_clipboard_dock, False),
            ("📝", "Notes", self._on_notes_dock, False),
            ("⏱️", "Focus", self._on_focus_dock, False),
            ("📁", "Shelf", self._on_shelf_dock, False),
            ("🗄️", "Drawer", self._on_drawer_dock, False),
            ("⛅", "Weather", self._on_weather_dock, False),
            ("🕒", "Clock", self._on_clock_dock, False),
            ("📏", "Tools", self._on_tools_dock, False),
            ("🔗", "Links", self._on_links_dock, False),
            ("🗂️", "Windows", self._on_windows_dock, False),
            ("📊", "Screen Time", self._on_screentime_dock, False),
            ("|", "Separator", None, False),
            ("+", "Add", self._on_add_dock, False)
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
        card.setFixedHeight(130)
        card.setStyleSheet("""
            QFrame {
                background: #111114;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 16px;
            }
        """)
        return card

    def _set_active_dock_button(self, active_name: str):
        self.active_dock_name = active_name
        for name, btn in self.dock_buttons.items():
            if name == active_name:
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
                        background: rgba(255, 255, 255, 0.12);
                        color: #ffffff;
                    }
                """)

    def _flash_dock_button(self, name: str):
        if name in self.dock_buttons:
            btn = self.dock_buttons[name]
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(0, 210, 255, 0.35);
                    color: #00d2ff;
                    border: 1px solid #00d2ff;
                    border-radius: 10px;
                    font-size: 14px;
                    font-weight: 800;
                }
            """)
            QTimer.singleShot(400, lambda: self._set_active_dock_button(getattr(self, "active_dock_name", "Home")))

    def _flash_card(self, card_widget):
        if not card_widget:
            return
        orig_style = """
            QFrame {
                background: #111114;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 16px;
            }
        """
        flash_style = """
            QFrame {
                background: #15151c;
                border: 1.5px solid #00d2ff;
                border-radius: 16px;
            }
        """
        card_widget.setStyleSheet(flash_style)
        QTimer.singleShot(500, lambda: card_widget.setStyleSheet(orig_style))

    def _show_home(self):
        self.content_stack.setCurrentWidget(self.cards_page)
        self.home_btn.setText("Home")
        now_dt = datetime.now()
        self.date_lbl.setText(now_dt.strftime("%A, %d %b").replace(" 0", " "))
        self._set_active_dock_button("Home")

    def _show_settings(self):
        self.content_stack.setCurrentWidget(self.settings_page)
        self.home_btn.setText("Settings")
        self.date_lbl.setText("Appearance & Customization")
        self._set_active_dock_button("System")

    def _on_clipboard_dock(self):
        self._show_home()
        self._flash_card(self.card_notes)
        self._open_clipboard_win_v()
        self._flash_dock_button("Clipboard")

    def _on_notes_dock(self):
        self._show_home()
        self._flash_card(self.card_notes)
        self.note_input.setFocus()
        self.note_input.selectAll()
        self._flash_dock_button("Notes")

    def _on_focus_dock(self):
        self._show_home()
        if self.prod_stack.currentIndex() != 0:
            self._toggle_prod_mode()
        self._toggle_focus()
        self._flash_card(self.card_focus)
        self._flash_dock_button("Focus")

    def _on_shelf_dock(self):
        self._flash_dock_button("Shelf")
        self.shelf_requested.emit()

    def _on_drawer_dock(self):
        self._show_home()
        self._flash_card(self.card_actions)
        self._flash_dock_button("Drawer")

    def _on_weather_dock(self):
        self._show_home()
        self._flash_card(self.card_weather)
        if self.weather_service:
            self.weather_service.fetch()
        self._flash_dock_button("Weather")

    def _on_clock_dock(self):
        self._show_home()
        if self.prod_stack.currentIndex() != 1:
            self._toggle_prod_mode()
        self._toggle_stopwatch()
        self._flash_card(self.card_focus)
        self._flash_dock_button("Clock")

    def _on_tools_dock(self):
        self._flash_dock_button("Tools")
        self._launch_app("calc.exe")

    def _on_links_dock(self):
        self._flash_dock_button("Links")
        self._launch_app("powershell.exe")

    def _on_windows_dock(self):
        self._flash_dock_button("Windows")
        self._launch_app("taskmgr.exe")

    def _on_screentime_dock(self):
        self._show_home()
        self._toggle_c1_mode()
        self._flash_card(self.card_screen)
        self._flash_dock_button("Screen Time")

    def _on_add_dock(self):
        self._show_home()
        self._flash_card(self.card_notes)
        if self.note_input.text().strip():
            self._save_note()
        else:
            self.note_input.setFocus()
        self._flash_dock_button("Add")

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
            new_item = {"title": f"Note · {text[:35]}", "time": "Just now"}
            if hasattr(self, "_current_clip_items"):
                self._current_clip_items.insert(0, new_item)
            else:
                self._current_clip_items = [new_item, {"title": "Image · 1041 × 162", "time": "29m"}]
            self._render_clip_items(self._current_clip_items)
            self.note_input.clear()

    def _on_stats_updated(self, stats: dict):
        self.cpu_gauge.set_value(stats.get("cpu", 0))
        self.ram_gauge.set_value(stats.get("ram", 0))
        self.gpu_gauge.set_value(stats.get("gpu", 0))
        self.disk_gauge.set_value(stats.get("disk", 0))

        self.screen_time_val.setText(stats.get("screen_time_total", "1h"))
        self.screen_top_app.setText(stats.get("top_app_str", "Antigravity IDE · 26m"))

        bat = stats.get("battery", 95)
        is_charging = stats.get("is_charging", False)
        self.bat_lbl.setText(f"{bat}% {'⚡' if is_charging else '🔋'}")
        if hasattr(self, "bat_glyph"):
            self.bat_glyph.update_battery(bat, is_charging)
        if hasattr(self, "bat_pct_lbl"):
            self.bat_pct_lbl.setText(f"{bat}% {'⚡' if is_charging else ''}")
        if hasattr(self, "bat_state_lbl"):
            self.bat_state_lbl.setText("Plugged In · Fast Charging" if is_charging else "On Battery")

        if hasattr(self, "net_down_lbl"):
            self.net_down_lbl.setText(f"↓ {stats.get('net_down_str', '0 KB/s')}")
        if hasattr(self, "net_up_lbl"):
            self.net_up_lbl.setText(f"↑ {stats.get('net_up_str', '0 KB/s')}")

    def _toggle_c1_mode(self):
        curr = self.c1_stack.currentIndex()
        next_idx = 1 if curr == 0 else 0
        self.c1_stack.setCurrentIndex(next_idx)
        if next_idx == 0:
            self.c1_title_lbl.setText("🎵  NOW PLAYING")
            self.c1_toggle_btn.setText("Stats ⮂")
        else:
            self.c1_title_lbl.setText("📊  SCREEN TIME")
            self.c1_toggle_btn.setText("Music ⮂")

    def _toggle_prod_mode(self):
        curr = self.prod_stack.currentIndex()
        next_idx = 1 if curr == 0 else 0
        self.prod_stack.setCurrentIndex(next_idx)
        if next_idx == 0:
            self.prod_title_lbl.setText("⏱️  POMODORO")
            self.prod_mode_btn.setText("Stopwatch ⮂")
        else:
            self.prod_title_lbl.setText("⏱️  STOPWATCH")
            self.prod_mode_btn.setText("Pomodoro ⮂")

    def _reset_focus(self):
        self.focus_running = False
        self.focus_timer.stop()
        self.focus_seconds = 25 * 60
        self.focus_val.setText("25:00")
        self.focus_state_lbl.setText("Ready")
        self.focus_play_btn.setText("▶")

    def _toggle_stopwatch(self):
        self.stopwatch_running = not self.stopwatch_running
        if self.stopwatch_running:
            self.stopwatch_last_time = time.time()
            self.stopwatch_play_btn.setText("⏸")
            self.stopwatch_state_lbl.setText("Running...")
            self.stopwatch_timer.start(50)
        else:
            self.stopwatch_play_btn.setText("▶")
            self.stopwatch_state_lbl.setText("Paused")
            self.stopwatch_timer.stop()

    def _reset_stopwatch(self):
        self.stopwatch_running = False
        self.stopwatch_timer.stop()
        self.stopwatch_elapsed_ms = 0
        self.stopwatch_val.setText("00:00.0")
        self.stopwatch_state_lbl.setText("Stopped")
        self.stopwatch_play_btn.setText("▶")

    def _tick_stopwatch(self):
        now = time.time()
        dt_ms = int((now - self.stopwatch_last_time) * 1000)
        self.stopwatch_last_time = now
        self.stopwatch_elapsed_ms += dt_ms
        total_s = self.stopwatch_elapsed_ms // 1000
        ms = (self.stopwatch_elapsed_ms % 1000) // 100
        m = total_s // 60
        s = total_s % 60
        self.stopwatch_val.setText(f"{m:02d}:{s:02d}.{ms}")

    def _trigger_screenshot(self):
        try:
            os.startfile("ms-screenclip:")
        except Exception:
            try:
                subprocess.Popen(["explorer.exe", "ms-screenclip:"])
            except Exception:
                pass

    def _open_clipboard_win_v(self):
        try:
            import ctypes
            # Win+V
            ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x56, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)
            ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
        except Exception:
            self.shelf_requested.emit()

    def _toggle_mic_mute(self):
        if self.volume_service:
            new_state = self.volume_service.toggle_microphone_mute()
            self.is_mic_muted = new_state
            self._update_mic_btn_ui(new_state)

    def _update_mic_btn_ui(self, is_muted: bool):
        if hasattr(self, "act_mic_btn"):
            if is_muted:
                self.act_mic_btn.setText("🎙️ Muted")
                self.act_mic_btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 75, 75, 0.22);
                        border: 1px solid rgba(255, 75, 75, 0.4);
                        border-radius: 8px;
                        color: #ff4b4b;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 4px 6px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 75, 75, 0.35);
                    }
                """)
            else:
                self.act_mic_btn.setText("🎙️ Active")
                self.act_mic_btn.setStyleSheet("""
                    QPushButton {
                        background: #1b1b21;
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 8px;
                        color: #00d2ff;
                        font-size: 11px;
                        font-weight: 600;
                        padding: 4px 6px;
                    }
                    QPushButton:hover {
                        background: #262630;
                        border-color: rgba(255, 255, 255, 0.16);
                    }
                """)

    def _launch_app(self, app_cmd: str):
        try:
            subprocess.Popen([app_cmd], shell=True)
        except Exception:
            pass

    def _toggle_speaker_mute(self):
        if self.volume_service:
            new_mute = self.volume_service.toggle_mute()
            self.vol_mute_btn.setText("🔇" if new_mute else "🔊")

    def _on_vol_slider_moved(self, val: int):
        if self.volume_service:
            self.volume_service.set_volume(val)

    def _on_media_updated(self, data: dict):
        title = data.get("title", "") or "No Media Playing"
        artist = data.get("artist", "") or "MicaBay Media"
        is_playing = data.get("is_playing", False)
        thumb_bytes = data.get("thumbnail")

        if len(title) > 22:
            title = title[:20] + "..."
        if len(artist) > 24:
            artist = artist[:22] + "..."

        self.media_title_lbl.setText(title)
        self.media_artist_lbl.setText(artist)
        self.media_play_btn.setText("⏸" if is_playing else "▶")
        self.media_eq_bars.set_playing(is_playing)

        if thumb_bytes:
            pix = QPixmap()
            pix.loadFromData(thumb_bytes)
            scaled = pix.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.media_thumb_lbl.setPixmap(scaled)
        else:
            self.media_thumb_lbl.setText("🎵")
            self.media_thumb_lbl.setStyleSheet("background: #222228; border-radius: 6px; font-size: 14px;")

    def _on_volume_changed(self, pct: int, is_muted: bool):
        if hasattr(self, "vol_slider") and not self.vol_slider.isSliderDown():
            self.vol_slider.blockSignals(True)
            self.vol_slider.setValue(0 if is_muted else pct)
            self.vol_slider.blockSignals(False)
        if hasattr(self, "vol_mute_btn"):
            self.vol_mute_btn.setText("🔇" if is_muted or pct == 0 else "🔊")

    def _on_mic_mute_changed(self, is_muted: bool):
        self.is_mic_muted = is_muted
        self._update_mic_btn_ui(is_muted)

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
        if hasattr(self, "weather_sub") and self.weather_sub:
            self.weather_sub.setText(f"{city} · Humidity {hum_pct}% · H: {h}° L: {l}°")

    def _populate_mock_clipboard(self):
        # Initial clipboard items matching screenshot
        self._current_clip_items = [
            {"title": "Image · 1041 × 162", "time": "29m"},
            {"title": "Image · 583 × 342", "time": "29m"}
        ]
        self._render_clip_items(self._current_clip_items)

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
