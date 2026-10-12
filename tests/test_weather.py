import unittest
from datetime import datetime
from unittest import mock

import requests

from app.weather import (
    CURRENT_FIELDS,
    DAILY_FIELDS,
    GEOCODE_URL,
    HOURLY_FIELDS,
    MAX_FORECAST_DAYS,
    WMO_LABELS,
    WMO_SEVERITY,
    DailyPoint,
    Forecast,
    Place,
    WeatherError,
    build_forecast_params,
    code_severity,
    describe_code,
    fetch_forecast,
    is_precipitation,
    parse_date,
    parse_datetime,
    parse_forecast,
    request_json,
    search_places,
)


def _response(payload=None, status=200, json_error=None):
    response = mock.Mock()
    response.status_code = status
    if json_error is not None:
        response.json.side_effect = json_error
    else:
        response.json.return_value = payload
    return response


class _FakeSettings:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)

    def __getitem__(self, key):
        return self.values[key]


def _settings(**overrides):
    values = {
        "units": "metric",
        "units_wind": "",
        "daily_days": 7,
        "hourly_hours": 24,
    }
    values.update(overrides)
    return _FakeSettings(**values)


class WmoLabelTests(unittest.TestCase):
    def test_every_documented_code_has_a_label(self):
        expected = {0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67,
                    71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}
        self.assertEqual(set(WMO_LABELS), expected)

    def test_every_code_has_a_severity(self):
        self.assertEqual(set(WMO_SEVERITY), set(WMO_LABELS))

    def test_labels_start_with_a_capital_and_have_no_trailing_space(self):
        for code, label in WMO_LABELS.items():
            self.assertEqual(label, label.strip(), code)
            self.assertTrue(label[0].isupper(), code)

    def test_describe_code_accepts_numeric_strings(self):
        self.assertEqual(describe_code("95"), "Trovoada")

    def test_describe_code_falls_back_for_unknown_values(self):
        self.assertEqual(describe_code(7), "Condição desconhecida")
        self.assertEqual(describe_code(None), "Condição desconhecida")
        self.assertEqual(describe_code("abc"), "Condição desconhecida")

    def test_severity_orders_the_worst_conditions_last(self):
        self.assertEqual(code_severity(0), 0)
        self.assertGreater(code_severity(99), code_severity(65))
        self.assertGreater(code_severity(95), code_severity(61))

    def test_severity_of_an_unknown_code_is_zero(self):
        self.assertEqual(code_severity(7), 0)
        self.assertEqual(code_severity(None), 0)

    def test_precipitation_starts_at_the_drizzle_codes(self):
        self.assertFalse(is_precipitation(3))
        self.assertFalse(is_precipitation(45))
        self.assertTrue(is_precipitation(51))
        self.assertTrue(is_precipitation(95))
        self.assertFalse(is_precipitation(None))


class PlaceTests(unittest.TestCase):
    PAYLOAD = {
        "id": 3448439,
        "name": "São Paulo",
        "latitude": -23.5475,
        "longitude": -46.63611,
        "timezone": "America/Sao_Paulo",
        "country": "Brasil",
        "admin1": "São Paulo",
        "admin2": "São Paulo",
        "population": 12300000,
    }

    def test_label_joins_name_region_and_country(self):
        payload = dict(self.PAYLOAD, name="Santos", admin1="São Paulo")
        self.assertEqual(Place.from_payload(payload).label, "Santos, São Paulo, Brasil")

    def test_label_does_not_repeat_the_region_when_it_matches_the_name(self):
        self.assertEqual(Place.from_payload(self.PAYLOAD).label, "São Paulo, Brasil")

    def test_label_falls_back_to_admin2(self):
        payload = dict(self.PAYLOAD, name="Santos", admin1="", admin2="Santos")
        self.assertEqual(Place.from_payload(payload).label, "Santos, Brasil")

    def test_label_without_a_country(self):
        payload = dict(self.PAYLOAD, country="", admin1="")
        self.assertEqual(Place.from_payload(payload).label, "São Paulo")

    def test_key_is_stable_and_differentiates_coordinates(self):
        first = Place.from_payload(self.PAYLOAD)
        second = Place.from_payload(self.PAYLOAD)
        self.assertEqual(first.key, second.key)
        moved = Place.from_payload(dict(self.PAYLOAD, latitude=-23.0))
        self.assertNotEqual(first.key, moved.key)

    def test_missing_coordinates_are_rejected(self):
        payload = {key: value for key, value in self.PAYLOAD.items() if key != "latitude"}
        with self.assertRaises(WeatherError):
            Place.from_payload(payload)

    def test_non_numeric_coordinates_are_rejected(self):
        with self.assertRaises(WeatherError):
            Place.from_payload(dict(self.PAYLOAD, longitude="oeste"))

    def test_non_dict_payload_is_rejected(self):
        with self.assertRaises(WeatherError):
            Place.from_payload(["São Paulo"])

    def test_missing_name_gets_a_readable_placeholder(self):
        payload = dict(self.PAYLOAD)
        del payload["name"]
        self.assertEqual(Place.from_payload(payload).name, "Local sem nome")

    def test_round_trips_through_dict(self):
        place = Place.from_payload(self.PAYLOAD)
        self.assertEqual(Place.from_dict(place.to_dict()), place)

    def test_from_dict_rejects_a_non_dict(self):
        with self.assertRaises(WeatherError):
            Place.from_dict("São Paulo")


class SearchPlacesTests(unittest.TestCase):
    def test_empty_query_does_not_reach_the_network(self):
        with mock.patch("app.weather.requests.get") as get:
            self.assertEqual(search_places("   "), ())
        get.assert_not_called()

    def test_returns_places_in_api_order(self):
        payload = {
            "results": [
                {"id": 1, "name": "Santos", "latitude": -23.9, "longitude": -46.3},
                {"id": 2, "name": "Campinas", "latitude": -22.9, "longitude": -47.0},
            ]
        }
        with mock.patch(
            "app.weather.requests.get", return_value=_response(payload)
        ) as get:
            places = search_places("Santos")
        self.assertEqual([place.name for place in places], ["Santos", "Campinas"])
        args, kwargs = get.call_args
        self.assertEqual(args[0], GEOCODE_URL)
        self.assertEqual(kwargs["params"]["name"], "Santos")
        self.assertEqual(kwargs["params"]["language"], "pt")

    def test_missing_results_key_returns_an_empty_tuple(self):
        with mock.patch("app.weather.requests.get", return_value=_response({"generationtime_ms": 1})):
            self.assertEqual(search_places("Santos"), ())

    def test_invalid_entries_are_skipped_not_fatal(self):
        payload = {
            "results": [
                {"name": "Sem coordenadas"},
                {"id": 2, "name": "Santos", "latitude": -23.9, "longitude": -46.3},
            ]
        }
        with mock.patch("app.weather.requests.get", return_value=_response(payload)):
            places = search_places("Santos")
        self.assertEqual([place.name for place in places], ["Santos"])

    def test_count_is_clamped(self):
        with mock.patch(
            "app.weather.requests.get", return_value=_response({"results": []})
        ) as get:
            search_places("Santos", count=500)
            self.assertEqual(get.call_args.kwargs["params"]["count"], 50)
            search_places("Santos", count=0)
            self.assertEqual(get.call_args.kwargs["params"]["count"], 1)

    def test_network_failure_becomes_a_weather_error(self):
        with mock.patch(
            "app.weather.requests.get", side_effect=requests.ConnectionError("sem rede")
        ):
            with self.assertRaises(WeatherError):
                search_places("Santos")


class RequestJsonTests(unittest.TestCase):
    def test_sends_an_identifying_user_agent(self):
        with mock.patch(
            "app.weather.requests.get", return_value=_response({"ok": True})
        ) as get:
            self.assertEqual(request_json("https://exemplo", {"a": 1}), {"ok": True})
        headers = get.call_args.kwargs["headers"]
        self.assertIn("AccessWeather", headers["User-Agent"])

    def test_closes_the_response(self):
        response = _response({"ok": True})
        with mock.patch("app.weather.requests.get", return_value=response):
            request_json("https://exemplo", {})
        response.close.assert_called_once()

    def test_retries_a_temporary_status_and_then_succeeds(self):
        responses = [
            _response(status=503),
            _response(status=429),
            _response({"ok": True}),
        ]
        with mock.patch(
            "app.weather.requests.get", side_effect=responses
        ) as get, mock.patch("app.weather.time.sleep") as sleep:
            self.assertEqual(request_json("https://exemplo", {}), {"ok": True})
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_gives_up_after_the_last_attempt(self):
        with mock.patch(
            "app.weather.requests.get", return_value=_response(status=500)
        ) as get, mock.patch("app.weather.time.sleep"):
            with self.assertRaisesRegex(WeatherError, "temporariamente"):
                request_json("https://exemplo", {})
        self.assertEqual(get.call_count, 3)

    def test_retries_a_connection_error(self):
        with mock.patch(
            "app.weather.requests.get",
            side_effect=[requests.ConnectionError("sem rede"), _response({"ok": True})],
        ) as get, mock.patch("app.weather.time.sleep"):
            self.assertEqual(request_json("https://exemplo", {}), {"ok": True})
        self.assertEqual(get.call_count, 2)

    def test_does_not_retry_a_client_error(self):
        with mock.patch(
            "app.weather.requests.get", return_value=_response(status=404)
        ) as get, mock.patch("app.weather.time.sleep") as sleep:
            with self.assertRaisesRegex(WeatherError, "404"):
                request_json("https://exemplo", {})
        get.assert_called_once()
        sleep.assert_not_called()

    def test_invalid_json_becomes_a_weather_error(self):
        with mock.patch(
            "app.weather.requests.get",
            return_value=_response(json_error=ValueError("ruim")),
        ):
            with self.assertRaisesRegex(WeatherError, "resposta inválida"):
                request_json("https://exemplo", {})


class ForecastParamsTests(unittest.TestCase):
    PLACE = Place(name="Santos", latitude=-23.9, longitude=-46.3)

    def test_uses_metric_codes_by_default(self):
        params = build_forecast_params(self.PLACE)
        self.assertEqual(params["temperature_unit"], "celsius")
        self.assertEqual(params["wind_speed_unit"], "kmh")
        self.assertEqual(params["precipitation_unit"], "mm")

    def test_follows_the_selected_units(self):
        params = build_forecast_params(self.PLACE, _settings(units="imperial"))
        self.assertEqual(params["temperature_unit"], "fahrenheit")
        self.assertEqual(params["wind_speed_unit"], "mph")

    def test_requests_the_configured_windows(self):
        params = build_forecast_params(self.PLACE, _settings(daily_days=5, hourly_hours=48))
        self.assertEqual(params["forecast_days"], 5)
        self.assertEqual(params["forecast_hours"], 48)

    def test_explicit_arguments_win_over_settings(self):
        params = build_forecast_params(
            self.PLACE, _settings(daily_days=5), days=2, hours=6
        )
        self.assertEqual(params["forecast_days"], 2)
        self.assertEqual(params["forecast_hours"], 6)

    def test_clamps_the_requested_window(self):
        params = build_forecast_params(self.PLACE, None, days=99, hours=9999)
        self.assertEqual(params["forecast_days"], MAX_FORECAST_DAYS)
        self.assertEqual(params["forecast_hours"], MAX_FORECAST_DAYS * 24)
        params = build_forecast_params(self.PLACE, None, days=0, hours=0)
        self.assertEqual(params["forecast_days"], 1)
        self.assertEqual(params["forecast_hours"], 1)

    def test_asks_the_api_for_its_local_timezone(self):
        self.assertEqual(build_forecast_params(self.PLACE)["timezone"], "auto")

    def test_requests_exactly_the_fields_the_app_parses(self):
        params = build_forecast_params(self.PLACE)
        self.assertEqual(params["hourly"].split(","), list(HOURLY_FIELDS))
        self.assertEqual(params["daily"].split(","), list(DAILY_FIELDS))
        self.assertEqual(params["current"].split(","), list(CURRENT_FIELDS))


class ParseForecastTests(unittest.TestCase):
    PAYLOAD = {
        "timezone": "America/Sao_Paulo",
        "elevation": 8.0,
        "current": {
            "time": "2026-10-02T18:45",
            "temperature_2m": 15.4,
            "apparent_temperature": 15.1,
            "weather_code": 3,
            "wind_speed_10m": 9.8,
            "relative_humidity_2m": 88,
            "precipitation": 0.0,
            "is_day": 0,
        },
        "hourly": {
            "time": ["2026-10-02T18:00", "2026-10-02T19:00", "2026-10-02T20:00"],
            "temperature_2m": [15.7, 15.2, None],
            "apparent_temperature": [15.3, 14.8, 14.0],
            "precipitation_probability": [6, 12, 20],
            "precipitation": [0.0, 0.1, 0.2],
            "weather_code": [3, 61, 95],
            "wind_speed_10m": [10.3, 9.9, 8.0],
            "relative_humidity_2m": [87, 88, 90],
            "is_day": [0, 0, 0],
        },
        "daily": {
            "time": ["2026-10-02", "2026-10-03"],
            "weather_code": [53, 95],
            "temperature_2m_max": [18.3, 20.0],
            "temperature_2m_min": [15.1, 16.0],
            "sunrise": ["2026-10-02T05:45", "2026-10-03T05:46"],
            "sunset": ["2026-10-02T18:05", "2026-10-03T18:04"],
            "precipitation_sum": [2.1, 8.0],
            "precipitation_probability_max": [99, 80],
            "wind_speed_10m_max": [11.0, 22.0],
        },
    }

    def test_reads_the_current_conditions(self):
        current = parse_forecast(self.PAYLOAD).current
        self.assertEqual(current.temperature, 15.4)
        self.assertEqual(current.code, 3)
        self.assertEqual(current.description, "Encoberto")
        self.assertTrue(current.is_night)

    def test_reads_every_hour_in_order(self):
        hourly = parse_forecast(self.PAYLOAD).hourly
        self.assertEqual(len(hourly), 3)
        self.assertEqual(hourly[1].time, datetime(2026, 10, 2, 19, 0))
        self.assertEqual(hourly[1].description, "Chuva fraca")

    def test_tolerates_a_missing_value_inside_a_series(self):
        hourly = parse_forecast(self.PAYLOAD).hourly
        self.assertIsNone(hourly[2].temperature)
        self.assertEqual(hourly[2].code, 95)

    def test_reads_every_day(self):
        daily = parse_forecast(self.PAYLOAD).daily
        self.assertEqual(len(daily), 2)
        self.assertEqual(daily[0].date, datetime(2026, 10, 2))
        self.assertEqual(daily[0].temperature_max, 18.3)
        self.assertEqual(daily[0].sunrise, datetime(2026, 10, 2, 5, 45))
        self.assertEqual(daily[1].description, "Trovoada")

    def test_keeps_the_timezone_and_elevation(self):
        forecast = parse_forecast(self.PAYLOAD)
        self.assertEqual(forecast.timezone, "America/Sao_Paulo")
        self.assertEqual(forecast.elevation, 8.0)

    def test_keeps_the_requested_units(self):
        forecast = parse_forecast(self.PAYLOAD, units={"temperature": "celsius"})
        self.assertEqual(forecast.units["temperature"], "celsius")

    def test_empty_blocks_do_not_raise(self):
        forecast = parse_forecast({"timezone": "UTC"})
        self.assertEqual(forecast.hourly, ())
        self.assertEqual(forecast.daily, ())
        self.assertIsNone(forecast.current.temperature)
        self.assertEqual(forecast.current.description, "Condição desconhecida")
        self.assertTrue(forecast.current.is_day)

    def test_a_time_block_that_is_not_a_list_is_ignored(self):
        payload = {"hourly": {"time": "2026-10-02T18:00"}, "daily": {"time": None}}
        forecast = parse_forecast(payload)
        self.assertEqual(forecast.hourly, ())
        self.assertEqual(forecast.daily, ())

    def test_shorter_series_are_truncated(self):
        payload = {
            "hourly": {"time": ["2026-10-02T18:00", "2026-10-02T19:00"],
                       "weather_code": [0]},
        }
        hourly = parse_forecast(payload).hourly
        self.assertEqual(len(hourly), 2)
        self.assertEqual(hourly[0].code, 0)
        self.assertIsNone(hourly[1].code)

    def test_string_numbers_are_converted(self):
        payload = {"current": {"temperature_2m": "15.4", "weather_code": "3"}}
        current = parse_forecast(payload).current
        self.assertEqual(current.temperature, 15.4)
        self.assertEqual(current.code, 3)

    def test_booleans_are_not_read_as_numbers(self):
        payload = {"current": {"temperature_2m": True, "is_day": True}}
        current = parse_forecast(payload).current
        self.assertIsNone(current.temperature)
        self.assertTrue(current.is_day)

    def test_non_dict_payload_is_rejected(self):
        with self.assertRaises(WeatherError):
            parse_forecast(["não é um objeto"])


class ForecastHelpersTests(unittest.TestCase):
    HOURS = (
        mock.Mock(time=datetime(2026, 10, 2, 17, 0), code=0),
        mock.Mock(time=datetime(2026, 10, 2, 18, 0), code=61),
        mock.Mock(time=datetime(2026, 10, 2, 19, 0), code=95),
    )
    DAYS = (
        DailyPoint(date=datetime(2026, 10, 2), code=3, temperature_max=18.0,
                   temperature_min=15.0),
        DailyPoint(date=datetime(2026, 10, 3), code=95, temperature_max=20.0,
                   temperature_min=16.0),
        DailyPoint(date=datetime(2026, 10, 4), code=61, temperature_max=21.0,
                   temperature_min=17.0),
    )

    def _forecast(self):
        return Forecast(place=None, hourly=self.HOURS, daily=self.DAYS)

    def test_hourly_in_window_keeps_the_future_hours(self):
        window = self._forecast().hourly_in_window(datetime(2026, 10, 2, 18, 0))
        self.assertEqual([point.time.hour for point in window], [18, 19])

    def test_hourly_in_window_without_a_start_returns_everything(self):
        self.assertEqual(len(self._forecast().hourly_in_window(None)), 3)

    def test_hourly_in_window_drops_points_without_a_time(self):
        forecast = Forecast(place=None, hourly=(mock.Mock(time=None, code=0),))
        self.assertEqual(forecast.hourly_in_window(datetime(2026, 10, 2)), ())

    def test_next_days_limits_the_list(self):
        self.assertEqual(len(self._forecast().next_days(2)), 2)
        self.assertEqual(self._forecast().next_days(0), ())

    def test_worst_severity_looks_at_the_whole_week(self):
        self.assertEqual(self._forecast().worst_severity(), code_severity(95))

    def test_worst_severity_without_days_is_zero(self):
        self.assertEqual(Forecast(place=None).worst_severity(), 0)


class TimeParsingTests(unittest.TestCase):
    def test_parses_minutes(self):
        self.assertEqual(parse_datetime("2026-10-02T18:45"), datetime(2026, 10, 2, 18, 45))

    def test_parses_seconds_and_offsets(self):
        self.assertEqual(
            parse_datetime("2026-10-02T18:45:30"), datetime(2026, 10, 2, 18, 45, 30)
        )
        parsed = parse_datetime("2026-10-02T18:45:00Z")
        self.assertEqual((parsed.year, parsed.month, parsed.day), (2026, 10, 2))
        self.assertEqual(parsed.hour, 18)
        self.assertIsNone(parsed.tzinfo)

    def test_parses_a_plain_date(self):
        self.assertEqual(parse_datetime("2026-10-02"), datetime(2026, 10, 2))

    def test_rejects_unusable_values(self):
        for value in ("", "   ", "ontem", None, 20261002):
            self.assertIsNone(parse_datetime(value))

    def test_parse_date_falls_back_to_the_datetime_parser(self):
        self.assertEqual(parse_date("2026-10-02"), datetime(2026, 10, 2))
        self.assertEqual(parse_date("2026-10-02T00:00"), datetime(2026, 10, 2))
        self.assertIsNone(parse_date("sem data"))


class FetchForecastTests(unittest.TestCase):
    def test_builds_params_and_parses_in_one_call(self):
        place = Place(name="Santos", latitude=-23.9, longitude=-46.3)
        settings = _settings(units="imperial", daily_days=3, hourly_hours=12)
        payload = {"timezone": "America/Sao_Paulo", "current": {"temperature_2m": 20.0}}
        with mock.patch(
            "app.weather.requests.get", return_value=_response(payload)
        ) as get:
            forecast = fetch_forecast(place, settings)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["temperature_unit"], "fahrenheit")
        self.assertEqual(params["forecast_days"], 3)
        self.assertEqual(forecast.current.temperature, 20.0)
        self.assertEqual(forecast.place, place)
        self.assertEqual(forecast.units["temperature"], "fahrenheit")

    def test_propagates_a_weather_error(self):
        place = Place(name="Santos", latitude=-23.9, longitude=-46.3)
        with mock.patch(
            "app.weather.requests.get", return_value=_response(status=400)
        ):
            with self.assertRaises(WeatherError):
                fetch_forecast(place)


if __name__ == "__main__":
    unittest.main()