from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget

class WeeklyBarsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 7 days of the week: 6 subtle horizontal pills, 7th is today's active vertical bar
        x = 0.0
        for i in range(7):
            if i == 6:  # Today (Active)
                p.setBrush(QColor(255, 255, 255))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(QRectF(x, 2.0, 7.0, 18.0), 3.5, 3.5)
                x += 14.0
            else:
                p.setBrush(QColor(255, 255, 255, 38))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(QRectF(x, 15.0, 16.0, 4.0), 2.0, 2.0)
                x += 23.0
