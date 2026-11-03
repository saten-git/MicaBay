import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from media_service import MediaService
from clipboard_service import ClipboardService
from system_service import SystemService
from settings_service import SettingsService
from volume_service import VolumeService
from weather_service import WeatherService
from notch_window import NotchWindow

def create_tray_icon():
    logo_path = os.path.join(os.path.dirname(__file__), "micabay_logo.jpg")
    if os.path.exists(logo_path):
        return QIcon(logo_path)
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(0, 210, 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 8, 24, 16, 8, 8)
    p.end()
    return QIcon(pix)

def main():
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    media_service = MediaService()
    media_service.start()

    clipboard_service = ClipboardService()
    system_service = SystemService()
    settings_service = SettingsService()

    volume_service = VolumeService()
    volume_service.start()

    weather_service = WeatherService(settings_service)

    notch = NotchWindow(media_service, clipboard_service, system_service, settings_service, volume_service, weather_service)
    notch.show()

    # System Tray
    tray_menu = QMenu()
    
    act_expand = QAction("Open Dashboard", tray_menu)
    act_expand.triggered.connect(notch.expand_dashboard)
    tray_menu.addAction(act_expand)

    act_settings = QAction("⚙️ Settings...", tray_menu)
    act_settings.triggered.connect(notch.open_settings)
    tray_menu.addAction(act_settings)

    act_shelf = QAction("📁 File Shelf", tray_menu)
    act_shelf.triggered.connect(notch.open_shelf)
    tray_menu.addAction(act_shelf)

    # Size submenu
    size_menu = tray_menu.addMenu("Pill Size")
    for s_name, s_val in [("Compact (240px)", 240), ("Standard (270px)", 270), ("Medium (310px)", 310), ("Wide (350px)", 350)]:
        a = QAction(s_name, size_menu)
        a.triggered.connect(lambda _, v=s_val: settings_service.set("pill_width", v))
        size_menu.addAction(a)

    tray_menu.addSeparator()

    act_quit = QAction("Exit MicaBay", tray_menu)
    def on_quit():
        media_service.stop()
        volume_service.stop()
        system_service.stop()
        notch.close()
        app.quit()
    act_quit.triggered.connect(on_quit)
    tray_menu.addAction(act_quit)

    tray_icon = QSystemTrayIcon(create_tray_icon(), app)
    tray_icon.setToolTip("MicaBay")
    tray_icon.setContextMenu(tray_menu)
    tray_icon.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
