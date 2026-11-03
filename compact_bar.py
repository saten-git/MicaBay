from datetime import datetime
from PySide6.QtCore import Qt, QTimer, QObject, QEvent, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QColor, QPainter, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QStackedWidget, QSizePolicy, QPushButton, QGraphicsOpacityEffect, QGraphicsDropShadowEffect
)
from audio_visualizer import EqualizerBarsWidget
from battery_glyph import BatteryGlyphWidget
from volume_bar import VolumeBarWidget

class CompactClickRedirector(QObject):
    """Intercepts mouse clicks on any child widget and forwards to expand dashboard unless handled by an interactive control."""
    def __init__(self, compact_bar):
        super().__init__(compact_bar)
        self.compact_bar = compact_bar

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress:
            if ev.button() == Qt.MouseButton.LeftButton:
                if getattr(obj, "_is_interactive_control", False):
                    return False
                notch = self.compact_bar.window()
                if hasattr(notch, "current_state") and notch.current_state in ("EXPANDED", "SHELF"):
                    notch.collapse()
                    return True
                if hasattr(notch, "expand_dashboard"):
                    notch.expand_dashboard()
                    return True
        elif t == QEvent.Type.DragEnter:
            if ev.mimeData().hasUrls():
                ev.acceptProposedAction()
                notch = self.compact_bar.window()
                if hasattr(notch, "dragEnterEvent"):
                    notch.dragEnterEvent(ev)
                return True
        elif t == QEvent.Type.DragMove:
            if ev.mimeData().hasUrls():
                ev.acceptProposedAction()
                notch = self.compact_bar.window()
                if hasattr(notch, "dragMoveEvent"):
                    notch.dragMoveEvent(ev)
                return True
        elif t == QEvent.Type.Drop:
            notch = self.compact_bar.window()
            if hasattr(notch, "dropEvent"):
                notch.dropEvent(ev)
                return True
        return False

class CompactBar(QWidget):
    elastic_size_requested = Signal(int)

    def __init__(self, parent=None, weather_service=None, media_service=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.weather_service = weather_service
        self.media_service = media_service
        if parent and hasattr(parent, "settings_service"):
            self.placement = parent.settings_service.get("placement", "full_taskbar")
        else:
            self.placement = "full_taskbar"
        self.weather_visible = True
        self.raw_media_title = ""
        self.max_boundary_x = 505

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if self.placement in ("taskbar", "full_taskbar"):
            layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.stack = QStackedWidget(self)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Smooth cross-fade transition effect
        self._fade_effect = QGraphicsOpacityEffect(self.stack)
        self.stack.setGraphicsEffect(self._fade_effect)
        self._fade_anim = QVariantAnimation(self)
        self._fade_anim.setDuration(130)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.valueChanged.connect(self._fade_effect.setOpacity)

        # -------------------------------------------------------------
        # 1. Media Page (Weather | Thumbnail | Song Title ... | |||)
        # Self-elastic adjustable left-to-right layout
        # -------------------------------------------------------------
        self.media_page = QWidget()
        m_layout = QHBoxLayout(self.media_page)
        m_layout.setContentsMargins(8, 3, 8, 8)
        m_layout.setSpacing(7)
        m_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Weather badge in media page
        self.media_weather_widget = QWidget()
        mw_layout = QHBoxLayout(self.media_weather_widget)
        mw_layout.setContentsMargins(0, 0, 2, 0)
        mw_layout.setSpacing(4)
        mw_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.media_weather_icon = QLabel("🌙☁️")
        self.media_weather_icon.setStyleSheet("font-size: 11px; background: transparent;")
        self.media_weather_temp = QLabel("22°C")
        self.media_weather_temp.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 700; background: transparent;")
        self.media_weather_sep = QLabel("|")
        self.media_weather_sep.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        mw_layout.addWidget(self.media_weather_icon)
        mw_layout.addWidget(self.media_weather_temp)
        mw_layout.addWidget(self.media_weather_sep)

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(20, 20)
        self.thumb_lbl.setStyleSheet("""
            background: #222228;
            border-radius: 4px;
            border: 1px solid rgba(255, 255, 255, 0.12);
        """)
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_lbl = QLabel("No Media Playing")
        self.title_lbl.setStyleSheet("""
            color: #ffffff;
            font-size: 11px;
            font-weight: 600;
            background: transparent;
        """)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.eq_bars = EqualizerBarsWidget()

        # Media Clock Widget (separable for elastic collision-free drop)
        self.media_clock_widget = QWidget()
        mc_layout = QHBoxLayout(self.media_clock_widget)
        mc_layout.setContentsMargins(0, 0, 0, 0)
        mc_layout.setSpacing(5)
        mc_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.media_sep_status = QLabel("|")
        self.media_sep_status.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.media_time_lbl = QLabel("12:00 PM")
        self.media_time_lbl.setStyleSheet("""
            color: #ffffff;
            font-size: 11px;
            font-weight: 600;
            background: transparent;
        """)
        mc_layout.addWidget(self.media_sep_status)
        mc_layout.addWidget(self.media_time_lbl)
        self.media_clock_widget.setVisible(False)

        # Media Battery Widget (separable for elastic collision-free drop)
        self.media_battery_widget = QWidget()
        mb_layout = QHBoxLayout(self.media_battery_widget)
        mb_layout.setContentsMargins(0, 0, 0, 0)
        mb_layout.setSpacing(5)
        mb_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.media_sep_battery = QLabel("|")
        self.media_sep_battery.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.media_charge_lbl = QLabel("⚡")
        self.media_charge_lbl.setStyleSheet("color: #ffffff; font-size: 10px; font-weight: 800; background: transparent;")

        self.media_battery_glyph = BatteryGlyphWidget()

        self.media_battery_pct_lbl = QLabel("95")
        self.media_battery_pct_lbl.setStyleSheet("""
            color: #ffffff;
            font-size: 11px;
            font-weight: 600;
            background: transparent;
        """)

        mb_layout.addWidget(self.media_sep_battery)
        mb_layout.addWidget(self.media_charge_lbl)
        mb_layout.addWidget(self.media_battery_glyph)
        mb_layout.addWidget(self.media_battery_pct_lbl)
        self.media_battery_widget.setVisible(False)

        # Left stretch: active in Top / Pill mode; hidden in Full Taskbar mode to flow left-to-right!
        self.m_left_stretch = QWidget()
        self.m_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.m_left_stretch.setVisible(False)
        m_layout.addWidget(self.m_left_stretch)

        m_layout.addWidget(self.media_weather_widget)
        m_layout.addWidget(self.thumb_lbl)
        m_layout.addWidget(self.title_lbl)
        m_layout.addWidget(self.eq_bars)

        # Subtle interactive Play / Pause button
        self.media_play_btn = QPushButton("▶")
        self.media_play_btn.setFixedSize(16, 16)
        self.media_play_btn._is_interactive_control = True
        self.media_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.media_play_btn.setToolTip("Play / Pause")
        self.media_play_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.12);
                border: none;
                border-radius: 8px;
                color: #ffffff;
                font-size: 8px;
                font-weight: 700;
                padding-left: 1px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.28);
            }
        """)
        self.media_play_btn.clicked.connect(self._on_play_clicked)
        m_layout.addWidget(self.media_play_btn)

        m_layout.addWidget(self.media_clock_widget)
        m_layout.addWidget(self.media_battery_widget)

        # Right stretch absorbs leftover space
        self.m_right_stretch = QWidget()
        self.m_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        m_layout.addWidget(self.m_right_stretch)

        self.stack.addWidget(self.media_page)

        # -------------------------------------------------------------
        # 2. Toast Page (Copied · Image)
        # -------------------------------------------------------------
        self.toast_page = QWidget()
        t_layout = QHBoxLayout(self.toast_page)
        t_layout.setContentsMargins(12, 0, 12, 0)
        t_layout.setSpacing(6)
        t_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.t_left_stretch = QWidget()
        self.t_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.t_left_stretch.setVisible(False)
        t_layout.addWidget(self.t_left_stretch)

        self.toast_icon = QLabel("📋")
        self.toast_icon.setStyleSheet("font-size: 13px; background: transparent;")
        self.toast_text = QLabel("Copied · Image")
        self.toast_text.setStyleSheet("""
            color: #ffffff;
            font-size: 11px;
            font-weight: 700;
            background: transparent;
        """)

        t_layout.addWidget(self.toast_icon)
        t_layout.addWidget(self.toast_text)

        self.t_right_stretch = QWidget()
        self.t_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        t_layout.addWidget(self.t_right_stretch)
        self.stack.addWidget(self.toast_page)

        # -------------------------------------------------------------
        # 3. Idle Page (🌙☁️ 22°C Partly cloudy | 10:02 PM | ⚡ [battery] 89)
        # -------------------------------------------------------------
        self.idle_page = QWidget()
        i_layout = QHBoxLayout(self.idle_page)
        i_layout.setContentsMargins(12, 0, 12, 0)
        i_layout.setSpacing(6)
        i_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Left stretch for centering in Top / Pill mode; hidden in Full Taskbar mode
        self.i_left_stretch = QWidget()
        self.i_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.i_left_stretch.setVisible(False)
        i_layout.addWidget(self.i_left_stretch)

        self.idle_weather_icon = QLabel("🌙☁️")
        self.idle_weather_icon.setStyleSheet("font-size: 12px; background: transparent;")
        self.idle_weather_temp = QLabel("22°C")
        self.idle_weather_temp.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 700; background: transparent;")
        self.idle_weather_cond = QLabel("Partly cloudy")
        self.idle_weather_cond.setStyleSheet("color: #9a9ab0; font-size: 10px; font-weight: 500; background: transparent;")

        i_layout.addWidget(self.idle_weather_icon)
        i_layout.addWidget(self.idle_weather_temp)
        i_layout.addWidget(self.idle_weather_cond)

        # Idle Clock Widget
        self.idle_clock_widget = QWidget()
        ic_layout = QHBoxLayout(self.idle_clock_widget)
        ic_layout.setContentsMargins(0, 0, 0, 0)
        ic_layout.setSpacing(6)
        ic_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.idle_sep0 = QLabel("|")
        self.idle_sep0.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.time_lbl = QLabel("12:00 PM")
        self.time_lbl.setStyleSheet("""
            color: #ffffff;
            font-size: 11px;
            font-weight: 600;
            background: transparent;
        """)
        ic_layout.addWidget(self.idle_sep0)
        ic_layout.addWidget(self.time_lbl)
        i_layout.addWidget(self.idle_clock_widget)

        # Idle Battery Widget
        self.idle_battery_widget = QWidget()
        ib_layout = QHBoxLayout(self.idle_battery_widget)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        ib_layout.setSpacing(6)
        ib_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.idle_sep1 = QLabel("|")
        self.idle_sep1.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.charge_lbl = QLabel("⚡")
        self.charge_lbl.setStyleSheet("color: #ffffff; font-size: 10px; font-weight: 800; background: transparent;")

        self.battery_glyph = BatteryGlyphWidget()

        self.battery_pct_lbl = QLabel("95")
        self.battery_pct_lbl.setStyleSheet("""
            color: #ffffff;
            font-size: 11px;
            font-weight: 600;
            background: transparent;
        """)

        ib_layout.addWidget(self.idle_sep1)
        ib_layout.addWidget(self.charge_lbl)
        ib_layout.addWidget(self.battery_glyph)
        ib_layout.addWidget(self.battery_pct_lbl)
        i_layout.addWidget(self.idle_battery_widget)

        # Right stretch absorbs extra space
        self.i_right_stretch = QWidget()
        self.i_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        i_layout.addWidget(self.i_right_stretch)

        self.stack.addWidget(self.idle_page)

        # -------------------------------------------------------------
        # 4. Volume HUD Page (🔊 [========--] 64%)
        # -------------------------------------------------------------
        self.volume_page = QWidget()
        v_layout = QHBoxLayout(self.volume_page)
        v_layout.setContentsMargins(10, 0, 10, 0)
        v_layout.setSpacing(8)
        v_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.v_left_stretch = QWidget()
        self.v_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.v_left_stretch.setVisible(False)
        v_layout.addWidget(self.v_left_stretch)

        self.vol_icon = QLabel("🔊")
        self.vol_icon.setStyleSheet("font-size: 12px; background: transparent;")

        self.vol_bar = VolumeBarWidget()

        self.vol_pct_lbl = QLabel("50%")
        self.vol_pct_lbl.setStyleSheet("""
            color: #ffffff;
            font-size: 11px;
            font-weight: 700;
            min-width: 32px;
            background: transparent;
        """)

        v_layout.addWidget(self.vol_icon)
        v_layout.addWidget(self.vol_bar)
        v_layout.addWidget(self.vol_pct_lbl)

        self.v_right_stretch = QWidget()
        self.v_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        v_layout.addWidget(self.v_right_stretch)
        self.stack.addWidget(self.volume_page)

        # -------------------------------------------------------------
        # 5. Download HUD Page (📥 filename.zip | 12 MB · 1.5 MB/s)
        # -------------------------------------------------------------
        self.download_page = QWidget()
        dl_layout = QHBoxLayout(self.download_page)
        dl_layout.setContentsMargins(10, 0, 10, 0)
        dl_layout.setSpacing(6)
        dl_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Left stretch: active in Top / Pill mode; hidden in Full Taskbar mode to flow left-most!
        self.dl_left_stretch = QWidget()
        self.dl_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.dl_left_stretch.setVisible(False)
        dl_layout.addWidget(self.dl_left_stretch)

        self.dl_icon = QLabel("📥")
        self.dl_icon.setStyleSheet("font-size: 13px; background: transparent;")

        self.dl_name_lbl = QLabel("Downloading")
        self.dl_name_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        self.dl_sep = QLabel("|")
        self.dl_sep.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.dl_info_lbl = QLabel("0 MB/s")
        self.dl_info_lbl.setStyleSheet("color: #00d2ff; font-size: 11px; font-weight: 600; background: transparent;")
        self.dl_info_lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        dl_layout.addWidget(self.dl_icon)
        dl_layout.addWidget(self.dl_name_lbl)
        dl_layout.addWidget(self.dl_sep)
        dl_layout.addWidget(self.dl_info_lbl)

        # Right stretch absorbs extra space
        self.dl_right_stretch = QWidget()
        self.dl_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        dl_layout.addWidget(self.dl_right_stretch)

        self.stack.addWidget(self.download_page)

        # -------------------------------------------------------------
        # 6. Microphone HUD Page (🎙️ Microphone Active · Chrome)
        # -------------------------------------------------------------
        self.mic_page = QWidget()
        mic_layout = QHBoxLayout(self.mic_page)
        mic_layout.setContentsMargins(10, 0, 10, 0)
        mic_layout.setSpacing(6)
        mic_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.mic_left_stretch = QWidget()
        self.mic_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.mic_left_stretch.setVisible(False)
        mic_layout.addWidget(self.mic_left_stretch)

        self.mic_dot = QLabel("●")
        self.mic_dot.setStyleSheet("color: #00d2ff; font-size: 9px; background: transparent;")

        self.mic_icon = QLabel("🎙️")
        self.mic_icon.setStyleSheet("font-size: 12px; background: transparent;")

        self.mic_text_lbl = QLabel("Microphone Active")
        self.mic_text_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        mic_layout.addWidget(self.mic_dot)
        mic_layout.addWidget(self.mic_icon)
        mic_layout.addWidget(self.mic_text_lbl)

        self.mic_right_stretch = QWidget()
        self.mic_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        mic_layout.addWidget(self.mic_right_stretch)
        self.stack.addWidget(self.mic_page)

        # -------------------------------------------------------------
        # 7. Battery Alert Page (⚡ Charger Connected · 85%)
        # -------------------------------------------------------------
        self.battery_alert_page = QWidget()
        ba_layout = QHBoxLayout(self.battery_alert_page)
        ba_layout.setContentsMargins(10, 0, 10, 0)
        ba_layout.setSpacing(6)
        ba_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.ba_left_stretch = QWidget()
        self.ba_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.ba_left_stretch.setVisible(False)
        ba_layout.addWidget(self.ba_left_stretch)

        self.ba_icon = QLabel("⚡")
        self.ba_icon.setStyleSheet("font-size: 13px; background: transparent;")

        self.ba_text_lbl = QLabel("Charger Connected")
        self.ba_text_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        ba_layout.addWidget(self.ba_icon)
        ba_layout.addWidget(self.ba_text_lbl)

        self.ba_right_stretch = QWidget()
        self.ba_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        ba_layout.addWidget(self.ba_right_stretch)
        self.stack.addWidget(self.battery_alert_page)

        # -------------------------------------------------------------
        # 8. Apple-style Cursive Greeting Page ("Good morning", etc.)
        # -------------------------------------------------------------
        self.greeting_page = QWidget()
        g_layout = QHBoxLayout(self.greeting_page)
        g_layout.setContentsMargins(14, 0, 14, 0)
        g_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Left stretch: active in Top / Pill mode; hidden in Full Taskbar mode to flow left-to-right!
        self.g_left_stretch = QWidget()
        self.g_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.g_left_stretch.setVisible(False)
        g_layout.addWidget(self.g_left_stretch)

        self.greeting_lbl = QLabel("")
        self.greeting_lbl.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-family: 'Segoe Script', 'Segoe Print', cursive, 'Brush Script MT';
                font-size: 15px;
                font-style: italic;
                font-weight: 700;
                letter-spacing: 0.6px;
                background: transparent;
            }
        """)
        glow = QGraphicsDropShadowEffect(self.greeting_lbl)
        glow.setBlurRadius(14)
        glow.setColor(QColor(255, 255, 255, 220))
        glow.setOffset(0, 0)
        self.greeting_lbl.setGraphicsEffect(glow)

        g_layout.addWidget(self.greeting_lbl)

        # Right stretch absorbs extra space
        self.g_right_stretch = QWidget()
        self.g_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        g_layout.addWidget(self.g_right_stretch)

        self.stack.addWidget(self.greeting_page)

        # -------------------------------------------------------------
        # 9. Net Speed Page (↓ 4.8 MB/s  ↑ 820 KB/s)
        # -------------------------------------------------------------
        self.net_speed_page = QWidget()
        ns_layout = QHBoxLayout(self.net_speed_page)
        ns_layout.setContentsMargins(12, 0, 12, 0)
        ns_layout.setSpacing(6)
        ns_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.net_left_stretch = QWidget()
        self.net_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.net_left_stretch.setVisible(False)
        ns_layout.addWidget(self.net_left_stretch)

        self.net_down_icon = QLabel("↓")
        self.net_down_icon.setStyleSheet("color: #00d2ff; font-size: 12px; font-weight: 800; background: transparent;")

        self.net_down_lbl = QLabel("0 KB/s")
        self.net_down_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        self.net_sep = QLabel("|")
        self.net_sep.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.net_up_icon = QLabel("↑")
        self.net_up_icon.setStyleSheet("color: #00d2ff; font-size: 12px; font-weight: 800; background: transparent;")

        self.net_up_lbl = QLabel("0 KB/s")
        self.net_up_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        ns_layout.addWidget(self.net_down_icon)
        ns_layout.addWidget(self.net_down_lbl)
        ns_layout.addWidget(self.net_sep)
        ns_layout.addWidget(self.net_up_icon)
        ns_layout.addWidget(self.net_up_lbl)

        self.net_right_stretch = QWidget()
        self.net_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        ns_layout.addWidget(self.net_right_stretch)

        self.stack.addWidget(self.net_speed_page)

        # -------------------------------------------------------------
        # 10. CPU and RAM Page (💻 CPU 24% | RAM 62%)
        # -------------------------------------------------------------
        self.cpu_ram_page = QWidget()
        cr_layout = QHBoxLayout(self.cpu_ram_page)
        cr_layout.setContentsMargins(12, 0, 12, 0)
        cr_layout.setSpacing(6)
        cr_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.cpu_ram_left_stretch = QWidget()
        self.cpu_ram_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.cpu_ram_left_stretch.setVisible(False)
        cr_layout.addWidget(self.cpu_ram_left_stretch)

        self.cpu_icon = QLabel("💻")
        self.cpu_icon.setStyleSheet("font-size: 12px; background: transparent;")

        self.cpu_lbl = QLabel("CPU 0%")
        self.cpu_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        self.cpu_ram_sep = QLabel("|")
        self.cpu_ram_sep.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.ram_lbl = QLabel("RAM 0%")
        self.ram_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        cr_layout.addWidget(self.cpu_icon)
        cr_layout.addWidget(self.cpu_lbl)
        cr_layout.addWidget(self.cpu_ram_sep)
        cr_layout.addWidget(self.ram_lbl)

        self.cpu_ram_right_stretch = QWidget()
        self.cpu_ram_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cr_layout.addWidget(self.cpu_ram_right_stretch)

        self.stack.addWidget(self.cpu_ram_page)

        # -------------------------------------------------------------
        # 11. Weather & Temperature Page (⛅ 24°C | Partly Cloudy)
        # -------------------------------------------------------------
        self.weather_page = QWidget()
        wp_layout = QHBoxLayout(self.weather_page)
        wp_layout.setContentsMargins(12, 0, 12, 0)
        wp_layout.setSpacing(6)
        wp_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.w_left_stretch = QWidget()
        self.w_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.w_left_stretch.setVisible(False)
        wp_layout.addWidget(self.w_left_stretch)

        self.w_icon_lbl = QLabel("🌙☁️")
        self.w_icon_lbl.setStyleSheet("font-size: 12px; background: transparent;")

        self.w_temp_lbl = QLabel("22°C")
        self.w_temp_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 700; background: transparent;")

        self.w_sep = QLabel("|")
        self.w_sep.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.w_cond_lbl = QLabel("Partly cloudy")
        self.w_cond_lbl.setStyleSheet("color: #9a9ab0; font-size: 11px; font-weight: 600; background: transparent;")

        wp_layout.addWidget(self.w_icon_lbl)
        wp_layout.addWidget(self.w_temp_lbl)
        wp_layout.addWidget(self.w_sep)
        wp_layout.addWidget(self.w_cond_lbl)

        self.w_right_stretch = QWidget()
        self.w_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        wp_layout.addWidget(self.w_right_stretch)

        self.stack.addWidget(self.weather_page)

        # -------------------------------------------------------------
        # 12. Date & Day Page (📅 Tuesday | 03 November)
        # -------------------------------------------------------------
        self.date_page = QWidget()
        dp_layout = QHBoxLayout(self.date_page)
        dp_layout.setContentsMargins(12, 0, 12, 0)
        dp_layout.setSpacing(6)
        dp_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.date_left_stretch = QWidget()
        self.date_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.date_left_stretch.setVisible(False)
        dp_layout.addWidget(self.date_left_stretch)

        self.date_icon_lbl = QLabel("📅")
        self.date_icon_lbl.setStyleSheet("font-size: 12px; background: transparent;")

        self.date_day_lbl = QLabel("Tuesday")
        self.date_day_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 700; background: transparent;")

        self.date_sep = QLabel("|")
        self.date_sep.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.date_full_lbl = QLabel("03 November")
        self.date_full_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        dp_layout.addWidget(self.date_icon_lbl)
        dp_layout.addWidget(self.date_day_lbl)
        dp_layout.addWidget(self.date_sep)
        dp_layout.addWidget(self.date_full_lbl)

        self.date_right_stretch = QWidget()
        self.date_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        dp_layout.addWidget(self.date_right_stretch)

        self.stack.addWidget(self.date_page)

        # -------------------------------------------------------------
        # 13. Notifications Page (🔔 3 Unread or 🔔 No notifications)
        # -------------------------------------------------------------
        self.notification_page = QWidget()
        np_layout = QHBoxLayout(self.notification_page)
        np_layout.setContentsMargins(12, 0, 12, 0)
        np_layout.setSpacing(6)
        np_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.notif_left_stretch = QWidget()
        self.notif_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.notif_left_stretch.setVisible(False)
        np_layout.addWidget(self.notif_left_stretch)

        self.notif_icon_lbl = QLabel("🔔")
        self.notif_icon_lbl.setStyleSheet("font-size: 12px; background: transparent;")

        self.notif_text_lbl = QLabel("No notifications")
        self.notif_text_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        np_layout.addWidget(self.notif_icon_lbl)
        np_layout.addWidget(self.notif_text_lbl)

        self.notif_right_stretch = QWidget()
        self.notif_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        np_layout.addWidget(self.notif_right_stretch)

        self.stack.addWidget(self.notification_page)

        # -------------------------------------------------------------
        # 14. Real-time Notification Toast Page (💬 Telegram · John: Message)
        # -------------------------------------------------------------
        self.notification_toast_page = QWidget()
        nt_layout = QHBoxLayout(self.notification_toast_page)
        nt_layout.setContentsMargins(10, 0, 10, 0)
        nt_layout.setSpacing(6)
        nt_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.nt_left_stretch = QWidget()
        self.nt_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.placement in ("taskbar", "full_taskbar"):
            self.nt_left_stretch.setVisible(False)
        nt_layout.addWidget(self.nt_left_stretch)

        self.nt_icon_lbl = QLabel("💬")
        self.nt_icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")

        self.nt_app_lbl = QLabel("Telegram")
        self.nt_app_lbl.setStyleSheet("color: #00d2ff; font-size: 11px; font-weight: 700; background: transparent;")

        self.nt_sep = QLabel("·")
        self.nt_sep.setStyleSheet("color: #7a7a88; font-size: 11px; font-weight: 600;")

        self.nt_msg_lbl = QLabel("")
        self.nt_msg_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        nt_layout.addWidget(self.nt_icon_lbl)
        nt_layout.addWidget(self.nt_app_lbl)
        nt_layout.addWidget(self.nt_sep)
        nt_layout.addWidget(self.nt_msg_lbl)

        self.nt_right_stretch = QWidget()
        self.nt_right_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        nt_layout.addWidget(self.nt_right_stretch)

        self.stack.addWidget(self.notification_toast_page)

        layout.addWidget(self.stack)

        # Install click & drag redirector on stack and all children so interacting anywhere works
        self.stack.setAcceptDrops(True)
        self._click_filter = CompactClickRedirector(self)
        self.installEventFilter(self._click_filter)
        self.stack.installEventFilter(self._click_filter)
        for child in self.findChildren(QWidget):
            child.setCursor(Qt.CursorShape.PointingHandCursor)
            child.setAcceptDrops(True)
            child.installEventFilter(self._click_filter)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)
        self.clock_timer.start(1000)
        self._tick_clock()

        # Dynamic Weather Rotation Timer (Alternates Temp <-> Humid every 5.5s, matching Windows Taskbar Widget)
        self.weather_cycle_state = 0
        self.current_weather_data = None
        self.weather_cycle_timer = QTimer(self)
        self.weather_cycle_timer.timeout.connect(self._cycle_weather_display)
        self.weather_cycle_timer.start(5500)

        if self.weather_service:
            self.weather_service.weather_updated.connect(self.update_weather)
            self.update_weather(self.weather_service.get_data())

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))

    def childEvent(self, event):
        if event.type() == QEvent.Type.ChildAdded and hasattr(self, "_click_filter"):
            child = event.child()
            if child and child.isWidgetType():
                child.setCursor(Qt.CursorShape.PointingHandCursor)
                child.setAcceptDrops(True)
                child.installEventFilter(self._click_filter)
        super().childEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            notch = self.window()
            if hasattr(notch, "expand_dashboard"):
                notch.expand_dashboard()
                event.accept()
                return
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            notch = self.window()
            if hasattr(notch, "open_shelf"):
                notch.open_shelf()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        notch = self.window()
        if hasattr(notch, "dropEvent"):
            notch.dropEvent(event)
        else:
            event.acceptProposedAction()

    def update_weather(self, data: dict):
        self.current_weather_data = data
        icon = data.get("icon", "🌙☁️")
        temp = data.get("temp_str", "21°C")
        cond = data.get("condition", "Partly cloudy")
        humid = data.get("humidity_desc", "Humid")

        self.idle_weather_icon.setText(icon)
        self.idle_weather_temp.setText(temp)
        self.idle_weather_cond.setText(f"{cond} · {humid}" if humid else cond)

        if hasattr(self, "w_icon_lbl"):
            self.w_icon_lbl.setText(icon)
            self.w_temp_lbl.setText(temp)
            self.w_cond_lbl.setText(cond)

        self._apply_media_weather_text()

    def _cycle_weather_display(self):
        self.weather_cycle_state = (getattr(self, "weather_cycle_state", 0) + 1) % 2
        self._apply_media_weather_text()
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(self.max_boundary_x)

    def _apply_media_weather_text(self):
        data = getattr(self, "current_weather_data", None)
        if not data:
            return
        icon = data.get("icon", "🌙☁️")
        temp = data.get("temp_str", "21°C")
        humid = data.get("humidity_desc", "Humid")
        cond = data.get("condition", "Partly cloudy")

        self.media_weather_icon.setText(icon)
        # Alternate between Temperature ("21°C") and Humidity/Condition ("Humid") every 5.5s
        if getattr(self, "weather_cycle_state", 0) == 0:
            self.media_weather_temp.setText(temp)
        else:
            self.media_weather_temp.setText(humid or cond)

    def set_weather_visible(self, visible: bool):
        self.weather_visible = visible
        self.media_weather_widget.setVisible(False)
        self.idle_weather_icon.setVisible(visible)
        self.idle_weather_temp.setVisible(visible)
        self.idle_weather_cond.setVisible(visible)
        if hasattr(self, "idle_sep0"):
            self.idle_sep0.setVisible(visible)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(self.max_boundary_x)

    def set_placement(self, placement: str):
        self.placement = placement
        is_tb = (placement in ("taskbar", "full_taskbar"))
        is_full_tb = (placement == "full_taskbar")
        if hasattr(self, "layout") and self.layout():
            if is_tb:
                self.layout().setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            else:
                self.layout().setAlignment(Qt.AlignmentFlag.AlignCenter)

        for stretch_name in (
            "m_left_stretch", "i_left_stretch", "dl_left_stretch", "g_left_stretch",
            "net_left_stretch", "cpu_ram_left_stretch", "w_left_stretch",
            "date_left_stretch", "notif_left_stretch", "nt_left_stretch",
            "t_left_stretch", "v_left_stretch", "mic_left_stretch", "ba_left_stretch"
        ):
            st = getattr(self, stretch_name, None)
            if st:
                st.setVisible(not is_tb)

        # Media stays completely clean: no weather, no clock, no battery around it
        self.media_weather_widget.setVisible(False)
        self.media_clock_widget.setVisible(False)
        self.media_battery_widget.setVisible(False)
        self.idle_clock_widget.setVisible(True)
        self.idle_battery_widget.setVisible(True)

    def _finish_elastic(self, optimal_w: int) -> int:
        if optimal_w != getattr(self, "_last_elastic_w", -1):
            self._last_elastic_w = optimal_w
            self.elastic_size_requested.emit(optimal_w)
        return optimal_w

    def update_elastic_layout(self, max_boundary_x: int = 505) -> int:
        """
        Dynamically fits elements from left to right.
        Reserves a generous safety buffer before the Start button (max_boundary_x - 36),
        strictly halting any overlap.
        """
        self.max_boundary_x = max_boundary_x
        if getattr(self, "placement", "top") != "full_taskbar":
            return self.width()

        current_widget = self.stack.currentWidget()
        # Safe barrier: reserve 36px buffer before the Start button so it never collides
        safe_max_w = max(200, max_boundary_x - 36)
        self.setFixedWidth(safe_max_w)
        self.stack.setMinimumWidth(0)
        self.stack.setMaximumWidth(safe_max_w)
        self.stack.setFixedWidth(safe_max_w)

        if current_widget == self.media_page or (hasattr(self, "media_page") and self.stack.currentWidget() is None):
            # Clean Media Page: nothing to left or right of media
            self.media_weather_widget.setVisible(False)
            self.media_clock_widget.setVisible(False)
            self.media_battery_widget.setVisible(False)

            pad_left = 10
            pad_right = 10
            spacing = 7
            cur_x = pad_left

            # 1. Thumbnail
            self.thumb_lbl.setVisible(True)
            cur_x += 20 + spacing

            # 2. Equalizer & Play button
            w_eq = 18
            w_play = 16

            fixed_w = cur_x + spacing + w_eq + spacing + w_play + pad_right
            avail_title = max(50, safe_max_w - fixed_w)

            raw_title = getattr(self, "raw_media_title", "") or "Playing Media"
            fm = QFontMetrics(self.title_lbl.font())
            full_title_w = fm.horizontalAdvance(raw_title)

            title_w = min(full_title_w, avail_title)
            elided = fm.elidedText(raw_title, Qt.TextElideMode.ElideRight, title_w)
            self.title_lbl.setText(elided)
            self.title_lbl.setMinimumWidth(0)
            self.title_lbl.setMaximumWidth(title_w)
            return self._finish_elastic(safe_max_w)

        elif current_widget == self.idle_page:
            pad = 12
            spacing = 6
            w_weather = 0
            if getattr(self, "weather_visible", True):
                w_weather = (self.idle_weather_icon.sizeHint().width() +
                             self.idle_weather_temp.sizeHint().width() +
                             self.idle_weather_cond.sizeHint().width() + 14)

            w_clock = self.time_lbl.sizeHint().width() + 12
            w_battery = (self.battery_glyph.width() +
                         self.battery_pct_lbl.sizeHint().width() +
                         self.charge_lbl.sizeHint().width() + 18)

            # Test 1: Full idle fits?
            if (pad + w_weather + spacing + w_clock + spacing + w_battery + pad) <= safe_max_w:
                self.idle_clock_widget.setVisible(True)
                self.idle_battery_widget.setVisible(True)
            # Test 2: Drop battery?
            elif (pad + w_weather + spacing + w_clock + pad) <= safe_max_w:
                self.idle_clock_widget.setVisible(True)
                self.idle_battery_widget.setVisible(False)
            else:
                self.idle_clock_widget.setVisible(False)
                self.idle_battery_widget.setVisible(False)

            return self._finish_elastic(safe_max_w)

        elif current_widget == self.download_page:
            pad_left = 10
            pad_right = 10
            spacing = 6
            cur_x = pad_left

            # 1. Download icon
            cur_x += self.dl_icon.sizeHint().width() + spacing

            # 2. Separator
            w_sep = self.dl_sep.sizeHint().width()

            # 3. Download Info (e.g. "710 MB · 1.5 MB/s") - MUST NEVER BE CROPPED!
            info_txt = getattr(self, "raw_download_info", "") or self.dl_info_lbl.text()
            fm_info = QFontMetrics(self.dl_info_lbl.font())
            w_info = max(self.dl_info_lbl.minimumWidth(), fm_info.horizontalAdvance(info_txt) + 8)
            self.dl_info_lbl.setMinimumWidth(w_info)

            # Fixed space excluding filename
            fixed_w = cur_x + spacing + w_sep + spacing + w_info + pad_right
            avail_name = max(40, safe_max_w - fixed_w)

            # 4. Download Filename (elided cleanly if needed)
            raw_name = getattr(self, "raw_download_filename", "") or self.dl_name_lbl.text()
            fm_name = QFontMetrics(self.dl_name_lbl.font())
            full_name_w = fm_name.horizontalAdvance(raw_name)

            name_w = min(full_name_w, avail_name)
            elided_name = fm_name.elidedText(raw_name, Qt.TextElideMode.ElideRight, name_w)
            self.dl_name_lbl.setText(elided_name)
            self.dl_name_lbl.setMinimumWidth(0)
            self.dl_name_lbl.setMaximumWidth(name_w)
            return self._finish_elastic(safe_max_w)

        elif current_widget == self.mic_page:
            return self._finish_elastic(safe_max_w)

        elif current_widget == self.battery_alert_page:
            return self._finish_elastic(safe_max_w)

        elif current_widget == self.toast_page:
            return self._finish_elastic(safe_max_w)

        elif current_widget == self.volume_page:
            return self._finish_elastic(safe_max_w)

        elif current_widget == self.greeting_page:
            return self._finish_elastic(safe_max_w)

        elif current_widget == getattr(self, "net_speed_page", None):
            return self._finish_elastic(safe_max_w)

        elif current_widget == getattr(self, "cpu_ram_page", None):
            return self._finish_elastic(safe_max_w)

        elif current_widget == getattr(self, "weather_page", None):
            return self._finish_elastic(safe_max_w)

        elif current_widget == getattr(self, "date_page", None):
            return self._finish_elastic(safe_max_w)

        elif current_widget == getattr(self, "notification_page", None):
            return self._finish_elastic(safe_max_w)

        elif current_widget == getattr(self, "notification_toast_page", None):
            pad = 20
            w_icon = 18
            w_app = self.nt_app_lbl.sizeHint().width()
            w_sep = 10
            fixed = pad + w_icon + 6 + w_app + w_sep
            avail_msg = max(80, safe_max_w - fixed)
            fm = QFontMetrics(self.nt_msg_lbl.font())
            raw_msg = self.nt_msg_lbl.text()
            full_msg_w = fm.horizontalAdvance(raw_msg)
            msg_w = min(full_msg_w, avail_msg)
            elided = fm.elidedText(raw_msg, Qt.TextElideMode.ElideRight, msg_w)
            self.nt_msg_lbl.setText(elided)
            self.nt_msg_lbl.setMinimumWidth(0)
            self.nt_msg_lbl.setMaximumWidth(msg_w)
            return self._finish_elastic(safe_max_w)

        return self._finish_elastic(safe_max_w)

    def _tick_clock(self):
        now = datetime.now()
        formatted_time = now.strftime("%I:%M %p").lstrip("0")
        self.time_lbl.setText(formatted_time)
        if hasattr(self, "media_time_lbl"):
            self.media_time_lbl.setText(formatted_time)
        if hasattr(self, "date_day_lbl"):
            self.date_day_lbl.setText(now.strftime("%A"))
            self.date_full_lbl.setText(now.strftime("%d %B"))

    def _on_play_clicked(self):
        if getattr(self, "media_service", None):
            self.media_service.play_pause()
        else:
            w = self.window()
            if hasattr(w, "media_service") and w.media_service:
                w.media_service.play_pause()

    def _fade_to_page(self, widget):
        if self.stack.currentWidget() == widget:
            return
        self.stack.setCurrentWidget(widget)
        if hasattr(self, "_fade_anim") and hasattr(self, "_fade_effect"):
            self._fade_anim.stop()
            self._fade_anim.setStartValue(0.25)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()

    def show_media(self, display_text: str, thumb_bytes: bytes, is_playing: bool):
        self.media_weather_widget.setVisible(False)
        self.media_clock_widget.setVisible(False)
        self.media_battery_widget.setVisible(False)
        self.raw_media_title = display_text or "Playing Media"

        if getattr(self, "placement", "top") == "full_taskbar":
            self.title_lbl.setText(self.raw_media_title)
        else:
            if len(self.raw_media_title) > 34:
                self.title_lbl.setText(self.raw_media_title[:31] + "...")
            else:
                self.title_lbl.setText(self.raw_media_title)

        if thumb_bytes:
            pix = QPixmap()
            pix.loadFromData(thumb_bytes)
            scaled = pix.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.thumb_lbl.setPixmap(scaled)
        else:
            self.thumb_lbl.setText("🎵")
            self.thumb_lbl.setStyleSheet("background: #222228; border-radius: 4px; font-size: 11px;")

        self.eq_bars.set_playing(is_playing)
        if hasattr(self, "media_play_btn"):
            self.media_play_btn.setText("⏸" if is_playing else "▶")

        self._fade_to_page(self.media_page)

        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def show_toast(self, icon: str, text: str):
        self.toast_icon.setText(icon)
        self.toast_text.setText(text)
        self._fade_to_page(self.toast_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def show_idle(self):
        self._tick_clock()
        self._fade_to_page(self.idle_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def show_download(self, filename: str, size_mb: float, speed_str: str):
        self.raw_download_filename = filename
        self.raw_download_info = f"{size_mb} MB · {speed_str}"
        self.dl_name_lbl.setText(filename)
        self.dl_info_lbl.setText(self.raw_download_info)
        fm_info = QFontMetrics(self.dl_info_lbl.font())
        w_info = fm_info.horizontalAdvance(self.raw_download_info) + 8
        self.dl_info_lbl.setMinimumWidth(w_info)
        self._fade_to_page(self.download_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def show_mic_status(self, app: str):
        self.mic_text_lbl.setText(f"Mic Active · {app}" if app else "Microphone Active")
        self._fade_to_page(self.mic_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def show_battery_alert(self, title: str, is_charging: bool, pct: int):
        self.ba_icon.setText("⚡" if is_charging else "🪫")
        self.ba_text_lbl.setText(f"{title} · {pct}%")
        self._fade_to_page(self.battery_alert_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def show_volume(self, pct: int, is_muted: bool, accent_color: QColor = None):
        if is_muted or pct == 0:
            self.vol_icon.setText("🔇")
            self.vol_pct_lbl.setText("Muted")
        elif pct <= 33:
            self.vol_icon.setText("🔈")
            self.vol_pct_lbl.setText(f"{pct}%")
        elif pct <= 66:
            self.vol_icon.setText("🔉")
            self.vol_pct_lbl.setText(f"{pct}%")
        else:
            self.vol_icon.setText("🔊")
            self.vol_pct_lbl.setText(f"{pct}%")

        self.vol_bar.set_volume(0 if is_muted else pct, accent_color or QColor(255, 255, 255))
        self._fade_to_page(self.volume_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def update_battery(self, pct: int, is_charging: bool):
        self.battery_glyph.update_battery(pct, is_charging)
        self.battery_pct_lbl.setText(str(pct))
        self.charge_lbl.setVisible(is_charging)

        if hasattr(self, "media_battery_glyph"):
            self.media_battery_glyph.update_battery(pct, is_charging)
            self.media_battery_pct_lbl.setText(str(pct))
            self.media_charge_lbl.setVisible(is_charging)

    def show_greeting(self, text: str):
        self.greeting_lbl.setText(text)
        if self.stack.currentWidget() != self.greeting_page:
            self.stack.setCurrentWidget(self.greeting_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def show_net_speed(self, down_str: str, up_str: str):
        self.update_net_speed_data(down_str, up_str)
        self._fade_to_page(self.net_speed_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def update_net_speed_data(self, down_str: str, up_str: str):
        if hasattr(self, "net_down_lbl"):
            self.net_down_lbl.setText(down_str or "0 KB/s")
            self.net_up_lbl.setText(up_str or "0 KB/s")

    def show_cpu_ram(self, cpu_pct: int, ram_pct: int):
        self.update_cpu_ram_data(cpu_pct, ram_pct)
        self._fade_to_page(self.cpu_ram_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def update_cpu_ram_data(self, cpu_pct: int, ram_pct: int):
        if hasattr(self, "cpu_lbl"):
            self.cpu_lbl.setText(f"CPU {int(cpu_pct)}%")
            self.ram_lbl.setText(f"RAM {int(ram_pct)}%")

    def show_weather_page(self, temp_str: str, cond_str: str, icon_str: str):
        if hasattr(self, "w_temp_lbl"):
            self.w_temp_lbl.setText(temp_str or "22°C")
            self.w_cond_lbl.setText(cond_str or "Partly cloudy")
            self.w_icon_lbl.setText(icon_str or "🌙☁️")
        self._fade_to_page(self.weather_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def update_weather_page_data(self, data: dict):
        if hasattr(self, "w_temp_lbl") and data:
            self.w_temp_lbl.setText(data.get("temp_str", "22°C"))
            self.w_cond_lbl.setText(data.get("condition", "Partly cloudy"))
            self.w_icon_lbl.setText(data.get("icon", "🌙☁️"))

    def show_date_page(self):
        self._tick_clock()
        self._fade_to_page(self.date_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def show_notification_page(self, count: int, display_text: str):
        self.update_notification_data(count, display_text)
        self._fade_to_page(self.notification_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))

    def update_notification_data(self, count: int, display_text: str):
        if hasattr(self, "notif_text_lbl"):
            if count > 0:
                self.notif_text_lbl.setText(f"{count} Unread")
            else:
                self.notif_text_lbl.setText("No notifications")

    def show_notification_toast(self, app: str, message: str, icon: str = "💬"):
        self.nt_icon_lbl.setText(icon or "💬")
        self.nt_app_lbl.setText(app or "Notification")
        self.nt_msg_lbl.setText(message or "")
        self._fade_to_page(self.notification_toast_page)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(getattr(self, "max_boundary_x", 505))
