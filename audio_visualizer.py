import math
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush
from PySide6.QtWidgets import QWidget

class EqualizerBarsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.is_playing = False
        self.bar_heights = [5.0, 11.0, 7.0]
        self.phase = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(35)

    def set_playing(self, playing: bool):
        self.is_playing = playing
        self.update()

    def _animate(self):
        self.phase += 0.22
        if self.is_playing:
            for i in range(len(self.bar_heights)):
                val = 4.0 + 9.5 * abs(math.sin(self.phase * (1.25 + i * 0.45) + i * 0.8))
                self.bar_heights[i] += (val - self.bar_heights[i]) * 0.45
        else:
            for i in range(len(self.bar_heights)):
                self.bar_heights[i] += (3.0 - self.bar_heights[i]) * 0.25
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_w = 2.2
        spacing = 2.2
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
