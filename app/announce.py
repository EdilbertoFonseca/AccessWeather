from __future__ import annotations

import ctypes
import threading

from .config import app_root


class Announcer:
    def __init__(self):
        self._nvda = self._load_nvda()

    @staticmethod
    def _load_nvda():
        candidates = [
            app_root() / "nvdaControllerClient64.dll",
            app_root() / "tools" / "nvdaControllerClient64.dll",
        ]
        for path in candidates:
            if path.exists():
                try:
                    dll = ctypes.WinDLL(str(path))
                    dll.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
                    return dll
                except OSError:
                    pass
        return None

    def speak(self, text: str) -> None:
        if not text:
            return
        if self._nvda:
            self._nvda.nvdaController_speakText(text)
            return

        def sapi():
            try:
                import win32com.client

                win32com.client.Dispatch("SAPI.SpVoice").Speak(text, 1)
            except Exception:
                pass

        threading.Thread(target=sapi, daemon=True).start()