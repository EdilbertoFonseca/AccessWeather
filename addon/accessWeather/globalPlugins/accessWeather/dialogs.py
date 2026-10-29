"""Diálogos do AccessWeather para NVDA: busca de local e configurações."""

import threading

import ui
import wx

try:
    from gui.settingsDialogs import SettingsPanel
except Exception:  # fora do NVDA (testes offline)
    SettingsPanel = wx.Panel

from .core.beeps import (
    BEEP,
    BEEP_DURATION_DEFAULT,
    BEEP_DURATION_MAX,
    BEEP_DURATION_MIN,
    DEFAULT_BEEP_SEQUENCE,
    FREQUENCY_DEFAULT,
    FREQUENCY_MAX,
    FREQUENCY_MIN,
    SILENCE,
    SILENCE_DURATION_DEFAULT,
    SILENCE_DURATION_MAX,
    SILENCE_DURATION_MIN,
    STEP_TYPES,
    normalize_sequence,
    normalize_step,
    sequence_summary,
    step_label,
)
from .core.config import (
    DEFAULT_NOTIFICATION_FIELDS,
    DATE_FORMATS,
    NOTIFICATION_INTERVAL_CHOICES,
    NOTIFICATION_INTERVAL_MAX,
    NOTIFICATION_INTERVAL_MIN,
    TIME_FORMATS,
    UNIT_GROUPS,
    WEATHER_NOTIFICATION_FIELDS,
    WIND_OPTIONS,
    clamp_notification_interval,
)
from .core.weather import search_places
from .playback import BeepSequencer


def _ordered_field_keys(stored):
    keys = [
        key for key in (stored or ()) if key in WEATHER_NOTIFICATION_FIELDS
    ]
    if not keys:
        keys = [
            key
            for key in DEFAULT_NOTIFICATION_FIELDS
            if key in WEATHER_NOTIFICATION_FIELDS
        ]
    return list(keys) + [
        key for key in WEATHER_NOTIFICATION_FIELDS if key not in keys
    ]


class SearchLocationDialog(wx.Dialog):
    """Pesquisa um local pelo nome e devolve o escolhido em `selected`."""

    def __init__(self, parent):
        super().__init__(parent, title="Pesquisar local")
        self.selected = None
        self._results = []
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(panel, label="Nome do local:"), 0, wx.ALL, 5)
        self.query_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        sizer.Add(self.query_ctrl, 0, wx.EXPAND | wx.ALL, 5)

        search_button = wx.Button(panel, label="&Pesquisar")
        sizer.Add(search_button, 0, wx.ALL, 5)

        sizer.Add(wx.StaticText(panel, label="Resultados:"), 0, wx.ALL, 5)
        self.results_list = wx.ListBox(panel, size=(-1, 160), style=wx.LB_SINGLE)
        sizer.Add(self.results_list, 1, wx.EXPAND | wx.ALL, 5)

        button_row = wx.BoxSizer(wx.HORIZONTAL)
        ok_button = wx.Button(panel, wx.ID_OK, "OK")
        cancel_button = wx.Button(panel, wx.ID_CANCEL, "Cancelar")
        button_row.Add(ok_button, 0, wx.ALL, 5)
        button_row.Add(cancel_button, 0, wx.ALL, 5)
        sizer.Add(button_row, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        search_button.Bind(wx.EVT_BUTTON, self._on_search)
        self.query_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.results_list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_ok)
        ok_button.Bind(wx.EVT_BUTTON, self._on_ok)

        panel.SetSizer(sizer)
        sizer.Fit(panel)
        self.Fit()
        self.query_ctrl.SetFocus()

    def _on_search(self, event):
        query = self.query_ctrl.GetValue().strip()
        if not query:
            return
        self.results_list.Set(["Pesquisando..."])
        self.results_list.Disable()
        threading.Thread(
            target=self._search_worker, args=(query,), daemon=True
        ).start()

    def _search_worker(self, query):
        try:
            results = search_places(query)
        except Exception:
            results = ()
        wx.CallAfter(self._show_results, results)

    def _show_results(self, results):
        self.results_list.Enable(True)
        if not results:
            self._results = []
            self.results_list.Set(["Nenhum local encontrado."])
            ui.message("Nenhum local encontrado.")
            return
        self._results = list(results)
        self.results_list.Set([place.label for place in self._results])
        self.results_list.SetSelection(0)
        self.results_list.SetFocus()

    def _on_ok(self, event):
        selection = self.results_list.GetSelection()
        if 0 <= selection < len(self._results):
            self.selected = self._results[selection]
            self.EndModal(wx.ID_OK)
        else:
            ui.message("Pesquise e selecione um local primeiro.")


class WhatsNewDialog(wx.Dialog):
    """Resumo das novidades de uma ou mais versões, para ler com calma."""

    def __init__(self, parent, version, entries, first_install=False):
        title = (
            "Bem-vindo ao AccessWeather"
            if first_install
            else f"Novidades do AccessWeather {version}"
        )
        super().__init__(
            parent,
            title=title,
            size=(620, 540),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        if first_install:
            heading = (
                f"Bem-vindo ao AccessWeather {version}! "
                "Atalho principal: NVDA+Shift+W."
            )
        else:
            heading = (
                f"Atualizado para a versão {version}. Resumo do que mudou:"
            )
        sizer.Add(wx.StaticText(panel, label=heading), 0, wx.ALL, 12)
        self.text = wx.TextCtrl(
            panel,
            value=self._build_text(version, entries, first_install),
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="Novidades",
        )
        sizer.Add(self.text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        close_button = wx.Button(panel, wx.ID_OK, "&OK")
        close_button.SetDefault()
        buttons.Add(close_button, 0)
        sizer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 12)

        panel.SetSizer(sizer)
        close_button.Bind(wx.EVT_BUTTON, self._on_ok)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.text.SetInsertionPoint(0)
        self.text.SetFocus()

    @staticmethod
    def _build_text(version, entries, first_install):
        lines = []
        if first_install:
            lines.extend(
                (
                    "Atalho NVDA+Shift+W: um toque anuncia o clima atual, dois "
                    "as próximas horas, três os próximos dias e quatro abre as "
                    "configurações do AccessWeather.",
                    "",
                )
            )
        for entry_version, bullets in entries or ():
            lines.append(f"Versão {entry_version}")
            lines.extend(f"- {bullet}" for bullet in bullets)
            lines.append("")
        lines.append(
            "Para rever este resumo, abra Preferências, Configurações, "
            "AccessWeather e use o botão Novidades desta versão."
        )
        return "\n".join(lines).strip()

    def _on_ok(self, event):
        self.EndModal(wx.ID_OK)

    def _on_char_hook(self, event):
        if event.GetKeyCode() in (wx.WXK_ESCAPE, wx.WXK_RETURN):
            self.EndModal(wx.ID_OK)
            return
        event.Skip()


class AccessWeatherSettingsPanel(SettingsPanel):
    """Página de configurações do AccessWeather dentro do NVDA."""

    title = "AccessWeather"
    plugin = None

    def makeSettings(self, settingsSizer):
        plugin = self.plugin
        if plugin is None:
            settingsSizer.Add(
                wx.StaticText(self, label="AccessWeather indisponível."),
                0, wx.ALL, 5,
            )
            return
        self.settings = plugin.settings
        self.store = plugin.store
        self.sequencer = BeepSequencer()
        self.tester = plugin._test_announcement
        self.field_previewer = getattr(plugin, "_announce_field", None)
        self._locations = list(self.store.locations)
        self._default_key = self.store.default_key

        panel = self
        sizer = settingsSizer
        settings = self.settings

        sizer.Add(
            wx.StaticText(
                panel,
                label="Locais salvos (o marcado como padrão é usado nos anúncios):",
            ),
            0, wx.ALL, 5,
        )
        self.locations_list = wx.ListBox(
            panel, size=(-1, 140), style=wx.LB_SINGLE
        )
        sizer.Add(self.locations_list, 1, wx.EXPAND | wx.ALL, 5)

        location_buttons = wx.BoxSizer(wx.HORIZONTAL)
        add_button = wx.Button(panel, label="&Adicionar...")
        remove_button = wx.Button(panel, label="&Remover")
        up_button = wx.Button(panel, label="&Subir")
        down_button = wx.Button(panel, label="&Descer")
        default_button = wx.Button(panel, label="Definir como &padrão")
        customize_button = wx.Button(panel, label="Personalizar &alertas...")
        for button in (
            add_button, remove_button, up_button, down_button, default_button,
            customize_button,
        ):
            location_buttons.Add(button, 0, wx.ALL, 3)
        sizer.Add(location_buttons, 0, wx.ALL, 2)
        add_button.Bind(wx.EVT_BUTTON, self._on_add)
        remove_button.Bind(wx.EVT_BUTTON, self._on_remove)
        up_button.Bind(wx.EVT_BUTTON, self._on_move_up)
        down_button.Bind(wx.EVT_BUTTON, self._on_move_down)
        default_button.Bind(wx.EVT_BUTTON, self._on_set_default)
        customize_button.Bind(wx.EVT_BUTTON, self._on_customize_alerts)

        sizer.Add(
            wx.StaticText(
                panel,
                label="O que anunciar; Alt+setas muda a ordem; F2 lê o valor:",
            ),
            0, wx.LEFT | wx.RIGHT, 5,
        )
        self._field_keys = self._initial_field_order(settings)
        checked = set(
            settings.get("announce_fields") or DEFAULT_NOTIFICATION_FIELDS
        )
        self.fields_list = wx.CheckListBox(
            panel,
            choices=[WEATHER_NOTIFICATION_FIELDS[key] for key in self._field_keys],
            size=(-1, 130),
            name="Campos do anúncio",
        )
        for index, key in enumerate(self._field_keys):
            self.fields_list.Check(index, key in checked)
        self.fields_list.Bind(wx.EVT_KEY_DOWN, self._on_fields_key)
        sizer.Add(self.fields_list, 1, wx.EXPAND | wx.ALL, 5)

        units_row, self.units_combo = self._make_combo(
            panel, sizer, "Unidades:", UNIT_GROUPS, settings.get("units", "metric")
        )
        wind_row, self.wind_combo = self._make_combo(
            panel, sizer, "Vento:", WIND_OPTIONS, settings.get("units_wind", "")
        )
        time_row, self.time_combo = self._make_combo(
            panel, sizer, "Formato de hora:", TIME_FORMATS,
            settings.get("time_format", "24h"),
        )
        date_row, self.date_combo = self._make_combo(
            panel, sizer, "Formato de data:", DATE_FORMATS,
            settings.get("date_format", "dmy"),
        )

        days_row = wx.BoxSizer(wx.HORIZONTAL)
        days_row.Add(
            wx.StaticText(panel, label="Dias na previsão estendida:"),
            0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8,
        )
        self.days_spin = wx.SpinCtrl(
            panel, min=1, max=16, initial=int(settings.get("daily_days", 7))
        )
        days_row.Add(self.days_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(days_row, 0, wx.ALL, 5)

        self.fetching_check = wx.CheckBox(
            panel, label='Dizer "Buscando previsão..." ao carregar'
        )
        self.fetching_check.SetValue(bool(settings.get("announce_fetching", False)))
        sizer.Add(self.fetching_check, 0, wx.ALL, 5)

        self.whats_new_check = wx.CheckBox(
            panel,
            label="Mostrar novidades ao iniciar depois de uma atualização",
        )
        self.whats_new_check.SetValue(bool(settings.get("show_whats_new", True)))
        sizer.Add(self.whats_new_check, 0, wx.ALL, 5)

        self.whats_new_button = wx.Button(
            self, label="&Novidades desta versão..."
        )
        self.whats_new_button.Bind(wx.EVT_BUTTON, self._on_whats_new)
        sizer.Add(self.whats_new_button, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.beeps_check = wx.CheckBox(
            self,
            label="Tocar beeps antes do anúncio atual (atalho uma vez)",
        )
        self.beeps_check.SetValue(
            bool(self.settings.get("beeps_on_announce", False))
        )
        self.beeps_check.Bind(wx.EVT_CHECKBOX, self._on_beeps_toggle)
        sizer.Add(self.beeps_check, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        beeps_row = wx.BoxSizer(wx.HORIZONTAL)
        self.beeps_button = wx.Button(self, label="Personalizar &beeps...")
        self.beeps_button.Bind(wx.EVT_BUTTON, self._on_customize_beeps)
        beeps_row.Add(self.beeps_button, 0, wx.RIGHT, 8)
        self.beeps_status = wx.StaticText(self, label="")
        beeps_row.Add(self.beeps_status, 1, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(beeps_row, 0, wx.ALL, 5)

        self._global_sequence = list(
            normalize_sequence(self.settings.get("beep_sequence"))
            or DEFAULT_BEEP_SEQUENCE
        )
        self._refresh_locations()
        self._on_beeps_toggle(None)

    # -- montagem ----------------------------------------------------------

    @staticmethod
    def _initial_field_order(settings):
        stored = [
            key
            for key in (settings.get("announce_fields") or ())
            if key in WEATHER_NOTIFICATION_FIELDS
        ]
        if not stored:
            stored = [
                key
                for key in DEFAULT_NOTIFICATION_FIELDS
                if key in WEATHER_NOTIFICATION_FIELDS
            ]
        return list(stored) + [
            key for key in WEATHER_NOTIFICATION_FIELDS if key not in stored
        ]

    @staticmethod
    def _option_label(value):
        if isinstance(value, dict):
            return str(value.get("label", ""))
        return str(value)

    def _make_combo(self, panel, sizer, label, options, current):
        keys = list(options)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(
            wx.StaticText(panel, label=label),
            0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8,
        )
        combo = wx.ComboBox(
            panel,
            choices=[self._option_label(options[key]) for key in keys],
            style=wx.CB_READONLY,
        )
        if current in keys:
            combo.SetSelection(keys.index(current))
        elif keys:
            combo.SetSelection(0)
        row.Add(combo, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(row, 0, wx.ALL, 5)
        combo._option_keys = keys  # noqa: SLF001 - mapeamento interno simples
        return row, combo

    @staticmethod
    def _combo_key(combo):
        selection = combo.GetSelection()
        keys = getattr(combo, "_option_keys", [])
        if 0 <= selection < len(keys):
            return keys[selection]
        return ""

    # -- locais ------------------------------------------------------------

    def _refresh_locations(self):
        self.locations_list.Set([loc.display_name for loc in self._locations])
        if not self._locations:
            return
        index = 0
        for position, loc in enumerate(self._locations):
            if loc.key == self._default_key:
                index = position
                break
        self.locations_list.SetSelection(index)

    def _selected_index(self):
        selection = self.locations_list.GetSelection()
        if 0 <= selection < len(self._locations):
            return selection
        return -1

    def _on_add(self, event):
        dialog = SearchLocationDialog(self)
        try:
            if dialog.ShowModal() == wx.ID_OK and dialog.selected is not None:
                place = dialog.selected
                existing = None
                for loc in self._locations:
                    if loc.key == place.key or (
                        place.place_id and loc.place.place_id == place.place_id
                    ):
                        existing = loc
                        break
                if existing is not None:
                    existing.place = place
                    added = existing
                else:
                    from .core.locations import SavedLocation

                    added = SavedLocation(place=place)
                    self._locations.append(added)
                if not self._default_key:
                    self._default_key = added.key
                self._refresh_locations()
                self.locations_list.SetSelection(self._locations.index(added))
                ui.message(f"{added.display_name} adicionado.")
        finally:
            dialog.Destroy()

    def _on_remove(self, event):
        index = self._selected_index()
        if index < 0:
            ui.message("Selecione um local para remover.")
            return
        removed = self._locations.pop(index)
        if self._default_key == removed.key:
            self._default_key = self._locations[0].key if self._locations else ""
        self._refresh_locations()
        ui.message(f"{removed.display_name} removido.")

    def _on_move_up(self, event):
        self._move_location(-1)

    def _on_move_down(self, event):
        self._move_location(1)

    def _move_location(self, offset):
        index = self._selected_index()
        target = index + offset
        if index < 0 or target < 0 or target >= len(self._locations):
            return
        self._locations[index], self._locations[target] = (
            self._locations[target],
            self._locations[index],
        )
        self._refresh_locations()
        self.locations_list.SetSelection(target)
        self.locations_list.SetFocus()

    def _on_set_default(self, event):
        index = self._selected_index()
        if index < 0:
            ui.message("Selecione um local para definir como padrão.")
            return
        self._default_key = self._locations[index].key
        ui.message(f"{self._locations[index].display_name} agora é o local padrão.")

    def _on_customize_alerts(self, event):
        index = self._selected_index()
        if index < 0:
            ui.message("Selecione um local para personalizar o anúncio.")
            return
        location = self._locations[index]
        dialog = WeatherNotificationDialog(
            self,
            location,
            self.settings,
            self.store,
            sequencer=self.sequencer,
            tester=self.tester,
            field_tester=self.field_previewer,
        )
        try:
            if dialog.ShowModal() == wx.ID_OK:
                dialog.apply_to_location()
        finally:
            dialog.Destroy()
        ui.message(
            f"Anúncio personalizado de {location.display_name} atualizado."
        )

    def _on_whats_new(self, event):
        opener = getattr(self.plugin, "_open_whats_new", None)
        if opener is None:
            ui.message("Novidades indisponíveis.")
            return
        opener()

    # -- beeps do anúncio atual --------------------------------------------

    def _on_beeps_toggle(self, event):
        checked = self.beeps_check.GetValue()
        self.beeps_button.Show(checked)
        self.beeps_status.Show(checked)
        self._refresh_beeps_status()
        self.Layout()

    def _refresh_beeps_status(self):
        if self.beeps_check.GetValue():
            self.beeps_status.SetLabel(sequence_summary(self._global_sequence))
        else:
            self.beeps_status.SetLabel("")

    def _on_customize_beeps(self, event):
        dialog = BeepSequenceDialog(self, self._global_sequence, self.sequencer)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self._global_sequence = list(dialog.result_sequence())
        finally:
            dialog.Destroy()
        self._refresh_beeps_status()

    # -- campos ------------------------------------------------------------

    def _on_fields_key(self, event):
        code = event.GetKeyCode()
        if code == wx.WXK_F2:
            self._preview_field()
            return
        if event.AltDown() and code in (wx.WXK_UP, wx.WXK_DOWN):
            self._move_field(-1 if code == wx.WXK_UP else 1)
            return
        event.Skip()

    def _preview_field(self):
        index = self.fields_list.GetSelection()
        if index < 0 or index >= len(self._field_keys):
            ui.message("Selecione um campo para ouvir o valor.")
            return
        location_index = self._selected_index()
        if location_index < 0:
            ui.message("Selecione um local para ouvir o valor do campo.")
            return
        if self.field_previewer is None:
            ui.message("Prévia do campo indisponível.")
            return
        self.field_previewer(
            self._locations[location_index], self._field_keys[index]
        )

    def _move_field(self, offset):
        index = self.fields_list.GetSelection()
        target = index + offset
        if index < 0 or target < 0 or target >= len(self._field_keys):
            return
        self._field_keys[index], self._field_keys[target] = (
            self._field_keys[target],
            self._field_keys[index],
        )
        checked = [
            self.fields_list.IsChecked(i) for i in range(len(self._field_keys))
        ]
        checked[index], checked[target] = checked[target], checked[index]
        self.fields_list.Set(
            [WEATHER_NOTIFICATION_FIELDS[key] for key in self._field_keys]
        )
        for position, value in enumerate(checked):
            self.fields_list.Check(position, value)
        self.fields_list.SetSelection(target)
        self.fields_list.SetFocus()

    def selected_fields(self):
        return tuple(
            key
            for index, key in enumerate(self._field_keys)
            if self.fields_list.IsChecked(index)
        )

    # -- aplicar -----------------------------------------------------------

    def onSave(self):
        self.store.locations = list(self._locations)
        self.store.default_key = self._default_key or (
            self._locations[0].key if self._locations else ""
        )
        self.store.save()

        self.settings["announce_fields"] = list(self.selected_fields())
        self.settings["units"] = self._combo_key(self.units_combo) or "metric"
        self.settings["units_wind"] = self._combo_key(self.wind_combo)
        self.settings["time_format"] = self._combo_key(self.time_combo) or "24h"
        self.settings["date_format"] = self._combo_key(self.date_combo) or "dmy"
        self.settings["daily_days"] = int(self.days_spin.GetValue())
        self.settings["announce_fetching"] = bool(self.fetching_check.GetValue())
        self.settings["show_whats_new"] = bool(self.whats_new_check.GetValue())
        self.settings["beeps_on_announce"] = bool(self.beeps_check.GetValue())
        self.settings["beep_sequence"] = [
            dict(step) for step in self._global_sequence
        ]
        self.settings.save()
        try:
            self.plugin.cache.minutes = int(
                self.settings.get("cache_minutes", 15)
            )
        except Exception:
            pass

    def onPanelDeactivated(self):
        try:
            super().onPanelDeactivated()
        except Exception:
            pass
        try:
            self.sequencer.stop()
        except Exception:
            pass


class BeepStepDialog(wx.Dialog):
    """Edita um passo da sequência: um beep ou um silêncio."""

    def __init__(self, parent, step=None, sequencer=None):
        super().__init__(parent, title="Passo da sequência", size=(460, 320))
        self.sequencer = sequencer or BeepSequencer()
        self._owns_sequencer = sequencer is None
        step = normalize_step(step) if step else None
        if step is None:
            step = {
                "type": BEEP,
                "frequency": FREQUENCY_DEFAULT,
                "duration": BEEP_DURATION_DEFAULT,
            }

        outer = wx.BoxSizer(wx.VERTICAL)
        type_row = wx.BoxSizer(wx.HORIZONTAL)
        type_row.Add(
            wx.StaticText(self, label="Tipo de beep:"),
            0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8,
        )
        self.type_combo = wx.ComboBox(
            self,
            choices=[STEP_TYPES[BEEP], STEP_TYPES[SILENCE]],
            style=wx.CB_READONLY,
            name="Tipo de beep",
        )
        type_row.Add(self.type_combo, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(type_row, 0, wx.ALL, 12)

        self.beep_panel = wx.Panel(self)
        beep_grid = wx.FlexGridSizer(rows=0, cols=2, vgap=8, hgap=8)
        beep_grid.AddGrowableCol(1, 1)
        beep_grid.Add(
            wx.StaticText(self.beep_panel, label="Frequência do beep (Hz):"),
            0, wx.ALIGN_CENTER_VERTICAL,
        )
        self.frequency_spin = wx.SpinCtrl(
            self.beep_panel,
            min=FREQUENCY_MIN,
            max=FREQUENCY_MAX,
            initial=int(step.get("frequency", FREQUENCY_DEFAULT)),
            name="Frequência do beep",
        )
        beep_grid.Add(self.frequency_spin, 1, wx.EXPAND)
        beep_grid.Add(
            wx.StaticText(self.beep_panel, label="Duração do beep (ms):"),
            0, wx.ALIGN_CENTER_VERTICAL,
        )
        self.beep_duration_spin = wx.SpinCtrl(
            self.beep_panel,
            min=BEEP_DURATION_MIN,
            max=BEEP_DURATION_MAX,
            initial=int(step.get("duration", BEEP_DURATION_DEFAULT)),
            name="Duração do beep",
        )
        beep_grid.Add(self.beep_duration_spin, 1, wx.EXPAND)
        self.beep_panel.SetSizer(beep_grid)
        outer.Add(self.beep_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        self.beep_test_button = wx.Button(self, label="Testar &beep")
        self.beep_test_button.Bind(wx.EVT_BUTTON, self._on_test_beep)
        outer.Add(self.beep_test_button, 0, wx.ALL, 12)

        self.silence_panel = wx.Panel(self)
        silence_grid = wx.FlexGridSizer(rows=0, cols=2, vgap=8, hgap=8)
        silence_grid.AddGrowableCol(1, 1)
        silence_grid.Add(
            wx.StaticText(self.silence_panel, label="Duração do silêncio (ms):"),
            0, wx.ALIGN_CENTER_VERTICAL,
        )
        self.silence_spin = wx.SpinCtrl(
            self.silence_panel,
            min=SILENCE_DURATION_MIN,
            max=SILENCE_DURATION_MAX,
            initial=int(step.get("duration", SILENCE_DURATION_DEFAULT)),
            name="Duração do silêncio",
        )
        silence_grid.Add(self.silence_spin, 1, wx.EXPAND)
        self.silence_panel.SetSizer(silence_grid)
        outer.Add(self.silence_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        outer.Add(
            self.CreateButtonSizer(wx.OK | wx.CANCEL),
            0, wx.ALIGN_RIGHT | wx.ALL, 12,
        )
        self.SetSizer(outer)

        self.type_combo.SetSelection(0 if step.get("type") == BEEP else 1)
        self.type_combo.Bind(wx.EVT_CHOICE, self._on_type)
        self._on_type(None)

    def _on_type(self, event):
        is_beep = self.type_combo.GetSelection() != 1
        self.beep_panel.Show(is_beep)
        self.beep_test_button.Show(is_beep)
        self.silence_panel.Show(not is_beep)
        self.Layout()
        self.Fit()

    def _beep_step(self):
        return {
            "type": BEEP,
            "frequency": int(self.frequency_spin.GetValue()),
            "duration": int(self.beep_duration_spin.GetValue()),
        }

    def _on_test_beep(self, event):
        self.sequencer.play((self._beep_step(),))

    def step(self):
        if self.type_combo.GetSelection() == 1:
            return {
                "type": SILENCE,
                "duration": int(self.silence_spin.GetValue()),
            }
        return self._beep_step()


class BeepSequenceDialog(wx.Dialog):
    """Lista ordenada de beeps e silêncios tocada antes do anúncio."""

    def __init__(self, parent, sequence=(), sequencer=None):
        super().__init__(parent, title="Sequência de beeps", size=(540, 440))
        self.sequence = list(normalize_sequence(sequence))
        self.sequencer = sequencer or BeepSequencer()
        self._owns_sequencer = sequencer is None

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(
            wx.StaticText(
                self,
                label="A sequência toca antes do anúncio, na ordem abaixo:",
            ),
            0, wx.ALL, 10,
        )
        self.list = wx.ListBox(self, name="Passos da sequência")
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_edit)
        outer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.add_button = wx.Button(self, label="&Adicionar...")
        self.edit_button = wx.Button(self, label="&Editar...")
        self.remove_button = wx.Button(self, label="&Remover")
        self.add_button.Bind(wx.EVT_BUTTON, self._on_add)
        self.edit_button.Bind(wx.EVT_BUTTON, self._on_edit)
        self.remove_button.Bind(wx.EVT_BUTTON, self._on_remove)
        for button in (self.add_button, self.edit_button, self.remove_button):
            buttons.Add(button, 0, wx.RIGHT, 6)
        outer.Add(buttons, 0, wx.ALL, 10)

        self.test_button = wx.Button(self, label="Testar &sequência de beeps")
        self.test_button.Bind(wx.EVT_BUTTON, self._on_test)
        outer.Add(self.test_button, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        outer.Add(
            self.CreateButtonSizer(wx.OK | wx.CANCEL),
            0, wx.ALIGN_RIGHT | wx.ALL, 10,
        )
        self.SetSizer(outer)
        self._refresh()

    def _refresh(self, select=None):
        self.list.Set(
            [step_label(step, index) for index, step in enumerate(self.sequence)]
        )
        has_items = bool(self.sequence)
        self.edit_button.Enable(has_items)
        self.remove_button.Enable(has_items)
        self.test_button.Enable(has_items)
        if has_items:
            index = (
                0 if select is None
                else max(0, min(select, len(self.sequence) - 1))
            )
            self.list.SetSelection(index)

    def _selected_index(self):
        index = self.list.GetSelection()
        return index if 0 <= index < len(self.sequence) else -1

    def _on_add(self, event):
        dialog = BeepStepDialog(self, None, self.sequencer)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.sequence.append(dialog.step())
        finally:
            dialog.Destroy()
        self._refresh(len(self.sequence) - 1)

    def _on_edit(self, event):
        index = self._selected_index()
        if index < 0:
            return
        dialog = BeepStepDialog(self, self.sequence[index], self.sequencer)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.sequence[index] = dialog.step()
        finally:
            dialog.Destroy()
        self._refresh(index)

    def _on_remove(self, event):
        index = self._selected_index()
        if index < 0:
            return
        self.sequence.pop(index)
        self._refresh(index)

    def _on_test(self, event):
        self.sequencer.play(tuple(self.sequence))

    def result_sequence(self):
        return tuple(self.sequence)


class WeatherNotificationDialog(wx.Dialog):
    """Edita o anúncio personalizado de clima de um local."""

    def __init__(
        self, parent, location, settings, store, sequencer=None, tester=None,
        field_tester=None,
    ):
        super().__init__(
            parent,
            title=f"Anúncio personalizado de {location.full_label}",
            size=(560, 640),
        )
        self.location = location
        self.settings = settings
        self.store = store
        self.sequencer = sequencer or BeepSequencer()
        self._owns_sequencer = sequencer is None
        self.tester = tester
        self.field_tester = field_tester
        self.sequence = normalize_sequence(location.beep_sequence)

        outer = wx.BoxSizer(wx.VERTICAL)
        self.enabled = wx.CheckBox(
            self, label="Ativar anúncio personalizado de clima"
        )
        self.enabled.SetValue(bool(location.notify_hourly))
        outer.Add(self.enabled, 0, wx.ALL, 12)

        interval_row = wx.BoxSizer(wx.HORIZONTAL)
        interval_row.Add(
            wx.StaticText(
                self,
                label=f"Atualizar a cada (minutos, {NOTIFICATION_INTERVAL_MIN} a "
                f"{NOTIFICATION_INTERVAL_MAX}):",
            ),
            0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8,
        )
        self.interval_choice = wx.ComboBox(
            self,
            value=str(location.notify_interval),
            choices=[str(number) for number in NOTIFICATION_INTERVAL_CHOICES],
            style=wx.CB_DROPDOWN,
            name="Intervalo do anúncio em minutos",
        )
        self.interval_choice.SetMinSize(wx.Size(90, -1))
        interval_row.Add(self.interval_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(interval_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        outer.Add(
            wx.StaticText(
                self,
                label="Marque o que anunciar; Alt+setas muda a ordem; F2 lê o valor:",
            ),
            0, wx.LEFT | wx.RIGHT, 12,
        )
        self.keys = _ordered_field_keys(location.notify_fields)
        checked = set(location.notify_fields) or set(DEFAULT_NOTIFICATION_FIELDS)
        self.field_list = wx.CheckListBox(
            self,
            choices=[WEATHER_NOTIFICATION_FIELDS[key] for key in self.keys],
            name="Campos do anúncio",
        )
        for index, key in enumerate(self.keys):
            self.field_list.Check(index, key in checked)
        self.field_list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        outer.Add(self.field_list, 1, wx.EXPAND | wx.ALL, 12)

        move = wx.BoxSizer(wx.HORIZONTAL)
        self.up_button = wx.Button(self, label="Mover para cima")
        self.down_button = wx.Button(self, label="Mover para baixo")
        self.up_button.Bind(wx.EVT_BUTTON, lambda event: self._move(-1))
        self.down_button.Bind(wx.EVT_BUTTON, lambda event: self._move(1))
        move.Add(self.up_button, 0, wx.RIGHT, 6)
        move.Add(self.down_button, 0)
        outer.Add(move, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.beeps_check = wx.CheckBox(
            self, label="Reproduzir beeps antes do anúncio personalizado"
        )
        self.beeps_check.SetValue(bool(location.beeps_enabled))
        self.beeps_check.Bind(wx.EVT_CHECKBOX, self._on_beeps_toggle)
        outer.Add(self.beeps_check, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)

        beeps_row = wx.BoxSizer(wx.HORIZONTAL)
        self.beeps_button = wx.Button(self, label="Personalizar &beeps...")
        self.beeps_button.Bind(wx.EVT_BUTTON, self._on_customize_beeps)
        beeps_row.Add(self.beeps_button, 0, wx.RIGHT, 8)
        self.beeps_status = wx.StaticText(self, label="")
        beeps_row.Add(self.beeps_status, 1, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(beeps_row, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)

        self.test_button = wx.Button(self, label="Testar anúncio")
        self.test_button.Bind(wx.EVT_BUTTON, self._on_test)
        outer.Add(self.test_button, 0, wx.ALL, 12)

        outer.Add(
            self.CreateButtonSizer(wx.OK | wx.CANCEL),
            0, wx.ALIGN_RIGHT | wx.ALL, 12,
        )
        self.SetSizer(outer)
        self._on_beeps_toggle(None)

    def _on_list_key(self, event):
        code = event.GetKeyCode()
        if code == wx.WXK_F2:
            self._preview_field()
            return
        if event.AltDown() and code in (wx.WXK_UP, wx.WXK_DOWN):
            self._move(-1 if code == wx.WXK_UP else 1)
            return
        event.Skip()

    def _preview_field(self):
        index = self.field_list.GetSelection()
        if index < 0 or index >= len(self.keys):
            ui.message("Selecione um campo para ouvir o valor.")
            return
        if self.field_tester is None:
            ui.message("Prévia do campo indisponível.")
            return
        self.field_tester(self.location, self.keys[index])

    def _move(self, offset):
        index = self.field_list.GetSelection()
        target = index + offset
        if index < 0 or target < 0 or target >= len(self.keys):
            return
        self.keys[index], self.keys[target] = self.keys[target], self.keys[index]
        checked = [self.field_list.IsChecked(i) for i in range(len(self.keys))]
        checked[index], checked[target] = checked[target], checked[index]
        self.field_list.Set([WEATHER_NOTIFICATION_FIELDS[key] for key in self.keys])
        for position, value in enumerate(checked):
            self.field_list.Check(position, value)
        self.field_list.SetSelection(target)
        self.field_list.EnsureVisible(target)
        self.field_list.SetFocus()

    def selected_fields(self):
        return tuple(
            key
            for index, key in enumerate(self.keys)
            if self.field_list.IsChecked(index)
        )

    def interval(self):
        return clamp_notification_interval(self.interval_choice.GetValue())

    def _on_beeps_toggle(self, event):
        checked = self.beeps_check.GetValue()
        self.beeps_button.Show(checked)
        self.beeps_status.Show(checked)
        self._refresh_beeps_status()
        self.Layout()

    def _refresh_beeps_status(self):
        if not self.beeps_check.GetValue():
            self.beeps_status.SetLabel("")
        else:
            self.beeps_status.SetLabel(sequence_summary(self.sequence))

    def _on_customize_beeps(self, event):
        dialog = BeepSequenceDialog(self, self.sequence, self.sequencer)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.sequence = dialog.result_sequence()
        finally:
            dialog.Destroy()
        self._refresh_beeps_status()

    def _on_test(self, event):
        if not self.selected_fields():
            ui.message("Marque ao menos um item para anunciar.")
            return
        self.apply_to_location()
        if self.tester is None:
            ui.message("Teste do anúncio indisponível.")
            return
        self.tester(self.location)

    def apply_to_location(self):
        self.location.notify_hourly = bool(self.enabled.GetValue())
        self.location.notify_fields = tuple(self.selected_fields())
        self.location.notify_interval = self.interval()
        self.location.beeps_enabled = bool(self.beeps_check.GetValue())
        self.location.beep_sequence = tuple(self.sequence)


class WeatherListDialog(wx.Dialog):
    """Janela não modal com uma lista navegável (horas ou dias)."""

    def __init__(self, parent, title, items, header=""):
        super().__init__(
            parent,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.on_close = None
        items = list(items)
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        if header:
            sizer.Add(wx.StaticText(panel, label=header), 0, wx.ALL, 8)
        self.list_box = wx.ListBox(panel, choices=items, style=wx.LB_SINGLE)
        sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 8)
        close_button = wx.Button(panel, label="&Fechar")
        sizer.Add(close_button, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        panel.SetSizer(sizer)
        self.SetSize((560, 420))
        self.CentreOnScreen()
        close_button.Bind(wx.EVT_BUTTON, self._on_close_request)
        self.list_box.Bind(wx.EVT_LISTBOX_DCLICK, self._on_close_request)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        if items:
            self.list_box.SetSelection(0)
        self.list_box.SetFocus()

    def _on_char_hook(self, event):
        if event.GetKeyCode() in (wx.WXK_ESCAPE, wx.WXK_RETURN):
            self._on_close_request(event)
        else:
            event.Skip()

    def _on_close_request(self, event):
        self.Close()

    def _on_close(self, event):
        if self.on_close is not None:
            self.on_close(self)
        self.Destroy()
