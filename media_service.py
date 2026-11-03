import asyncio
import threading
import time
from PySide6.QtCore import QObject, Signal

class MediaService(QObject):
    media_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self._loop = None
        self._thread = None
        self._running = True
        self._current_session = None
        self.current_media = {
            "has_media": False,
            "app": "",
            "title": "",
            "artist": "",
            "display_text": "",
            "is_playing": False,
            "thumbnail": None
        }

    def start(self):
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._media_polling_worker())

    async def _media_polling_worker(self):
        try:
            from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SMTCManager
            from winsdk.windows.storage.streams import DataReader
        except ImportError:
            print("[MediaService] winsdk not available.")
            return

        while self._running:
            try:
                mgr = await SMTCManager.request_async()
                session = mgr.get_current_session()
                self._current_session = session

                if session:
                    source_app = session.source_app_user_model_id or "Media"
                    if "\\" in source_app:
                        source_app = source_app.split("\\")[-1]
                    if ".exe" in source_app.lower():
                        source_app = source_app.replace(".exe", "").capitalize()

                    props = await session.try_get_media_properties_async()
                    playback_info = session.get_playback_info()
                    # 4 = Playing, 5 = Paused
                    status = playback_info.playback_status if playback_info else 0
                    is_playing = (status == 4)

                    title = props.title.strip() if (props and props.title) else ""
                    artist = props.artist.strip() if (props and props.artist) else ""

                    if title and artist:
                        display = f"{title} · {artist}"
                    elif title:
                        display = title
                    else:
                        display = ""

                    # Get thumbnail if available
                    thumb_bytes = None
                    if props and props.thumbnail:
                        try:
                            stream = await props.thumbnail.open_read_async()
                            size = stream.size
                            if 0 < size < 6 * 1024 * 1024:
                                reader = DataReader(stream)
                                await reader.load_async(size)
                                raw = bytearray(size)
                                reader.read_bytes(raw)
                                thumb_bytes = bytes(raw)
                        except Exception:
                            pass

                    payload = {
                        "has_media": bool(title),
                        "app": source_app,
                        "title": title or "Unknown Track",
                        "artist": artist,
                        "display_text": display,
                        "is_playing": is_playing,
                        "thumbnail": thumb_bytes
                    }
                    self.current_media = payload
                    self.media_updated.emit(payload)
                else:
                    payload = {
                        "has_media": False,
                        "app": "",
                        "title": "",
                        "artist": "",
                        "display_text": "",
                        "is_playing": False,
                        "thumbnail": None
                    }
                    self.current_media = payload
                    self.media_updated.emit(payload)
            except Exception:
                pass

            await asyncio.sleep(0.8)

    def _send_win32_media_key(self, vk_code: int):
        try:
            import ctypes
            # KEYEVENTF_EXTENDEDKEY = 1, KEYEVENTF_KEYUP = 2
            ctypes.windll.user32.keybd_event(vk_code, 0, 1, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, 1 | 2, 0)
        except Exception:
            pass

    def play_pause(self):
        sent = False
        if self._loop and self._current_session:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._current_session.try_toggle_play_pause_async(), self._loop)
                # If SMTC is responsive, it will handle it
                sent = True
            except Exception:
                sent = False
        if not sent:
            self._send_win32_media_key(0xB3)

    def next_track(self):
        sent = False
        if self._loop and self._current_session:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._current_session.try_skip_next_async(), self._loop)
                sent = True
            except Exception:
                sent = False
        if not sent:
            self._send_win32_media_key(0xB0)

    def prev_track(self):
        sent = False
        if self._loop and self._current_session:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._current_session.try_skip_previous_async(), self._loop)
                sent = True
            except Exception:
                sent = False
        if not sent:
            self._send_win32_media_key(0xB1)

    def stop(self):
        self._running = False
