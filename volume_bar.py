from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush
from PySide6.QtWidgets import QWidget

class VolumeBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(110, 6)
        self.percentage = 50
        self.accent_color = QColor(255, 255, 255)

    def set_volume(self, pct: int, color: QColor = None):
        self.percentage = max(0, min(100, pct))
        if color:
            self.accent_color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Track background
        track_rect = QRectF(0, 0, self.width(), self.height())
        painter.setBrush(QBrush(QColor(45, 45, 52)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track_rect, 3.0, 3.0)

        # Filled progress
        if self.percentage > 0:
            fill_w = max(3.0, self.width() * (self.percentage / 100.0))
            fill_rect = QRectF(0, 0, fill_w, self.height())
            r = min(3.0, fill_w / 2.0)
            painter.setBrush(QBrush(self.accent_color))
            painter.drawRoundedRect(fill_rect, r, r)
