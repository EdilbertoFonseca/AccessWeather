import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import notify
from app.notify import Notifier


class _FakeToaster:
    def __init__(self):
        self.shown = []
        self.cleared = 0

    def show_toast(self, toast):
        self.shown.append(toast)

    def clear_toasts(self):
        self.cleared += 1


def _notifier(settings=None):
    notifier = Notifier(settings=settings)
    fake = _FakeToaster()
    notifier._toaster = fake
    return notifier, fake


class AvailabilityTests(unittest.TestCase):
    def test_icon_path_is_none_when_tools_are_empty(self):
        with mock.patch.object(notify, "tools_dir", lambda: Path(tempfile.mkdtemp())):
            self.assertIsNone(notify.toast_icon_path())

    def test_icon_path_finds_a_png(self):
        directory = Path(tempfile.mkdtemp())
        icon = directory / "toast.png"
        icon.write_bytes(b"png")
        with mock.patch.object(notify, "tools_dir", lambda: directory):
            self.assertEqual(notify.toast_icon_path(), icon)


class PermissionTests(unittest.TestCase):
    def test_missing_settings_allow_every_category(self):
        notifier = Notifier()
        self.assertTrue(notifier._allowed("alerts"))

    def test_disabled_category_is_refused(self):
        settings = {"notifications": {"alerts": False, "forecast": True}}
        notifier = Notifier(settings=settings)
        self.assertFalse(notifier._allowed("alerts"))
        self.assertTrue(notifier._allowed("forecast"))

    def test_unknown_category_defaults_to_enabled(self):
        notifier = Notifier(settings={"notifications": {}})
        self.assertTrue(notifier._allowed("update"))

    def test_non_dict_group_allows(self):
        self.assertTrue(Notifier(settings={"notifications": None})._allowed("alerts"))


class SendTests(unittest.TestCase):
    def test_disabled_category_does_not_reach_the_toaster(self):
        notifier, fake = _notifier({"notifications": {"alerts": False}})
        self.assertFalse(notifier.send("t", "b", category="alerts"))
        self.assertEqual(fake.shown, [])

    def test_send_uses_title_and_body(self):
        notifier, fake = _notifier()
        self.assertTrue(notifier.send("Título", "Corpo", category="forecast"))
        self.assertEqual(list(fake.shown[0].text_fields), ["Título", "Corpo"])

    def test_send_without_body_has_one_field(self):
        notifier, fake = _notifier()
        notifier.send("Só título", category="forecast")
        self.assertEqual(list(fake.shown[0].text_fields), ["Só título"])

    def test_backend_failure_is_swallowed(self):
        notifier = Notifier()
        with mock.patch.object(notify, "TOASTS_AVAILABLE", False):
            self.assertFalse(notifier.send("t", "b"))
        self.assertFalse(notifier.available)

    def test_show_toast_error_marks_the_notifier_failed(self):
        class Broken(_FakeToaster):
            def show_toast(self, toast):
                raise RuntimeError("boom")

        notifier = Notifier()
        notifier._toaster = Broken()
        self.assertFalse(notifier.send("t", "b"))
        self.assertFalse(notifier.available)


class ConvenienceTests(unittest.TestCase):
    def test_alert_title_includes_the_location(self):
        notifier, fake = _notifier()
        notifier.alert("Casa", "Chuva forte.")
        self.assertIn("Casa", fake.shown[0].text_fields[0])
        self.assertEqual(fake.shown[0].text_fields[1], "Chuva forte.")

    def test_alert_without_location_has_generic_title(self):
        notifier, fake = _notifier()
        notifier.alert("", "Chuva forte.")
        self.assertEqual(fake.shown[0].text_fields[0], "Alerta meteorológico")

    def test_forecast_uses_the_location_as_title(self):
        notifier, fake = _notifier()
        notifier.forecast("Santos", "15 °C")
        self.assertEqual(fake.shown[0].text_fields[0], "Santos")

    def test_update_mentions_the_version(self):
        notifier, fake = _notifier()
        notifier.update("0.2.0")
        self.assertIn("0.2.0", fake.shown[0].text_fields[1])

    def test_clear_calls_the_toaster(self):
        notifier, fake = _notifier()
        self.assertTrue(notifier.clear())
        self.assertEqual(fake.cleared, 1)


if __name__ == "__main__":
    unittest.main()
