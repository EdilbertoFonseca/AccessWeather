import unittest
from datetime import datetime

from app.formatting import notification_body
from app.locations import SavedLocation
from app.weather import (
    CurrentWeather,
    DailyPoint,
    Forecast,
    HourlyPoint,
    Place,
)


SYMBOLS = {"temperature": "°C", "wind": "km/h", "precipitation": "mm"}


def _location():
    return SavedLocation(
        place=Place(
            name="Santos",
            latitude=-23.96,
            longitude=-46.33,
            country="Brasil",
            admin1="São Paulo",
            place_id=3449433,
        )
    )


def _forecast():
    return Forecast(
        place=None,
        current=CurrentWeather(
            time=datetime(2026, 10, 2, 18, 0),
            temperature=25.4,
            apparent_temperature=26.1,
            code=3,
            wind_speed=12.0,
            humidity=80.0,
            precipitation=0.0,
        ),
        hourly=(
            HourlyPoint(
                time=datetime(2026, 10, 2, 18, 0),
                temperature=25.4,
                apparent_temperature=26.1,
                precipitation_probability=40.0,
                precipitation=0.0,
                code=3,
                wind_speed=12.0,
                humidity=80.0,
            ),
        ),
        daily=(
            DailyPoint(
                date=datetime(2026, 10, 2),
                code=3,
                temperature_max=28.0,
                temperature_min=17.0,
            ),
        ),
    )


class NotificationBodyTests(unittest.TestCase):
    def test_only_the_selected_fields_appear(self):
        body = notification_body(_location(), _forecast(), ["temperature"], SYMBOLS)
        self.assertIn("25 °C", body)
        self.assertNotIn("Vento", body)
        self.assertNotIn("Umidade", body)

    def test_order_follows_the_requested_fields(self):
        body = notification_body(
            _location(), _forecast(), ["humidity", "temperature"], SYMBOLS
        )
        self.assertLess(body.index("Umidade"), body.index("25 °C"))

    def test_named_parts_are_labelled(self):
        body = notification_body(
            _location(), _forecast(), ["apparent_temperature", "wind_speed"], SYMBOLS
        )
        self.assertIn("Sensação", body)
        self.assertIn("Vento", body)

    def test_probability_comes_from_the_next_hour(self):
        body = notification_body(
            _location(), _forecast(), ["precipitation_probability"], SYMBOLS
        )
        self.assertIn("40%", body)

    def test_daily_extremes_are_available(self):
        body = notification_body(
            _location(), _forecast(), ["daily_max", "daily_min"], SYMBOLS
        )
        self.assertIn("Máxima 28 °C", body)
        self.assertIn("Mínima 17 °C", body)

    def test_time_is_appended(self):
        body = notification_body(_location(), _forecast(), ["temperature"], SYMBOLS)
        self.assertIn("18:00", body)

    def test_no_forecast_returns_a_placeholder(self):
        self.assertEqual(
            notification_body(_location(), None, ["temperature"], SYMBOLS),
            "Sem dados de clima no momento.",
        )

    def test_no_selected_fields_returns_a_placeholder(self):
        self.assertEqual(
            notification_body(_location(), _forecast(), [], SYMBOLS),
            "Sem dados de clima no momento.",
        )

    def test_unknown_fields_are_ignored(self):
        body = notification_body(
            _location(), _forecast(), ["temperature", "inventado"], SYMBOLS
        )
        self.assertIn("25 °C", body)


if __name__ == "__main__":
    unittest.main()
