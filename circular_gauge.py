import math
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget

class CircularGauge(QWidget):
    def __init__(self, title="CPU", parent=None, gauge_size=40):
        super().__init__(parent)
        self.title = title
        self.gauge_size = gauge_size
        self.target_value = 0
        self.display_value = 0.0
        self.setFixedSize(gauge_size + 12, gauge_size + 28)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_anim)

    def set_value(self, val: int):
        self.target_value = max(0, min(100, int(val)))
        if not self._anim_timer.isActive():
            self._anim_timer.start(25)

    def _tick_anim(self):
        diff = self.target_value - self.display_value
        if abs(diff) < 0.4:
            self.display_value = float(self.target_value)
            self._anim_timer.stop()
        else:
            self.display_value += diff * 0.28
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = self.gauge_size
        margin_x = (self.width() - size) / 2
        margin_y = 2
        rect = QRectF(margin_x, margin_y, size, size)

        # 1. Full 360-degree Background Track
        track_pen = QPen(QColor(36, 36, 42), 3.8)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        # 2. Progress Arc (Sweeps clockwise from 12 o'clock / 90 degrees)
        cur_pct = max(0.0, min(100.0, self.display_value))
        if cur_pct > 0.5:
            active_pen = QPen(QColor(255, 255, 255, 245), 3.8)
            active_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(active_pen)
            
            start_angle = 90 * 16  # 12 o'clock
            span_angle = -int(360 * 16 * (cur_pct / 100.0))  # negative sweeps clockwise
            painter.drawArc(rect, start_angle, span_angle)

        # 3. Center Percentage Text
        painter.setPen(QColor(255, 255, 255, 245))
        val_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(val_font)
        painter.drawText(QRectF(margin_x, margin_y, size, size), Qt.AlignmentFlag.AlignCenter, f"{int(round(cur_pct))}%")

        # 4. Bottom Title Label (CPU, RAM, GPU, DISK)
        painter.setPen(QColor(140, 140, 150))
        lbl_font = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        painter.setFont(lbl_font)
        painter.drawText(QRectF(0, size + 4, self.width(), 18), Qt.AlignmentFlag.AlignCenter, self.title)
