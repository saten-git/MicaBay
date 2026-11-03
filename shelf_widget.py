import os
from PySide6.QtCore import Qt, QMimeData, QUrl, QPoint
from PySide6.QtGui import QDrag, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QFrame
)

class FileShelfWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parked_files = []
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        # Header
        h_layout = QHBoxLayout()
        title = QLabel("📁  File Shelf (Drop Zone)")
        title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 700;")
        
        clear_btn = QPushButton("Clear All")
        clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #b0b0b8;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(255, 70, 70, 0.3);
                color: #ffffff;
            }
        """)
        clear_btn.clicked.connect(self.clear_shelf)
        h_layout.addWidget(title)
        h_layout.addStretch()
        h_layout.addWidget(clear_btn)
        layout.addLayout(h_layout)

        # Drop Zone / List Widget
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: rgba(20, 20, 24, 0.85);
                border: 1.5px dashed rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                color: #ffffff;
                padding: 8px;
            }
            QListWidget::item {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 6px;
                padding: 6px 10px;
                margin-bottom: 4px;
            }
            QListWidget::item:hover {
                background: rgba(255, 255, 255, 0.1);
            }
        """)
        self.list_widget.setDragEnabled(True)
        self.list_widget.startDrag = self._start_drag
        layout.addWidget(self.list_widget)

        self.tip_lbl = QLabel("Drag & drop files here to park them. Drag them out anywhere else anytime.")
        self.tip_lbl.setStyleSheet("color: #808088; font-size: 11px; text-align: center;")
        self.tip_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.tip_lbl)

    def add_paths(self, paths):
        for p in paths:
            if p not in self.parked_files and os.path.exists(p):
                self.parked_files.append(p)
                name = os.path.basename(p)
                size_kb = os.path.getsize(p) / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                item = QListWidgetItem(f"📄  {name}  ({size_str})")
                item.setData(Qt.ItemDataRole.UserRole, p)
                self.list_widget.addItem(item)

    def clear_shelf(self):
        self.parked_files.clear()
        self.list_widget.clear()

    def _start_drag(self, supported_actions):
        current_item = self.list_widget.currentItem()
        if not current_item:
            return
        path = current_item.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()
