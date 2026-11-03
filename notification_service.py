import os
import re
import json
import time
import asyncio
import threading
import sqlite3
import shutil
import psutil
import ctypes
from ctypes import wintypes
import xml.etree.ElementTree as ET
from PySide6.QtCore import QObject, Signal, QTimer

try:
    import winsdk.windows.ui.notifications.management as mgmt
    from winsdk.windows.ui.notifications import NotificationKinds
    WINSDK_AVAILABLE = True
except Exception:
    WINSDK_AVAILABLE = False

class NotificationService(QObject):
    notifications_updated = Signal(dict)
    notification_toast_requested = Signal(dict)

    def __init__(self, settings_service=None, parent=None):
        super().__init__(parent)
        self.settings = settings_service
        self._running = True
        self.source = "system" if WINSDK_AVAILABLE else "app"
        self.unread_count = 0
        self.app_notifications = []
        self._last_emitted_count = -1
        self._seen_ids = set()
        self._initial_id_scan_done = False
        self._last_db_order = 0
        self._pending_toasts = []
        self._lock = threading.Lock()
        self._last_tg_count = None
        self._tg_init_done = False
        self._last_tg_toast_time = 0.0
        self._cache_file = os.path.join(os.path.dirname(__file__), "notifications_cache.json")
        self._wpn_db_path = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db")

        self._load_cache()

        # Background worker thread for responsive non-blocking Windows toast detection
        self._poll_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._poll_thread.start()

        # Qt timer on main thread to emit signals safely
        self._emit_timer = QTimer(self)
        self._emit_timer.timeout.connect(self._check_and_emit)
        self._emit_timer.start(250)  # fast 250ms reaction

    def _load_cache(self):
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.unread_count = max(0, data.get("unread_count", 0))
                    self.app_notifications = data.get("app_notifications", [])
            except Exception:
                pass

    def _save_cache(self):
        try:
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "unread_count": self.unread_count,
                    "app_notifications": self.app_notifications[-20:]
                }, f, indent=2)
        except Exception:
            pass

    def _get_app_icon(self, app_name: str) -> str:
        name_lower = (app_name or "").lower()
        if "telegram" in name_lower:
            return "💬"
        elif "whatsapp" in name_lower:
            return "💬"
        elif "mail" in name_lower or "outlook" in name_lower:
            return "✉️"
        elif "slack" in name_lower or "discord" in name_lower or "teams" in name_lower:
            return "💬"
        elif "chrome" in name_lower or "edge" in name_lower or "brave" in name_lower or "firefox" in name_lower:
            return "🌐"
        elif "download" in name_lower:
            return "📥"
        elif "screenshot" in name_lower or "snip" in name_lower:
            return "📸"
        return "💬"

    def _worker_loop(self):
        # Background loop monitoring Windows notifications & direct Telegram messages
        while self._running:
            try:
                if WINSDK_AVAILABLE:
                    self._check_winsdk_notifications()
                else:
                    self._check_db_notifications()
            except Exception:
                pass

            try:
                self._check_telegram_direct()
            except Exception:
                pass

            # Fast 350ms sleep loop for snappy responsiveness
            for _ in range(7):
                if not self._running:
                    break
                time.sleep(0.05)

    def _check_telegram_direct(self):
        try:
            tg_title = None
            tg_hwnd = None

            user32 = ctypes.windll.user32
            hw = user32.OpenWindowStationW('WinSta0', False, 0x037F)
            if hw:
                user32.SetProcessWindowStation(hw)
            hd = user32.OpenDesktopW('Default', 0, False, 0x01FF)

            def enum_cb(hwnd, lparam):
                nonlocal tg_title, tg_hwnd
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:
                    p = psutil.Process(pid.value)
                    if "telegram" in p.name().lower():
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            title = buf.value
                            if title.startswith("Telegram"):
                                tg_title = title
                                tg_hwnd = hwnd
                                return False
                except Exception:
                    pass
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            if hd:
                user32.EnumDesktopWindows(hd, WNDENUMPROC(enum_cb), 0)
                user32.CloseDesktop(hd)
            else:
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

            if tg_title:
                m = re.search(r"Telegram\s*(?:\(([0-9,]+)\))?", tg_title)
                cnt = 0
                if m:
                    c_str = m.group(1)
                    cnt = int(c_str.replace(",", "")) if c_str else 0

                if not self._tg_init_done:
                    self._last_tg_count = cnt
                    self._tg_init_done = True
                else:
                    if cnt > self._last_tg_count:
                        diff = cnt - self._last_tg_count
                        # Prevent duplicate alert if Windows Action Center already caught it within 3s
                        if time.time() - getattr(self, "_last_tg_toast_time", 0) > 3.0:
                            self._last_tg_toast_time = time.time()
                            msg_body = "New message received" if diff == 1 else f"{diff} new messages"
                            new_toast = {
                                "id": f"tg_{time.time()}",
                                "app": "Telegram",
                                "title": "Telegram",
                                "body": msg_body,
                                "icon": "💬",
                                "display_text": f"Telegram · {msg_body}"
                            }
                            with self._lock:
                                self._pending_toasts.append(new_toast)
                        self._last_tg_count = cnt
                    elif cnt < self._last_tg_count:
                        self._last_tg_count = cnt
        except Exception:
            pass

    def _check_winsdk_notifications(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            listener = mgmt.UserNotificationListener.current
            status = listener.get_access_status()

            if status == mgmt.UserNotificationListenerAccessStatus.ALLOWED:
                notifs = loop.run_until_complete(
                    listener.get_notifications_async(NotificationKinds.TOAST)
                )
                self.unread_count = len(notifs)
                self.source = "system"

                current_ids = set()
                new_items = []

                for n in notifs:
                    nid = n.id
                    current_ids.add(nid)
                    if self._initial_id_scan_done and nid not in self._seen_ids:
                        # NEW NOTIFICATION ARRIVED!
                        try:
                            app_name = n.app_info.display_info.display_name or "Notification"
                        except Exception:
                            app_name = "Notification"

                        texts = []
                        try:
                            for b in n.notification.visual.bindings:
                                for t in b.get_text_elements():
                                    if t.text and t.text.strip():
                                        texts.append(t.text.strip())
                        except Exception:
                            pass

                        if len(texts) >= 2:
                            title = texts[0]
                            body = " · ".join(texts[1:])
                        elif len(texts) == 1:
                            title = app_name
                            body = texts[0]
                        else:
                            title = app_name
                            body = "New message"

                        icon = self._get_app_icon(app_name)
                        if "telegram" in app_name.lower():
                            self._last_tg_toast_time = time.time()

                        new_items.append({
                            "id": nid,
                            "app": app_name,
                            "title": title,
                            "body": body,
                            "icon": icon,
                            "display_text": f"{app_name} · {title}: {body}" if title != app_name else f"{app_name} · {body}"
                        })

                self._seen_ids = current_ids
                self._initial_id_scan_done = True

                if new_items:
                    with self._lock:
                        self._pending_toasts.extend(new_items)
            else:
                self._check_db_notifications()
            loop.close()
        except Exception:
            self._check_db_notifications()

    def _check_db_notifications(self):
        # Fallback / Dual detector querying Windows Notification database
        if not os.path.exists(self._wpn_db_path):
            return
        try:
            temp_copy = os.path.join(os.path.dirname(__file__), "wpn_check.tmp")
            shutil.copy2(self._wpn_db_path, temp_copy)
            conn = sqlite3.connect(temp_copy)
            cur = conn.cursor()
            cur.execute("""
                SELECT n."Order", n.Id, h.PrimaryId, n.Payload
                FROM Notification n
                LEFT JOIN NotificationHandler h ON n.HandlerId = h.RecordId
                ORDER BY n."Order" DESC LIMIT 5;
            """)
            rows = cur.fetchall()
            conn.close()
            try:
                os.remove(temp_copy)
            except Exception:
                pass

            if not rows:
                return

            if self._last_db_order == 0:
                self._last_db_order = max(r[0] for r in rows)
                return

            new_db_items = []
            max_seen = self._last_db_order
            for order, nid, primary_id, payload in rows:
                if order > self._last_db_order:
                    max_seen = max(max_seen, order)
                    app_name = (primary_id or "Notification").split("!")[-1].split(".")[-1].capitalize()
                    payload_str = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload)
                    texts = []
                    try:
                        root = ET.fromstring(payload_str)
                        for el in root.iter("text"):
                            if el.text and el.text.strip():
                                texts.append(el.text.strip())
                    except Exception:
                        pass

                    if len(texts) >= 2:
                        title = texts[0]
                        body = " · ".join(texts[1:])
                    elif len(texts) == 1:
                        title = app_name
                        body = texts[0]
                    else:
                        title = app_name
                        body = "New message"

                    icon = self._get_app_icon(app_name)
                    if "telegram" in app_name.lower():
                        self._last_tg_toast_time = time.time()
                    new_db_items.append({
                        "id": nid,
                        "app": app_name,
                        "title": title,
                        "body": body,
                        "icon": icon,
                        "display_text": f"{app_name} · {title}: {body}" if title != app_name else f"{app_name} · {body}"
                    })

            self._last_db_order = max_seen
            if new_db_items:
                with self._lock:
                    self._pending_toasts.extend(new_db_items)
        except Exception:
            pass

    def _check_and_emit(self):
        # 1. Emit pending real-time notification toasts directly to Live Pill!
        toasts_to_emit = []
        with self._lock:
            if self._pending_toasts:
                toasts_to_emit = list(self._pending_toasts)
                self._pending_toasts.clear()

        for toast in toasts_to_emit:
            self.notification_toast_requested.emit(toast)

        # 2. Emit unread count if changed
        if self.unread_count != self._last_emitted_count:
            self._last_emitted_count = self.unread_count
            self.notifications_updated.emit(self.get_data())

    def get_data(self) -> dict:
        cnt = max(0, self.unread_count)
        return {
            "count": cnt,
            "has_unread": cnt > 0,
            "source": self.source,
            "summary": f"{cnt} Unread" if cnt > 0 else "No new notifications",
            "display_text": f"{cnt} Unread" if cnt > 0 else "No notifications"
        }

    def trigger_test_notification(self, app="Telegram", title="John", body="Hey, are you free now?"):
        toast = {
            "id": int(time.time()),
            "app": app,
            "title": title,
            "body": body,
            "icon": self._get_app_icon(app),
            "display_text": f"{app} · {title}: {body}" if title != app else f"{app} · {body}"
        }
        self.notification_toast_requested.emit(toast)

    def add_app_notification(self, title: str, text: str = ""):
        self.app_notifications.append({
            "title": title,
            "text": text,
            "time": time.time()
        })
        if self.source == "app":
            self.unread_count = len(self.app_notifications)
        self._save_cache()
        self.trigger_test_notification("MicaBay", title, text)
        self.notifications_updated.emit(self.get_data())

    def mark_all_read(self):
        if self.source == "app":
            self.app_notifications.clear()
            self.unread_count = 0
            self._save_cache()
            self.notifications_updated.emit(self.get_data())

    def stop(self):
        self._running = False
        if hasattr(self, "_emit_timer"):
            self._emit_timer.stop()
