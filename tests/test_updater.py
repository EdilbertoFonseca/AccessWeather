import os
import shutil
import subprocess
import tempfile
import time
import unittest
import zipfile
from unittest import mock

import requests

from app.updater import (
    PACKAGE_EXECUTABLE,
    _get_base_dir,
    _version_tuple,
    apply_update,
    check_for_update,
    download_update,
)
from app.version import UPDATE_URL


class VersionTupleTests(unittest.TestCase):
    def test_standard(self):
        self.assertEqual(_version_tuple("0.2.1"), (0, 2, 1))

    def test_ignores_non_numeric_parts(self):
        self.assertEqual(_version_tuple("1.2.3-beta.4"), (1, 2, 4))

    def test_empty_string(self):
        self.assertEqual(_version_tuple(""), ())

    def test_invalid_value(self):
        self.assertEqual(_version_tuple(None), ())

    def test_ordering(self):
        self.assertLess(_version_tuple("0.2.0"), _version_tuple("0.2.1"))
        self.assertGreater(_version_tuple("1.0.0"), _version_tuple("0.9.9"))


class BaseDirTests(unittest.TestCase):
    def test_not_frozen_points_to_project_root(self):
        with mock.patch("app.updater.sys.frozen", False, create=True):
            base = _get_base_dir()
        self.assertEqual(os.path.basename(base), "AccessWeather")

    def test_frozen_points_to_executable_dir(self):
        fake = "C:\\fake\\AccessWeather.exe"
        with mock.patch("app.updater.sys.frozen", True, create=True), mock.patch(
            "app.updater.sys.executable", fake
        ):
            self.assertEqual(_get_base_dir(), "C:\\fake")


class CheckForUpdateTests(unittest.TestCase):
    def _response(self, payload):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def test_update_available_returns_remote(self):
        remote = {"version": "0.2.1", "notes": "novo"}
        with mock.patch("app.updater.requests.get", return_value=self._response(remote)):
            self.assertEqual(check_for_update("0.2.0"), remote)

    def test_no_update_when_equal(self):
        with mock.patch(
            "app.updater.requests.get", return_value=self._response({"version": "0.2.0"})
        ):
            self.assertIsNone(check_for_update("0.2.0"))

    def test_no_update_when_remote_is_older(self):
        with mock.patch(
            "app.updater.requests.get", return_value=self._response({"version": "0.1.0"})
        ):
            self.assertIsNone(check_for_update("0.2.0"))

    def test_no_update_when_version_missing(self):
        with mock.patch(
            "app.updater.requests.get",
            return_value=self._response({"notes": "sem versão"}),
        ):
            self.assertIsNone(check_for_update("0.2.0"))

    def test_raises_on_http_error(self):
        response = self._response({"version": "9.9.9"})
        response.raise_for_status.side_effect = RuntimeError("HTTP 500")
        with mock.patch("app.updater.requests.get", return_value=response):
            with self.assertRaises(RuntimeError):
                check_for_update("0.2.0")

    def test_raises_on_invalid_json(self):
        response = self._response({"version": "9.9.9"})
        response.json.side_effect = ValueError("bad json")
        with mock.patch("app.updater.requests.get", return_value=response):
            with self.assertRaises(ValueError):
                check_for_update("0.2.0")

    def test_uses_update_url_and_timeout_from_version_module(self):
        with mock.patch(
            "app.updater.requests.get",
            return_value=self._response({"version": "9.9.9"}),
        ) as patcher:
            check_for_update("0.0.1")
            args, kwargs = patcher.call_args
            self.assertEqual(args[0], UPDATE_URL)
            self.assertEqual(kwargs.get("timeout"), 10)


class DownloadUpdateTests(unittest.TestCase):
    def _fake_response(self, chunks, total=None):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.iter_content.return_value = iter(chunks)
        response.headers = {"content-length": str(total) if total is not None else ""}
        response.status_code = 200
        return response

    def test_downloads_streaming_chunks(self):
        with tempfile.TemporaryDirectory(prefix="aw-update-test-") as directory:
            response = self._fake_response([b"primeiro", b"-", b"segundo"], total=16)
            with mock.patch(
                "app.updater.requests.get", return_value=response
            ), mock.patch("app.updater.tempfile.mkdtemp", return_value=directory):
                zip_path = download_update("https://exemplo/zip")
            self.assertTrue(os.path.exists(zip_path))
            with open(zip_path, "rb") as f:
                self.assertEqual(f.read(), b"primeiro-segundo")

    def test_progress_callback_reports_down(self):
        with tempfile.TemporaryDirectory(prefix="aw-update-test-") as directory:
            response = self._fake_response([b"abc", b"def"], total=6)
            calls = []
            with mock.patch(
                "app.updater.requests.get", return_value=response
            ), mock.patch("app.updater.tempfile.mkdtemp", return_value=directory):
                download_update(
                    "https://exemplo/zip",
                    progress_callback=lambda down, total: calls.append((down, total)),
                )
            self.assertEqual(calls, [(3, 6), (6, 6)])

    def test_resumes_an_interrupted_download(self):
        with tempfile.TemporaryDirectory(prefix="aw-update-test-") as directory:
            def interrupted_chunks():
                yield b"abc"
                raise requests.ConnectionError("conexão interrompida")

            first = self._fake_response(interrupted_chunks(), total=6)
            second = self._fake_response([b"def"], total=3)
            second.status_code = 206
            second.headers["content-range"] = "bytes 3-5/6"
            with mock.patch(
                "app.updater.requests.get", side_effect=[first, second]
            ) as get, mock.patch("app.updater.tempfile.mkdtemp", return_value=directory):
                zip_path = download_update("https://exemplo/zip")
            with open(zip_path, "rb") as f:
                self.assertEqual(f.read(), b"abcdef")
            self.assertEqual(get.call_args_list[1].kwargs["headers"], {"Range": "bytes=3-"})

    def test_raises_on_http_error_and_cleans_up(self):
        with tempfile.TemporaryDirectory(prefix="aw-update-test-") as directory:
            response = self._fake_response([], total=0)
            response.raise_for_status.side_effect = RuntimeError("boom")
            with mock.patch(
                "app.updater.requests.get", return_value=response
            ), mock.patch("app.updater.tempfile.mkdtemp", return_value=directory):
                with self.assertRaises(RuntimeError):
                    download_update("https://exemplo/zip")
            self.assertFalse(os.path.exists(directory))


class ValidatePackageTests(unittest.TestCase):
    def _zip(self, directory, names):
        zip_path = os.path.join(directory, "AccessWeather.zip")
        with zipfile.ZipFile(zip_path, "w") as archive:
            for name, payload in names.items():
                archive.writestr(name, payload)
        return zip_path

    def test_accepts_the_executable_and_tools(self):
        from app.updater import _validate_update

        with tempfile.TemporaryDirectory() as directory:
            zip_path = self._zip(
                directory,
                {PACKAGE_EXECUTABLE: b"exe", "tools/icone.png": b"png"},
            )
            _validate_update(zip_path)

    def test_rejects_a_missing_executable(self):
        from app.updater import _validate_update

        with tempfile.TemporaryDirectory() as directory:
            zip_path = self._zip(directory, {"tools/icone.png": b"png"})
            with self.assertRaisesRegex(ValueError, PACKAGE_EXECUTABLE):
                _validate_update(zip_path)

    def test_rejects_user_data_in_the_package(self):
        from app.updater import _validate_update

        with tempfile.TemporaryDirectory() as directory:
            zip_path = self._zip(
                directory, {PACKAGE_EXECUTABLE: b"exe", "data/settings.json": b"{}"}
            )
            with self.assertRaisesRegex(ValueError, "inesperado"):
                _validate_update(zip_path)

    def test_rejects_path_traversal(self):
        from app.updater import _validate_update

        with tempfile.TemporaryDirectory() as directory:
            zip_path = self._zip(
                directory, {PACKAGE_EXECUTABLE: b"exe", "../fora.txt": b"x"}
            )
            with self.assertRaisesRegex(ValueError, "caminho inválido"):
                _validate_update(zip_path)


class ApplyUpdateTests(unittest.TestCase):
    @staticmethod
    def _make_update_zip(directory):
        zip_path = os.path.join(directory, "AccessWeather.zip")
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(PACKAGE_EXECUTABLE, b"exe")
            archive.writestr("tools/icone.png", b"png")
        return zip_path

    def _apply(self, directory, **kwargs):
        zip_path = self._make_update_zip(directory)
        popen = mock.Mock()
        with mock.patch(
            "app.updater.download_update", return_value=zip_path
        ), mock.patch("app.updater.subprocess.Popen", popen):
            apply_update("https://exemplo/zip", **kwargs)
        return popen

    def _script(self, directory):
        with open(os.path.join(directory, "update.ps1"), encoding="utf-8-sig") as f:
            return f.read()

    def test_apply_update_writes_script_and_launches(self):
        with tempfile.TemporaryDirectory(prefix="aw-update-test-") as directory:
            popen = self._apply(directory)
            content = self._script(directory)
            self.assertIn("WaitForExit", content)
            self.assertIn("Expand-Archive", content)
            self.assertIn("accessweather-update-error.log", content)
            self.assertIn("O AccessWeather não encerrou", content)
            self.assertIn("_PYI_*", content)
            self.assertIn("PYINSTALLER_RESET_ENVIRONMENT", content)
            self.assertIn("update-installed.json", content)
            self.assertNotIn("taskkill", content)
            popen.assert_called_once()
            args, kwargs = popen.call_args
            self.assertEqual(args[0][0], "powershell.exe")
            self.assertEqual(args[0][-1], os.path.join(directory, "update.ps1"))
            self.assertEqual(kwargs["creationflags"], 0x08000000)
            self.assertTrue(kwargs["close_fds"])

    def test_apply_update_passes_progress_callback(self):
        with tempfile.TemporaryDirectory(prefix="aw-update-test-") as directory:
            seen = []
            callback = lambda down, total: seen.append((down, total))
            with mock.patch(
                "app.updater.download_update", return_value=self._make_update_zip(directory)
            ) as download, mock.patch("app.updater.subprocess.Popen"):
                apply_update("https://exemplo/zip", progress_callback=callback)
            download.assert_called_once()
            args, kwargs = download.call_args
            self.assertEqual(args[0], "https://exemplo/zip")
            self.assertEqual(args[1], callback)

    def test_apply_update_writes_installed_version_marker(self):
        with tempfile.TemporaryDirectory(prefix="aw-update-test-") as directory:
            self._apply(directory, target_version="1.2.3")
            content = self._script(directory)
            self.assertIn("$installedVersion = '1.2.3'", content)
            self.assertIn("ConvertTo-Json", content)

    def test_apply_update_creates_relaunch_line(self):
        with tempfile.TemporaryDirectory(prefix="aw-update-test-") as directory:
            self._apply(directory)
            content = self._script(directory)
            self.assertIn("Start-Process", content)
            self.assertIn("Start-AccessWeather", content)
            self.assertIn(PACKAGE_EXECUTABLE, content)

    def test_apply_update_rejects_an_invalid_zip(self):
        directory = tempfile.mkdtemp(prefix="aw-update-test-")
        zip_path = os.path.join(directory, "AccessWeather.zip")
        with open(zip_path, "wb") as f:
            f.write(b"not a zip")
        with mock.patch(
            "app.updater.download_update", return_value=zip_path
        ), mock.patch("app.updater.subprocess.Popen") as popen:
            with self.assertRaisesRegex(ValueError, "inválido"):
                apply_update("https://exemplo/zip")
        popen.assert_not_called()
        self.assertFalse(os.path.exists(directory))

    @unittest.skipUnless(os.name == "nt", "o instalador usa PowerShell do Windows")
    def test_update_script_replaces_files_and_relaunches(self):
        # O executável recém-instalado é relançado pelo script, então a pasta
        # pode ficar bloqueada por um instante; a limpeza ignora erros.
        base_dir = tempfile.mkdtemp(prefix="aw-update-base-")
        try:
            update_dir = tempfile.mkdtemp(prefix="aw-update-test-")
            zip_path = os.path.join(update_dir, "AccessWeather.zip")
            replacement = os.path.join(
                os.environ["SystemRoot"], "System32", "where.exe"
            )
            running_executable = os.path.join(
                os.environ["SystemRoot"], "System32", "ping.exe"
            )
            target = os.path.join(base_dir, PACKAGE_EXECUTABLE)
            shutil.copy2(running_executable, target)
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.write(replacement, PACKAGE_EXECUTABLE)
                archive.writestr("tools/update-test.txt", b"updated")
            running = subprocess.Popen(
                [target, "-t", "127.0.0.1"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                with mock.patch(
                    "app.updater.download_update", return_value=zip_path
                ), mock.patch(
                    "app.updater._get_base_dir", return_value=base_dir
                ), mock.patch(
                    "app.updater.os.getpid", return_value=running.pid
                ), mock.patch(
                    "app.updater.sys.frozen", False, create=True
                ):
                    updater = apply_update("https://exemplo/zip")

                time.sleep(1)
                self.assertEqual(
                    os.path.getsize(target), os.path.getsize(running_executable)
                )
                running.terminate()
                running.wait(timeout=5)
                updater.wait(timeout=15)
                self.assertEqual(os.path.getsize(target), os.path.getsize(replacement))
                self.assertTrue(
                    os.path.exists(os.path.join(base_dir, "tools", "update-test.txt"))
                )
                self.assertFalse(
                    os.path.exists(
                        os.path.join(base_dir, "accessweather-update-error.log")
                    )
                )
                self.assertEqual(updater.returncode, 0)
            finally:
                if running.poll() is None:
                    running.kill()
                    running.wait(timeout=5)
                shutil.rmtree(update_dir, ignore_errors=True)
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()