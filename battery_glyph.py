from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import QWidget

class BatteryGlyphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 12)
        self.percentage = 95
        self.is_charging = False

    def update_battery(self, pct: int, is_charging: bool):
        self.percentage = max(0, min(100, pct))
        self.is_charging = is_charging
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Body outline: 17 x 10
        body_rect = QRectF(1.0, 1.0, 17.0, 10.0)
        
        # Chrome white border
        border_col = QColor(255, 255, 255, 180)
        painter.setPen(QPen(border_col, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body_rect, 2.5, 2.5)

        # Chrome white terminal nipple on right
        nipple_rect = QRectF(18.5, 3.8, 1.8, 4.4)
        painter.setBrush(QBrush(border_col))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(nipple_rect, 0.8, 0.8)

        # Inner fill: White Chrome Metallic
        fill_w = max(1.5, 13.4 * (self.percentage / 100.0))
        fill_rect = QRectF(2.8, 2.8, fill_w, 6.4)

        if self.is_charging or self.percentage > 15:
            # White chrome metallic gradient
            chrome_grad = QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
            chrome_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
            chrome_grad.setColorAt(0.45, QColor(235, 240, 248, 245))
            chrome_grad.setColorAt(1.0, QColor(200, 208, 220, 235))
            painter.setBrush(QBrush(chrome_grad))
        else:
            painter.setBrush(QBrush(QColor(255, 75, 75, 235))) # warning red when critical

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(fill_rect, 1.5, 1.5)
