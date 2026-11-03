import time
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

class ClipboardService(QObject):
    item_copied = Signal(dict)
    history_updated = Signal(list)

    def __init__(self):
        super().__init__()
        self.clipboard = QApplication.clipboard()
        self.history = []
        self._last_content_hash = None
        self._last_event_time = 0
        self._internal_copy = False

        self.clipboard.dataChanged.connect(self._on_data_changed)

    def _on_data_changed(self):
        # Ignore programmatic copies by our own app
        if self._internal_copy:
            self._internal_copy = False
            return

        # Throttle rapid duplicate events
        now = time.time()
        if now - self._last_event_time < 0.2:
            return
        self._last_event_time = now

        mime = self.clipboard.mimeData()
        if mime is None:
            return

        item = None

        try:
            if mime.hasImage():
                img = self.clipboard.image()
                if not img.isNull():
                    w, h = img.width(), img.height()
                    # PySide6 uses sizeInBytes()
                    b_size = img.sizeInBytes() if hasattr(img, "sizeInBytes") else (w * h * 4)
                    content_hash = f"img_{w}_{h}_{b_size}"
                    if content_hash == self._last_content_hash:
                        return
                    self._last_content_hash = content_hash

                    thumb = img.scaled(48, 48)
                    item = {
                        "type": "image",
                        "title": "Image",
                        "detail": f"{w} × {h}",
                        "preview": f"Image",
                        "time_str": "now",
                        "timestamp": now,
                        "image": img,
                        "thumbnail": thumb
                    }

            elif mime.hasUrls():
                urls = mime.urls()
                if urls:
                    paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
                    if paths:
                        content_hash = f"files_{'_'.join(paths)}"
                        if content_hash == self._last_content_hash:
                            return
                        self._last_content_hash = content_hash

                        count = len(paths)
                        first_name = paths[0].split("\\")[-1]
                        detail = f"{first_name}" if count == 1 else f"{first_name} (+{count-1})"
                        item = {
                            "type": "files",
                            "title": "Files",
                            "detail": detail,
                            "preview": f"{count} file{'s' if count > 1 else ''}",
                            "paths": paths,
                            "time_str": "now",
                            "timestamp": now
                        }

            elif mime.hasText():
                text = self.clipboard.text().strip()
                if text:
                    content_hash = f"txt_{hash(text)}"
                    if content_hash == self._last_content_hash:
                        return
                    self._last_content_hash = content_hash

                    short_preview = text.replace("\n", " ").strip()
                    if len(short_preview) > 28:
                        short_preview = short_preview[:25] + "..."

                    item = {
                        "type": "text",
                        "title": "Text",
                        "detail": short_preview,
                        "preview": short_preview,
                        "full_text": text,
                        "time_str": "now",
                        "timestamp": now
                    }
        except Exception as e:
            print("[ClipboardService] Error handling clip data:", e)
            return

        if item:
            self.history.insert(0, item)
            if len(self.history) > 40:
                self.history.pop()

            self.item_copied.emit(item)
            self.history_updated.emit(self.history)

    def copy_back(self, index: int):
        if 0 <= index < len(self.history):
            item = self.history[index]
            self._internal_copy = True
            if item["type"] == "text":
                self.clipboard.setText(item["full_text"])
            elif item["type"] == "image":
                self.clipboard.setImage(item["image"])
