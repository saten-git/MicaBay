import time
import threading
import ctypes
from PySide6.QtCore import QObject, Signal

class VolumeService(QObject):
    volume_changed = Signal(int, bool)
    mic_mute_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self._running = True
        self._thread = None
        self._last_vol = None
        self._last_mute = None
        self._last_mic_mute = None

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
        mic_endpoint = None

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

            # Poll microphone mute status
            try:
                if mic_endpoint is None:
                    import comtypes
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    m = AudioUtilities.GetMicrophone()
                    if m:
                        iface = m.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_INPROC_SERVER, None)
                        mic_endpoint = ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))

                if mic_endpoint:
                    is_mic_muted = bool(mic_endpoint.GetMute())
                    if self._last_mic_mute is None or is_mic_muted != self._last_mic_mute:
                        self._last_mic_mute = is_mic_muted
                        self.mic_mute_changed.emit(is_mic_muted)
            except Exception:
                mic_endpoint = None

            time.sleep(0.09)  # ~11 checks/sec, <0.02% CPU

        try:
            import comtypes
            comtypes.CoUninitialize()
        except Exception:
            pass

    def get_volume(self) -> int:
        if self._last_vol is not None:
            return self._last_vol
        try:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if speakers:
                return int(round(speakers.volume_percent))
        except Exception:
            pass
        return 50

    def is_muted(self) -> bool:
        if self._last_mute is not None:
            return self._last_mute
        try:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if speakers and speakers.EndpointVolume:
                return bool(speakers.EndpointVolume.GetMute())
        except Exception:
            pass
        return False

    def set_volume(self, pct: int):
        pct = max(0, min(100, pct))
        try:
            import comtypes
            comtypes.CoInitialize()
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if speakers and speakers.EndpointVolume:
                speakers.EndpointVolume.SetMasterVolumeLevelScalar(pct / 100.0, None)
                if speakers.EndpointVolume.GetMute() and pct > 0:
                    speakers.EndpointVolume.SetMute(0, None)
        except Exception:
            pass

    def toggle_mute(self) -> bool:
        try:
            import comtypes
            comtypes.CoInitialize()
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if speakers and speakers.EndpointVolume:
                curr = speakers.EndpointVolume.GetMute()
                new_state = 0 if curr else 1
                speakers.EndpointVolume.SetMute(new_state, None)
                return bool(new_state)
        except Exception:
            pass
        return False

    def is_microphone_muted(self) -> bool:
        if self._last_mic_mute is not None:
            return self._last_mic_mute
        is_main = threading.current_thread() is threading.main_thread()
        co_init = False
        m = None
        iface = None
        ep = None
        try:
            if not is_main:
                import comtypes
                try:
                    comtypes.CoInitialize()
                    co_init = True
                except Exception:
                    pass
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            m = AudioUtilities.GetMicrophone()
            if m:
                iface = m.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_INPROC_SERVER, None)
                ep = ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))
                val = bool(ep.GetMute())
                self._last_mic_mute = val
                return val
        except Exception:
            pass
        finally:
            del ep
            del iface
            del m
            if co_init and not is_main:
                try:
                    import comtypes
                    comtypes.CoUninitialize()
                except Exception:
                    pass
        return False

    def toggle_microphone_mute(self) -> bool:
        is_main = threading.current_thread() is threading.main_thread()
        co_init = False
        m = None
        iface = None
        ep = None
        try:
            if not is_main:
                import comtypes
                try:
                    comtypes.CoInitialize()
                    co_init = True
                except Exception:
                    pass
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            m = AudioUtilities.GetMicrophone()
            if m:
                iface = m.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_INPROC_SERVER, None)
                ep = ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))
                curr = ep.GetMute()
                new_state = 0 if curr else 1
                ep.SetMute(new_state, None)
                self._last_mic_mute = bool(new_state)
                self.mic_mute_changed.emit(bool(new_state))
                return bool(new_state)
        except Exception:
            pass
        finally:
            del ep
            del iface
            del m
            if co_init and not is_main:
                try:
                    import comtypes
                    comtypes.CoUninitialize()
                except Exception:
                    pass
        return False

    def stop(self):
        self._running = False
