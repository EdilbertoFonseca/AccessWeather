from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

import requests

from .version import UPDATE_URL


PACKAGE_EXECUTABLE = "AccessWeather.exe"
PACKAGE_NAME = "AccessWeather"


def _get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _version_tuple(value):
    try:
        return tuple(int(part) for part in str(value).split(".") if part.isdigit())
    except Exception:
        return ()


def check_for_update(current_version):
    response = requests.get(UPDATE_URL, timeout=10)
    response.raise_for_status()
    remote = response.json()
    version = remote.get("version", "")
    if _version_tuple(version) > _version_tuple(current_version):
        return remote
    return None


def download_update(download_url, progress_callback=None):
    temp_dir = tempfile.mkdtemp(prefix="accessweather-update-")
    zip_path = os.path.join(temp_dir, f"{PACKAGE_NAME}.zip")
    try:
        for attempt in range(3):
            downloaded = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
            headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}
            response = None
            try:
                response = requests.get(
                    download_url,
                    stream=True,
                    timeout=(10, 120),
                    headers=headers,
                )
                response.raise_for_status()
                status = response.status_code
                if downloaded and status != 206:
                    downloaded = 0
                mode = "ab" if downloaded else "wb"
                content_range = response.headers.get("content-range", "")
                if status == 206 and "/" in content_range:
                    total = int(content_range.rsplit("/", 1)[1])
                else:
                    length = int(response.headers.get("content-length", 0) or 0)
                    total = downloaded + length if status == 206 else length
                with open(zip_path, mode) as f:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)
                if total and downloaded != total:
                    raise OSError(
                        f"Download incompleto: {downloaded} de {total} bytes."
                    )
                return zip_path
            except (requests.RequestException, OSError):
                if attempt == 2:
                    raise
            finally:
                if response is not None:
                    response.close()
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _validate_update(zip_path):
    try:
        with zipfile.ZipFile(zip_path) as archive:
            has_executable = False
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/"):
                    raise ValueError("O pacote de atualização contém um caminho inválido.")
                name = name.strip("/")
                parts = tuple(part for part in name.split("/") if part)
                if not parts or ".." in parts:
                    raise ValueError("O pacote de atualização contém um caminho inválido.")
                if parts == (PACKAGE_EXECUTABLE,) and not info.is_dir():
                    has_executable = True
                elif parts[0] != "tools":
                    raise ValueError(
                        f"Arquivo inesperado no pacote de atualização: {info.filename}"
                    )
            if not has_executable:
                raise ValueError(f"O pacote não contém {PACKAGE_EXECUTABLE}.")
    except zipfile.BadZipFile as exc:
        raise ValueError("O pacote de atualização baixado é inválido.") from exc


def _powershell_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def apply_update(download_url, progress_callback=None, target_version=""):
    zip_path = download_update(download_url, progress_callback)
    base_dir = _get_base_dir()
    temp_dir = os.path.dirname(zip_path)
    script_path = os.path.join(temp_dir, "update.ps1")
    executable = os.path.join(base_dir, PACKAGE_EXECUTABLE)
    target_version = str(target_version or "")
    process_ids = [os.getpid()]
    if getattr(sys, "frozen", False):
        process_ids.append(os.getppid())
    process_list = ", ".join(str(process_id) for process_id in process_ids)
    try:
        _validate_update(zip_path)
        script = f'''$ErrorActionPreference = "Stop"
$processIds = @({process_list})
$baseDir = {_powershell_literal(base_dir)}
$zipPath = {_powershell_literal(zip_path)}
$tempDir = {_powershell_literal(temp_dir)}
$executable = {_powershell_literal(executable)}
$installedVersion = {_powershell_literal(target_version)}

function Start-AccessWeather {{
    Get-ChildItem Env: | Where-Object {{ $_.Name -like "_PYI_*" }} | ForEach-Object {{
        Remove-Item -LiteralPath ("Env:" + $_.Name) -ErrorAction SilentlyContinue
    }}
    $env:PYINSTALLER_RESET_ENVIRONMENT = "1"
    Start-Process -FilePath $executable -WorkingDirectory $baseDir
}}

try {{
    foreach ($processId in $processIds) {{
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -ne $process -and -not $process.WaitForExit(120000)) {{
            throw "O AccessWeather não encerrou dentro do tempo esperado."
        }}
    }}
    Start-Sleep -Milliseconds 750
    Expand-Archive -LiteralPath $zipPath -DestinationPath $baseDir -Force
    if ($installedVersion) {{
        $markerDir = Join-Path $baseDir "data"
        $markerPath = Join-Path $markerDir "update-installed.json"
        New-Item -ItemType Directory -Path $markerDir -Force | Out-Null
        @{{ version = $installedVersion; installed_at = (Get-Date).ToString("o") }} | ConvertTo-Json -Compress | Set-Content -LiteralPath $markerPath -Encoding UTF8
    }}
    Start-AccessWeather
    Start-Sleep -Milliseconds 500
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}} catch {{
    ($_ | Out-String) | Set-Content -LiteralPath (Join-Path $baseDir "accessweather-update-error.log") -Encoding UTF8
    if (Test-Path -LiteralPath $executable) {{
        Start-AccessWeather
    }}
    exit 1
}}
'''
        with open(script_path, "w", encoding="utf-8-sig") as f:
            f.write(script)
        return subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise