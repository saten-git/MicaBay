import math
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush
from PySide6.QtWidgets import QWidget

class EqualizerBarsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 16)
        self.is_playing = False
        self.bar_heights = [3.0, 3.0, 3.0, 3.0]
        self.phase = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(35)

    def set_playing(self, playing: bool):
        if self.is_playing != playing:
            self.is_playing = playing
            if not self.timer.isActive():
                self.timer.start(35)
            self.update()

    def _animate(self):
        self.phase += 0.24
        if self.is_playing:
            freqs = [1.1, 1.7, 1.4, 2.0]
            offsets = [0.0, 1.2, 2.4, 0.7]
            max_h = [9.0, 13.0, 11.5, 8.5]
            for i in range(len(self.bar_heights)):
                target = 3.5 + max_h[i] * abs(math.sin(self.phase * freqs[i] + offsets[i]))
                self.bar_heights[i] += (target - self.bar_heights[i]) * 0.42
            self.update()
        else:
            settled = True
            for i in range(len(self.bar_heights)):
                diff = 2.5 - self.bar_heights[i]
                if abs(diff) > 0.1:
                    self.bar_heights[i] += diff * 0.25
                    settled = False
                else:
                    self.bar_heights[i] = 2.5
            self.update()
            if settled and not self.is_playing:
                self.timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_w = 2.2
        spacing = 1.8
        total_w = len(self.bar_heights) * bar_w + (len(self.bar_heights) - 1) * spacing
        start_x = (self.width() - total_w) / 2.0
        base_y = self.height() - 1

        color = QColor(255, 255, 255, 240) if self.is_playing else QColor(140, 140, 150, 140)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)

        for i, h in enumerate(self.bar_heights):
            x = start_x + i * (bar_w + spacing)
            y = base_y - h
            painter.drawRoundedRect(QRectF(x, y, bar_w, h), 1.1, 1.1)
