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
        if ev.type() == QEvent.Type.MouseButtonPress:
            if ev.button() == Qt.MouseButton.LeftButton:
                if getattr(obj, "_is_interactive_control", False):
                    return False
                notch = self.compact_bar.window()
                if hasattr(notch, "expand_dashboard"):
                    notch.expand_dashboard()
                    return True
        return False

class CompactBar(QWidget):
    elastic_size_requested = Signal(int)

    def __init__(self, parent=None, weather_service=None, media_service=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.weather_service = weather_service
        self.media_service = media_service
        self.placement = "top"
        self.weather_visible = True
        self.raw_media_title = ""
        self.max_boundary_x = 505

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget(self)

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
        t_layout.setContentsMargins(4, 0, 4, 0)
        t_layout.setSpacing(6)
        t_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)

        self.toast_icon = QLabel("📋")
        self.toast_icon.setStyleSheet("font-size: 13px; background: transparent;")
        self.toast_text = QLabel("Copied · Image")
        self.toast_text.setStyleSheet("""
            color: #ffffff;
            font-size: 11px;
            font-weight: 700;
            background: transparent;
        """)

        t_layout.addStretch()
        t_layout.addWidget(self.toast_icon)
        t_layout.addWidget(self.toast_text)
        t_layout.addStretch()
        self.stack.addWidget(self.toast_page)

        # -------------------------------------------------------------
        # 3. Idle Page (🌙☁️ 22°C Partly cloudy | 10:02 PM | ⚡ [battery] 89)
        # -------------------------------------------------------------
        self.idle_page = QWidget()
        i_layout = QHBoxLayout(self.idle_page)
        i_layout.setContentsMargins(12, 0, 12, 0)
        i_layout.setSpacing(6)
        i_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Left stretch for centering in Top / Pill mode; hidden in Full Taskbar mode
        self.i_left_stretch = QWidget()
        self.i_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
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
        v_layout.setContentsMargins(6, 0, 6, 0)
        v_layout.setSpacing(8)
        v_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)

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

        v_layout.addStretch()
        v_layout.addWidget(self.vol_icon)
        v_layout.addWidget(self.vol_bar)
        v_layout.addWidget(self.vol_pct_lbl)
        v_layout.addStretch()
        self.stack.addWidget(self.volume_page)

        # -------------------------------------------------------------
        # 5. Download HUD Page (📥 filename.zip | 12 MB · 1.5 MB/s)
        # -------------------------------------------------------------
        self.download_page = QWidget()
        dl_layout = QHBoxLayout(self.download_page)
        dl_layout.setContentsMargins(10, 0, 10, 0)
        dl_layout.setSpacing(7)
        dl_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)

        self.dl_icon = QLabel("📥")
        self.dl_icon.setStyleSheet("font-size: 13px; background: transparent;")

        self.dl_name_lbl = QLabel("Downloading")
        self.dl_name_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        self.dl_sep = QLabel("|")
        self.dl_sep.setStyleSheet("color: #4a4a54; font-size: 11px; font-weight: 500;")

        self.dl_info_lbl = QLabel("0 MB/s")
        self.dl_info_lbl.setStyleSheet("color: #00d2ff; font-size: 11px; font-weight: 600; background: transparent;")

        dl_layout.addStretch()
        dl_layout.addWidget(self.dl_icon)
        dl_layout.addWidget(self.dl_name_lbl)
        dl_layout.addWidget(self.dl_sep)
        dl_layout.addWidget(self.dl_info_lbl)
        dl_layout.addStretch()
        self.stack.addWidget(self.download_page)

        # -------------------------------------------------------------
        # 6. Microphone HUD Page (🎙️ Microphone Active · Chrome)
        # -------------------------------------------------------------
        self.mic_page = QWidget()
        mic_layout = QHBoxLayout(self.mic_page)
        mic_layout.setContentsMargins(10, 0, 10, 0)
        mic_layout.setSpacing(6)
        mic_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)

        self.mic_dot = QLabel("●")
        self.mic_dot.setStyleSheet("color: #00d2ff; font-size: 9px; background: transparent;")

        self.mic_icon = QLabel("🎙️")
        self.mic_icon.setStyleSheet("font-size: 12px; background: transparent;")

        self.mic_text_lbl = QLabel("Microphone Active")
        self.mic_text_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        mic_layout.addStretch()
        mic_layout.addWidget(self.mic_dot)
        mic_layout.addWidget(self.mic_icon)
        mic_layout.addWidget(self.mic_text_lbl)
        mic_layout.addStretch()
        self.stack.addWidget(self.mic_page)

        # -------------------------------------------------------------
        # 7. Battery Alert Page (⚡ Charger Connected · 85%)
        # -------------------------------------------------------------
        self.battery_alert_page = QWidget()
        ba_layout = QHBoxLayout(self.battery_alert_page)
        ba_layout.setContentsMargins(10, 0, 10, 0)
        ba_layout.setSpacing(6)
        ba_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)

        self.ba_icon = QLabel("⚡")
        self.ba_icon.setStyleSheet("font-size: 13px; background: transparent;")

        self.ba_text_lbl = QLabel("Charger Connected")
        self.ba_text_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 600; background: transparent;")

        ba_layout.addStretch()
        ba_layout.addWidget(self.ba_icon)
        ba_layout.addWidget(self.ba_text_lbl)
        ba_layout.addStretch()
        self.stack.addWidget(self.battery_alert_page)

        # -------------------------------------------------------------
        # 8. Apple-style Cursive Greeting Page ("Good morning", etc.)
        # -------------------------------------------------------------
        self.greeting_page = QWidget()
        g_layout = QHBoxLayout(self.greeting_page)
        g_layout.setContentsMargins(14, 0, 14, 0)
        g_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Left stretch: active in Top / Pill mode; hidden in Full Taskbar mode to flow left-to-right!
        self.g_left_stretch = QWidget()
        self.g_left_stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
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

        layout.addWidget(self.stack)

        # Install click redirector on stack and all children so clicking ANY pixel opens dashboard
        self._click_filter = CompactClickRedirector(self)
        self.installEventFilter(self._click_filter)
        self.stack.installEventFilter(self._click_filter)
        for child in self.findChildren(QWidget):
            child.setCursor(Qt.CursorShape.PointingHandCursor)
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

    def update_weather(self, data: dict):
        self.current_weather_data = data
        icon = data.get("icon", "🌙☁️")
        temp = data.get("temp_str", "21°C")
        cond = data.get("condition", "Partly cloudy")
        humid = data.get("humidity_desc", "Humid")

        self.idle_weather_icon.setText(icon)
        self.idle_weather_temp.setText(temp)
        self.idle_weather_cond.setText(f"{cond} · {humid}" if humid else cond)

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
        self.media_weather_widget.setVisible(visible)
        self.idle_weather_icon.setVisible(visible)
        self.idle_weather_temp.setVisible(visible)
        self.idle_weather_cond.setVisible(visible)
        if hasattr(self, "idle_sep0"):
            self.idle_sep0.setVisible(visible)
        if getattr(self, "placement", "top") == "full_taskbar":
            self.update_elastic_layout(self.max_boundary_x)

    def set_placement(self, placement: str):
        if getattr(self, "placement", None) == placement:
            return
        self.placement = placement
        is_full_tb = (placement == "full_taskbar")
        self.m_left_stretch.setVisible(not is_full_tb)
        self.i_left_stretch.setVisible(not is_full_tb)
        if hasattr(self, "g_left_stretch"):
            self.g_left_stretch.setVisible(not is_full_tb)
        if not is_full_tb:
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
        If something strikes the Start button boundary, removes/halts it so it fits
        whatever can fit cleanly without any collision.
        Returns the optimal elastic width for the window.
        """
        self.max_boundary_x = max_boundary_x
        if getattr(self, "placement", "top") != "full_taskbar":
            return self.width()

        current_widget = self.stack.currentWidget()
        # Safe barrier: reserve 14px before the Start button so it never collides
        safe_max_w = max(240, max_boundary_x - 14)

        if current_widget == self.media_page or (hasattr(self, "media_page") and self.stack.currentWidget() is None):
            pad_left = 10
            spacing = 7
            cur_x = pad_left

            # 1. Weather badge
            if getattr(self, "weather_visible", True):
                self.media_weather_widget.setVisible(True)
                cur_x += self.media_weather_widget.sizeHint().width() + spacing
            else:
                self.media_weather_widget.setVisible(False)

            # 2. Thumbnail
            self.thumb_lbl.setVisible(True)
            cur_x += 20 + spacing

            # 3. Equalizer width
            w_eq = 18

            # Measurements for Clock and Battery
            w_clock = self.media_clock_widget.sizeHint().width()
            w_battery = self.media_battery_widget.sizeHint().width()

            raw_title = getattr(self, "raw_media_title", "") or "Playing Media"
            fm = QFontMetrics(self.title_lbl.font())
            full_title_w = fm.horizontalAdvance(raw_title)

            MIN_TITLE_W = 95
            PREF_TITLE_W = 160

            # Test 1: Does (Title >= PREF_TITLE_W + EQ + Clock + Battery) fit within safe_max_w?
            space_with_both = cur_x + min(full_title_w, PREF_TITLE_W) + spacing + w_eq + spacing + w_clock + spacing + w_battery + 12
            if space_with_both <= safe_max_w:
                self.media_clock_widget.setVisible(True)
                self.media_battery_widget.setVisible(True)

                # Title can expand further if extra space is available
                fixed_rest = cur_x + spacing + w_eq + spacing + w_clock + spacing + w_battery + 12
                avail_title = max(MIN_TITLE_W, safe_max_w - fixed_rest)
                title_w = min(full_title_w, avail_title)
                elided = fm.elidedText(raw_title, Qt.TextElideMode.ElideRight, title_w)
                self.title_lbl.setText(elided)

                optimal_w = cur_x + title_w + spacing + w_eq + spacing + w_clock + spacing + w_battery + 12
                optimal_w = min(optimal_w, safe_max_w)
                return self._finish_elastic(optimal_w)

            # Test 2: Battery strikes Start button! Remove & halt Battery.
            # Does (Title >= MIN_TITLE_W + EQ + Clock) fit?
            space_with_clock = cur_x + min(full_title_w, MIN_TITLE_W) + spacing + w_eq + spacing + w_clock + 12
            if space_with_clock <= safe_max_w:
                self.media_clock_widget.setVisible(True)
                self.media_battery_widget.setVisible(False)

                fixed_rest = cur_x + spacing + w_eq + spacing + w_clock + 12
                avail_title = max(MIN_TITLE_W, safe_max_w - fixed_rest)
                title_w = min(full_title_w, avail_title)
                elided = fm.elidedText(raw_title, Qt.TextElideMode.ElideRight, title_w)
                self.title_lbl.setText(elided)

                optimal_w = cur_x + title_w + spacing + w_eq + spacing + w_clock + 12
                optimal_w = min(optimal_w, safe_max_w)
                return self._finish_elastic(optimal_w)

            # Test 3: Clock also strikes Start button! Remove & halt Clock too!
            # Title gets available space, truncated with ellipsis before Start button
            self.media_clock_widget.setVisible(False)
            self.media_battery_widget.setVisible(False)

            fixed_rest = cur_x + spacing + w_eq + 12
            avail_title = max(50, safe_max_w - fixed_rest)
            title_w = min(full_title_w, avail_title)
            elided = fm.elidedText(raw_title, Qt.TextElideMode.ElideRight, title_w)
            self.title_lbl.setText(elided)

            optimal_w = cur_x + title_w + spacing + w_eq + 12
            optimal_w = min(optimal_w, safe_max_w)
            return self._finish_elastic(optimal_w)

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
                optimal_w = min(pad + w_weather + spacing + w_clock + spacing + w_battery + pad, safe_max_w)
                return self._finish_elastic(optimal_w)
            # Test 2: Drop battery?
            elif (pad + w_weather + spacing + w_clock + pad) <= safe_max_w:
                self.idle_clock_widget.setVisible(True)
                self.idle_battery_widget.setVisible(False)
                optimal_w = min(pad + w_weather + spacing + w_clock + pad, safe_max_w)
                return self._finish_elastic(optimal_w)
            else:
                self.idle_clock_widget.setVisible(False)
                self.idle_battery_widget.setVisible(False)
                optimal_w = min(pad + w_weather + pad, safe_max_w)
                return self._finish_elastic(optimal_w)

        elif current_widget == self.download_page:
            w_dl = 26 + self.dl_name_lbl.sizeHint().width() + 12 + self.dl_info_lbl.sizeHint().width() + 24
            return self._finish_elastic(min(w_dl, safe_max_w))

        elif current_widget == self.mic_page:
            w_mic = 32 + self.mic_text_lbl.sizeHint().width() + 24
            return self._finish_elastic(min(w_mic, safe_max_w))

        elif current_widget == self.battery_alert_page:
            w_ba = 26 + self.ba_text_lbl.sizeHint().width() + 24
            return self._finish_elastic(min(w_ba, safe_max_w))

        elif current_widget == self.toast_page:
            w_toast = 24 + self.toast_text.sizeHint().width() + 24
            return self._finish_elastic(min(w_toast, safe_max_w))

        elif current_widget == self.volume_page:
            return self._finish_elastic(min(260, safe_max_w))

        elif current_widget == self.greeting_page:
            return self._finish_elastic(safe_max_w)

        return self._finish_elastic(safe_max_w)

    def _tick_clock(self):
        now = datetime.now()
        formatted_time = now.strftime("%I:%M %p").lstrip("0")
        self.time_lbl.setText(formatted_time)
        if hasattr(self, "media_time_lbl"):
            self.media_time_lbl.setText(formatted_time)

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
        self.dl_name_lbl.setText(filename)
        self.dl_info_lbl.setText(f"{size_mb} MB · {speed_str}")
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
