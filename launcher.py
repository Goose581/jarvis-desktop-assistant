"""J.A.R.V.I.S. Windows launcher with GitHub Releases auto-update support.

The launcher lives outside the replaceable app folder so it can safely update
JARVIS.exe and its PyInstaller support files while the app is closed.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import threading
import tkinter as tk
from tkinter import ttk
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

APP_EXE_NAME = "JARVIS.exe"
RELEASE_ZIP_NAME = "JARVIS-Windows.zip"
CHECKSUM_NAME = RELEASE_ZIP_NAME + ".sha256"
USER_AGENT = "JARVIS-Windows-Updater/1.6.4"
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


def check_for_update(app_dir: Path, repo: str) -> dict | None:
    """Return validated release metadata when a newer installable release exists.

    This function never downloads anything. The user is always asked before
    the update ZIP and checksum are fetched.
    """
    release = latest_release(repo)
    new_version = str(release.get("tag_name", "")).strip().lstrip("vV")
    old_version = current_version(app_dir)

    if not re.fullmatch(r"\d+(?:\.\d+){0,3}", new_version):
        raise ValueError("The latest GitHub release tag must be a numeric version such as v1.6.4.")
    if version_tuple(new_version) <= version_tuple(old_version):
        log(f"No update available. Installed={old_version}, latest={new_version}")
        return None

    # Validate that both required assets exist before offering the update.
    zip_url = find_asset(release, RELEASE_ZIP_NAME)
    checksum_url = find_asset(release, CHECKSUM_NAME)
    body = release.get("body", "")
    if not isinstance(body, str):
        body = ""
    name = release.get("name")
    if not isinstance(name, str) or not name.strip():
        name = f"J.A.R.V.I.S. v{new_version}"

    log(f"Update available. Installed={old_version}, latest={new_version}")
    return {
        "version": new_version,
        "current_version": old_version,
        "name": name,
        "body": body,
        "html_url": release.get("html_url", ""),
        "zip_url": zip_url,
        "checksum_url": checksum_url,
    }


def download_available_update(update: dict) -> Path:
    """Download and verify the two assets for a release the user accepted."""
    if not isinstance(update, dict):
        raise ValueError("Invalid update information.")
    zip_url = update.get("zip_url")
    checksum_url = update.get("checksum_url")
    if not isinstance(zip_url, str) or not isinstance(checksum_url, str):
        raise ValueError("The selected release is missing update download URLs.")

    update_base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    update_dir = Path(update_base) / "JARVIS" / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    zip_path = update_dir / RELEASE_ZIP_NAME
    checksum_path = update_dir / CHECKSUM_NAME
    zip_path.unlink(missing_ok=True)
    checksum_path.unlink(missing_ok=True)

    log(f"Downloading accepted update {update.get('current_version', '?')} -> {update.get('version', '?')}")
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

    checksum_path.unlink(missing_ok=True)
    return zip_path


def _clean_release_notes(value: str, limit: int = 1800) -> str:
    """Make release markdown safe and compact for a plain-text startup dialog."""
    text = re.sub(r"<[^>]*>", " ", value or "")
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit("\n", 1)[0].rstrip() + "\n\n(Release notes shortened.)"
    return text or "Bug fixes, improvements and new features."


def _center_window(window: tk.Tk, width: int, height: int) -> None:
    window.update_idletasks()
    x = max(0, (window.winfo_screenwidth() - width) // 2)
    y = max(0, (window.winfo_screenheight() - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def _create_startup_window(title: str, width: int, height: int) -> tk.Tk:
    window = tk.Tk()
    window.title(title)
    window.configure(bg="#071426")
    window.resizable(False, False)
    try:
        window.attributes("-topmost", True)
    except tk.TclError:
        pass
    _center_window(window, width, height)
    return window


def prompt_for_update(current: str, update: dict) -> bool:
    """Show a branded startup prompt and return True only when user accepts."""
    version = str(update.get("version", "unknown"))
    title = str(update.get("name") or f"J.A.R.V.I.S. v{version}")
    notes = _clean_release_notes(str(update.get("body", "")))
    accepted = {"value": False}

    try:
        window = _create_startup_window("J.A.R.V.I.S. — Update available", 600, 500)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        outer = tk.Frame(window, bg="#071426", padx=26, pady=22)
        outer.pack(fill="both", expand=True)

        brand = tk.Frame(outer, bg="#071426")
        brand.pack(fill="x")
        tk.Label(brand, text="J.A.R.V.I.S.", bg="#071426", fg="#EAF7FF",
                 font=("Segoe UI", 19, "bold")).pack(side="left")
        tk.Label(brand, text="SOFTWARE UPDATE", bg="#12364A", fg="#42E6D4",
                 font=("Segoe UI", 9, "bold"), padx=11, pady=6).pack(side="right")

        tk.Frame(outer, bg="#28DCCB", height=2).pack(fill="x", pady=(16, 20))
        tk.Label(outer, text="A new version is ready", bg="#071426", fg="#F1FAFF",
                 font=("Segoe UI", 21, "bold"), anchor="w").pack(fill="x")
        tk.Label(outer, text=f"{title}  ·  v{current}  →  v{version}", bg="#071426",
                 fg="#85A9C2", font=("Segoe UI", 10), anchor="w").pack(fill="x", pady=(7, 14))

        notes_frame = tk.Frame(outer, bg="#10253A", padx=14, pady=12)
        notes_frame.pack(fill="both", expand=True)
        tk.Label(notes_frame, text="WHAT'S NEW", bg="#10253A", fg="#42E6D4",
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 8))
        notes_box = tk.Text(notes_frame, height=9, wrap="word", bg="#10253A", fg="#DCEAF4",
                            insertbackground="#42E6D4", relief="flat", borderwidth=0,
                            font=("Segoe UI", 9), padx=0, pady=0)
        notes_box.pack(fill="both", expand=True)
        notes_box.insert("1.0", notes)
        notes_box.configure(state="disabled")

        footer = tk.Frame(outer, bg="#071426")
        footer.pack(fill="x", pady=(18, 0))
        tk.Label(footer, text="You can install now or skip this update and continue.",
                 bg="#071426", fg="#7796AC", font=("Segoe UI", 8)).pack(side="left")

        buttons = tk.Frame(outer, bg="#071426")
        buttons.pack(fill="x", pady=(18, 0))

        def skip() -> None:
            accepted["value"] = False
            window.destroy()

        def install() -> None:
            accepted["value"] = True
            window.destroy()

        tk.Button(buttons, text="Not now", command=skip, bg="#142A40", fg="#D7E7F1",
                  activebackground="#1D3B55", activeforeground="#FFFFFF", relief="flat",
                  bd=0, padx=22, pady=11, cursor="hand2", font=("Segoe UI", 9, "bold")).pack(side="right")
        tk.Button(buttons, text="Install update", command=install, bg="#21BFB6", fg="#04151E",
                  activebackground="#42E6D4", activeforeground="#04151E", relief="flat",
                  bd=0, padx=22, pady=11, cursor="hand2", font=("Segoe UI", 9, "bold")).pack(side="right", padx=(0, 10))

        try:
            window.attributes("-topmost", True)
            window.focus_force()
        except tk.TclError:
            pass
        window.mainloop()
        return accepted["value"]
    except Exception as error:
        log(f"Could not display graphical update prompt: {type(error).__name__}: {error}")
        # On Windows, retain the explicit opt-in requirement even if Tk cannot start.
        try:
            result = ctypes.windll.user32.MessageBoxW(
                None,
                f"J.A.R.V.I.S. v{version} is available.\n\n"
                f"You are using v{current}.\n\nInstall the update now?",
                "J.A.R.V.I.S. Update Available",
                0x00000004 | 0x00000040 | 0x00000100,  # YES/NO, information, default NO
            )
            return result == 6
        except Exception:
            log("No graphical or native update prompt was available; update was skipped safely.")
            return False


def show_download_progress(update: dict, download_function=None) -> Path:
    """Keep the startup experience visible while downloading/verifying an accepted update."""
    if download_function is None:
        download_function = download_available_update
    version = str(update.get("version", "unknown"))
    result: dict[str, object] = {"path": None, "error": None, "finished": False}
    try:
        window = _create_startup_window("J.A.R.V.I.S. — Installing update", 470, 230)
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        outer = tk.Frame(window, bg="#071426", padx=28, pady=25)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="J.A.R.V.I.S.", bg="#071426", fg="#42E6D4",
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(outer, text=f"Downloading and verifying v{version}…", bg="#071426", fg="#F1FAFF",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(18, 6))
        tk.Label(outer, text="Please keep this window open. Your current version is still safe.",
                 bg="#071426", fg="#85A9C2", font=("Segoe UI", 9)).pack(anchor="w")
        progress = ttk.Progressbar(outer, mode="indeterminate", length=400)
        progress.pack(fill="x", pady=(22, 0))
        progress.start(12)

        def worker() -> None:
            try:
                result["path"] = download_function(update)
            except Exception as error:
                result["error"] = error
            finally:
                result["finished"] = True

        threading.Thread(target=worker, name="JARVIS-update-download", daemon=True).start()

        def poll() -> None:
            if result["finished"]:
                progress.stop()
                window.destroy()
            else:
                window.after(100, poll)

        window.after(100, poll)
        window.mainloop()
    except Exception as error:
        log(f"Update progress window failed: {type(error).__name__}: {error}")
        # The update is still explicitly user-approved, so a no-window fallback is safe.
        result["path"] = download_function(update)

    if result["error"] is not None:
        raise result["error"]  # type: ignore[misc]
    path = result["path"]
    if not isinstance(path, Path):
        raise RuntimeError("The update download did not produce a package path.")
    return path


def check_and_download_update(root: Path, app_dir: Path, repo: str) -> Path | None:
    """Compatibility helper: detect, prompt, then download only after consent."""
    update = check_for_update(app_dir, repo)
    if update is None:
        return None
    if not prompt_for_update(current_version(app_dir), update):
        log(f"User skipped update v{update['version']} for this launch.")
        return None
    return show_download_progress(update)


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
        update = check_for_update(app_dir, repo)
        if update is not None:
            log(f"Showing startup update prompt for v{update['version']}.")
            if prompt_for_update(current_version(app_dir), update):
                zip_path = show_download_progress(update)
                if getattr(sys, "frozen", False):
                    helper_command = [sys.executable, "--apply-update", str(zip_path), str(app_dir), str(os.getpid())]
                else:
                    helper_command = [sys.executable, str(Path(__file__).resolve()), "--apply-update", str(zip_path), str(app_dir), str(os.getpid())]

                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen(helper_command, creationflags=flags)
                return 0
            log(f"User chose Not now for update v{update['version']}.")
    except Exception as error:
        # A network outage or cancelled/invalid update must never prevent the
        # currently installed assistant from starting.
        log(f"Update check/install skipped: {type(error).__name__}: {error}")
        try:
            show_error("J.A.R.V.I.S. update", f"The update could not be completed. Your current version will start.\n\n{error}")
        except Exception:
            pass

    launch_app(app_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
