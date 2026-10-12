import unittest
from unittest import mock

from app.changelog import FALLBACK_CHANGELOG, fetch_changelog
from app.version import CHANGELOG_URL


class ChangelogTests(unittest.TestCase):
    def test_fetch_changelog_reads_remote_markdown(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.encoding = None
        response.text = "\n# Changelog\n"
        with mock.patch("app.changelog.requests.get", return_value=response) as get:
            self.assertEqual(fetch_changelog(), "# Changelog")
        args, kwargs = get.call_args
        self.assertEqual(args[0], CHANGELOG_URL)
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(response.encoding, "utf-8")

    def test_fetch_changelog_rejects_empty_response(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.encoding = "utf-8"
        response.text = "  "
        with mock.patch("app.changelog.requests.get", return_value=response):
            with self.assertRaises(ValueError):
                fetch_changelog()

    def test_fallback_matches_the_bundled_changelog_version(self):
        self.assertIn("## 0.1.0", FALLBACK_CHANGELOG)

    def test_fallback_mentions_the_current_version(self):
        from app.version import VERSION

        self.assertIn(VERSION, FALLBACK_CHANGELOG)


if __name__ == "__main__":
    unittest.main()