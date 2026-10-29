"""Reprodução da sequência de beeps pelos tons do NVDA.

A sequência é agendada no thread principal com ``wx.CallLater``: cada beep
toca logo após o anterior, e o silêncio avança o relógio sem tocar nada. O
callback final é chamado quando toda a sequência terminou.
"""

import wx

try:
    import tones
except Exception:  # fora do NVDA (testes offline)
    tones = None

from .core.beeps import step_duration


class BeepSequencer:
    """Toca beeps e silêncios em ordem, avisando quando terminar."""

    def __init__(self):
        self._timers = []
        self._done = None

    def stop(self):
        for timer in self._timers:
            try:
                timer.Stop()
            except Exception:
                pass
        self._timers = []
        self._done = None

    @property
    def playing(self) -> bool:
        return bool(self._timers)

    def play(self, sequence, done=None):
        self.stop()
        self._done = done
        offset = 0
        for step in sequence or ():
            if not isinstance(step, dict):
                continue
            duration = step_duration(step)
            if step.get("type") == "beep":
                try:
                    frequency = max(1, int(step.get("frequency", 800) or 800))
                except (TypeError, ValueError):
                    frequency = 800
                timer = wx.CallLater(max(offset, 1), self._beep, frequency, duration)
                self._timers.append(timer)
            offset += duration
        if done is not None:
            self._timers.append(wx.CallLater(max(offset, 1), self._finish))

    def _beep(self, frequency, duration):
        if tones is None:
            return
        try:
            tones.beep(frequency, duration)
        except Exception:
            pass

    def _finish(self):
        self._timers = []
        callback = self._done
        self._done = None
        if callback is not None:
            callback()
