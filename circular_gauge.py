import math
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget

class CircularGauge(QWidget):
    def __init__(self, title="CPU", parent=None):
        super().__init__(parent)
        self.title = title
        self.value = 0
        self.setFixedSize(64, 82)

    def set_value(self, val: int):
        self.value = max(0, min(100, int(val)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = 48
        margin_x = (self.width() - size) / 2
        margin_y = 4
        rect = QRectF(margin_x, margin_y, size, size)

        # 1. Full 360-degree Background Track
        track_pen = QPen(QColor(36, 36, 42), 4.5)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        # 2. Progress Arc (Sweeps clockwise from 12 o'clock / 90 degrees)
        if self.value > 0:
            active_pen = QPen(QColor(255, 255, 255, 245), 4.5)
            active_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(active_pen)
            
            start_angle = 90 * 16  # 12 o'clock
            span_angle = -int(360 * 16 * (self.value / 100.0))  # negative sweeps clockwise
            painter.drawArc(rect, start_angle, span_angle)

        # 3. Center Percentage Text
        painter.setPen(QColor(255, 255, 255, 245))
        val_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(val_font)
        painter.drawText(QRectF(margin_x, margin_y, size, size), Qt.AlignmentFlag.AlignCenter, f"{self.value}%")

        # 4. Bottom Title Label (CPU, RAM, DISK)
        painter.setPen(QColor(140, 140, 150))
        lbl_font = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        painter.setFont(lbl_font)
        painter.drawText(QRectF(0, size + 8, self.width(), 18), Qt.AlignmentFlag.AlignCenter, self.title)
