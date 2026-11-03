import time
import threading
from PySide6.QtCore import QObject, Signal

class VolumeService(QObject):
    volume_changed = Signal(int, bool)

    def __init__(self):
        super().__init__()
        self._running = True
        self._thread = None
        self._last_vol = None
        self._last_mute = None

    def start(self):
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass

        speakers = None
        while self._running:
            try:
                if speakers is None:
                    from pycaw.pycaw import AudioUtilities
                    speakers = AudioUtilities.GetSpeakers()

                if speakers:
                    cur_vol = int(round(speakers.volume_percent))
                    is_muted = bool(speakers.EndpointVolume.GetMute()) if speakers.EndpointVolume else False

                    if self._last_vol is None:
                        # Initial state: cache without triggering HUD
                        self._last_vol = cur_vol
                        self._last_mute = is_muted
                    elif cur_vol != self._last_vol or is_muted != self._last_mute:
                        self._last_vol = cur_vol
                        self._last_mute = is_muted
                        self.volume_changed.emit(cur_vol, is_muted)
            except Exception:
                speakers = None

            time.sleep(0.09)  # ~11 checks/sec, <0.02% CPU

        try:
            import comtypes
            comtypes.CoUninitialize()
        except Exception:
            pass

    def stop(self):
        self._running = False
