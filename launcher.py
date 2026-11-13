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
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

APP_EXE_NAME = "JARVIS.exe"
RELEASE_ZIP_NAME = "JARVIS-Windows.zip"
CHECKSUM_NAME = RELEASE_ZIP_NAME + ".sha256"
USER_AGENT = "JARVIS-Windows-Updater/1.6.0"
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
MAX_ARCHIVE_FILES = 20000
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
MAX_LOG_BYTES = 1_000_000


def install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def log(message: str) -> None:
    """Write updater diagnostics to a small rotating per-user log."""
    try:
        base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home()) / "JARVIS"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "launcher.log"
        if path.exists() and path.stat().st_size >= MAX_LOG_BYTES:
            backup = path.with_suffix(path.suffix + ".1")
            backup.unlink(missing_ok=True)
            path.replace(backup)
        with path.open("a", encoding="utf-8", errors="replace") as handle:
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
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("update_config.json must contain a JSON object.")
    return config


def version_tuple(value: str) -> tuple[int, ...]:
    """Parse bounded numeric release versions consistently (1.2 == 1.2.0)."""
    core = str(value).strip().lstrip("vV")
    # Bound both total size and each component before converting to int. This
    # avoids pathological release tags causing oversized integer conversions.
    if len(core) > 40 or not re.fullmatch(r"\d{1,9}(?:\.\d{1,9}){0,3}", core):
        return (0, 0, 0)
    numbers = [int(item) for item in core.split(".")]
    while len(numbers) < 3:
        numbers.append(0)
    while len(numbers) > 3 and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers)


def http_json(url: str) -> dict:
    """Fetch a bounded JSON document from an HTTPS endpoint."""
    try:
        parsed_url = urllib.parse.urlsplit(url)
    except ValueError as error:
        raise ValueError("The release API URL is invalid.") from error
    if parsed_url.scheme.lower() != "https" or not parsed_url.hostname:
        raise ValueError("The release API must use a valid HTTPS URL.")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        if not response.geturl().startswith("https://"):
            raise ValueError("GitHub API redirected to a non-HTTPS address.")
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("GitHub returned an unexpectedly large release response.")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub returned an invalid release response.")
    return payload


def download(url: str, destination: Path, max_bytes: int = MAX_DOWNLOAD_BYTES) -> None:
    """Download to a temporary file with a size limit, then atomically publish it."""
    try:
        parsed_url = urllib.parse.urlsplit(url)
    except ValueError as error:
        raise ValueError("The update URL is invalid.") from error
    if parsed_url.scheme.lower() != "https" or not parsed_url.hostname:
        raise ValueError("Update downloads must use a valid HTTPS URL.")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("The download size limit must be a positive integer.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    temporary = destination.with_suffix(destination.suffix + ".part")
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as out:
            if not response.geturl().startswith("https://"):
                raise ValueError("The update download redirected to a non-HTTPS address.")
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise ValueError("The update download is larger than the allowed size.")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("The update download exceeded the allowed size.")
                out.write(chunk)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    if not isinstance(release, dict):
        raise ValueError("GitHub returned an invalid release object.")
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError("GitHub returned an invalid release asset list.")
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") == name:
            url = asset.get("browser_download_url")
            if isinstance(url, str):
                try:
                    parsed_url = urllib.parse.urlsplit(url)
                except ValueError:
                    parsed_url = None
                if parsed_url and parsed_url.scheme.lower() == "https" and parsed_url.hostname:
                    return url
            raise ValueError(f"Release asset has an invalid download URL: {name}")
    raise ValueError(f"Release is missing required asset: {name}")


def check_and_download_update(root: Path, app_dir: Path, repo: str) -> Path | None:
    release = latest_release(repo)
    new_version = str(release.get("tag_name", "")).strip().lstrip("vV")
    old_version = current_version(app_dir)

    if not re.fullmatch(r"\d+(?:\.\d+){0,3}", new_version):
        raise ValueError("The latest GitHub release tag must be a numeric version such as v1.1.0.")
    if version_tuple(new_version) <= version_tuple(old_version):
        log(f"No update available. Installed={old_version}, latest={new_version}")
        return None

    zip_url = find_asset(release, RELEASE_ZIP_NAME)
    checksum_url = find_asset(release, CHECKSUM_NAME)

    update_base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    update_dir = Path(update_base) / "JARVIS" / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    zip_path = update_dir / RELEASE_ZIP_NAME
    checksum_path = update_dir / CHECKSUM_NAME
    zip_path.unlink(missing_ok=True)
    checksum_path.unlink(missing_ok=True)

    log(f"Downloading update {old_version} -> {new_version}")
    download(zip_url, zip_path)
    download(checksum_url, checksum_path, max_bytes=1024 * 1024)

    checksum_parts = checksum_path.read_text(encoding="utf-8").strip().split()
    if not checksum_parts:
        raise ValueError("The release checksum file is empty.")
    expected_hash = checksum_parts[0].lower()
    actual_hash = sha256_file(zip_path).lower()
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
    """Extract an update only after rejecting traversal, links, and oversized ZIPs."""
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_FILES:
            raise ValueError("The update archive contains too many files.")
        total_size = 0
        seen_paths: set[str] = set()
        file_paths: set[str] = set()
        parent_directories: set[str] = set()
        reserved_windows_names = {
            "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
            *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10)),
            "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³",
        }
        for member in members:
            normalized = member.filename.replace("\\", "/")
            parts = normalized.rstrip("/").split("/")
            invalid_windows_chars = set('<>"|?*')
            if (
                not normalized.rstrip("/")
                or normalized.startswith("/")
                or re.match(r"^[A-Za-z]:", normalized)
                or any(part in {"", ".", ".."} for part in parts)
                or any(
                    any(ord(char) < 32 or char in invalid_windows_chars or char == ":" for char in part)
                    or part.endswith((".", " "))
                    or len(part.encode("utf-16-le")) // 2 > 255
                    for part in parts if part
                )
                or any(
                    unicodedata.normalize("NFC", part.split(".", 1)[0]).upper() in reserved_windows_names
                    for part in parts if part
                )
            ):
                raise ValueError("The update archive contains an unsafe or Windows-invalid file path.")
            is_directory = member.is_dir() or normalized.endswith("/")
            canonical = normalized.rstrip("/")
            folded = unicodedata.normalize("NFC", canonical).casefold()
            if not canonical or folded in seen_paths:
                raise ValueError("The update archive contains duplicate or empty file paths.")
            seen_paths.add(folded)
            components = canonical.split("/")
            for index in range(1, len(components)):
                parent_key = "/".join(
                    unicodedata.normalize("NFC", part) for part in components[:index]
                ).casefold()
                parent_directories.add(parent_key)
            if not is_directory:
                file_paths.add(folded)
            mode = (member.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode):
                raise ValueError("The update archive contains a symbolic link, which is not allowed.")
            if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("The update archive contains an unsupported special file type.")
            total_size += member.file_size
            if member.file_size > MAX_EXTRACTED_BYTES or total_size > MAX_EXTRACTED_BYTES:
                raise ValueError("The update archive expands beyond the allowed size.")
            target = (destination / canonical).resolve()
            if target != destination_resolved and destination_resolved not in target.parents:
                raise ValueError("The update archive contains an unsafe file path.")
        if file_paths.intersection(parent_directories):
            raise ValueError("The update archive contains a file/directory path collision.")
        archive.extractall(destination)


def _valid_app_directory(path: Path) -> bool:
    """Check the minimum structure needed to launch a staged/installed app."""
    executable = path / APP_EXE_NAME
    version_file = path / "version.txt"
    try:
        if path.is_symlink() or not path.is_dir():
            return False
        if executable.is_symlink() or version_file.is_symlink():
            return False
        if not executable.is_file() or executable.stat().st_size < 1024:
            return False
        if version_file.stat().st_size > 64:
            return False
        version = version_file.read_text(encoding="utf-8").strip()
        return bool(re.fullmatch(r"\d{1,9}(?:\.\d{1,9}){0,3}", version))
    except (OSError, UnicodeError):
        return False


def _remove_path(path: Path) -> None:
    """Remove a file, directory, or symlink without following symlinks."""
    try:
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)
    except OSError as error:
        log(f"Could not remove temporary updater path {path}: {error}")
        raise


def recover_interrupted_update(app_dir: Path) -> str:
    """Restore the previous app if Windows was interrupted mid-folder swap."""
    app_dir = app_dir.resolve()
    staging = app_dir.parent / (app_dir.name + ".new")
    backup = app_dir.parent / (app_dir.name + ".previous")
    app_valid = _valid_app_directory(app_dir)
    backup_valid = _valid_app_directory(backup)

    if not app_valid and backup_valid:
        if app_dir.exists() or app_dir.is_symlink():
            _remove_path(app_dir)
        backup.rename(app_dir)
        log("Recovered the previous J.A.R.V.I.S. installation after an interrupted update.")
        result = "restored-previous"
    elif app_valid:
        if backup.exists() or backup.is_symlink():
            _remove_path(backup)
        result = "current-valid"
    else:
        if backup.exists() or backup.is_symlink():
            _remove_path(backup)
        result = "current-invalid-no-backup" if app_dir.exists() else "no-installation"

    if staging.exists() or staging.is_symlink():
        _remove_path(staging)
    return result


def apply_update(zip_path: Path, app_dir: Path, parent_pid: int) -> None:
    wait_for_parent_exit(parent_pid)
    app_dir = app_dir.resolve()
    app_dir.parent.mkdir(parents=True, exist_ok=True)
    recover_interrupted_update(app_dir)

    staging = app_dir.parent / (app_dir.name + ".new")
    backup = app_dir.parent / (app_dir.name + ".previous")
    if staging.exists() or staging.is_symlink():
        _remove_path(staging)
    if backup.exists() or backup.is_symlink():
        _remove_path(backup)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        safe_extract(zip_path, staging)
        app_binary = staging / APP_EXE_NAME
        version_file = staging / "version.txt"
        if not app_binary.is_file() or app_binary.stat().st_size < 1024:
            raise ValueError(f"Update archive does not contain a valid {APP_EXE_NAME} at its root.")
        if not version_file.is_file():
            raise ValueError("Update archive is missing its version.txt file.")
        new_version = version_file.read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"\d{1,9}(?:\.\d{1,9}){0,3}", new_version):
            raise ValueError("Update archive contains an invalid version.txt value.")
        if _valid_app_directory(app_dir) and version_tuple(new_version) <= version_tuple(current_version(app_dir)):
            raise ValueError("The update package is not newer than the installed version.")

        if app_dir.exists():
            app_dir.rename(backup)
        try:
            staging.rename(app_dir)
        except Exception:
            if backup.exists() and not app_dir.exists():
                backup.rename(app_dir)
            raise

        app_exe = app_dir / APP_EXE_NAME
        # JARVIS.exe is built with PyInstaller --windowed; no console is needed.
        try:
            subprocess.Popen([str(app_exe)], cwd=str(app_dir))
        except Exception:
            # If Windows refuses to start the new build, restore the previous app.
            shutil.rmtree(app_dir, ignore_errors=True)
            if backup.exists():
                backup.rename(app_dir)
            raise
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
    # JARVIS.exe is a windowed desktop app, so launch it without a terminal.
    try:
        subprocess.Popen([str(app_exe)], cwd=str(app_dir))
    except OSError as error:
        log(f"Application launch failed: {error}")
        show_error("J.A.R.V.I.S. could not start", f"The app could not be launched.\n\n{error}")


def run_update_helper(args: list[str]) -> int:
    if len(args) != 4:
        log("Update helper received an invalid argument count.")
        return 2
    app_dir = Path(args[2])
    try:
        zip_path = Path(args[1])
        parent_pid = int(args[3])
        if parent_pid < 0:
            raise ValueError("The parent process ID must not be negative.")
        apply_update(zip_path, app_dir, parent_pid)
        return 0
    except Exception as error:
        log(f"Update helper error: {type(error).__name__}: {error}")
        show_error("J.A.R.V.I.S. update failed", f"The update could not be installed.\n\n{error}")
        launch_app(app_dir)
        return 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--apply-update":
        return run_update_helper(sys.argv[1:])

    root = install_root()
    app_dir = root / "app"
    try:
        recover_interrupted_update(app_dir)
    except Exception as error:
        log(f"Installation recovery check failed: {type(error).__name__}: {error}")
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
    except Exception as error:
        # An update service outage or malformed release must not prevent the
        # already-installed assistant from starting. The reason is preserved in the log.
        log(f"Update check skipped: {type(error).__name__}: {error}")

    launch_app(app_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
