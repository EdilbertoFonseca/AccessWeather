# AccessWeather para NVDA
# Anuncia o clima atual e a previsão usando a API Open-Meteo (sem chave).
#
# Copyright (C) 2026
# Este add-on é software livre sob a GNU GPL v2 ou posterior.

import threading
from datetime import datetime

import config
import globalPluginHandler
import gui
import scriptHandler
import ui
import wx
from scriptHandler import script

try:
    from gui.settingsDialogs import NVDASettingsDialog
except Exception:  # fora do NVDA (testes offline)
    NVDASettingsDialog = None

from .core.beeps import DEFAULT_BEEP_SEQUENCE, normalize_sequence
from .core.cache import ForecastCache
from .core.changelog import current_news, news_for, version_key
from .core.config import (
    DEFAULT_NOTIFICATION_FIELDS,
    Settings,
    unit_codes,
    unit_symbols,
)
from .core.formatting import day_text, field_text, hour_text, notification_body
from .core.locations import LocationStore
from .core.weather import (
    WeatherError,
    fetch_forecast_payload,
    parse_forecast,
)
from .dialogs import (
    AccessWeatherSettingsPanel,
    WeatherListDialog,
    WhatsNewDialog,
)
from .playback import BeepSequencer


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = "AccessWeather"

    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.store = LocationStore()
        self.cache = ForecastCache(minutes=self.settings.get("cache_minutes", 15))
        self.forecasts = {}
        self._list_dialog = None
        self._repeat_timer = None
        self._last_notify = {}
        self._field_preview_running = False
        self._whats_new_timer = None
        self._sequencer = BeepSequencer()
        self._notify_timer = wx.PyTimer(self._on_notify_timer)
        self._notify_timer.Start(60000)
        AccessWeatherSettingsPanel.plugin = self
        if (
            NVDASettingsDialog is not None
            and AccessWeatherSettingsPanel not in NVDASettingsDialog.categoryClasses
        ):
            NVDASettingsDialog.categoryClasses.append(
                AccessWeatherSettingsPanel
            )
        self._schedule_whats_new()

    def terminate(self):
        try:
            self._notify_timer.Stop()
        except Exception:
            pass
        if self._whats_new_timer is not None:
            try:
                self._whats_new_timer.Stop()
            except Exception:
                pass
            self._whats_new_timer = None
        try:
            self._sequencer.stop()
        except Exception:
            pass
        if self._repeat_timer is not None:
            try:
                self._repeat_timer.Stop()
            except Exception:
                pass
            self._repeat_timer = None
        if self._list_dialog is not None:
            try:
                self._list_dialog.Destroy()
            except Exception:
                pass
            self._list_dialog = None
        if NVDASettingsDialog is not None:
            try:
                NVDASettingsDialog.categoryClasses.remove(
                    AccessWeatherSettingsPanel
                )
            except ValueError:
                pass
        AccessWeatherSettingsPanel.plugin = None

    # -- novidades da versão -----------------------------------------------

    @staticmethod
    def _addon_version():
        """Versão do manifest.ini, lida em tempo de execução."""
        try:
            import addonHandler

            addon = addonHandler.getCodeAddon()
            if addon is not None:
                return str(addon.manifest["version"]).strip()
        except Exception:
            pass
        try:
            from pathlib import Path

            manifest = Path(__file__).resolve().parents[2] / "manifest.ini"
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if line.strip().lower().startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        return ""

    def _schedule_whats_new(self):
        """Agenda a janela de novidades para depois da inicialização do NVDA."""
        try:
            if not self._can_show_whats_new():
                return
            version = self._addon_version()
            seen = str(self.settings.get("installed_version", "") or "")
            if not version or version_key(seen) == version_key(version):
                return
            # Sem settings.json é a primeira instalação; com ele, é atualização.
            self._whats_new_first_install = not self.settings.path.exists()
            if not self.settings.get("show_whats_new", True):
                self._mark_version_seen(version)
                return
            self._whats_new_timer = wx.CallLater(3000, self._on_whats_new_timer)
        except Exception:
            pass

    @staticmethod
    def _can_show_whats_new():
        """Evita a janela em modo seguro e em instalações automatizadas."""
        try:
            import globalVars

            args = getattr(globalVars, "appArgs", None)
            if args is None:
                return True
            for name in ("secure", "install", "createPortable"):
                if getattr(args, name, False):
                    return False
        except Exception:
            pass
        return True

    def _on_whats_new_timer(self):
        self._whats_new_timer = None
        try:
            version = self._addon_version()
            seen = str(self.settings.get("installed_version", "") or "")
            if not version or version_key(seen) == version_key(version):
                return
            first_install = bool(getattr(self, "_whats_new_first_install", False))
            entries = news_for(seen, version, first_install=first_install)
            self._display_whats_new(version, entries, first_install)
        except Exception:
            pass

    def _open_whats_new(self):
        """Abre a janela de novidades pelo botão das configurações."""
        version = self._addon_version()
        if not version:
            ui.message("Versão do add-on não encontrada.")
            return
        self._display_whats_new(version, current_news(version), False)

    def _display_whats_new(self, version, entries, first_install):
        if not entries:
            return
        parent = getattr(gui, "mainFrame", None) or wx.GetApp().GetTopWindow()
        try:
            dialog = WhatsNewDialog(parent, version, entries, first_install)
        except Exception:
            return
        try:
            dialog.ShowModal()
        finally:
            try:
                dialog.Destroy()
            except Exception:
                pass
        self._mark_version_seen(version)

    def _mark_version_seen(self, version):
        self.settings["installed_version"] = version
        try:
            self.settings.save()
        except OSError:
            pass

    # -- utilidades --------------------------------------------------------

    def _current_location(self):
        return self.store.default

    def _require_location(self):
        location = self._current_location()
        if location is None:
            ui.message(
                "Nenhum local salvo. Abra as configurações do AccessWeather "
                "para adicionar um local."
            )
        return location

    def _forecast_for(self, location):
        """Devolve a previsão, usando o cache quando ainda estiver válido."""
        cached = self.cache.get(location.key)
        if cached is not None:
            try:
                forecast = parse_forecast(
                    cached, place=location.place, units=unit_codes(self.settings)
                )
                self.forecasts[location.key] = forecast
                return forecast
            except WeatherError:
                pass
        try:
            payload = fetch_forecast_payload(location.place, self.settings)
            forecast = parse_forecast(
                payload, place=location.place, units=unit_codes(self.settings)
            )
        except WeatherError as error:
            wx.CallAfter(ui.message, str(error))
            return None
        self.cache.set(location.key, payload)
        try:
            self.cache.save()
        except OSError:
            pass
        self.forecasts[location.key] = forecast
        return forecast

    def _spoken_weather(self, location, forecast):
        fields = (
            self.settings.get("announce_fields") or DEFAULT_NOTIFICATION_FIELDS
        )
        body = notification_body(
            location,
            forecast,
            fields,
            unit_symbols(self.settings),
            self.settings.get("time_format", "24h"),
        )
        name = location.display_name
        return f"{name}: {body}" if name else body

    # -- anúncios ----------------------------------------------------------

    def _announce_weather(self):
        location = self._require_location()
        if location is None:
            return
        if self.settings.get("announce_fetching", False):
            ui.message(f"Buscando previsão para {location.display_name}, aguarde...")
        threading.Thread(
            target=self._weather_worker, args=(location,), daemon=True
        ).start()

    def _weather_worker(self, location):
        forecast = self._forecast_for(location)
        if forecast is None:
            return
        message = self._spoken_weather(location, forecast)
        wx.CallAfter(self._announce_current, message)

    def _announce_current(self, message):
        sequence = ()
        if self.settings.get("beeps_on_announce", False):
            sequence = normalize_sequence(
                self.settings.get("beep_sequence") or DEFAULT_BEEP_SEQUENCE
            )
        if sequence:
            self._sequencer.play(sequence, lambda: ui.message(message))
        else:
            ui.message(message)

    def _announce_days(self):
        location = self._require_location()
        if location is None:
            return
        if self.settings.get("announce_fetching", False):
            ui.message(f"Buscando previsão para {location.display_name}, aguarde...")
        threading.Thread(
            target=self._days_worker, args=(location,), daemon=True
        ).start()

    def _days_worker(self, location):
        forecast = self._forecast_for(location)
        if forecast is None:
            return
        days = forecast.next_days(self.settings.get("daily_days", 7))
        symbols = unit_symbols(self.settings)
        date_format = self.settings.get("date_format", "dmy")
        lines = [day_text(day, symbols, date_format) for day in days]
        if not lines:
            wx.CallAfter(ui.message, "Sem previsão diária disponível.")
            return
        title = f"Próximos dias — {location.display_name}"
        wx.CallAfter(self._show_list, title, lines)

    def _announce_hours(self):
        location = self._require_location()
        if location is None:
            return
        if self.settings.get("announce_fetching", False):
            ui.message(f"Buscando previsão para {location.display_name}, aguarde...")
        threading.Thread(
            target=self._hours_worker, args=(location,), daemon=True
        ).start()

    def _hours_worker(self, location):
        forecast = self._forecast_for(location)
        if forecast is None:
            return
        symbols = unit_symbols(self.settings)
        time_format = self.settings.get("time_format", "24h")
        start = forecast.current.time if forecast.current else None
        points = forecast.hourly_in_window(start)[:24]
        lines = [hour_text(point, symbols, time_format) for point in points]
        if not lines:
            wx.CallAfter(ui.message, "Sem previsão por hora disponível.")
            return
        title = f"Próximas 24 horas — {location.display_name}"
        wx.CallAfter(self._show_list, title, lines)

    def _show_list(self, title, items, header=""):
        if not items:
            ui.message("Sem dados de previsão.")
            return
        if self._list_dialog is not None:
            try:
                self._list_dialog.Destroy()
            except Exception:
                pass
            self._list_dialog = None
        dialog = WeatherListDialog(gui.mainFrame, title, items, header=header)
        dialog.on_close = self._on_list_closed
        self._list_dialog = dialog
        gui.mainFrame.prePopup()
        dialog.Show()
        gui.mainFrame.postPopup()
        dialog.Raise()

    def _on_list_closed(self, dialog):
        if self._list_dialog is dialog:
            self._list_dialog = None

    # -- scripts -----------------------------------------------------------

    @script(
        description=(
            "Clima do local selecionado. Uma vez: condições atuais; "
            "duas: próximas 24 horas; três: próximos dias; "
            "quatro: configurações; cinco: ativa/desativa os anúncios "
            "personalizados deste local"
        ),
        gesture="kb:NVDA+shift+w",
    )
    def script_announceWeather(self, gesture):
        if self._repeat_timer is not None:
            try:
                self._repeat_timer.Stop()
            except Exception:
                pass
            self._repeat_timer = None
        presses = scriptHandler.getLastScriptRepeatCount() + 1
        try:
            timeout = int(config.conf["keyboard"]["multiPressTimeout"])
        except Exception:
            timeout = 500
        self._repeat_timer = wx.CallLater(timeout, self._run_repeat, presses)

    def _run_repeat(self, presses):
        self._repeat_timer = None
        try:
            scriptHandler.clearLastScript()
        except Exception:
            pass
        if presses <= 1:
            self._announce_weather()
        elif presses == 2:
            self._announce_hours()
        elif presses == 3:
            self._announce_days()
        elif presses == 4:
            wx.CallAfter(self._open_settings)
        else:
            self._toggle_notification()

    def _toggle_notification(self):
        location = self._require_location()
        if location is None:
            return
        enabled = not location.notify_hourly
        fields = location.notify_fields or tuple(
            self.settings.get("announce_fields") or DEFAULT_NOTIFICATION_FIELDS
        )
        self.store.set_notification(
            location.key, enabled, fields, location.notify_interval
        )
        self.store.save()
        if enabled:
            self._last_notify[location.key] = datetime.now()
            ui.message(
                f"Anúncios personalizados ativados para {location.display_name}, "
                f"a cada {location.notify_interval} minutos."
            )
        else:
            self._last_notify.pop(location.key, None)
            ui.message(
                f"Anúncios personalizados desativados para "
                f"{location.display_name}."
            )

    # -- anúncios periódicos por local -------------------------------------

    def _on_notify_timer(self):
        now = datetime.now()
        due = []
        for location in self.store.locations:
            if not location.notify_hourly:
                continue
            interval = max(1, int(location.notify_interval)) * 60
            last = self._last_notify.get(location.key)
            if last is None:
                self._last_notify[location.key] = now
                continue
            if (now - last).total_seconds() >= interval:
                self._last_notify[location.key] = now
                due.append(location)
        if due:
            threading.Thread(
                target=self._notify_worker, args=(due,), daemon=True
            ).start()

    def _notify_worker(self, locations):
        symbols = unit_symbols(self.settings)
        time_format = self.settings.get("time_format", "24h")
        items = []
        for location in locations:
            forecast = self._forecast_for(location)
            if forecast is None:
                continue
            body = notification_body(
                location,
                forecast,
                location.notification_fields,
                symbols,
                time_format,
            )
            name = location.display_name
            items.append((location, f"{name}: {body}" if name else body))
        if items:
            wx.CallAfter(self._announce_items, items)

    def _announce_items(self, items):
        """Fala cada anúncio, tocando a sequência de beeps do local antes."""
        def announce(index):
            if index >= len(items):
                return
            location, message = items[index]
            sequence = location.beep_sequence if location.beeps_enabled else ()
            if sequence:
                def done(message=message, index=index):
                    ui.message(message)
                    announce(index + 1)

                self._sequencer.play(sequence, done)
            else:
                ui.message(message)
                announce(index + 1)

        announce(0)

    def _test_announcement(self, location):
        threading.Thread(
            target=self._notify_worker, args=([location],), daemon=True
        ).start()

    # -- prévia de um campo (F2 nas listas de campos) ----------------------

    def _announce_field(self, location, field):
        """Lê um único campo do anúncio para o local indicado."""
        if self._field_preview_running:
            ui.message("Aguarde, ainda buscando os dados.")
            return
        self._field_preview_running = True
        threading.Thread(
            target=self._field_worker, args=(location, field), daemon=True
        ).start()

    def _field_worker(self, location, field):
        try:
            if self.settings.get("announce_fetching", False):
                wx.CallAfter(
                    ui.message,
                    f"Buscando previsão para {location.display_name}, aguarde...",
                )
            forecast = self._forecast_for(location)
            if forecast is None:
                return
            text = field_text(
                field,
                forecast,
                unit_symbols(self.settings),
                self.settings.get("time_format", "24h"),
            )
            wx.CallAfter(
                ui.message,
                text or "Sem dados para este campo no momento.",
            )
        finally:
            self._field_preview_running = False

    # -- configurações -----------------------------------------------------

    def _open_settings(self):
        if NVDASettingsDialog is None:
            ui.message("Configurações do NVDA indisponíveis.")
            return
        popup = getattr(gui.mainFrame, "popupSettingsDialog", None)
        if popup is None:
            popup = gui.mainFrame._popupSettingsDialog
        popup(NVDASettingsDialog, AccessWeatherSettingsPanel)
