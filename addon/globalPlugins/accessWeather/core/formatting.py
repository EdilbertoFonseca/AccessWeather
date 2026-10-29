from __future__ import annotations

from datetime import datetime


DASH = "—"

LOCATION_COLUMNS = ("Local", "Agora", "Condição", "Máxima e mínima")
HOURLY_COLUMNS = (
    "Hora",
    "Temperatura",
    "Condição",
    "Chance de chuva",
    "Vento",
    "Umidade",
)
DAILY_COLUMNS = (
    "Dia",
    "Condição",
    "Máxima",
    "Mínima",
    "Chuva",
    "Vento",
    "Nascer do sol",
    "Pôr do sol",
)

WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)
WEEKDAYS_SHORT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def _number(value, digits=0):
    if value is None or isinstance(value, bool):
        return DASH
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return DASH


def format_temperature(value, symbol="") -> str:
    text = _number(value, 0)
    if text == DASH:
        return DASH
    return f"{text} {symbol}".strip()


WIND_DIRECTION_NAMES = (
    "norte",
    "nordeste",
    "leste",
    "sudeste",
    "sul",
    "sudoeste",
    "oeste",
    "noroeste",
)


def wind_direction_name(value) -> str:
    """Nome da direção (rosa dos ventos de 8 pontos) a partir dos graus."""
    if value is None or isinstance(value, bool):
        return ""
    try:
        degrees = float(value) % 360.0
    except (TypeError, ValueError):
        return ""
    return WIND_DIRECTION_NAMES[int((degrees + 22.5) // 45.0) % 8]


def format_wind(value, symbol="", direction=None) -> str:
    text = _number(value, 0)
    name = wind_direction_name(direction)
    parts = []
    if text != DASH:
        parts.append(f"{text} {symbol}".strip())
    if name:
        parts.append(name)
    if not parts:
        return DASH
    return ", ".join(parts)


UV_LEVELS = (
    (2, "baixo"),
    (5, "moderado"),
    (7, "alto"),
    (10, "muito alto"),
    (None, "extremo"),
)

AQI_LEVELS = (
    (50, "bom"),
    (100, "moderado"),
    (150, "ruim para grupos sensíveis"),
    (200, "ruim"),
    (300, "muito ruim"),
    (None, "perigoso"),
)


def _numbered(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def uv_level(value) -> str:
    number = _numbered(value)
    if number is None:
        return ""
    level = int(round(number))
    for limit, name in UV_LEVELS:
        if limit is None or level <= limit:
            return name
    return ""


def aqi_level(value) -> str:
    number = _numbered(value)
    if number is None:
        return ""
    level = int(round(number))
    for limit, name in AQI_LEVELS:
        if limit is None or level <= limit:
            return name
    return ""


def format_uv(value) -> str:
    text = _number(value, 0)
    if text == DASH:
        return DASH
    name = uv_level(value)
    return f"{text} ({name})" if name else text


def format_air_quality(value) -> str:
    text = _number(value, 0)
    if text == DASH:
        return DASH
    name = aqi_level(value)
    return f"{text} ({name})" if name else text


def format_pm25(value) -> str:
    text = _number(value, 1)
    if text == DASH:
        return DASH
    return f"{text} µg/m³"


def format_visibility(value, symbol="km") -> str:
    number = _numbered(value)
    if number is None:
        return DASH
    amount = number / 1609.344 if symbol == "mi" else number / 1000.0
    digits = 1 if amount < 10 else 0
    return f"{amount:.{digits}f} {symbol}".strip()


def format_pressure(value) -> str:
    text = _number(value, 0)
    if text == DASH:
        return DASH
    return f"{text} hPa"


def format_duration(value) -> str:
    """Segundos do Open-Meteo em horas e minutos (ex.: 6h 20min)."""
    number = _numbered(value)
    if number is None:
        return DASH
    minutes = int(round(number)) // 60
    hours, minutes = divmod(max(0, minutes), 60)
    if minutes:
        return f"{hours}h {minutes}min"
    return f"{hours}h"


MOON_PHASES = (
    "nova",
    "crescente",
    "quarto crescente",
    "crescente gibosa",
    "cheia",
    "minguante gibosa",
    "quarto minguante",
    "minguante",
)


def moon_phase_name(value) -> str:
    """Nome da fase da lua a partir da fração do ciclo (0 = nova, 0.5 = cheia)."""
    if value is None or isinstance(value, bool):
        return ""
    try:
        fraction = float(value) % 1.0
    except (TypeError, ValueError):
        return ""
    return MOON_PHASES[int((fraction + 0.0625) // 0.125) % 8]


def format_precipitation(value, symbol="", digits=1) -> str:
    text = _number(value, digits)
    if text == DASH:
        return DASH
    return f"{text} {symbol}".strip()


def format_percent(value) -> str:
    text = _number(value, 0)
    if text == DASH:
        return DASH
    return f"{text}%"


def format_time(value, time_format="24h") -> str:
    if not isinstance(value, datetime):
        return DASH
    if time_format == "12h":
        clock = value.strftime("%I:%M").lstrip("0")
        suffix = "AM" if value.hour < 12 else "PM"
        return f"{clock} {suffix}"
    return value.strftime("%H:%M")


def format_date(value, date_format="dmy") -> str:
    if not isinstance(value, datetime):
        return DASH
    if date_format == "mdy":
        return value.strftime("%m/%d/%Y")
    if date_format == "ymd":
        return value.strftime("%Y/%m/%d")
    return value.strftime("%d/%m/%Y")


def format_day_label(value, date_format="dmy", today=None, short=False) -> str:
    if not isinstance(value, datetime):
        return DASH
    reference = today or datetime.now()
    difference = (value.date() - reference.date()).days
    if difference == 0:
        return "Hoje"
    if difference == 1:
        return "Amanhã"
    if short:
        weekday = WEEKDAYS_SHORT[value.weekday()].capitalize()
    else:
        weekday = WEEKDAYS[value.weekday()].capitalize()
    return f"{weekday}, {format_date(value, date_format)}"


def _max_min(forecast, symbols) -> str:
    if not forecast or not forecast.daily:
        return DASH
    day = forecast.daily[0]
    maximum = format_temperature(day.temperature_max, symbols["temperature"])
    minimum = format_temperature(day.temperature_min, symbols["temperature"])
    if maximum == DASH or minimum == DASH:
        return DASH
    return f"{maximum} / {minimum}"


def location_row(location, forecast, symbols) -> tuple:
    current = forecast.current if forecast else None
    if current is None or current.temperature is None:
        return (location.full_label, DASH, "Sem dados", DASH)
    return (
        location.full_label,
        format_temperature(current.temperature, symbols["temperature"]),
        current.description,
        _max_min(forecast, symbols),
    )


def hourly_rows(forecast, symbols, time_format="24h", limit=None) -> list:
    if forecast is None:
        return []
    points = forecast.hourly if limit is None else forecast.hourly[: max(0, int(limit))]
    return [
        (
            format_time(point.time, time_format),
            format_temperature(point.temperature, symbols["temperature"]),
            point.description,
            format_percent(point.precipitation_probability),
            format_wind(point.wind_speed, symbols["wind"], point.wind_direction),
            format_percent(point.humidity),
        )
        for point in points
    ]


def daily_rows(
    forecast, symbols, date_format="dmy", today=None, limit=None
) -> list:
    if forecast is None:
        return []
    days = forecast.daily if limit is None else forecast.daily[: max(0, int(limit))]
    return [
        (
            format_day_label(day.date, date_format, today=today),
            day.description,
            format_temperature(day.temperature_max, symbols["temperature"]),
            format_temperature(day.temperature_min, symbols["temperature"]),
            format_precipitation(day.precipitation_sum, symbols["precipitation"]),
            format_wind(day.wind_speed_max, symbols["wind"], day.wind_direction),
            format_time(day.sunrise),
            format_time(day.sunset),
        )
        for day in days
    ]


def current_lines(location, forecast, symbols, time_format="24h") -> str:
    if location is None:
        return "Nenhum local selecionado."
    header = location.full_label
    current = forecast.current if forecast else None
    if current is None or current.temperature is None:
        return f"{header}\nSem dados. Use Atualizar agora."
    lines = [
        header,
        f"{format_temperature(current.temperature, symbols['temperature'])} · "
        f"{current.description}",
        " · ".join(
            (
                f"Sensação {format_temperature(current.apparent_temperature, symbols['temperature'])}",
                f"Vento {format_wind(current.wind_speed, symbols['wind'], current.wind_direction)}",
                f"Umidade {format_percent(current.humidity)}",
                f"Chuva {format_precipitation(current.precipitation, symbols['precipitation'])}",
            )
        ),
    ]
    if current.time is not None:
        lines.append(f"Atualizado às {format_time(current.time, time_format)}")
    return "\n".join(lines)


def current_summary(location, forecast, symbols) -> str:
    if location is None:
        return "Nenhum local selecionado."
    current = forecast.current if forecast else None
    if current is None or current.temperature is None:
        return f"{location.full_label}: sem dados."
    parts = [
        format_temperature(current.temperature, symbols["temperature"]),
        current.description,
        f"sensação {format_temperature(current.apparent_temperature, symbols['temperature'])}",
        f"vento {format_wind(current.wind_speed, symbols['wind'], current.wind_direction)}",
        f"umidade {format_percent(current.humidity)}",
    ]
    return f"{location.full_label}: " + ", ".join(parts) + "."


def _notification_part(field, forecast, symbols, time_format="24h"):
    current = forecast.current if forecast else None
    point = forecast.hourly[0] if forecast and forecast.hourly else None
    day = forecast.daily[0] if forecast and forecast.daily else None
    if field == "temperature":
        return (
            format_temperature(current.temperature, symbols["temperature"])
            if current else DASH
        )
    if field == "condition":
        return current.description if current else DASH
    if field == "apparent_temperature":
        return (
            f"Sensação: {format_temperature(current.apparent_temperature, symbols['temperature'])}"
            if current else ""
        )
    if field == "wind_speed":
        return (
            f"Vento: {format_wind(current.wind_speed, symbols['wind'], current.wind_direction)}"
            if current else ""
        )
    if field == "humidity":
        return f"Umidade: {format_percent(current.humidity)}" if current else ""
    if field == "precipitation":
        return (
            f"Chuva: {format_precipitation(current.precipitation, symbols['precipitation'])}"
            if current else ""
        )
    if field == "precipitation_probability":
        return (
            f"Chance de chuva: {format_percent(point.precipitation_probability)}"
            if point else ""
        )
    if field == "daily_precipitation":
        return (
            f"Chuva esperada no dia: {format_precipitation(day.precipitation_sum, symbols['precipitation'])}"
            if day else ""
        )
    if field == "daily_max":
        return (
            f"Temperatura máxima: {format_temperature(day.temperature_max, symbols['temperature'])}"
            if day else ""
        )
    if field == "daily_min":
        return (
            f"Temperatura mínima: {format_temperature(day.temperature_min, symbols['temperature'])}"
            if day else ""
        )
    if field == "observation_time":
        moment = current.time if current else None
        if isinstance(moment, datetime):
            return f"Hora: {format_time(moment, time_format)}"
        return ""
    if field == "sunrise":
        text = format_time(day.sunrise, time_format) if day else DASH
        return f"Nascer do sol: {text}" if text != DASH else ""
    if field == "sunset":
        text = format_time(day.sunset, time_format) if day else DASH
        return f"Pôr do sol: {text}" if text != DASH else ""
    if field == "moonrise":
        text = format_time(day.moonrise, time_format) if day else DASH
        return f"Nascer da lua: {text}" if text != DASH else ""
    if field == "moonset":
        text = format_time(day.moonset, time_format) if day else DASH
        return f"Pôr da lua: {text}" if text != DASH else ""
    if field == "moon_phase":
        text = moon_phase_name(day.moon_phase) if day else ""
        return f"Fase da lua: {text}" if text else ""
    if field == "wind_gusts":
        text = format_wind(current.wind_gusts, symbols["wind"]) if current else DASH
        return f"Rajadas de vento: {text}" if text != DASH else ""
    if field == "rain":
        text = (
            format_precipitation(current.rain, symbols["precipitation"])
            if current else DASH
        )
        return f"Chuva contínua: {text}" if text != DASH else ""
    if field == "showers":
        text = (
            format_precipitation(current.showers, symbols["precipitation"])
            if current else DASH
        )
        return f"Pancadas: {text}" if text != DASH else ""
    if field == "uv_index":
        text = format_uv(current.uv_index) if current else DASH
        return f"Índice UV: {text}" if text != DASH else ""
    if field == "visibility":
        text = (
            format_visibility(
                current.visibility, symbols.get("visibility", "km")
            ) if current else DASH
        )
        return f"Visibilidade: {text}" if text != DASH else ""
    if field == "pressure":
        text = format_pressure(current.pressure) if current else DASH
        return f"Pressão: {text}" if text != DASH else ""
    if field == "cloud_cover":
        text = format_percent(current.cloud_cover) if current else DASH
        return f"Nebulosidade: {text}" if text != DASH else ""
    if field == "air_quality":
        text = format_air_quality(current.air_quality) if current else DASH
        return f"Qualidade do ar: {text}" if text != DASH else ""
    if field == "pm2_5":
        text = format_pm25(current.pm2_5) if current else DASH
        return f"PM2.5: {text}" if text != DASH else ""
    if field == "wind_gusts_max":
        text = (
            format_wind(day.wind_gusts_max, symbols["wind"]) if day else DASH
        )
        return f"Rajadas máximas do dia: {text}" if text != DASH else ""
    if field == "apparent_max":
        text = (
            format_temperature(day.apparent_max, symbols["temperature"])
            if day else DASH
        )
        return f"Sensação máxima do dia: {text}" if text != DASH else ""
    if field == "apparent_min":
        text = (
            format_temperature(day.apparent_min, symbols["temperature"])
            if day else DASH
        )
        return f"Sensação mínima do dia: {text}" if text != DASH else ""
    if field == "rain_sum":
        text = (
            format_precipitation(day.rain_sum, symbols["precipitation"])
            if day else DASH
        )
        return f"Chuva contínua no dia: {text}" if text != DASH else ""
    if field == "showers_sum":
        text = (
            format_precipitation(day.showers_sum, symbols["precipitation"])
            if day else DASH
        )
        return f"Pancadas no dia: {text}" if text != DASH else ""
    if field == "precipitation_hours":
        text = _number(day.precipitation_hours, 0) if day else DASH
        return f"Horas de chuva no dia: {text} h" if text != DASH else ""
    if field == "uv_index_max":
        text = format_uv(day.uv_index_max) if day else DASH
        return f"UV máximo do dia: {text}" if text != DASH else ""
    if field == "sunshine_duration":
        text = format_duration(day.sunshine_duration) if day else DASH
        return f"Horas de sol: {text}" if text != DASH else ""
    if field == "daylight_duration":
        text = format_duration(day.daylight_duration) if day else DASH
        return f"Duração do dia: {text}" if text != DASH else ""
    return ""


def field_text(field, forecast, symbols, time_format="24h") -> str:
    """Texto de um único campo do anúncio, usado pela prévia com F2."""
    text = _notification_part(field, forecast, symbols, time_format)
    return text if text and text != DASH else ""


def notification_body(location, forecast, fields, symbols, time_format="24h") -> str:
    """Corpo da notificação de clima de hora em hora, só com os campos escolhidos."""
    if not forecast or forecast.current is None:
        return "Sem dados de clima no momento."
    selected = [field for field in (fields or ()) if field]
    parts = []
    for field in selected:
        text = _notification_part(field, forecast, symbols, time_format)
        if text and text != DASH:
            parts.append(text)
    if not parts:
        return "Sem dados de clima no momento."
    return ", ".join(parts)


def hour_text(point, symbols, time_format="24h") -> str:
    return (
        f"{format_time(point.time, time_format)}: "
        f"{format_temperature(point.temperature, symbols['temperature'])}, "
        f"{point.description}, "
        f"chance de chuva {format_percent(point.precipitation_probability)}, "
        f"vento {format_wind(point.wind_speed, symbols['wind'], point.wind_direction)}, "
        f"umidade {format_percent(point.humidity)}."
    )


def day_text(day, symbols, date_format="dmy", today=None) -> str:
    return (
        f"{format_day_label(day.date, date_format, today=today)}: "
        f"{day.description}, "
        f"máxima {format_temperature(day.temperature_max, symbols['temperature'])}, "
        f"mínima {format_temperature(day.temperature_min, symbols['temperature'])}, "
        f"chuva {format_precipitation(day.precipitation_sum, symbols['precipitation'])}, "
        f"vento {format_wind(day.wind_speed_max, symbols['wind'], day.wind_direction)}."
    )
