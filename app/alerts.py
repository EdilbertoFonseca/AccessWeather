from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .formatting import (
    format_date,
    format_percent,
    format_precipitation,
    format_temperature,
    format_time,
    format_wind,
)
from .weather import code_severity


# Cada métrica diz de onde vem o valor, em que período é medida e como é
# escrita. A UI usa esta tabela para montar o editor de alertas.
ALERT_METRICS = {
    "temperature": {
        "label": "Temperatura",
        "scope": "hourly",
        "unit": "temperature",
        "field": "temperature",
    },
    "apparent_temperature": {
        "label": "Sensação térmica",
        "scope": "hourly",
        "unit": "temperature",
        "field": "apparent_temperature",
    },
    "wind_speed": {
        "label": "Vento",
        "scope": "hourly",
        "unit": "wind",
        "field": "wind_speed",
    },
    "precipitation": {
        "label": "Chuva na hora",
        "scope": "hourly",
        "unit": "precipitation",
        "field": "precipitation",
    },
    "precipitation_probability": {
        "label": "Chance de chuva na hora",
        "scope": "hourly",
        "unit": "percent",
        "field": "precipitation_probability",
    },
    "humidity": {
        "label": "Umidade",
        "scope": "hourly",
        "unit": "percent",
        "field": "humidity",
    },
    "daily_temperature_max": {
        "label": "Máxima do dia",
        "scope": "daily",
        "unit": "temperature",
        "field": "temperature_max",
    },
    "daily_temperature_min": {
        "label": "Mínima do dia",
        "scope": "daily",
        "unit": "temperature",
        "field": "temperature_min",
    },
    "daily_precipitation_sum": {
        "label": "Chuva acumulada no dia",
        "scope": "daily",
        "unit": "precipitation",
        "field": "precipitation_sum",
    },
    "daily_precipitation_probability": {
        "label": "Chance de chuva no dia",
        "scope": "daily",
        "unit": "percent",
        "field": "precipitation_probability_max",
    },
    "daily_wind_speed_max": {
        "label": "Vento máximo do dia",
        "scope": "daily",
        "unit": "wind",
        "field": "wind_speed_max",
    },
    "severe_weather": {
        "label": "Tempo severo",
        "scope": "daily",
        "unit": "severity",
        "field": "code",
    },
}

ALERT_OPERATORS = {
    "above": "acima de",
    "below": "abaixo de",
    "at_least": "pelo menos",
}

SEVERITY_LEVELS = {
    1: "atenção",
    2: "moderado",
    3: "alto",
    4: "severo",
    5: "extremo",
}

DEFAULT_LEAD_HOURS = 24


def metric_scope(metric) -> str:
    entry = ALERT_METRICS.get(str(metric))
    return entry["scope"] if entry else "hourly"


def severity_label(level) -> str:
    try:
        return SEVERITY_LEVELS.get(int(level), "sem alerta")
    except (TypeError, ValueError):
        return "sem alerta"


def _as_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


@dataclass(frozen=True)
class AlertRule:
    metric: str
    operator: str
    threshold: float
    scope: str = ""
    lead_hours: int = DEFAULT_LEAD_HOURS
    enabled: bool = True
    toast: bool = True
    announce: bool = True
    identifier: str = ""

    def __post_init__(self):
        if not self.scope:
            object.__setattr__(self, "scope", metric_scope(self.metric))

    @property
    def key(self) -> str:
        if self.identifier:
            return str(self.identifier)
        return f"{self.metric}:{self.operator}:{self.threshold:g}"

    @classmethod
    def from_dict(cls, payload) -> "AlertRule":
        if not isinstance(payload, dict):
            raise ValueError("Regra de alerta inválida.")
        metric = str(payload.get("metric") or "")
        if metric not in ALERT_METRICS:
            raise ValueError(f"Métrica desconhecida: {metric!r}")
        operator = str(payload.get("operator") or "above")
        if operator not in ALERT_OPERATORS:
            operator = "above"
        return cls(
            metric=metric,
            operator=operator,
            threshold=_as_float(payload.get("threshold")),
            scope=str(payload.get("scope") or "") or metric_scope(metric),
            lead_hours=int(_as_float(payload.get("lead_hours"), DEFAULT_LEAD_HOURS)),
            enabled=bool(payload.get("enabled", True)),
            toast=bool(payload.get("toast", True)),
            announce=bool(payload.get("announce", True)),
            identifier=str(payload.get("id") or payload.get("identifier") or ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.identifier,
            "metric": self.metric,
            "operator": self.operator,
            "threshold": self.threshold,
            "scope": self.scope,
            "lead_hours": self.lead_hours,
            "enabled": self.enabled,
            "toast": self.toast,
            "announce": self.announce,
        }


@dataclass(frozen=True)
class AlertHit:
    rule: AlertRule
    moment: object | None
    value: float
    message: str


def parse_rules(payloads) -> tuple:
    """Converte a lista guardada por local em regras, ignorando as inválidas."""
    rules = []
    for item in payloads or ():
        try:
            rules.append(item if isinstance(item, AlertRule) else AlertRule.from_dict(item))
        except (ValueError, TypeError):
            continue
    return tuple(rules)


def rules_to_payload(rules) -> list:
    return [rule.to_dict() for rule in rules]


def make_rule(metric, operator="above", threshold=0.0, **kwargs) -> AlertRule:
    return AlertRule(
        metric=metric, operator=operator, threshold=_as_float(threshold), **kwargs
    )


def describe_rule(rule) -> str:
    entry = ALERT_METRICS.get(rule.metric, {"label": rule.metric})
    verb = ALERT_OPERATORS.get(rule.operator, rule.operator)
    if rule.metric == "severe_weather":
        condition = f"tempo {severity_label(rule.threshold)} ou pior"
    else:
        condition = f"{entry['label']} {verb} {rule.threshold:g}"
    if rule.scope == "hourly" and rule.lead_hours:
        return f"{condition} nas próximas {rule.lead_hours} horas"
    return condition


def format_value(metric, value, symbols) -> str:
    entry = ALERT_METRICS.get(metric, {"unit": "number"})
    unit = entry["unit"]
    if unit == "temperature":
        return format_temperature(value, symbols["temperature"])
    if unit == "wind":
        return format_wind(value, symbols["wind"])
    if unit == "precipitation":
        return format_precipitation(value, symbols["precipitation"])
    if unit == "percent":
        return format_percent(value)
    if unit == "severity":
        return severity_label(value)
    return f"{value:g}"


def _within_window(point_time, now, lead_hours):
    if now is None or point_time is None or not lead_hours:
        return True
    limit = now + timedelta(hours=int(lead_hours))
    return now <= point_time <= limit


def _matches(operator, value, threshold) -> bool:
    if operator == "below":
        return value < threshold
    if operator == "at_least":
        return value >= threshold
    return value > threshold


def _hourly_hit(rule, forecast, now):
    field_name = ALERT_METRICS[rule.metric]["field"]
    for point in forecast.hourly:
        if not _within_window(point.time, now, rule.lead_hours):
            continue
        if rule.metric == "severe_weather":
            value = code_severity(point.code)
        else:
            value = getattr(point, field_name, None)
        if value is None:
            continue
        if _matches(rule.operator, float(value), rule.threshold):
            return point.time, float(value)
    return None, None


def _daily_hit(rule, forecast, now):
    field_name = ALERT_METRICS[rule.metric]["field"]
    for day in forecast.daily:
        if rule.metric == "severe_weather":
            value = code_severity(day.code)
        else:
            value = getattr(day, field_name, None)
        if value is None:
            continue
        if _matches(rule.operator, float(value), rule.threshold):
            return day.date, float(value)
    return None, None


def evaluate_rule(rule, forecast, symbols, now=None):
    if forecast is None or not rule.enabled:
        return None
    if rule.metric not in ALERT_METRICS:
        return None
    if rule.scope == "daily":
        moment, value = _daily_hit(rule, forecast, now)
    else:
        moment, value = _hourly_hit(rule, forecast, now)
    if moment is None and value is None:
        return None
    when = ""
    if isinstance(moment, datetime):
        if rule.scope == "daily":
            when = f" em {format_date(moment)}"
        else:
            when = f" às {format_time(moment)}"
    message = f"{describe_rule(rule)}: {format_value(rule.metric, value, symbols)}{when}."
    return AlertHit(rule=rule, moment=moment, value=value, message=message)


def evaluate(forecast, rules, symbols, now=None) -> list:
    hits = []
    for rule in parse_rules(rules):
        hit = evaluate_rule(rule, forecast, symbols, now=now)
        if hit is not None:
            hits.append(hit)
    return hits
