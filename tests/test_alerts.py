import unittest
from datetime import datetime

from app.alerts import (
    ALERT_METRICS,
    ALERT_OPERATORS,
    DEFAULT_LEAD_HOURS,
    AlertRule,
    describe_rule,
    evaluate,
    evaluate_rule,
    format_value,
    make_rule,
    metric_scope,
    parse_rules,
    rules_to_payload,
    severity_label,
)
from app.formatting import DASH
from app.weather import (
    DailyPoint,
    Forecast,
    HourlyPoint,
)


SYMBOLS = {"temperature": "°C", "wind": "km/h", "precipitation": "mm"}
NOW = datetime(2026, 10, 2, 18, 0)


def _hourly(hour, temperature, code=0, wind=5.0, precipitation=0.0, probability=0.0):
    return HourlyPoint(
        time=datetime(2026, 10, 2, hour),
        temperature=temperature,
        apparent_temperature=temperature - 1,
        precipitation_probability=probability,
        precipitation=precipitation,
        code=code,
        wind_speed=wind,
        humidity=60.0,
    )


def _day(day, code=0, maxi=25.0, mini=15.0, rain=0.0, wind=10.0):
    return DailyPoint(
        date=datetime(2026, 10, day),
        code=code,
        temperature_max=maxi,
        temperature_min=mini,
        precipitation_sum=rain,
        precipitation_probability_max=10.0,
        wind_speed_max=wind,
    )


def _forecast(hourly=(), daily=()):
    return Forecast(place=None, current=None, hourly=tuple(hourly), daily=tuple(daily))


class MetricTableTests(unittest.TestCase):
    def test_every_metric_declares_scope_and_field(self):
        for name, entry in ALERT_METRICS.items():
            self.assertIn(entry["scope"], {"hourly", "daily"}, name)
            self.assertTrue(entry["field"], name)
            self.assertTrue(entry["label"], name)

    def test_metric_scope_falls_back_to_hourly(self):
        self.assertEqual(metric_scope("temperature"), "hourly")
        self.assertEqual(metric_scope("daily_temperature_max"), "daily")
        self.assertEqual(metric_scope("nope"), "hourly")

    def test_severity_labels(self):
        self.assertEqual(severity_label(5), "extremo")
        self.assertEqual(severity_label("3"), "alto")
        self.assertEqual(severity_label(0), "sem alerta")
        self.assertEqual(severity_label("x"), "sem alerta")


class AlertRuleTests(unittest.TestCase):
    def test_scope_is_inferred_from_the_metric(self):
        self.assertEqual(make_rule("daily_wind_speed_max").scope, "daily")
        self.assertEqual(make_rule("temperature").scope, "hourly")

    def test_roundtrip_through_dict(self):
        rule = make_rule("precipitation", "above", 10, lead_hours=6, identifier="r1")
        restored = AlertRule.from_dict(rule.to_dict())
        self.assertEqual(restored, rule)

    def test_from_dict_rejects_unknown_metric(self):
        with self.assertRaises(ValueError):
            AlertRule.from_dict({"metric": "mars", "threshold": 1})

    def test_from_dict_tolerates_bad_values(self):
        rule = AlertRule.from_dict(
            {"metric": "temperature", "operator": "sideways", "threshold": "abc"}
        )
        self.assertEqual(rule.operator, "above")
        self.assertEqual(rule.threshold, 0.0)

    def test_key_prefers_the_identifier(self):
        self.assertEqual(make_rule("temperature", identifier="abc").key, "abc")
        self.assertIn("temperature", make_rule("temperature", "above", 30).key)

    def test_parse_rules_skips_invalid_entries(self):
        rules = parse_rules(
            [{"metric": "temperature", "operator": "above", "threshold": 30},
             {"metric": "unknown"}, "junk", None]
        )
        self.assertEqual(len(rules), 1)

    def test_rules_to_payload_is_json_ready(self):
        payload = rules_to_payload([make_rule("temperature", "above", 30)])
        self.assertEqual(payload[0]["metric"], "temperature")
        self.assertEqual(payload[0]["threshold"], 30.0)

    def test_describe_rule_mentions_lead_hours(self):
        text = describe_rule(make_rule("precipitation", "above", 10, lead_hours=12))
        self.assertIn("10", text)
        self.assertIn("12 horas", text)

    def test_describe_severe_weather_uses_level(self):
        text = describe_rule(make_rule("severe_weather", "at_least", 4))
        self.assertIn("severo", text)


class FormatValueTests(unittest.TestCase):
    def test_units_are_applied(self):
        self.assertEqual(format_value("temperature", 30, SYMBOLS), "30 °C")
        self.assertEqual(format_value("wind_speed", 40, SYMBOLS), "40 km/h")
        self.assertEqual(format_value("precipitation", 1.5, SYMBOLS), "1.5 mm")
        self.assertEqual(format_value("humidity", 80, SYMBOLS), "80%")

    def test_severity_unit_uses_labels(self):
        self.assertEqual(format_value("severe_weather", 5, SYMBOLS), "extremo")

    def test_missing_values_become_dashes(self):
        self.assertEqual(format_value("temperature", None, SYMBOLS), DASH)


class EvaluateTests(unittest.TestCase):
    def test_temperature_above_hits_the_first_matching_hour(self):
        forecast = _forecast(hourly=[_hourly(18, 28), _hourly(19, 31), _hourly(20, 33)])
        hit = evaluate_rule(make_rule("temperature", "above", 30), forecast, SYMBOLS, now=NOW)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.value, 31.0)
        self.assertIn("31 °C", hit.message)

    def test_lead_hours_limits_the_window(self):
        forecast = _forecast(hourly=[_hourly(22, 33), _hourly(23, 34)])
        rule = make_rule("temperature", "above", 30, lead_hours=1)
        hit = evaluate_rule(rule, forecast, SYMBOLS, now=NOW)
        self.assertIsNone(hit)
        rule = make_rule("temperature", "above", 30, lead_hours=5)
        self.assertIsNotNone(evaluate_rule(rule, forecast, SYMBOLS, now=NOW))

    def test_below_operator(self):
        forecast = _forecast(hourly=[_hourly(18, 4)])
        hit = evaluate_rule(make_rule("temperature", "below", 5), forecast, SYMBOLS, now=NOW)
        self.assertIsNotNone(hit)

    def test_daily_metric_uses_the_daily_series(self):
        forecast = _forecast(daily=[_day(2, maxi=24), _day(4, maxi=36)])
        hit = evaluate_rule(
            make_rule("daily_temperature_max", "above", 30), forecast, SYMBOLS, now=NOW
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit.value, 36.0)
        self.assertIn("04/10/2026", hit.message)

    def test_severe_weather_uses_severity(self):
        forecast = _forecast(daily=[_day(2, code=63), _day(3, code=95)])
        hit = evaluate_rule(
            make_rule("severe_weather", "at_least", 4), forecast, SYMBOLS, now=NOW
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit.value, 4.0)

    def test_disabled_rule_never_hits(self):
        forecast = _forecast(hourly=[_hourly(18, 40)])
        rule = make_rule("temperature", "above", 30, enabled=False)
        self.assertIsNone(evaluate_rule(rule, forecast, SYMBOLS, now=NOW))

    def test_evaluate_collects_every_matching_rule(self):
        forecast = _forecast(hourly=[_hourly(18, 31, wind=50)])
        rules = [
            make_rule("temperature", "above", 30),
            make_rule("wind_speed", "above", 40),
            make_rule("temperature", "below", 0),
        ]
        hits = evaluate(forecast, rules, SYMBOLS, now=NOW)
        self.assertEqual(len(hits), 2)

    def test_evaluate_without_forecast_is_empty(self):
        self.assertEqual(evaluate(None, [make_rule("temperature")], SYMBOLS), [])

    def test_missing_values_are_skipped(self):
        point = HourlyPoint(
            time=datetime(2026, 10, 2, 18),
            temperature=None,
            apparent_temperature=None,
            precipitation_probability=None,
            precipitation=None,
            code=None,
            wind_speed=None,
            humidity=None,
        )
        forecast = _forecast(hourly=[point])
        self.assertIsNone(
            evaluate_rule(make_rule("temperature", "above", 0), forecast, SYMBOLS, now=NOW)
        )

    def test_default_lead_hours_is_24(self):
        self.assertEqual(make_rule("temperature").lead_hours, DEFAULT_LEAD_HOURS)

    def test_operators_table_is_complete(self):
        self.assertEqual(set(ALERT_OPERATORS), {"above", "below", "at_least"})


if __name__ == "__main__":
    unittest.main()
