from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

from .config import unit_codes


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = "AccessWeather-NVDA/0.1.0 (+https://jrtec.ddns.net/accessweather)"

TEMPORARY_STATUS = frozenset({429, 500, 502, 503, 504})
RETRY_DELAYS = (1.0, 2.0)

HOURLY_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "relative_humidity_2m",
    "is_day",
)
DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "sunrise",
    "sunset",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
)
CURRENT_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "weather_code",
    "wind_speed_10m",
    "relative_humidity_2m",
    "precipitation",
    "is_day",
)

MAX_FORECAST_DAYS = 16

# WMO 4677, em um único lugar para que listas, anúncios e notificações nunca
# discordem sobre a condição do tempo.
WMO_LABELS = {
    0: "Céu limpo",
    1: "Predominantemente limpo",
    2: "Parcialmente nublado",
    3: "Encoberto",
    45: "Nevoeiro",
    48: "Nevoeiro com geada",
    51: "Garoa fraca",
    53: "Garoa moderada",
    55: "Garoa intensa",
    56: "Garoa congelante fraca",
    57: "Garoa congelante intensa",
    61: "Chuva fraca",
    63: "Chuva moderada",
    65: "Chuva forte",
    66: "Chuva congelante fraca",
    67: "Chuva congelante forte",
    71: "Neve fraca",
    73: "Neve moderada",
    75: "Neve forte",
    77: "Grãos de neve",
    80: "Pancadas de chuva fracas",
    81: "Pancadas de chuva moderadas",
    82: "Pancadas de chuva fortes",
    85: "Pancadas de neve fracas",
    86: "Pancadas de neve fortes",
    95: "Trovoada",
    96: "Trovoada com granizo pequeno",
    99: "Trovoada com granizo grande",
}

# Códigos que valem um alerta por severidade, do mais brando ao mais grave.
WMO_SEVERITY = {
    0: 0, 1: 0, 2: 0, 3: 1,
    45: 2, 48: 2,
    51: 1, 53: 2, 55: 3,
    56: 3, 57: 4,
    61: 2, 63: 3, 65: 4,
    66: 4, 67: 5,
    71: 2, 73: 3, 75: 4,
    77: 1,
    80: 2, 81: 3, 82: 5,
    85: 3, 86: 5,
    95: 4, 96: 5, 99: 5,
}


class WeatherError(RuntimeError):
    """Falha ao falar com o Open-Meteo ou ao interpretar a resposta."""


def describe_code(code) -> str:
    try:
        return WMO_LABELS[int(code)]
    except (KeyError, TypeError, ValueError):
        return "Condição desconhecida"


def code_severity(code) -> int:
    try:
        return WMO_SEVERITY.get(int(code), 0)
    except (TypeError, ValueError):
        return 0


def is_precipitation(code) -> bool:
    try:
        return int(code) >= 51
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class Place:
    name: str
    latitude: float
    longitude: float
    country: str = ""
    admin1: str = ""
    admin2: str = ""
    timezone: str = ""
    place_id: int = 0
    population: int = 0

    @property
    def label(self) -> str:
        parts = [self.name]
        detail = self.admin1 or self.admin2
        if detail and detail != self.name:
            parts.append(detail)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)

    @property
    def key(self) -> str:
        return f"{self.place_id or 0}:{self.latitude:.4f}:{self.longitude:.4f}"

    @classmethod
    def from_payload(cls, payload) -> "Place":
        if not isinstance(payload, dict):
            raise WeatherError("O serviço de busca devolveu um local inválido.")
        try:
            return cls(
                name=str(payload.get("name") or "Local sem nome"),
                latitude=float(payload["latitude"]),
                longitude=float(payload["longitude"]),
                country=str(payload.get("country") or ""),
                admin1=str(payload.get("admin1") or ""),
                admin2=str(payload.get("admin2") or ""),
                timezone=str(payload.get("timezone") or ""),
                place_id=int(payload.get("id") or payload.get("place_id") or 0),
                population=int(payload.get("population") or 0),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherError("O serviço de busca devolveu um local inválido.") from exc

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "country": self.country,
            "admin1": self.admin1,
            "admin2": self.admin2,
            "timezone": self.timezone,
            "place_id": self.place_id,
            "population": self.population,
        }

    @classmethod
    def from_dict(cls, payload) -> "Place":
        if not isinstance(payload, dict):
            raise WeatherError("Local salvo inválido.")
        return cls.from_payload(payload)


@dataclass(frozen=True)
class CurrentWeather:
    time: object | None
    temperature: float | None
    apparent_temperature: float | None
    code: int | None
    wind_speed: float | None
    humidity: float | None
    precipitation: float | None
    is_day: bool = True

    @property
    def description(self) -> str:
        return describe_code(self.code)

    @property
    def is_night(self) -> bool:
        return not self.is_day


@dataclass(frozen=True)
class HourlyPoint:
    time: object | None
    temperature: float | None
    apparent_temperature: float | None
    precipitation_probability: float | None
    precipitation: float | None
    code: int | None
    wind_speed: float | None
    humidity: float | None
    is_day: bool = True

    @property
    def description(self) -> str:
        return describe_code(self.code)

    @property
    def is_night(self) -> bool:
        return not self.is_day


@dataclass(frozen=True)
class DailyPoint:
    date: object | None
    code: int | None
    temperature_max: float | None
    temperature_min: float | None
    sunrise: object | None = None
    sunset: object | None = None
    precipitation_sum: float | None = None
    precipitation_probability_max: float | None = None
    wind_speed_max: float | None = None

    @property
    def description(self) -> str:
        return describe_code(self.code)


@dataclass(frozen=True)
class Forecast:
    place: Place | None
    current: CurrentWeather | None = None
    hourly: tuple = field(default_factory=tuple)
    daily: tuple = field(default_factory=tuple)
    timezone: str = ""
    units: dict = field(default_factory=dict)
    elevation: float | None = None

    def hourly_in_window(self, start: object | None = None) -> tuple:
        """Horas a partir de `start`; sem `start` devolve a lista inteira."""
        if start is None:
            return self.hourly
        return tuple(point for point in self.hourly if point.time and point.time >= start)

    def next_days(self, count: int) -> tuple:
        return self.daily[: max(0, int(count))]

    def worst_severity(self) -> int:
        codes = [code_severity(point.code) for point in self.daily]
        return max(codes) if codes else 0


def _sleep_for(attempt: int) -> None:
    time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])


def request_json(url, params, timeout=20, attempts=3):
    """GET no Open-Meteo com User-Agent e repetição em erros temporários."""
    query = urllib.parse.urlencode(params or {})
    full_url = f"{url}?{query}" if query else url
    last_error = "O serviço de clima está indisponível."
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                full_url, headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", "replace")
            try:
                return json.loads(raw)
            except ValueError as exc:
                raise WeatherError(
                    "O serviço de clima devolveu uma resposta inválida."
                ) from exc
        except urllib.error.HTTPError as exc:
            status = exc.code
            if status in TEMPORARY_STATUS:
                last_error = (
                    f"O serviço de clima respondeu temporariamente ({status})."
                )
                if attempt < attempts - 1:
                    _sleep_for(attempt)
                    continue
                break
            raise WeatherError(
                f"O serviço de clima respondeu com erro {status}."
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"Falha de conexão com o serviço de clima: {exc}"
            if attempt < attempts - 1:
                _sleep_for(attempt)
                continue
            break
    raise WeatherError(last_error)


def search_places(query, count=10, language="pt", timeout=20) -> tuple:
    text = str(query or "").strip()
    if not text:
        return ()
    payload = request_json(
        GEOCODE_URL,
        {"name": text, "count": max(1, min(50, int(count))), "language": language,
         "format": "json"},
        timeout=timeout,
    )
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return ()
    places = []
    for item in results:
        try:
            places.append(Place.from_payload(item))
        except WeatherError:
            continue
    return tuple(places)


def build_forecast_params(place, settings=None, days=None, hours=None) -> dict:
    units = unit_codes(settings)
    params = {
        "latitude": place.latitude,
        "longitude": place.longitude,
        "timezone": "auto",
        "temperature_unit": units["temperature"],
        "wind_speed_unit": units["wind"],
        "precipitation_unit": units["precipitation"],
        "hourly": ",".join(HOURLY_FIELDS),
        "daily": ",".join(DAILY_FIELDS),
        "current": ",".join(CURRENT_FIELDS),
    }
    if days is None:
        days = settings.get("daily_days", 7) if settings is not None else 7
    if hours is None:
        hours = settings.get("hourly_hours", 24) if settings is not None else 24
    params["forecast_days"] = max(
        1, min(MAX_FORECAST_DAYS, _as_int(days, 7))
    )
    params["forecast_hours"] = max(
        1, min(MAX_FORECAST_DAYS * 24, _as_int(hours, 24))
    )
    return params


def parse_forecast(payload, place=None, units=None) -> Forecast:
    if not isinstance(payload, dict):
        raise WeatherError("O serviço de clima devolveu uma resposta inválida.")

    def block(name):
        value = payload.get(name)
        return value if isinstance(value, dict) else {}

    def series(source, name, index):
        values = source.get(name)
        if isinstance(values, list) and index < len(values):
            return values[index]
        return None

    def entries(source, name):
        values = source.get(name)
        return values if isinstance(values, list) else []

    def number(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    current_block = block("current")
    current = CurrentWeather(
        time=parse_datetime(current_block.get("time")),
        temperature=number(current_block.get("temperature_2m")),
        apparent_temperature=number(current_block.get("apparent_temperature")),
        code=_as_code(current_block.get("weather_code")),
        wind_speed=number(current_block.get("wind_speed_10m")),
        humidity=number(current_block.get("relative_humidity_2m")),
        precipitation=number(current_block.get("precipitation")),
        is_day=_as_flag(current_block.get("is_day")),
    )

    hourly_block = block("hourly")
    hourly = []
    for index, raw_time in enumerate(entries(hourly_block, "time")):
        hourly.append(HourlyPoint(
            time=parse_datetime(raw_time),
            temperature=number(series(hourly_block, "temperature_2m", index)),
            apparent_temperature=number(series(hourly_block, "apparent_temperature", index)),
            precipitation_probability=number(
                series(hourly_block, "precipitation_probability", index)
            ),
            precipitation=number(series(hourly_block, "precipitation", index)),
            code=_as_code(series(hourly_block, "weather_code", index)),
            wind_speed=number(series(hourly_block, "wind_speed_10m", index)),
            humidity=number(
                series(hourly_block, "relative_humidity_2m", index)
            ),
            is_day=_as_flag(series(hourly_block, "is_day", index)),
        ))

    daily_block = block("daily")
    daily = []
    for index, raw_date in enumerate(entries(daily_block, "time")):
        daily.append(DailyPoint(
            date=parse_date(raw_date),
            code=_as_code(series(daily_block, "weather_code", index)),
            temperature_max=number(
                series(daily_block, "temperature_2m_max", index)
            ),
            temperature_min=number(
                series(daily_block, "temperature_2m_min", index)
            ),
            sunrise=parse_datetime(series(daily_block, "sunrise", index)),
            sunset=parse_datetime(series(daily_block, "sunset", index)),
            precipitation_sum=number(
                series(daily_block, "precipitation_sum", index)
            ),
            precipitation_probability_max=number(
                series(
                    daily_block, "precipitation_probability_max", index
                )
            ),
            wind_speed_max=number(
                series(daily_block, "wind_speed_10m_max", index)
            ),
        ))

    return Forecast(
        place=place,
        current=current,
        hourly=tuple(hourly),
        daily=tuple(daily),
        timezone=str(payload.get("timezone") or ""),
        units=dict(units or {}),
        elevation=number(payload.get("elevation")),
    )


def fetch_forecast_payload(place, settings=None, days=None, hours=None, timeout=20) -> dict:
    """Payload cru do Open-Meteo, para guardar no cache antes de interpretar."""
    params = build_forecast_params(place, settings, days=days, hours=hours)
    return request_json(FORECAST_URL, params, timeout=timeout)


def fetch_forecast(place, settings=None, days=None, hours=None, timeout=20) -> Forecast:
    params = build_forecast_params(place, settings, days=days, hours=hours)
    payload = request_json(FORECAST_URL, params, timeout=timeout)
    return parse_forecast(payload, place=place, units=unit_codes(settings))


def parse_datetime(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    return None


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return parse_datetime(value)


def _as_code(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_int(value, default=0):
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_flag(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return default