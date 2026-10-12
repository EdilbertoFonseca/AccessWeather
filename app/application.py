from __future__ import annotations

import threading
from datetime import datetime

import wx

from .announce import Announcer
from .cache import ForecastCache
from .config import (
    ACTION_LABELS,
    APP_NAME,
    DEFAULT_NOTIFICATION_FIELDS,
    Settings,
    unit_codes,
    unit_symbols,
)
from . import changelog, dialogs, updater
from .alerts import evaluate, parse_rules
from .formatting import (
    DAILY_COLUMNS,
    HOURLY_COLUMNS,
    LOCATION_COLUMNS,
    current_lines,
    current_summary,
    daily_rows,
    day_text,
    hour_text,
    hourly_rows,
    location_row,
    notification_body,
)
from .locations import LocationStore
from .notify import Notifier
from .tray import TrayIcon
from .version import VERSION
from .weather import (
    FORECAST_URL,
    WeatherError,
    build_forecast_params,
    parse_forecast,
    request_json,
    search_places,
)


LOCATION_WIDTHS = (280, 90, 170, 180)
HOURLY_WIDTHS = (70, 110, 170, 140, 110, 90)
DAILY_WIDTHS = (160, 180, 90, 90, 90, 110, 120, 120)


class Controller(wx.Frame):
    """Janela principal: lista de locais, condições atuais, hora a hora e diária."""

    def __init__(self, settings=None, announcer=None, store=None, cache=None):
        super().__init__(None, title=APP_NAME, size=(1020, 640))
        self.settings = settings or Settings()
        self.announcer = announcer or Announcer()
        self.store = store or LocationStore()
        self.cache = cache or ForecastCache(minutes=self.settings.get("cache_minutes", 15))
        self.forecasts: dict = {}
        self.symbols = unit_symbols(self.settings)
        self._closing = False
        self._refreshing = False
        self._rendering = False
        self._refresh_sequence = 0
        self._search_sequence = 0
        self._update_sequence = 0
        self._selected_key = ""
        self.notifier = Notifier(self.settings)
        self._alert_marks = set()

        self._build_ui()
        self._build_menu()
        self.tray = TrayIcon(self)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self.timer)
        self.notify_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_notify_timer, self.notify_timer)
        self.notify_timer.Start(60 * 1000)
        self._last_hourly_notify = {}
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Centre()

        self._show_cached()
        wx.CallAfter(self._initial_refresh)

    # -- construção da interface -------------------------------------------

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.HORIZONTAL)

        left = wx.BoxSizer(wx.VERTICAL)
        caption = wx.StaticText(panel, label="Locais")
        left.Add(caption, 0, wx.ALL, 6)
        self.location_list = self._make_list(
            panel, LOCATION_COLUMNS, LOCATION_WIDTHS, "Lista de locais"
        )
        left.Add(self.location_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        right = wx.BoxSizer(wx.VERTICAL)
        self.current_text = wx.StaticText(panel, label="Nenhum local selecionado.")
        self.current_text.SetName("Condições atuais")
        font = self.current_text.GetFont()
        font.MakeBold()
        font.SetPointSize(font.GetPointSize() + 1)
        self.current_text.SetFont(font)
        right.Add(self.current_text, 0, wx.ALL | wx.EXPAND, 8)

        self.notebook = wx.Notebook(panel)
        hourly_page, self.hourly_list = self._make_page(
            HOURLY_COLUMNS, HOURLY_WIDTHS, "Previsão hora a hora"
        )
        self.notebook.AddPage(hourly_page, "Hora a hora")
        daily_page, self.daily_list = self._make_page(
            DAILY_COLUMNS, DAILY_WIDTHS, "Previsão diária"
        )
        self.notebook.AddPage(daily_page, "Diária")
        right.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 6)

        outer.Add(left, 0, wx.EXPAND)
        outer.Add(right, 1, wx.EXPAND)
        panel.SetSizer(outer)

        self.CreateStatusBar()
        self.SetStatusText(f"{APP_NAME} {VERSION}")

        self._bind_list_events()

    def _make_list(self, parent, columns, widths, name):
        control = wx.ListCtrl(
            parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN
        )
        control.SetName(name)
        for index, title in enumerate(columns):
            control.InsertColumn(index, title, width=widths[index])
        return control

    def _make_page(self, columns, widths, name):
        page = wx.Panel(self.notebook, name=name)
        control = self._make_list(page, columns, widths, name)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(control, 1, wx.EXPAND | wx.ALL, 4)
        page.SetSizer(sizer)
        return page, control

    def _build_menu(self):
        bar = wx.MenuBar()

        file_menu = wx.Menu()
        self._menu_item(file_menu, "Adicionar local...\tCtrl+N", "add_location")
        self._menu_item(file_menu, "Atualizar agora\tF5", "refresh_now")
        file_menu.AppendSeparator()
        self._menu_item(file_menu, "Sair", "quit")
        bar.Append(file_menu, "Arquivo")

        view_menu = wx.Menu()
        self._menu_item(view_menu, "Ir para a lista de locais", "open_locations")
        self._menu_item(view_menu, "Trocar de local", "cycle_location")
        self._menu_item(view_menu, "Copiar previsão do local atual", "copy_current")
        bar.Append(view_menu, "Exibir")

        tools_menu = wx.Menu()
        self._menu_item(tools_menu, "Configurações...", "open_settings")
        self._menu_item(tools_menu, "Alertas...", "open_alerts")
        self._menu_item(tools_menu, "Verificar atualizações...", "check_update")
        bar.Append(tools_menu, "Ferramentas")

        help_menu = wx.Menu()
        self._menu_item(help_menu, "Changelog...", "show_changelog")
        self._menu_item(help_menu, "Sobre", "about")
        bar.Append(help_menu, "Ajuda")

        self.SetMenuBar(bar)

    def _menu_item(self, menu, label, action):
        item = menu.Append(wx.ID_ANY, label)
        self.Bind(wx.EVT_MENU, lambda event, name=action: self.dispatch(name), item)
        return item

    def _bind_list_events(self):
        self.location_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_location_selected)
        self.location_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_location_activated)
        self.location_list.Bind(wx.EVT_CONTEXT_MENU, self._on_location_context)
        self.location_list.Bind(wx.EVT_KEY_DOWN, self._on_location_key)
        self.hourly_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_hourly_activated)
        self.daily_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_daily_activated)

    # -- anúncios ----------------------------------------------------------

    def _announce_status(self, message, category="system"):
        if self.settings["announcements"].get(category, True):
            self.announcer.speak(message)

    def _current_location(self):
        return self.store.find(self._selected_key) or self.store.default

    def _announce_current(self, category="forecast"):
        location = self._current_location()
        forecast = self.forecasts.get(location.key) if location else None
        self._announce_status(current_summary(location, forecast, self.symbols), category)

    # -- renderização ------------------------------------------------------

    def _fill_list(self, control, rows):
        control.Freeze()
        try:
            control.DeleteAllItems()
            for row in rows:
                index = control.InsertItem(control.GetItemCount(), str(row[0]))
                for column, value in enumerate(row[1:], start=1):
                    control.SetItem(index, column, str(value))
        finally:
            control.Thaw()

    def _show_cached(self):
        for location in self.store:
            payload = self.cache.peek(location.key)
            if payload is None:
                continue
            try:
                self.forecasts[location.key] = parse_forecast(
                    payload, place=location.place, units=unit_codes(self.settings)
                )
            except WeatherError:
                continue
        if not self._selected_key:
            default = self.store.default
            self._selected_key = default.key if default else ""
        self._render_location_list()
        self._render_selected()

    def _render_location_list(self):
        rows = [
            location_row(location, self.forecasts.get(location.key), self.symbols)
            for location in self.store
        ]
        self._rendering = True
        try:
            self._fill_list(self.location_list, rows)
            index = self.store.index_of(self._selected_key)
            if index < 0 and self.store.locations:
                index = 0
                self._selected_key = self.store.locations[0].key
            if index >= 0:
                self.location_list.Select(index)
                self.location_list.Focus(index)
        finally:
            self._rendering = False

    def _render_selected(self):
        location = self._current_location()
        forecast = self.forecasts.get(location.key) if location else None
        self.current_text.SetLabel(
            current_lines(location, forecast, self.symbols, self.settings["time_format"])
        )
        self.current_text.InvalidateBestSize()
        self._fill_list(
            self.hourly_list,
            hourly_rows(forecast, self.symbols, self.settings["time_format"]),
        )
        self._fill_list(
            self.daily_list,
            daily_rows(forecast, self.symbols, self.settings["date_format"]),
        )
        self.current_text.GetParent().Layout()

    # -- eventos de lista --------------------------------------------------

    def _on_location_selected(self, event):
        if self._rendering:
            return
        index = event.GetIndex()
        if index < 0 or index >= len(self.store.locations):
            return
        location = self.store.locations[index]
        if location.key == self._selected_key:
            return
        self._selected_key = location.key
        self._render_selected()
        self._announce_current("location")

    def _on_location_activated(self, event):
        self._announce_current("forecast")

    def _on_hourly_activated(self, event):
        index = event.GetIndex()
        forecast = self.forecasts.get(self._selected_key)
        if forecast is None or index < 0 or index >= len(forecast.hourly):
            return
        self._announce_status(
            hour_text(forecast.hourly[index], self.symbols, self.settings["time_format"]),
            "forecast",
        )

    def _on_daily_activated(self, event):
        index = event.GetIndex()
        forecast = self.forecasts.get(self._selected_key)
        if forecast is None or index < 0 or index >= len(forecast.daily):
            return
        self._announce_status(
            day_text(
                forecast.daily[index], self.symbols, self.settings["date_format"]
            ),
            "forecast",
        )

    def _on_location_key(self, event):
        code = event.GetKeyCode()
        if code == wx.WXK_DELETE:
            self.dispatch("remove_location")
            return
        if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._announce_current("forecast")
            return
        event.Skip()

    def _on_location_context(self, event):
        position = event.GetPosition()
        index = -1
        if position != wx.DefaultPosition and position.x >= 0 and position.y >= 0:
            index, _ = self.location_list.HitTest(position)
        if index < 0:
            index = self.location_list.GetFirstSelected()
        if 0 <= index < len(self.store.locations):
            self._selected_key = self.store.locations[index].key
            self.location_list.Select(index)
            self.location_list.Focus(index)
            self._render_selected()
        self._show_context_menu(index)

    def _show_context_menu(self, index):
        menu = wx.Menu()
        entries = [
            ("Adicionar local...", "add_location"),
            (None, None),
            ("Renomear...", "rename_location"),
            ("Favoritar ou desfavoritar", "toggle_favorite_location"),
            ("Definir como padrão", "set_default_location"),
            ("Copiar previsão", "copy_current"),
            ("Personalizar notificação de clima...", "customize_notification"),
        ]
        if index >= 0:
            entries.append((None, None))
            entries.append(("Remover local", "remove_location"))
        for label, action in entries:
            if label is None:
                menu.AppendSeparator()
                continue
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(
                wx.EVT_MENU, lambda event, name=action: self.dispatch(name), item
            )
        self.PopupMenu(menu)
        menu.Destroy()

    # -- atualização -------------------------------------------------------

    def _initial_refresh(self):
        if not self.store.locations:
            self._announce_status(
                "Nenhum local salvo. Use Adicionar local, no menu Arquivo.",
                "location",
            )
            return
        if self.settings.get("refresh_on_start", True):
            self._start_refresh()
        else:
            self._schedule_next_refresh()

    def _on_timer(self, event):
        self._start_refresh()

    def _on_notify_timer(self, event):
        self._check_hourly_notifications()

    def _check_hourly_notifications(self):
        now = datetime.now()
        for location in self.store.locations:
            if not location.notify_hourly:
                continue
            last = self._last_hourly_notify.get(location.key)
            if last is None:
                # Primeira observação: espera o intervalo antes de avisar.
                self._last_hourly_notify[location.key] = now
                continue
            due_seconds = max(1, location.notify_interval) * 60
            if (now - last).total_seconds() < due_seconds:
                continue
            forecast = self.forecasts.get(location.key)
            if forecast is None or forecast.current is None:
                continue
            fields = location.notification_fields or DEFAULT_NOTIFICATION_FIELDS
            text = notification_body(
                location, forecast, fields, self.symbols,
                self.settings.get("time_format", "24h"),
            )
            if not text:
                continue
            self.notifier.forecast(location.full_label, text)
            self._announce_status(f"{location.full_label}: {text}", "notifications")
            self._last_hourly_notify[location.key] = now

    def _schedule_next_refresh(self):
        minutes = max(5, int(self.settings.get("refresh_minutes", 30)))
        if self.timer.IsRunning():
            self.timer.Stop()
        self.timer.Start(minutes * 60 * 1000)

    def _start_refresh(self, targets=None, force=False):
        if self._closing or self._refreshing:
            return
        wanted = list(targets) if targets is not None else list(self.store.locations)
        if not wanted:
            return
        self._refreshing = True
        self._refresh_sequence += 1
        sequence = self._refresh_sequence
        self._announce_status(
            f"Atualizando {len(wanted)} local(is)...", "refresh"
        )
        threading.Thread(
            target=self._refresh_worker,
            args=(sequence, wanted, force),
            daemon=True,
        ).start()

    def _refresh_worker(self, sequence, targets, force):
        results = []
        for location in targets:
            key = location.key
            payload = None if force else self.cache.get(key)
            if payload is not None:
                results.append((key, payload, None))
                continue
            try:
                params = build_forecast_params(location.place, self.settings)
                payload = request_json(FORECAST_URL, params)
            except WeatherError as exc:
                results.append((key, None, str(exc)))
                continue
            self.cache.set(key, payload)
            results.append((key, payload, None))
        try:
            self.cache.save()
        except OSError:
            pass
        wx.CallAfter(self._apply_refresh, sequence, results)

    def _apply_refresh(self, sequence, results):
        if self._closing or sequence != self._refresh_sequence:
            return
        self._refreshing = False
        errors = []
        updated = 0
        for key, payload, error in results:
            if error:
                errors.append(error)
                continue
            location = self.store.find(key)
            if location is None:
                continue
            try:
                self.forecasts[key] = parse_forecast(
                    payload, place=location.place, units=unit_codes(self.settings)
                )
            except WeatherError:
                continue
            updated += 1
        self._render_location_list()
        self._render_selected()
        self._schedule_next_refresh()
        alerts_fired = self._run_alerts()
        if errors:
            self._announce_status(errors[0], "refresh")
        elif updated and not alerts_fired:
            self._announce_status("Previsão atualizada.", "refresh")

    def _run_alerts(self) -> bool:
        fired = False
        for location in self.store.locations:
            if not location.notify:
                continue
            rules = parse_rules(location.alerts)
            if not rules:
                continue
            forecast = self.forecasts.get(location.key)
            if forecast is None:
                continue
            for hit in evaluate(forecast, rules, self.symbols):
                mark = (location.key, hit.rule.key, hit.moment)
                if mark in self._alert_marks:
                    continue
                self._alert_marks.add(mark)
                fired = True
                if hit.rule.toast:
                    self.notifier.alert(location.full_label, hit.message)
                if hit.rule.announce:
                    self._announce_status(hit.message, "alerts")
        return fired

    # -- ações -------------------------------------------------------------

    def dispatch(self, action):
        if self._closing:
            return False
        handler = getattr(self, f"_action_{action}", None)
        if handler is None or action not in ACTION_LABELS:
            return False
        handler()
        return True

    def _action_show_window(self):
        if self.IsIconized():
            self.Iconize(False)
        self.Show()
        self.Raise()
        self.location_list.SetFocus()

    def _action_open_locations(self):
        self._present(self)
        self.location_list.SetFocus()

    def _action_add_location(self):
        with wx.TextEntryDialog(
            self, "Nome do local:", "Adicionar local"
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            query = dialog.GetValue().strip()
        if not query:
            self._announce_status("Nenhum nome informado.", "location")
            return
        self._announce_status(f"Buscando {query}...", "location")
        self._search_sequence += 1
        sequence = self._search_sequence
        threading.Thread(
            target=self._search_worker, args=(sequence, query), daemon=True
        ).start()

    def _search_worker(self, sequence, query):
        try:
            places = search_places(query, count=10)
            error = None
        except WeatherError as exc:
            places = ()
            error = str(exc)
        wx.CallAfter(self._present_search_results, sequence, query, places, error)

    def _present_search_results(self, sequence, query, places, error):
        if self._closing or sequence != self._search_sequence:
            return
        if error:
            self._announce_status(error, "refresh")
            return
        if not places:
            self._announce_status(f"Nenhum local encontrado para {query}.", "location")
            return
        if len(places) == 1:
            chosen = places[0]
        else:
            labels = [place.label for place in places]
            with wx.SingleChoiceDialog(
                self, f"Resultados para {query}:", "Adicionar local", labels
            ) as dialog:
                if dialog.ShowModal() != wx.ID_OK:
                    return
                chosen = places[dialog.GetSelection()]
        location = self.store.add(chosen)
        self.store.save()
        self.cache.prune(self.store.keys())
        self._selected_key = location.key
        self._announce_status(f"{location.full_label} adicionado.", "location")
        self._render_location_list()
        self._render_selected()
        self._start_refresh([location], force=True)

    def _action_remove_location(self):
        location = self._current_location()
        if location is None:
            self._announce_status("Nenhum local para remover.", "location")
            return
        with wx.MessageDialog(
            self,
            f"Remover {location.full_label}?",
            APP_NAME,
            wx.YES_NO | wx.ICON_QUESTION,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_YES:
                return
        key = location.key
        index = self.store.index_of(key)
        self.store.remove(key)
        self.forecasts.pop(key, None)
        self.cache.drop(key)
        self.store.save()
        try:
            self.cache.save()
        except OSError:
            pass
        if self.store.locations:
            index = max(0, min(index, len(self.store.locations) - 1))
            self._selected_key = self.store.locations[index].key
        else:
            self._selected_key = ""
        self._render_location_list()
        self._render_selected()
        self._announce_status(f"{location.full_label} removido.", "location")

    def _action_rename_location(self):
        location = self._current_location()
        if location is None:
            self._announce_status("Nenhum local selecionado.", "location")
            return
        with wx.TextEntryDialog(
            self,
            "Apelido do local (deixe em branco para usar o nome real):",
            "Renomear local",
            location.alias,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            alias = dialog.GetValue().strip()
        self.store.set_alias(location.key, alias)
        self.store.save()
        self._render_location_list()
        self._render_selected()
        self._announce_status(f"Local renomeado para {location.display_name}.", "location")

    def _action_toggle_favorite_location(self):
        location = self._current_location()
        if location is None:
            self._announce_status("Nenhum local selecionado.", "location")
            return
        favorite = self.store.toggle_favorite(location.key)
        self.store.save()
        self._render_location_list()
        state = "favorito" if favorite else "não favorito"
        self._announce_status(f"{location.full_label} agora é {state}.", "location")

    def _action_set_default_location(self):
        location = self._current_location()
        if location is None:
            self._announce_status("Nenhum local selecionado.", "location")
            return
        self.store.set_default(location.key)
        self.store.save()
        self._announce_status(f"{location.full_label} é o local padrão.", "location")

    def _action_customize_notification(self):
        location = self._current_location()
        if location is None:
            self._announce_status(
                "Selecione um local para personalizar a notificação.", "notifications"
            )
            return
        self._present(self)
        forecast = self.forecasts.get(location.key)
        with dialogs.WeatherNotificationDialog(
            self, location, forecast, self.symbols, self.notifier
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            self.store.set_notification(
                location.key,
                dialog.enabled.GetValue(),
                dialog.selected_fields(),
                dialog.interval(),
            )
            self.store.save()
        if location.notify_hourly:
            self._announce_status(
                f"Notificação de clima ativada para {location.full_label}, a cada "
                f"{location.notify_interval} minutos.",
                "notifications",
            )
        else:
            self._announce_status(
                f"Notificação de clima desativada para {location.full_label}.",
                "notifications",
            )

    def _action_copy_current(self):
        location = self._current_location()
        forecast = self.forecasts.get(location.key) if location else None
        text = current_summary(location, forecast, self.symbols)
        if self._copy_text(text):
            self._announce_status("Previsão copiada.", "forecast")
        else:
            self._announce_status("Não foi possível copiar a previsão.", "system")

    def _action_refresh_now(self):
        self._start_refresh(force=True)

    def _action_cycle_location(self):
        if not self.store.locations:
            self._announce_status("Nenhum local salvo.", "location")
            return
        following = self.store.cycle(self._selected_key, 1)
        if following is None:
            return
        self._selected_key = following.key
        index = self.store.index_of(following.key)
        if index >= 0:
            self.location_list.Select(index)
            self.location_list.Focus(index)
        self._render_selected()
        self._announce_current("location")

    def _action_open_alerts(self):
        location = self._current_location()
        if location is None:
            self._announce_status("Adicione um local antes de criar alertas.", "alerts")
            return
        self._present(self)
        with dialogs.AlertsDialog(self, location, self.store) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            dialog.save()
        self._alert_marks.clear()
        rules = parse_rules(location.alerts)
        self._announce_status(
            f"{len(rules)} regra(s) de alerta para {location.full_label}.", "alerts"
        )

    def _action_open_settings(self):
        self._present(self)
        with dialogs.SettingsDialog(self, self.settings) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            self.settings.values.update(dialog.values())
            self.settings.save()
        self.symbols = unit_symbols(self.settings)
        self.cache.minutes = max(1, int(self.settings.get("cache_minutes", 15)))
        self._render_location_list()
        self._render_selected()
        self._schedule_next_refresh()
        self._announce_status("Configurações salvas.", "system")

    def _action_check_update(self):
        self._announce_status("Verificando atualizações...", "update")
        self._update_sequence += 1
        sequence = self._update_sequence
        threading.Thread(
            target=self._update_worker, args=(sequence,), daemon=True
        ).start()

    def _update_worker(self, sequence):
        try:
            remote = updater.check_for_update(VERSION)
            error = None
        except Exception as exc:
            remote = None
            error = str(exc)
        wx.CallAfter(self._present_update, sequence, remote, error)

    def _present_update(self, sequence, remote, error):
        if self._closing or sequence != self._update_sequence:
            return
        if error:
            self._announce_status(error, "update")
            return
        if not remote:
            self._announce_status(f"{APP_NAME} já está atualizado.", "update")
            return
        version = str(remote.get("version") or "")
        notes = str(remote.get("notes") or remote.get("changelog") or "").strip()
        message = f"Versão {version} disponível."
        if notes:
            message = f"{message}\n\n{notes}"
        message = f"{message}\n\nBaixar e instalar agora? O programa será reiniciado."
        with wx.MessageDialog(self, message, APP_NAME, wx.YES_NO | wx.ICON_QUESTION) as dialog:
            if dialog.ShowModal() != wx.ID_YES:
                return
        download_url = str(remote.get("download_url") or remote.get("url") or "")
        if not download_url:
            dialogs.show_error(self, "A atualização não informou o endereço do arquivo.")
            return
        self._install_update(download_url, version)

    def _install_update(self, download_url, version):
        progress = wx.ProgressDialog(
            "Atualizando", "Baixando a atualização...", maximum=100, parent=self,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE,
        )

        def report(fraction):
            if fraction is None:
                return
            percent = int(max(0.0, min(1.0, fraction)) * 100)
            wx.CallAfter(progress.Update, percent, f"Baixando... {percent}%")

        try:
            updater.apply_update(
                download_url, progress_callback=report, target_version=version
            )
        except Exception as exc:
            progress.Destroy()
            dialogs.show_error(self, f"Não foi possível atualizar: {exc}")
            return
        progress.Destroy()
        self._announce_status("Atualização baixada. Reiniciando...", "update")
        self._shutdown()

    def _action_show_changelog(self):
        self._announce_status("Carregando o changelog...", "system")
        self._update_sequence += 1
        sequence = self._update_sequence
        threading.Thread(
            target=self._changelog_worker, args=(sequence,), daemon=True
        ).start()

    def _changelog_worker(self, sequence):
        try:
            text = changelog.fetch_changelog()
        except Exception:
            text = changelog.FALLBACK_CHANGELOG
        wx.CallAfter(self._present_changelog, sequence, text)

    def _present_changelog(self, sequence, text):
        if self._closing or sequence != self._update_sequence:
            return
        self._present(self)
        dialogs.TextReportDialog(self, f"Changelog do {APP_NAME}", text).ShowModal()

    def _action_about(self):
        self._present(self)
        dialogs.AboutDialog(self).ShowModal()

    def _action_quit(self):
        self._shutdown()

    # -- utilidades --------------------------------------------------------

    def _copy_text(self, text):
        if not text:
            return False
        if not wx.TheClipboard.Open():
            return False
        try:
            return bool(wx.TheClipboard.SetData(wx.TextDataObject(text)))
        finally:
            wx.TheClipboard.Close()

    def _present(self, window):
        window.Show()
        window.Raise()
        try:
            window.RequestUserAttention()
        except Exception:
            pass

    def _on_close(self, event):
        if self.settings["close_to_tray"] and not self._closing:
            self.Hide()
            return
        self._shutdown()

    def _shutdown(self):
        self._closing = True
        try:
            if self.timer.IsRunning():
                self.timer.Stop()
        except Exception:
            pass
        try:
            if self.notify_timer.IsRunning():
                self.notify_timer.Stop()
        except Exception:
            pass
        try:
            self.tray.RemoveIcon()
            self.tray.Destroy()
        except Exception:
            pass
        self.Destroy()


def run():
    app = wx.App()
    controller = Controller()
    if not controller.settings["startup_minimized"]:
        controller.Show()
    else:
        controller.Hide()
    controller._announce_status(f"{APP_NAME} iniciado.", "startup")
    app.MainLoop()
