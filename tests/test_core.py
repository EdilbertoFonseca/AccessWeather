import json
import tempfile
import unittest
from pathlib import Path

from app.application import Controller
from app.config import (
    ACTION_LABELS,
    ANNOUNCEMENT_LABELS,
    APP_AUMID,
    CONTEXT_ACTIONS,
    DEFAULTS,
    NOTIFICATION_LABELS,
    Settings,
    UNIT_GROUPS,
    data_dir,
    unit_codes,
)
from app.version import APP_NAME, CHANGELOG_URL, UPDATE_URL, VERSION


class VersionTests(unittest.TestCase):
    def test_fields_are_consistent(self):
        self.assertEqual(APP_NAME, "AccessWeather")
        self.assertTrue(VERSION)
        self.assertIn("accessweather", UPDATE_URL)
        self.assertIn("accessweather", CHANGELOG_URL)

    def test_aumid_is_stable_and_namespaced(self):
        self.assertTrue(APP_AUMID.startswith("JuniorTec."))
        self.assertIn("AccessWeather", APP_AUMID)


class ActionTests(unittest.TestCase):
    def test_every_action_has_a_handler(self):
        for action in ACTION_LABELS:
            self.assertTrue(
                callable(getattr(Controller, f"_action_{action}", None)),
                f"falta o handler _action_{action}",
            )

    def test_every_handler_is_reachable_from_the_tray_menu(self):
        source = Path(__file__).resolve().parents[1] / "app" / "tray.py"
        content = source.read_text(encoding="utf-8")
        for action in set(ACTION_LABELS) - CONTEXT_ACTIONS:
            self.assertIn(f'"{action}"', content)


class SettingsTests(unittest.TestCase):
    def _settings(self, directory, name="settings.json"):
        return Settings(Path(directory) / name)

    def test_defaults_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self._settings(directory)
            self.assertEqual(settings["units"], "metric")
            self.assertEqual(settings["refresh_minutes"], 30)
            self.assertTrue(settings["announcements"]["refresh"])

    def test_survives_a_corrupted_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{nao e json", encoding="utf-8")
            settings = Settings(path)
            self.assertEqual(settings.values["units"], "metric")

    def test_ignores_unknown_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"units": "imperial", "inexistente": 1}', encoding="utf-8")
            settings = Settings(path)
            self.assertEqual(settings["units"], "imperial")
            self.assertNotIn("inexistente", settings.values)

    def test_rejects_an_unknown_unit_group(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"units": "kelvin"}', encoding="utf-8")
            self.assertEqual(Settings(path)["units"], "metric")

    def test_clamps_refresh_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"refresh_minutes": 1}', encoding="utf-8")
            self.assertEqual(Settings(path)["refresh_minutes"], 5)
            path.write_text('{"refresh_minutes": "muito"}', encoding="utf-8")
            self.assertEqual(Settings(path)["refresh_minutes"], 30)

    def test_keeps_unknown_keys_out_of_the_notification_group(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                '{"notifications": {"alerts": false, "fantasma": true}}',
                encoding="utf-8",
            )
            settings = Settings(path)
            self.assertFalse(settings["notifications"]["alerts"])
            self.assertNotIn("fantasma", settings["notifications"])

    def test_round_trips_through_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(path)
            settings["units"] = "imperial"
            settings["notifications"]["update"] = False
            settings.save()
            reloaded = Settings(path)
            self.assertEqual(reloaded["units"], "imperial")
            self.assertFalse(reloaded["notifications"]["update"])

    def test_saved_file_is_valid_json_in_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(path)
            settings["toast_app_name"] = "Clima da Casa"
            settings.save()
            raw = path.read_text(encoding="utf-8")
            self.assertEqual(json.loads(raw)["toast_app_name"], "Clima da Casa")


class LabelTests(unittest.TestCase):
    def test_default_announcements_cover_every_category(self):
        self.assertEqual(
            set(DEFAULTS["announcements"]), set(ANNOUNCEMENT_LABELS)
        )

    def test_default_notifications_cover_every_toggle(self):
        self.assertEqual(set(DEFAULTS["notifications"]), set(NOTIFICATION_LABELS))

    def test_labels_are_written_in_portuguese(self):
        labels = (
            list(ACTION_LABELS.values())
            + list(ANNOUNCEMENT_LABELS.values())
            + list(NOTIFICATION_LABELS.values())
        )
        self.assertTrue(all(label and label[0].isupper() for label in labels))

    def test_keys_are_snake_case_ascii(self):
        keys = list(ACTION_LABELS) + list(ANNOUNCEMENT_LABELS) + list(NOTIFICATION_LABELS)
        for key in keys:
            self.assertRegex(key, r"^[a-z][a-z0-9_]*$")


class UnitTests(unittest.TestCase):
    def test_metric_group_is_the_default(self):
        self.assertEqual(unit_codes(None), UNIT_GROUPS["metric"])

    def test_imperial_group_is_used_when_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"units": "imperial"}', encoding="utf-8")
            settings = Settings(path)
            self.assertEqual(unit_codes(settings)["temperature"], "fahrenheit")

    def test_wind_override_wins_over_the_group(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"units": "metric", "units_wind": "ms"}', encoding="utf-8")
            settings = Settings(path)
            self.assertEqual(unit_codes(settings)["wind"], "ms")

    def test_an_invalid_wind_override_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"units_wind": "knots"}', encoding="utf-8")
            settings = Settings(path)
            self.assertEqual(unit_codes(settings)["wind"], "kmh")


class PortablePathTests(unittest.TestCase):
    def test_data_dir_is_created_next_to_the_project(self):
        path = data_dir()
        self.assertTrue(path.is_dir())
        self.assertEqual(path.name, "data")


if __name__ == "__main__":
    unittest.main()