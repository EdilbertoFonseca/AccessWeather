from __future__ import annotations

import wx

from .alerts import (
    ALERT_METRICS,
    ALERT_OPERATORS,
    AlertRule,
    describe_rule,
    parse_rules,
    rules_to_payload,
)
from .config import (
    ANNOUNCEMENT_LABELS,
    APP_NAME,
    DATE_FORMATS,
    DEFAULT_NOTIFICATION_FIELDS,
    NOTIFICATION_INTERVAL_CHOICES,
    NOTIFICATION_INTERVAL_MAX,
    NOTIFICATION_INTERVAL_MIN,
    NOTIFICATION_LABELS,
    TIME_FORMATS,
    UNIT_GROUPS,
    WEATHER_NOTIFICATION_FIELDS,
    WIND_OPTIONS,
    clamp_notification_interval,
)
from .formatting import notification_body
from .version import VERSION


def _choice_for(control, options, current):
    keys = list(options)
    labels = []
    for key in keys:
        value = options[key]
        labels.append(value.get("label", key) if isinstance(value, dict) else value)
    control.Clear()
    control.AppendItems(labels)
    control.SetSelection(keys.index(current) if current in keys else 0)
    return keys


def _selected_key(control, keys, fallback=None):
    index = control.GetSelection()
    if index < 0 or index >= len(keys):
        return fallback if fallback is not None else keys[0]
    return keys[index]


class TextReportDialog(wx.Dialog):
    """Texto somente leitura: changelog, sobre e mensagens longas."""

    def __init__(self, parent, title, text, size=(680, 480)):
        super().__init__(parent, title=title, size=size)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.text = wx.TextCtrl(
            self,
            value=text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
            name=title,
        )
        sizer.Add(self.text, 1, wx.EXPAND | wx.ALL, 10)
        sizer.Add(self.CreateButtonSizer(wx.OK), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        self.text.SetFocus()


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, settings):
        super().__init__(parent, title="Configurações", size=(520, 640))
        self.settings = settings
        self.announcement_boxes = {}
        self.notification_boxes = {}

        outer = wx.BoxSizer(wx.VERTICAL)
        panel = wx.ScrolledWindow(self, style=wx.VSCROLL)
        panel.SetScrollRate(0, 12)
        body = wx.BoxSizer(wx.VERTICAL)

        body.Add(self._choice_row(
            panel, "Unidades", UNIT_GROUPS, settings["units"], "units"
        ), 0, wx.ALL | wx.EXPAND, 8)
        body.Add(self._choice_row(
            panel, "Vento (sobrepõe a unidade)", WIND_OPTIONS, settings["units_wind"],
            "units_wind",
        ), 0, wx.ALL | wx.EXPAND, 8)
        body.Add(self._choice_row(
            panel, "Formato de hora", TIME_FORMATS, settings["time_format"], "time_format"
        ), 0, wx.ALL | wx.EXPAND, 8)
        body.Add(self._choice_row(
            panel, "Formato de data", DATE_FORMATS, settings["date_format"], "date_format"
        ), 0, wx.ALL | wx.EXPAND, 8)

        body.Add(self._spin_row(
            panel, "Escala da fonte (por cento)", 75, 250, settings["font_scale"],
            "font_scale",
        ), 0, wx.ALL | wx.EXPAND, 8)
        body.Add(self._spin_row(
            panel, "Horas na previsão de hora em hora", 1, 48, settings["hourly_hours"],
            "hourly_hours",
        ), 0, wx.ALL | wx.EXPAND, 8)
        body.Add(self._spin_row(
            panel, "Dias na previsão diária", 1, 16, settings["daily_days"], "daily_days"
        ), 0, wx.ALL | wx.EXPAND, 8)
        body.Add(self._spin_row(
            panel, "Minutos entre atualizações", 5, 180, settings["refresh_minutes"],
            "refresh_minutes",
        ), 0, wx.ALL | wx.EXPAND, 8)
        body.Add(self._spin_row(
            panel, "Minutos de validade do cache", 1, 120, settings["cache_minutes"],
            "cache_minutes",
        ), 0, wx.ALL | wx.EXPAND, 8)

        self.refresh_on_start = self._checkbox(
            panel, "Atualizar ao abrir o programa", settings["refresh_on_start"]
        )
        self.close_to_tray = self._checkbox(
            panel, "Fechar a janela esconde para a bandeja", settings["close_to_tray"]
        )
        self.startup_minimized = self._checkbox(
            panel, "Iniciar minimizado na bandeja", settings["startup_minimized"]
        )
        for box in (self.refresh_on_start, self.close_to_tray, self.startup_minimized):
            body.Add(box, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        body.Add(self._group_label(panel, "Anúncios falados", ANNOUNCEMENT_LABELS), 0, wx.ALL, 8)
        body.Add(self._checkbox_group(
            panel, ANNOUNCEMENT_LABELS, settings["announcements"], self.announcement_boxes
        ), 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)
        body.Add(self._group_label(panel, "Notificações", NOTIFICATION_LABELS), 0, wx.ALL, 8)
        body.Add(self._checkbox_group(
            panel, NOTIFICATION_LABELS, settings["notifications"], self.notification_boxes
        ), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        panel.SetSizer(body)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(outer)

    # -- helpers -----------------------------------------------------------

    def _group_label(self, parent, text, options):
        return wx.StaticText(parent, label=text)

    def _choice_row(self, parent, label, options, current, attribute):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        caption = wx.StaticText(parent, label=label)
        caption.SetMinSize((220, -1))
        control = wx.Choice(parent, choices=[])
        control.SetName(label)
        keys = _choice_for(control, options, current)
        setattr(self, attribute, control)
        setattr(self, f"{attribute}_keys", keys)
        sizer.Add(caption, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        sizer.Add(control, 1, wx.ALIGN_CENTER_VERTICAL)
        return sizer

    def _spin_row(self, parent, label, minimum, maximum, current, attribute):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        caption = wx.StaticText(parent, label=label)
        caption.SetMinSize((280, -1))
        control = wx.SpinCtrl(parent, min=minimum, max=maximum, initial=int(current))
        control.SetName(label)
        setattr(self, attribute, control)
        sizer.Add(caption, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        sizer.Add(control, 1, wx.ALIGN_CENTER_VERTICAL)
        return sizer

    def _checkbox(self, parent, label, value):
        control = wx.CheckBox(parent, label=label)
        control.SetValue(bool(value))
        return control

    def _checkbox_group(self, parent, labels, values, store):
        box = wx.StaticBox(parent, label="")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        for key, text in labels.items():
            control = wx.CheckBox(box, label=text)
            control.SetValue(bool(values.get(key, True)))
            store[key] = control
            sizer.Add(control, 0, wx.ALL, 4)
        return sizer

    def values(self) -> dict:
        result = dict(self.settings.values)
        result["units"] = _selected_key(self.units, self.units_keys, "metric")
        result["units_wind"] = _selected_key(
            self.units_wind, self.units_wind_keys, ""
        )
        result["time_format"] = _selected_key(
            self.time_format, self.time_format_keys, "24h"
        )
        result["date_format"] = _selected_key(
            self.date_format, self.date_format_keys, "dmy"
        )
        result["font_scale"] = int(self.font_scale.GetValue())
        result["hourly_hours"] = int(self.hourly_hours.GetValue())
        result["daily_days"] = int(self.daily_days.GetValue())
        result["refresh_minutes"] = int(self.refresh_minutes.GetValue())
        result["cache_minutes"] = int(self.cache_minutes.GetValue())
        result["refresh_on_start"] = bool(self.refresh_on_start.GetValue())
        result["close_to_tray"] = bool(self.close_to_tray.GetValue())
        result["startup_minimized"] = bool(self.startup_minimized.GetValue())
        result["announcements"] = {
            key: bool(box.GetValue()) for key, box in self.announcement_boxes.items()
        }
        result["notifications"] = {
            key: bool(box.GetValue()) for key, box in self.notification_boxes.items()
        }
        return result


_METRIC_UNITS = {
    "temperature": (-80.0, 80.0, 1.0),
    "wind": (0.0, 300.0, 5.0),
    "precipitation": (0.0, 500.0, 1.0),
    "percent": (0.0, 100.0, 5.0),
    "severity": (1.0, 5.0, 1.0),
    "number": (-1000.0, 1000.0, 1.0),
}


class AlertRuleDialog(wx.Dialog):
    def __init__(self, parent, rule=None):
        super().__init__(parent, title="Regra de alerta", size=(460, 380))
        self.metric_keys = list(ALERT_METRICS)
        self.operator_keys = list(ALERT_OPERATORS)

        outer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(rows=0, cols=2, vgap=8, hgap=8)
        grid.AddGrowableCol(1, 1)

        self.metric = wx.Choice(
            self, choices=[ALERT_METRICS[key]["label"] for key in self.metric_keys],
            name="Métrica",
        )
        self.metric.Bind(wx.EVT_CHOICE, self._on_metric)
        grid.Add(wx.StaticText(self, label="Métrica"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.metric, 1, wx.EXPAND)

        self.operator = wx.Choice(
            self, choices=list(ALERT_OPERATORS.values()), name="Comparação"
        )
        grid.Add(wx.StaticText(self, label="Comparação"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.operator, 1, wx.EXPAND)

        self.threshold = wx.SpinCtrlDouble(
            self, min=-80, max=80, initial=0, inc=1, name="Valor"
        )
        grid.Add(wx.StaticText(self, label="Valor"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.threshold, 1, wx.EXPAND)

        self.lead = wx.SpinCtrl(self, min=0, max=168, initial=24, name="Horas à frente")
        grid.Add(
            wx.StaticText(self, label="Horas à frente (0 = todo o período)"),
            0, wx.ALIGN_CENTER_VERTICAL,
        )
        grid.Add(self.lead, 1, wx.EXPAND)

        outer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)

        self.enabled = wx.CheckBox(self, label="Regra ativa")
        self.toast = wx.CheckBox(self, label="Mostrar notificação")
        self.announce = wx.CheckBox(self, label="Anunciar por voz")
        for box in (self.enabled, self.toast, self.announce):
            box.SetValue(True)
            outer.Add(box, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)

        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 12)
        self.SetSizer(outer)

        if rule is not None:
            self._load(rule)
        else:
            self.metric.SetSelection(0)
            self._on_metric(None)

    def _load(self, rule):
        if rule.metric in self.metric_keys:
            self.metric.SetSelection(self.metric_keys.index(rule.metric))
        if rule.operator in self.operator_keys:
            self.operator.SetSelection(self.operator_keys.index(rule.operator))
        self._sync_threshold_range()
        self.threshold.SetValue(float(rule.threshold))
        self.lead.SetValue(int(rule.lead_hours))
        self.enabled.SetValue(bool(rule.enabled))
        self.toast.SetValue(bool(rule.toast))
        self.announce.SetValue(bool(rule.announce))
        self.identifier = rule.identifier

    def _metric_key(self):
        index = self.metric.GetSelection()
        if index < 0 or index >= len(self.metric_keys):
            return self.metric_keys[0]
        return self.metric_keys[index]

    def _sync_threshold_range(self):
        unit = ALERT_METRICS[self._metric_key()]["unit"]
        minimum, maximum, step = _METRIC_UNITS.get(unit, _METRIC_UNITS["number"])
        self.threshold.SetRange(minimum, maximum)
        self.threshold.SetIncrement(step)

    def _on_metric(self, event):
        self._sync_threshold_range()

    def rule(self) -> AlertRule:
        metric = self._metric_key()
        operator = _selected_key(self.operator, self.operator_keys, "above")
        threshold = self.threshold.GetValue()
        if ALERT_METRICS[metric]["unit"] == "severity":
            threshold = min(5, max(1, int(round(threshold))))
        return AlertRule(
            metric=metric,
            operator=operator,
            threshold=threshold,
            lead_hours=int(self.lead.GetValue()),
            enabled=bool(self.enabled.GetValue()),
            toast=bool(self.toast.GetValue()),
            announce=bool(self.announce.GetValue()),
            identifier=getattr(self, "identifier", ""),
        )


class AlertsDialog(wx.Dialog):
    def __init__(self, parent, location, store):
        super().__init__(parent, title=f"Alertas de {location.full_label}", size=(560, 420))
        self.location = location
        self.store = store
        self.rules = list(parse_rules(location.alerts))

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(
            wx.StaticText(self, label="As regras marcadas disparam avisos quando batem."),
            0, wx.ALL, 10,
        )
        self.list = wx.ListBox(self, name="Regras de alerta")
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_edit)
        outer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        add = wx.Button(self, label="Adicionar")
        edit = wx.Button(self, label="Editar")
        remove = wx.Button(self, label="Remover")
        add.Bind(wx.EVT_BUTTON, self._on_add)
        edit.Bind(wx.EVT_BUTTON, self._on_edit)
        remove.Bind(wx.EVT_BUTTON, self._on_remove)
        for button in (add, edit, remove):
            buttons.Add(button, 0, wx.RIGHT, 6)
        outer.Add(buttons, 0, wx.ALL, 10)

        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(outer)
        self._refresh()

    def _refresh(self, select=None):
        self.list.Set([describe_rule(rule) for rule in self.rules])
        if not self.rules:
            return
        index = 0 if select is None else max(0, min(select, len(self.rules) - 1))
        self.list.SetSelection(index)

    def _selected_index(self):
        index = self.list.GetSelection()
        return index if 0 <= index < len(self.rules) else -1

    def _on_add(self, event):
        with AlertRuleDialog(self) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.rules.append(dialog.rule())
        self._refresh(len(self.rules) - 1)

    def _on_edit(self, event):
        index = self._selected_index()
        if index < 0:
            return
        with AlertRuleDialog(self, self.rules[index]) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.rules[index] = dialog.rule()
        self._refresh(index)

    def _on_remove(self, event):
        index = self._selected_index()
        if index < 0:
            return
        rule = self.rules[index]
        with wx.MessageDialog(
            self, f"Remover a regra {describe_rule(rule)}?", APP_NAME,
            wx.YES_NO | wx.ICON_QUESTION,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_YES:
                return
        self.rules.pop(index)
        self._refresh(index)

    def save(self):
        self.store.set_alerts(self.location.key, rules_to_payload(self.rules))
        self.store.save()


class WeatherNotificationDialog(wx.Dialog):
    """Ativa, escolhe e ordena os campos da notificação de hora em hora."""

    def __init__(self, parent, location, forecast, symbols, notifier=None):
        super().__init__(
            parent,
            title=f"Notificação de clima de {location.full_label}",
            size=(520, 560),
        )
        self.location = location
        self.forecast = forecast
        self.symbols = symbols
        self.notifier = notifier

        stored = [
            key for key in location.notify_fields if key in WEATHER_NOTIFICATION_FIELDS
        ]
        if not stored:
            stored = [
                key
                for key in DEFAULT_NOTIFICATION_FIELDS
                if key in WEATHER_NOTIFICATION_FIELDS
            ]
        self.keys = list(stored) + [
            key for key in WEATHER_NOTIFICATION_FIELDS if key not in stored
        ]
        checked = set(location.notify_fields) or set(DEFAULT_NOTIFICATION_FIELDS)

        outer = wx.BoxSizer(wx.VERTICAL)
        self.enabled = wx.CheckBox(
            self, label="Ativar notificação personalizada de clima"
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
            name="Intervalo da notificação em minutos",
        )
        self.interval_choice.SetMinSize(wx.Size(90, -1))
        interval_row.Add(self.interval_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(interval_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        outer.Add(
            wx.StaticText(
                self,
                label="Marque o que mostrar; use Alt+setas para mudar a ordem:",
            ),
            0, wx.LEFT | wx.RIGHT, 12,
        )
        self.field_list = wx.CheckListBox(
            self,
            choices=[WEATHER_NOTIFICATION_FIELDS[key] for key in self.keys],
            name="Campos da notificação",
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

        self.test_button = wx.Button(self, label="Testar notificação")
        self.test_button.Bind(wx.EVT_BUTTON, self._on_test)
        outer.Add(self.test_button, 0, wx.LEFT | wx.RIGHT, 12)
        self.test_status = wx.StaticText(self, label="")
        outer.Add(self.test_status, 0, wx.ALL, 12)

        outer.Add(
            self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 12
        )
        self.SetSizer(outer)

    def _on_list_key(self, event):
        code = event.GetKeyCode()
        if event.AltDown() and code in (wx.WXK_UP, wx.WXK_DOWN):
            self._move(-1 if code == wx.WXK_UP else 1)
            return
        event.Skip()

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

    def selected_fields(self) -> tuple:
        return tuple(
            key
            for index, key in enumerate(self.keys)
            if self.field_list.IsChecked(index)
        )

    def interval(self) -> int:
        return clamp_notification_interval(self.interval_choice.GetValue())

    def message(self) -> str:
        return notification_body(
            self.location, self.forecast, self.selected_fields(), self.symbols
        )

    def _on_test(self, event):
        if not self.selected_fields():
            wx.MessageBox(
                "Marque ao menos um item para mostrar na notificação.",
                APP_NAME, wx.OK | wx.ICON_INFORMATION, self,
            )
            return
        if not self.forecast or self.forecast.current is None:
            wx.MessageBox(
                "Ainda não há previsão para este local. Atualize e tente de novo.",
                APP_NAME, wx.OK | wx.ICON_INFORMATION, self,
            )
            return
        text = self.message()
        self.test_status.SetLabel(f"Prévia: {text}")
        if self.notifier and self.notifier.forecast(
            self.location.full_label, text, force=True
        ):
            self.test_status.SetLabel("Notificação de teste enviada para o Windows.")
            return
        reason = getattr(self.notifier, "last_error", "") if self.notifier else ""
        message = "Não foi possível mostrar a notificação do Windows."
        if reason:
            message = f"{message}\n\n{reason}"
        message = f"{message}\n\nPrévia:\n{text}"
        wx.MessageBox(message, APP_NAME, wx.OK | wx.ICON_WARNING, self)


class AboutDialog(wx.Dialog):
    def __init__(self, parent, extra=""):
        super().__init__(parent, title=f"Sobre o {APP_NAME}", size=(440, 300))
        text = (
            f"{APP_NAME} {VERSION}\n\n"
            "Previsão do tempo acessível para leitores de tela.\n"
            "Dados por Open-Meteo (open-meteo.com).\n"
            "Anúncios por NVDA ou SAPI e notificações do Windows."
        )
        if extra:
            text = f"{text}\n\n{extra}"
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self, label=text)
        sizer.Add(label, 1, wx.EXPAND | wx.ALL, 14)
        sizer.Add(self.CreateButtonSizer(wx.OK), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)


def show_error(parent, message, title=APP_NAME):
    with wx.MessageDialog(parent, message, title, wx.OK | wx.ICON_ERROR) as dialog:
        dialog.ShowModal()
