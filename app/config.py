from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path


APP_NAME = "AccessWeather"

# Bundled icon for the toast notifications; the AUMID must stay stable across
# releases or Windows treats every update as a different app.
APP_AUMID = "JuniorTec.AccessWeather"

ACTION_LABELS = {
    "show_window": "Abrir a janela",
    "add_location": "Adicionar local...",
    "remove_location": "Remover local",
    "rename_location": "Renomear local...",
    "toggle_favorite_location": "Favoritar ou desfavoritar local",
    "set_default_location": "Definir como local padrão",
    "customize_notification": "Personalizar notificação de clima...",
    "refresh_now": "Atualizar agora",
    "cycle_location": "Trocar de local",
    "copy_current": "Copiar previsão do local atual",
    "open_locations": "Ir para a lista de locais",
    "open_alerts": "Gerenciar alertas...",
    "open_settings": "Configurações...",
    "check_update": "Verificar atualização",
    "show_changelog": "Abrir changelog",
    "about": "Sobre o AccessWeather",
    "quit": "Sair do AccessWeather",
}

# Ações que ficam no menu de contexto da lista de locais, não na bandeja.
CONTEXT_ACTIONS = frozenset({
    "remove_location",
    "rename_location",
    "toggle_favorite_location",
    "set_default_location",
    "customize_notification",
})

# Campos que o usuário escolhe para a notificação de clima por local. A ordem
# aqui é a ordem exibida na notificação.
WEATHER_NOTIFICATION_FIELDS = {
    "temperature": "Temperatura",
    "condition": "Condição do tempo",
    "apparent_temperature": "Sensação térmica",
    "wind_speed": "Vento",
    "humidity": "Umidade",
    "precipitation": "Chuva na hora",
    "precipitation_probability": "Chance de chuva",
    "daily_max": "Máxima do dia",
    "daily_min": "Mínima do dia",
}

DEFAULT_NOTIFICATION_FIELDS = (
    "temperature",
    "condition",
    "apparent_temperature",
    "wind_speed",
    "humidity",
    "precipitation_probability",
)

# Intervalo, em minutos, da notificação de clima por local (1 a 360).
NOTIFICATION_INTERVAL_MIN = 1
NOTIFICATION_INTERVAL_MAX = 360
DEFAULT_NOTIFICATION_INTERVAL = 60
NOTIFICATION_INTERVAL_CHOICES = (
    1, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 360,
)


def clamp_notification_interval(value) -> int:
    """Normaliza o valor da UI num intervalo válido de 1 a 360 minutos."""
    try:
        number = int(round(float(str(value).strip().replace(",", "."))))
    except (TypeError, ValueError):
        return DEFAULT_NOTIFICATION_INTERVAL
    return max(
        NOTIFICATION_INTERVAL_MIN, min(NOTIFICATION_INTERVAL_MAX, number)
    )


ANNOUNCEMENT_LABELS = {
    "startup": "Inicialização do AccessWeather",
    "refresh": "Atualização e erro de atualização do clima",
    "location": "Troca e seleção de local",
    "forecast": "Leitura da previsão",
    "alerts": "Alertas meteorológicos",
    "notifications": "Notificações",
    "update": "Atualizações do programa",
    "system": "Avisos gerais",
}

DEFAULT_ANNOUNCEMENTS = {key: True for key in ANNOUNCEMENT_LABELS}

NOTIFICATION_LABELS = {
    "alerts": "Alertas meteorológicos",
    "forecast": "Resumo da previsão",
    "update": "Atualização do programa disponível",
}

DEFAULT_NOTIFICATIONS = {key: True for key in NOTIFICATION_LABELS}

# Open-Meteo accepts these unit codes; the app stores the choice as one of the
# three unit groups below and maps it to the API parameters.
UNIT_GROUPS = {
    "metric": {
        "label": "Métrico (°C, km/h, mm)",
        "temperature": "celsius",
        "wind": "kmh",
        "precipitation": "mm",
    },
    "imperial": {
        "label": "Imperial (°F, mph, inch)",
        "temperature": "fahrenheit",
        "wind": "mph",
        "precipitation": "inch",
    },
}

TIME_FORMATS = {
    "24h": "24 horas",
    "12h": "12 horas",
}

TEMPERATURE_SYMBOLS = {"celsius": "°C", "fahrenheit": "°F"}

WIND_SYMBOLS = {"kmh": "km/h", "mph": "mph", "ms": "m/s", "kn": "nós"}

WIND_OPTIONS = {
    "": "Padrão da unidade escolhida",
    "kmh": "Quilômetros por hora (km/h)",
    "mph": "Milhas por hora (mph)",
    "ms": "Metros por segundo (m/s)",
    "kn": "Nós (kn)",
}

PRECIPITATION_SYMBOLS = {"mm": "mm", "inch": "pol"}

DATE_FORMATS = {
    "dmy": "Dia/Mês/Ano",
    "mdy": "Mês/Dia/Ano",
    "ymd": "Ano/Mês/Dia",
}

DEFAULTS = {
    "first_run": True,
    "startup_minimized": False,
    "close_to_tray": True,
    "units": "metric",
    "time_format": "24h",
    "date_format": "dmy",
    "font_scale": 100,
    "hourly_hours": 24,
    "daily_days": 7,
    "refresh_minutes": 30,
    "refresh_on_start": True,
    "cache_minutes": 15,
    "units_wind": "",
    "announcements": DEFAULT_ANNOUNCEMENTS,
    "notifications": DEFAULT_NOTIFICATIONS,
    "toast_app_name": "AccessWeather",
    "last_update_check": "",
    "installed_version": "",
    "update_pending_note": "",
}


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    path = app_root() / "data"
    path.mkdir(exist_ok=True)
    return path


def tools_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return app_root() / "tools"


def unit_codes(settings) -> dict:
    group = UNIT_GROUPS.get(
        settings["units"] if settings is not None else "metric", UNIT_GROUPS["metric"]
    )
    codes = dict(group)
    override = settings.get("units_wind") if settings is not None else ""
    if override in {"kmh", "mph", "ms", "kn"}:
        codes["wind"] = override
    return codes


def unit_symbols(settings) -> dict:
    codes = unit_codes(settings)
    return {
        "temperature": TEMPERATURE_SYMBOLS.get(codes["temperature"], "°C"),
        "wind": WIND_SYMBOLS.get(codes["wind"], "km/h"),
        "precipitation": PRECIPITATION_SYMBOLS.get(codes["precipitation"], "mm"),
    }


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        self.values = deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(loaded, dict):
            return
        announcements = loaded.pop("announcements", None)
        if not isinstance(announcements, dict):
            announcements = {
                key: bool(loaded.get("announce_status_changes", True))
                for key in ANNOUNCEMENT_LABELS
            }
        notifications = loaded.pop("notifications", None)
        if not isinstance(notifications, dict):
            notifications = dict(DEFAULT_NOTIFICATIONS)
        self.values.update({key: value for key, value in loaded.items() if key in DEFAULTS})
        self.values["announcements"].update({
            key: bool(value)
            for key, value in announcements.items()
            if key in ANNOUNCEMENT_LABELS
        })
        self.values["notifications"].update({
            key: bool(value)
            for key, value in notifications.items()
            if key in NOTIFICATION_LABELS
        })
        if self.values["units"] not in UNIT_GROUPS:
            self.values["units"] = "metric"
        if self.values["time_format"] not in TIME_FORMATS:
            self.values["time_format"] = "24h"
        if self.values["date_format"] not in DATE_FORMATS:
            self.values["date_format"] = "dmy"
        try:
            self.values["refresh_minutes"] = max(
                5, min(720, int(self.values["refresh_minutes"]))
            )
        except (TypeError, ValueError):
            self.values["refresh_minutes"] = 30
        try:
            self.values["font_scale"] = max(75, min(200, int(self.values["font_scale"])))
        except (TypeError, ValueError):
            self.values["font_scale"] = 100

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.values, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def __getitem__(self, key):
        return self.values[key]

    def get(self, key, default=None):
        return self.values.get(key, default)

    def __setitem__(self, key, value):
        self.values[key] = value