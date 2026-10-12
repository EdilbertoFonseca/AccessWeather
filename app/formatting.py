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


def format_wind(value, symbol="") -> str:
    text = _number(value, 0)
    if text == DASH:
        return DASH
    return f"{text} {symbol}".strip()


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
            format_wind(point.wind_speed, symbols["wind"]),
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
            format_wind(day.wind_speed_max, symbols["wind"]),
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
                f"Vento {format_wind(current.wind_speed, symbols['wind'])}",
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
        f"vento {format_wind(current.wind_speed, symbols['wind'])}",
        f"umidade {format_percent(current.humidity)}",
    ]
    return f"{location.full_label}: " + ", ".join(parts) + "."


def _notification_part(field, forecast, symbols):
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
            f"Sensação {format_temperature(current.apparent_temperature, symbols['temperature'])}"
            if current else ""
        )
    if field == "wind_speed":
        return (
            f"Vento {format_wind(current.wind_speed, symbols['wind'])}"
            if current else ""
        )
    if field == "humidity":
        return f"Umidade {format_percent(current.humidity)}" if current else ""
    if field == "precipitation":
        return (
            f"Chuva {format_precipitation(current.precipitation, symbols['precipitation'])}"
            if current else ""
        )
    if field == "precipitation_probability":
        return (
            f"Chance de chuva {format_percent(point.precipitation_probability)}"
            if point else ""
        )
    if field == "daily_max":
        return (
            f"Máxima {format_temperature(day.temperature_max, symbols['temperature'])}"
            if day else ""
        )
    if field == "daily_min":
        return (
            f"Mínima {format_temperature(day.temperature_min, symbols['temperature'])}"
            if day else ""
        )
    return ""


def notification_body(location, forecast, fields, symbols, time_format="24h") -> str:
    """Corpo da notificação de clima de hora em hora, só com os campos escolhidos."""
    if not forecast or forecast.current is None:
        return "Sem dados de clima no momento."
    selected = [field for field in (fields or ()) if field]
    parts = []
    for field in selected:
        text = _notification_part(field, forecast, symbols)
        if text and text != DASH:
            parts.append(text)
    if not parts:
        return "Sem dados de clima no momento."
    body = ", ".join(parts)
    moment = forecast.current.time
    if isinstance(moment, datetime):
        body = f"{body} — {format_time(moment, time_format)}"
    return body


def hour_text(point, symbols, time_format="24h") -> str:
    return (
        f"{format_time(point.time, time_format)}: "
        f"{format_temperature(point.temperature, symbols['temperature'])}, "
        f"{point.description}, "
        f"chance de chuva {format_percent(point.precipitation_probability)}, "
        f"vento {format_wind(point.wind_speed, symbols['wind'])}, "
        f"umidade {format_percent(point.humidity)}."
    )


def day_text(day, symbols, date_format="dmy", today=None) -> str:
    return (
        f"{format_day_label(day.date, date_format, today=today)}: "
        f"{day.description}, "
        f"máxima {format_temperature(day.temperature_max, symbols['temperature'])}, "
        f"mínima {format_temperature(day.temperature_min, symbols['temperature'])}, "
        f"chuva {format_precipitation(day.precipitation_sum, symbols['precipitation'])}, "
        f"vento {format_wind(day.wind_speed_max, symbols['wind'])}."
    )
