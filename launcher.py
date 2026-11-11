"""J.A.R.V.I.S. Windows launcher with GitHub Releases auto-update support.

The launcher lives outside the replaceable app folder so it can safely update
JARVIS.exe and its PyInstaller support files while the app is closed.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

APP_EXE_NAME = "JARVIS.exe"
RELEASE_ZIP_NAME = "JARVIS-Windows.zip"
CHECKSUM_NAME = RELEASE_ZIP_NAME + ".sha256"
USER_AGENT = "JARVIS-Windows-Updater/1.0"


def install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def log(message: str) -> None:
    try:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "JARVIS"
        base.mkdir(parents=True, exist_ok=True)
        with (base / "launcher.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def show_error(title: str, message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        log(f"{title}: {message}")


def load_config(root: Path) -> dict:
    config_path = root / "update_config.json"
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(value))
    return tuple(int(item) for item in numbers) if numbers else (0,)


def http_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def current_version(app_dir: Path) -> str:
    version_file = app_dir / "version.txt"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def latest_release(repo: str) -> dict:
    if not repo or "YOUR_GITHUB" in repo:
        raise ValueError("Set github_repo in update_config.json before enabling updates.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("github_repo must look like owner/repository.")
    return http_json(f"https://api.github.com/repos/{repo}/releases/latest")


def find_asset(release: dict, name: str) -> str:
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return asset["browser_download_url"]
    raise ValueError(f"Release is missing required asset: {name}")


def check_and_download_update(root: Path, app_dir: Path, repo: str) -> Path | None:
    release = latest_release(repo)
    new_version = str(release.get("tag_name", "")).strip().lstrip("vV")
    old_version = current_version(app_dir)

    if not new_version:
        raise ValueError("The latest GitHub release has no tag_name.")
    if version_tuple(new_version) <= version_tuple(old_version):
        log(f"No update available. Installed={old_version}, latest={new_version}")
        return None

    zip_url = find_asset(release, RELEASE_ZIP_NAME)
    checksum_url = find_asset(release, CHECKSUM_NAME)

    update_dir = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "JARVIS" / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    zip_path = update_dir / RELEASE_ZIP_NAME
    checksum_path = update_dir / CHECKSUM_NAME

    log(f"Downloading update {old_version} -> {new_version}")
    download(zip_url, zip_path)
    download(checksum_url, checksum_path)

    expected_hash = checksum_path.read_text(encoding="utf-8").strip().split()[0].lower()
    actual_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or actual_hash != expected_hash:
        zip_path.unlink(missing_ok=True)
        raise ValueError("Update verification failed: SHA-256 checksum did not match.")

    return zip_path


def wait_for_parent_exit(pid: int) -> None:
    """Wait for the launcher process to exit before replacing the app folder."""
    if os.name != "nt":
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int

    synchronize = 0x00100000
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if handle:
        try:
            kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        finally:
            kernel32.CloseHandle(handle)


def safe_extract(zip_path: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if target != destination_resolved and destination_resolved not in target.parents:
                raise ValueError("The update archive contains an unsafe file path.")
        archive.extractall(destination)


def apply_update(zip_path: Path, app_dir: Path, parent_pid: int) -> None:
    wait_for_parent_exit(parent_pid)
    app_dir = app_dir.resolve()
    app_dir.parent.mkdir(parents=True, exist_ok=True)

    staging = app_dir.parent / (app_dir.name + ".new")
    backup = app_dir.parent / (app_dir.name + ".previous")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        safe_extract(zip_path, staging)
        if not (staging / APP_EXE_NAME).is_file():
            raise ValueError(f"Update archive does not contain {APP_EXE_NAME} at its root.")

        if app_dir.exists():
            app_dir.rename(backup)
        try:
            staging.rename(app_dir)
        except Exception:
            if backup.exists() and not app_dir.exists():
                backup.rename(app_dir)
            raise

        app_exe = app_dir / APP_EXE_NAME
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen([str(app_exe)], cwd=str(app_dir), creationflags=creation_flags)
        shutil.rmtree(backup, ignore_errors=True)
        log(f"Update applied. Running version {current_version(app_dir)}")
        zip_path.unlink(missing_ok=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        log("Failed while applying update.")
        raise


def launch_app(app_dir: Path) -> None:
    app_exe = app_dir / APP_EXE_NAME
    if not app_exe.is_file():
        show_error(
            "J.A.R.V.I.S. installation problem",
            f"Could not find {APP_EXE_NAME} here:\n{app_exe}\n\nTry running the installer again.",
        )
        return
    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen([str(app_exe)], cwd=str(app_dir), creationflags=creation_flags)


def run_update_helper(args: list[str]) -> int:
    if len(args) != 4:
        return 2
    zip_path = Path(args[1])
    app_dir = Path(args[2])
    parent_pid = int(args[3])
    try:
        apply_update(zip_path, app_dir, parent_pid)
        return 0
    except Exception as error:
        log(f"Update helper error: {error}")
        show_error("J.A.R.V.I.S. update failed", f"The update could not be installed.\n\n{error}")
        launch_app(app_dir)
        return 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--apply-update":
        return run_update_helper(sys.argv[1:])

    root = install_root()
    app_dir = root / "app"
    try:
        config = load_config(root)
        repo = str(config.get("github_repo", "")).strip()
        zip_path = check_and_download_update(root, app_dir, repo)
        if zip_path is not None:
            if getattr(sys, "frozen", False):
                helper_command = [sys.executable, "--apply-update", str(zip_path), str(app_dir), str(os.getpid())]
            else:
                helper_command = [sys.executable, str(Path(__file__).resolve()), "--apply-update", str(zip_path), str(app_dir), str(os.getpid())]

            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(helper_command, creationflags=flags)
            return 0
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        # An update service outage should never prevent the installed assistant from starting.
        log(f"Update check skipped: {error}")

    launch_app(app_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
