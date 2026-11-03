from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSlider, QScrollArea
)

COLOR_PALETTE = [
    ("#ffffff", "White"),
    ("#facc15", "Yellow"),
    ("#f97316", "Orange"),
    ("#10b981", "Mint"),
    ("#06b6d4", "Cyan"),
    ("#3b82f6", "Blue"),
    ("#8b5cf6", "Violet"),
    ("#d946ef", "Purple"),
    ("#f43f5e", "Pink"),
    ("#fb923c", "Coral"),
    ("#38bdf8", "Sky")
]

class AppearanceSettingsWidget(QWidget):
    def __init__(self, settings_service, parent=None):
        super().__init__(parent)
        self.settings_service = settings_service
        self._init_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 12, 18, 16)
        layout.setSpacing(14)

        # -------------------------------------------------------------
        # SECTION 1: EDGE LIGHT (Screenshot 1)
        # -------------------------------------------------------------
        el_header = QHBoxLayout()
        el_title_v = QVBoxLayout()
        el_title_v.setSpacing(2)
        el_title = QLabel("Edge light")
        el_title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 700;")
        el_sub = QLabel("Light that runs along the notch outline")
        el_sub.setStyleSheet("color: #8e8e93; font-size: 11px;")
        el_title_v.addWidget(el_title)
        el_title_v.addWidget(el_sub)

        el_toggle = self._create_toggle_button(
            self.settings_service.get("edge_light_enabled", True),
            lambda v: self.settings_service.set("edge_light_enabled", v)
        )
        el_header.addLayout(el_title_v)
        el_header.addStretch()
        el_header.addWidget(el_toggle)
        layout.addLayout(el_header)

        # 3 Effect Cards: Comet | Twin comets | Breathe
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        effects = [
            ("Comet", "One light travels along the outline", "comet"),
            ("Twin comets", "Two lights meet at the bottom, then return", "twin_comets"),
            ("Breathe", "The whole outline glows softly", "breathe")
        ]

        self.effect_cards = {}
        curr_effect = self.settings_service.get("edge_light_effect", "twin_comets")

        for title, desc, key in effects:
            card = QPushButton()
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setFixedHeight(95)
            c_v = QVBoxLayout(card)
            c_v.setContentsMargins(10, 8, 10, 8)
            c_v.setSpacing(3)

            t_lbl = QLabel(title)
            t_lbl.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 700; background: transparent;")
            d_lbl = QLabel(desc)
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet("color: #8e8e93; font-size: 10px; background: transparent;")

            c_v.addStretch()
            c_v.addWidget(t_lbl)
            c_v.addWidget(d_lbl)

            card.clicked.connect(lambda _, k=key: self._select_effect(k))
            self.effect_cards[key] = card
            cards_layout.addWidget(card)

        self._update_effect_cards(curr_effect)
        layout.addLayout(cards_layout)

        # Match Music Cover Option
        music_color_row = QHBoxLayout()
        mc_v = QVBoxLayout()
        mc_v.setSpacing(2)
        mc_title = QLabel("🎵  Match Music Cover Art")
        mc_title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600;")
        mc_sub = QLabel("Automatically adapt edge light and glow to currently playing album artwork")
        mc_sub.setStyleSheet("color: #8e8e93; font-size: 10px;")
        mc_v.addWidget(mc_title)
        mc_v.addWidget(mc_sub)

        is_match = self.settings_service.get("match_music_color", False)
        self.mc_toggle = self._create_toggle_button(
            is_match,
            self._on_toggle_match_music
        )
        music_color_row.addLayout(mc_v)
        music_color_row.addStretch()
        music_color_row.addWidget(self.mc_toggle)
        layout.addLayout(music_color_row)

        # Color Palette Row
        color_row = QHBoxLayout()
        color_lbl = QLabel("Color")
        color_lbl.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600; min-width: 50px;")
        color_row.addWidget(color_lbl)

        palette_layout = QHBoxLayout()
        palette_layout.setSpacing(6)
        curr_color = self.settings_service.get("edge_light_color", "#ffffff").lower()

        self.color_swatches = {}
        for hex_code, name in COLOR_PALETTE:
            swatch = QPushButton()
            swatch.setFixedSize(22, 22)
            swatch.setToolTip(name)
            swatch.setCursor(Qt.CursorShape.PointingHandCursor)
            is_active = (hex_code == curr_color and not is_match)
            self._style_swatch(swatch, hex_code, is_active)
            swatch.clicked.connect(lambda _, h=hex_code: self._select_color(h))
            self.color_swatches[hex_code] = swatch
            palette_layout.addWidget(swatch)

        palette_layout.addStretch()
        color_row.addLayout(palette_layout)
        layout.addLayout(color_row)

        # Intensity Slider (Screenshot 1)
        int_row = QHBoxLayout()
        int_lbl = QLabel("Intensity")
        int_lbl.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600; min-width: 60px;")
        
        curr_int = self.settings_service.get("edge_light_intensity", 80)
        self.int_val_lbl = QLabel(f"{curr_int}%")
        self.int_val_lbl.setStyleSheet("color: #8e8e93; font-size: 11px; min-width: 35px;")

        self.int_slider = QSlider(Qt.Orientation.Horizontal)
        self.int_slider.setRange(20, 100)
        self.int_slider.setValue(curr_int)
        self.int_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #2a2a30; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #ffffff; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ffffff; width: 14px; margin-top: -5px; margin-bottom: -5px; border-radius: 7px; }
        """)
        self.int_slider.valueChanged.connect(self._on_intensity_change)

        int_row.addWidget(int_lbl)
        int_row.addWidget(self.int_val_lbl)
        int_row.addWidget(self.int_slider)
        layout.addLayout(int_row)

        # Speed (Screenshot 1)
        speed_row = QHBoxLayout()
        sp_lbl = QLabel("Speed")
        sp_lbl.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600; min-width: 60px;")
        
        sp_seg = self._create_segmented(
            ["Slow", "Normal", "Fast"],
            self.settings_service.get("edge_light_speed", "normal").capitalize(),
            lambda v: self.settings_service.set("edge_light_speed", v.lower())
        )
        speed_row.addWidget(sp_lbl)
        speed_row.addStretch()
        speed_row.addWidget(sp_seg)
        layout.addLayout(speed_row)

        # -------------------------------------------------------------
        # SECTION 2: STYLE & SHAPE (Screenshot 2)
        # -------------------------------------------------------------
        sep1 = QFrame()
        sep1.setStyleSheet("background: rgba(255, 255, 255, 0.08); max-height: 1px;")
        layout.addWidget(sep1)

        style_lbl = QLabel("STYLE")
        style_lbl.setStyleSheet("color: #6e6e73; font-size: 11px; font-weight: 700; letter-spacing: 0.8px;")
        layout.addWidget(style_lbl)

        styles_layout = QHBoxLayout()
        styles_layout.setSpacing(10)
        styles_def = [
            ("Notch", "Grows out of the screen edge", "notch"),
            ("Island", "A pill floating just below the edge", "island"),
            ("Line", "A slim bar along the top edge", "line")
        ]

        self.style_cards = {}
        curr_style = self.settings_service.get("notch_style", "notch")

        for title, desc, key in styles_def:
            card = QPushButton()
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setFixedHeight(80)
            c_v = QVBoxLayout(card)
            c_v.setContentsMargins(10, 8, 10, 8)
            c_v.setSpacing(2)

            t_lbl = QLabel(title)
            t_lbl.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 700; background: transparent;")
            d_lbl = QLabel(desc)
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet("color: #8e8e93; font-size: 10px; background: transparent;")

            c_v.addStretch()
            c_v.addWidget(t_lbl)
            c_v.addWidget(d_lbl)

            card.clicked.connect(lambda _, k=key: self._select_style(k))
            self.style_cards[key] = card
            styles_layout.addWidget(card)

        self._update_style_cards(curr_style)
        layout.addLayout(styles_layout)

        # Size Scale Slider (Screenshots 2 & 3)
        size_row = QHBoxLayout()
        sz_v = QVBoxLayout()
        sz_v.setSpacing(2)
        sz_title = QLabel("Size")
        sz_title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600;")
        sz_sub = QLabel("Scales the resting notch")
        sz_sub.setStyleSheet("color: #8e8e93; font-size: 10px;")
        sz_v.addWidget(sz_title)
        sz_v.addWidget(sz_sub)

        curr_scale = self.settings_service.get("notch_scale", 90)
        self.scale_val_lbl = QLabel(f"{curr_scale}%")
        self.scale_val_lbl.setStyleSheet("color: #8e8e93; font-size: 11px; min-width: 35px;")

        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(70, 130)
        self.scale_slider.setValue(curr_scale)
        self.scale_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #2a2a30; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #ffffff; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ffffff; width: 14px; margin-top: -5px; margin-bottom: -5px; border-radius: 7px; }
        """)
        self.scale_slider.valueChanged.connect(self._on_scale_change)

        size_row.addLayout(sz_v)
        size_row.addWidget(self.scale_val_lbl)
        size_row.addWidget(self.scale_slider)
        layout.addLayout(size_row)

        # Glass Transparency Slider (0 to 100)
        glass_row = QHBoxLayout()
        gt_v = QVBoxLayout()
        gt_v.setSpacing(2)
        gt_title = QLabel("Glass transparency")
        gt_title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600;")
        gt_sub = QLabel("Edge-to-center glass transparency and refraction")
        gt_sub.setStyleSheet("color: #8e8e93; font-size: 10px;")
        gt_v.addWidget(gt_title)
        gt_v.addWidget(gt_sub)

        curr_trans = self.settings_service.get("glass_transparency", 0)
        self.trans_val_lbl = QLabel(f"{curr_trans}%")
        self.trans_val_lbl.setStyleSheet("color: #8e8e93; font-size: 11px; min-width: 35px;")

        self.trans_slider = QSlider(Qt.Orientation.Horizontal)
        self.trans_slider.setRange(0, 100)
        self.trans_slider.setValue(curr_trans)
        self.trans_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #2a2a30; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #ffffff; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ffffff; width: 14px; margin-top: -5px; margin-bottom: -5px; border-radius: 7px; }
        """)
        self.trans_slider.valueChanged.connect(self._on_trans_change)

        glass_row.addLayout(gt_v)
        glass_row.addWidget(self.trans_val_lbl)
        glass_row.addWidget(self.trans_slider)
        layout.addLayout(glass_row)

        # Placement (Top Bezel vs Bottom Taskbar Pill vs Full Taskbar)
        place_row = QHBoxLayout()
        pl_v = QVBoxLayout()
        pl_v.setSpacing(2)
        pl_title = QLabel("Placement")
        pl_title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600;")
        pl_sub = QLabel("Top bezel, Taskbar pill, or Full Taskbar (without pill)")
        pl_sub.setStyleSheet("color: #8e8e93; font-size: 10px;")
        pl_v.addWidget(pl_title)
        pl_v.addWidget(pl_sub)

        raw_place = self.settings_service.get("placement", "full_taskbar")
        place_map = {"top": "Top", "taskbar": "Taskbar Pill", "full_taskbar": "Full Taskbar"}
        curr_place = place_map.get(raw_place, "Full Taskbar")
        pl_seg = self._create_segmented(
            ["Top", "Taskbar Pill", "Full Taskbar"],
            curr_place,
            self._on_placement_change
        )
        place_row.addLayout(pl_v)
        place_row.addStretch()
        place_row.addWidget(pl_seg)
        layout.addLayout(place_row)

        # Taskbar X Offset Slider (shown when Taskbar Pill is active)
        self.tb_offset_widget = QWidget()
        tb_layout = QHBoxLayout(self.tb_offset_widget)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(10)
        tb_v = QVBoxLayout()
        tb_v.setSpacing(2)
        tb_title = QLabel("Taskbar horizontal position")
        tb_title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600;")
        tb_sub = QLabel("Position notch pill to integrate and utilize the taskbar weather section")
        tb_sub.setStyleSheet("color: #8e8e93; font-size: 10px;")
        tb_v.addWidget(tb_title)
        tb_v.addWidget(tb_sub)

        curr_offset = self.settings_service.get("taskbar_x_offset", 250)
        self.tb_offset_lbl = QLabel(f"{curr_offset}px")
        self.tb_offset_lbl.setStyleSheet("color: #8e8e93; font-size: 11px; min-width: 45px;")

        self.tb_slider = QSlider(Qt.Orientation.Horizontal)
        self.tb_slider.setRange(80, 650)
        self.tb_slider.setValue(curr_offset)
        self.tb_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #2a2a30; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #ffffff; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ffffff; width: 14px; margin-top: -5px; margin-bottom: -5px; border-radius: 7px; }
        """)
        self.tb_slider.valueChanged.connect(self._on_taskbar_offset_change)

        tb_layout.addLayout(tb_v)
        tb_layout.addWidget(self.tb_offset_lbl)
        tb_layout.addWidget(self.tb_slider)
        layout.addWidget(self.tb_offset_widget)

        self.tb_offset_widget.setVisible(raw_place == "taskbar")

        # Full Taskbar Width Slider (shown when Full Taskbar is active)
        self.full_tb_width_widget = QWidget()
        fw_layout = QHBoxLayout(self.full_tb_width_widget)
        fw_layout.setContentsMargins(0, 0, 0, 0)
        fw_layout.setSpacing(10)
        fw_v = QVBoxLayout()
        fw_v.setSpacing(2)
        fw_title = QLabel("Start button position (Taskbar limit)")
        fw_title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600;")
        fw_sub = QLabel("Defines Start button barrier. Bar elastically adapts from left & halts items before colliding.")
        fw_sub.setStyleSheet("color: #8e8e93; font-size: 10px;")
        fw_v.addWidget(fw_title)
        fw_v.addWidget(fw_sub)

        curr_fw = self.settings_service.get("full_taskbar_width", 505)
        self.full_tb_width_lbl = QLabel(f"{curr_fw}px")
        self.full_tb_width_lbl.setStyleSheet("color: #8e8e93; font-size: 11px; min-width: 45px;")

        self.full_tb_slider = QSlider(Qt.Orientation.Horizontal)
        self.full_tb_slider.setRange(350, 750)
        self.full_tb_slider.setValue(curr_fw)
        self.full_tb_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #2a2a30; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #ffffff; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ffffff; width: 14px; margin-top: -5px; margin-bottom: -5px; border-radius: 7px; }
        """)
        self.full_tb_slider.valueChanged.connect(self._on_full_tb_width_change)

        fw_layout.addLayout(fw_v)
        fw_layout.addWidget(self.full_tb_width_lbl)
        fw_layout.addWidget(self.full_tb_slider)
        layout.addWidget(self.full_tb_width_widget)

        self.full_tb_width_widget.setVisible(raw_place == "full_taskbar")

        # Show Weather in Notch (Integrate cloud part into pill)
        weather_row = QHBoxLayout()
        w_v = QVBoxLayout()
        w_v.setSpacing(2)
        w_title = QLabel("Show Weather in pill")
        w_title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600;")
        w_sub = QLabel("Integrate cloud icon & temperature directly into the notch pill")
        w_sub.setStyleSheet("color: #8e8e93; font-size: 10px;")
        w_v.addWidget(w_title)
        w_v.addWidget(w_sub)

        w_sw = self._create_toggle_button(
            self.settings_service.get("weather_enabled", True),
            self._on_weather_toggle
        )
        weather_row.addLayout(w_v)
        weather_row.addStretch()
        weather_row.addWidget(w_sw)
        layout.addLayout(weather_row)

        # Weather Tip for Windows Taskbar
        self.w_tip_lbl = QLabel("💡 Tip: To hide Windows' duplicate weather widget, open Windows Settings > Personalization > Taskbar and turn off 'Widgets'.")
        self.w_tip_lbl.setWordWrap(True)
        self.w_tip_lbl.setStyleSheet("color: #7a7a88; font-size: 10px; font-style: italic; margin-top: -2px; margin-bottom: 6px;")
        layout.addWidget(self.w_tip_lbl)

        # Opens on (Screenshot 3)
        open_row = QHBoxLayout()
        op_title = QLabel("Opens on")
        op_title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 600;")
        op_sub = QLabel("Hover to open at once, or click on purpose")
        op_sub.setStyleSheet("color: #8e8e93; font-size: 10px;")
        op_v = QVBoxLayout()
        op_v.setSpacing(2)
        op_v.addWidget(op_title)
        op_v.addWidget(op_sub)

        op_seg = self._create_segmented(
            ["Hover", "Click"],
            self.settings_service.get("opens_on", "click").capitalize(),
            lambda v: self.settings_service.set("opens_on", v.lower())
        )
        open_row.addLayout(op_v)
        open_row.addStretch()
        open_row.addWidget(op_seg)
        layout.addLayout(open_row)

        scroll.setWidget(content)
        root_layout.addWidget(scroll)

    def _create_toggle_button(self, initial, on_toggle):
        btn = QPushButton("ON" if initial else "OFF")
        btn.setFixedSize(52, 26)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_toggle(btn, initial)

        def click():
            new_state = btn.text() == "OFF"
            btn.setText("ON" if new_state else "OFF")
            self._style_toggle(btn, new_state)
            on_toggle(new_state)

        btn.clicked.connect(click)
        return btn

    def _style_toggle(self, btn, is_on):
        if is_on:
            btn.setStyleSheet("""
                QPushButton {
                    background: #ffffff;
                    color: #000000;
                    border-radius: 13px;
                    font-size: 11px;
                    font-weight: 800;
                    border: none;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: #2a2a2e;
                    color: #8e8e93;
                    border-radius: 13px;
                    font-size: 11px;
                    font-weight: 700;
                    border: none;
                }
            """)

    def _create_segmented(self, options, current, on_change):
        container = QFrame()
        container.setStyleSheet("background: #1c1c1f; border-radius: 8px; padding: 2px;")
        c_layout = QHBoxLayout(container)
        c_layout.setContentsMargins(2, 2, 2, 2)
        c_layout.setSpacing(2)

        buttons = {}
        for opt in options:
            b = QPushButton(opt)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(26)
            buttons[opt] = b
            c_layout.addWidget(b)

        def refresh(selected):
            for opt, b in buttons.items():
                if opt == selected:
                    b.setStyleSheet("background: #323238; color: #ffffff; font-size: 11px; font-weight: 700; border-radius: 6px; border: none; padding: 0 10px;")
                else:
                    b.setStyleSheet("background: transparent; color: #8e8e93; font-size: 11px; font-weight: 500; border-radius: 6px; border: none; padding: 0 10px;")

        for opt, b in buttons.items():
            b.clicked.connect(lambda _, o=opt: (refresh(o), on_change(o)))

        refresh(current)
        return container

    def _select_effect(self, key):
        self.settings_service.set("edge_light_effect", key)
        self._update_effect_cards(key)

    def _update_effect_cards(self, active_key):
        for k, card in self.effect_cards.items():
            if k == active_key:
                card.setStyleSheet("""
                    QPushButton {
                        background: #18181c;
                        border: 1.8px solid #ffffff;
                        border-radius: 12px;
                        text-align: left;
                    }
                """)
            else:
                card.setStyleSheet("""
                    QPushButton {
                        background: #121215;
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 12px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        border: 1px solid rgba(255, 255, 255, 0.2);
                    }
                """)

    def _select_style(self, key):
        self.settings_service.set("notch_style", key)
        self._update_style_cards(key)

    def _update_style_cards(self, active_key):
        for k, card in self.style_cards.items():
            if k == active_key:
                card.setStyleSheet("""
                    QPushButton {
                        background: #18181c;
                        border: 1.8px solid #ffffff;
                        border-radius: 12px;
                        text-align: left;
                    }
                """)
            else:
                card.setStyleSheet("""
                    QPushButton {
                        background: #121215;
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 12px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        border: 1px solid rgba(255, 255, 255, 0.2);
                    }
                """)

    def _on_toggle_match_music(self, val):
        self.settings_service.set("match_music_color", val)
        if val:
            for h, swatch in self.color_swatches.items():
                self._style_swatch(swatch, h, False)

    def _select_color(self, hex_code):
        # Explicit user selection: turn off match_music_color and apply color immediately!
        self.settings_service.set("match_music_color", False)
        self.settings_service.set("edge_light_color", hex_code)
        self.mc_toggle.setText("OFF")
        self._style_toggle(self.mc_toggle, False)
        for h, swatch in self.color_swatches.items():
            self._style_swatch(swatch, h, h == hex_code)

    def _style_swatch(self, swatch, hex_code, is_active):
        border = "2.5px solid #ffffff" if is_active else "1px solid rgba(255, 255, 255, 0.2)"
        swatch.setStyleSheet(f"""
            QPushButton {{
                background: {hex_code};
                border: {border};
                border-radius: 11px;
            }}
        """)

    def _on_intensity_change(self, val):
        self.int_val_lbl.setText(f"{val}%")
        self.settings_service.set("edge_light_intensity", val)

    def _on_scale_change(self, val):
        self.scale_val_lbl.setText(f"{val}%")
        self.settings_service.set("notch_scale", val)

    def _on_trans_change(self, val):
        self.trans_val_lbl.setText(f"{val}%")
        self.settings_service.set("glass_transparency", val)

    def _on_placement_change(self, opt):
        rev_map = {"Top": "top", "Taskbar Pill": "taskbar", "Full Taskbar": "full_taskbar"}
        val = rev_map.get(opt, "full_taskbar")
        self.settings_service.set("placement", val)
        if hasattr(self, "tb_offset_widget"):
            self.tb_offset_widget.setVisible(val == "taskbar")
        if hasattr(self, "full_tb_width_widget"):
            self.full_tb_width_widget.setVisible(val == "full_taskbar")

    def _on_taskbar_offset_change(self, val):
        self.tb_offset_lbl.setText(f"{val}px")
        self.settings_service.set("taskbar_x_offset", val)

    def _on_full_tb_width_change(self, val):
        self.full_tb_width_lbl.setText(f"{val}px")
        self.settings_service.set("full_taskbar_width", val)

    def _on_weather_toggle(self, checked: bool):
        self.settings_service.set("weather_enabled", checked)
