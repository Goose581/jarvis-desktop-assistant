"""Core logic and desktop tools for J.A.R.V.I.S.

The GUI lives in JARVIS_GUI.py.  This module intentionally keeps imports for
optional desktop integrations lazy so that tests and startup diagnostics can
run even when Ollama, pyttsx3, or PyAutoGUI is not installed yet.
"""

from __future__ import annotations

import ast
import datetime as _datetime
from collections import deque
import json
import ipaddress
import inspect
import math
import operator
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

import jarvis_workspace as workspace

APP_NAME = "J.A.R.V.I.S."
APP_VERSION = "1.6.0"
# Recommended lightweight model for J.A.R.V.I.S. on the user's 16 GB DDR3 PC.
DEFAULT_MODEL = "gemma4:e2b"
LEGACY_DEFAULT_MODELS = {"llama3.2:1b"}
DEFAULT_NUM_CTX = 8192
SETTINGS_VERSION = 4
SUPPORTED_CONTEXT_SIZES = (2048, 4096, 8192, 12288, 16384)
SUPPORTED_THEMES = ("midnight", "arctic", "emerald", "violet", "crimson", "amber")
MODEL_SUGGESTIONS = ("gemma4:e2b", "gemma4:e4b", "gemma4:12b", "llama3.2:1b", "llama3.2:3b", "qwen2.5:3b")
_OLLAMA_HOST_LOCK = threading.RLock()
_OLLAMA_ACTIVE_HOST: str | None = None
OLLAMA_KEEP_ALIVE = "30m"
_OLLAMA_THINK_CACHE: dict[str, tuple[float, bool | str | None]] = {}
_OLLAMA_THINK_CACHE_LOCK = threading.Lock()
_OLLAMA_THINK_CACHE_SECONDS = 1800
MAX_HISTORY_MESSAGES = 18  # keep recent context compact on older PCs
MAX_INPUT_LENGTH = 5000
MAX_MATH_LENGTH = 250


# ==========================================
# USER DATA, LOGGING, AND SETTINGS
# ==========================================

MAX_LOG_BYTES = 1_000_000
MAX_SETTINGS_BYTES = 64 * 1024
_settings_lock = threading.RLock()
_log_lock = threading.Lock()
_WINDOW_GEOMETRY_RE = re.compile(r"^(\d{3,4})x(\d{3,4})(?:[+-]\d{1,5}){0,2}$")


def user_data_dir() -> Path:
    """Return a per-user writable directory without requiring admin rights."""
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
    path = base / "JARVIS"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _rotate_log_if_needed(log_path: Path) -> None:
    try:
        if log_path.exists() and log_path.stat().st_size >= MAX_LOG_BYTES:
            backup = log_path.with_suffix(log_path.suffix + ".1")
            backup.unlink(missing_ok=True)
            log_path.replace(backup)
    except OSError:
        # Logging must never prevent the application from working.
        pass


def log_error(message: str, error: BaseException | None = None) -> None:
    """Write diagnostics to a bounded, rotating log file."""
    try:
        log_path = user_data_dir() / "jarvis.log"
        entry = f"\n[{_datetime.datetime.now().astimezone().isoformat(timespec='seconds')}] {message}\n"
        if error is not None:
            entry += "".join(traceback.format_exception(type(error), error, error.__traceback__))
        with _log_lock:
            _rotate_log_if_needed(log_path)
            with log_path.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(entry)
    except Exception:
        pass


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def _valid_window_geometry(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    match = _WINDOW_GEOMETRY_RE.fullmatch(value.strip())
    if not match:
        return False
    width, height = int(match.group(1)), int(match.group(2))
    return 860 <= width <= 10000 and 620 <= height <= 10000


def load_settings() -> dict[str, Any]:
    """Load a small allowlist of preferences; corrupt settings are non-fatal."""
    defaults: dict[str, Any] = {
        "voice_enabled": True,
        "model": DEFAULT_MODEL,
        "num_ctx": DEFAULT_NUM_CTX,
        "window_geometry": "1360x860",
        "theme": "midnight",
        "timer_sound_enabled": True,
        "settings_version": SETTINGS_VERSION,
    }
    with _settings_lock:
        try:
            path = settings_path()
            if path.stat().st_size > MAX_SETTINGS_BYTES:
                raise ValueError("The settings file is unexpectedly large.")
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("The settings file must contain a JSON object.")
            voice_value = raw.get("voice_enabled", defaults["voice_enabled"])
            if isinstance(voice_value, bool):
                defaults["voice_enabled"] = voice_value
            settings_version = raw.get("settings_version", 0)
            if not isinstance(settings_version, int) or isinstance(settings_version, bool):
                settings_version = 0
            model = raw.get("model", DEFAULT_MODEL)
            if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", model.strip()):
                cleaned_model = model.strip()
                # Only migrate the previous app's default on pre-v2 settings.
                # Once a user deliberately chooses a model in this version,
                # even llama3.2:1b remains their choice on later launches.
                if settings_version < SETTINGS_VERSION and cleaned_model.lower() in LEGACY_DEFAULT_MODELS:
                    cleaned_model = DEFAULT_MODEL
                defaults["model"] = cleaned_model
            num_ctx = raw.get("num_ctx", DEFAULT_NUM_CTX)
            if isinstance(num_ctx, int) and not isinstance(num_ctx, bool) and num_ctx in SUPPORTED_CONTEXT_SIZES:
                defaults["num_ctx"] = num_ctx
            geometry = raw.get("window_geometry")
            if _valid_window_geometry(geometry):
                defaults["window_geometry"] = geometry.strip()
            theme = raw.get("theme", "midnight")
            if isinstance(theme, str) and theme in SUPPORTED_THEMES:
                defaults["theme"] = theme
            timer_sound = raw.get("timer_sound_enabled", True)
            if isinstance(timer_sound, bool):
                defaults["timer_sound_enabled"] = timer_sound
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            log_error("Could not read settings; defaults will be used.", error)
    return defaults


def save_settings(**changes: Any) -> None:
    """Validate and atomically save supported preferences, without write races."""
    allowed = {"voice_enabled", "model", "num_ctx", "window_geometry", "theme", "timer_sound_enabled"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Unsupported settings: {', '.join(sorted(unknown))}")
    if "voice_enabled" in changes and not isinstance(changes["voice_enabled"], bool):
        raise ValueError("voice_enabled must be a boolean.")
    if "timer_sound_enabled" in changes and not isinstance(changes["timer_sound_enabled"], bool):
        raise ValueError("timer_sound_enabled must be a boolean.")
    if "model" in changes:
        model = changes["model"]
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", model.strip()):
            raise ValueError("The Ollama model name is invalid.")
        changes["model"] = model.strip()
    if "num_ctx" in changes:
        num_ctx = changes["num_ctx"]
        if isinstance(num_ctx, bool) or not isinstance(num_ctx, int) or num_ctx not in SUPPORTED_CONTEXT_SIZES:
            choices = ", ".join(str(item) for item in SUPPORTED_CONTEXT_SIZES)
            raise ValueError(f"Context length must be one of: {choices}.")
    if "window_geometry" in changes and not _valid_window_geometry(changes["window_geometry"]):
        raise ValueError("The saved window size is invalid.")
    if "theme" in changes and changes["theme"] not in SUPPORTED_THEMES:
        raise ValueError(f"Theme must be one of: {', '.join(SUPPORTED_THEMES)}.")

    with _settings_lock:
        settings = load_settings()
        settings.update(changes)
        settings["settings_version"] = SETTINGS_VERSION
        path = settings_path()
        temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            temporary.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise


_settings = load_settings()
MODEL_NAME = str(_settings.get("model", DEFAULT_MODEL))
NUM_CTX = int(_settings.get("num_ctx", DEFAULT_NUM_CTX))
voice_enabled = bool(_settings.get("voice_enabled", True))
timer_sound_enabled = bool(_settings.get("timer_sound_enabled", True))


def get_app_version() -> str:
    """Read the build's version file when frozen; fall back to the source constant."""
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    try:
        value = (base / "version.txt").read_text(encoding="utf-8").strip()
        return value or APP_VERSION
    except OSError:
        return APP_VERSION


def set_model_name(model: str) -> str:
    """Persist the selected Ollama model without changing other preferences."""
    global MODEL_NAME
    cleaned = str(model).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", cleaned):
        raise ValueError("Model names may only contain letters, numbers, dots, underscores, colons, slashes and hyphens.")
    save_settings(model=cleaned)
    MODEL_NAME = cleaned
    return MODEL_NAME


def get_model_name() -> str:
    return MODEL_NAME


def get_num_ctx() -> int:
    return NUM_CTX


def set_num_ctx(num_ctx: int) -> int:
    """Set the Ollama context window to one of the supported safe presets."""
    global NUM_CTX
    save_settings(num_ctx=num_ctx)
    NUM_CTX = num_ctx
    return NUM_CTX


def set_runtime_preferences(model: str, num_ctx: int) -> tuple[str, int]:
    """Atomically persist the model and context selected in Assistant Settings."""
    global MODEL_NAME, NUM_CTX
    cleaned = str(model).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", cleaned):
        raise ValueError("Enter a valid Ollama model name, such as gemma4:e2b.")
    if isinstance(num_ctx, bool) or not isinstance(num_ctx, int) or num_ctx not in SUPPORTED_CONTEXT_SIZES:
        raise ValueError("Choose a supported context length from the list.")
    save_settings(model=cleaned, num_ctx=num_ctx)
    MODEL_NAME = cleaned
    NUM_CTX = num_ctx
    return MODEL_NAME, NUM_CTX


def ollama_chat_options(max_output_tokens: int = 448) -> dict[str, int | float]:
    """Return consistent inference settings tuned for a memory-constrained PC."""
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int):
        max_output_tokens = 448
    return {
        "num_ctx": NUM_CTX,
        "num_predict": max(64, min(max_output_tokens, 768)),
        "temperature": 0.25,
        "top_p": 0.9,
        "repeat_penalty": 1.08,
    }


# ==========================================
# VOICE + DESKTOP UI CALLBACKS
# ==========================================

ui_message_callback = None
MAX_PENDING_SPEECH = 40
_speech_queue: queue.Queue[str | None] = queue.Queue(maxsize=MAX_PENDING_SPEECH)
_speech_thread: threading.Thread | None = None
_speech_lock = threading.Lock()


def set_voice_enabled(enabled: bool, persist: bool = True) -> None:
    """Enable or disable spoken responses while retaining on-screen replies."""
    global voice_enabled
    voice_enabled = bool(enabled)
    if persist:
        try:
            save_settings(voice_enabled=voice_enabled)
        except OSError as error:
            log_error("Could not save voice preference.", error)


def _speech_worker() -> None:
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 205)
    except Exception as error:
        log_error("Voice output could not be initialized.", error)
        return

    while True:
        message = _speech_queue.get()
        try:
            if message is None:
                return
            if not voice_enabled:
                continue
            engine.say(message)
            engine.runAndWait()
        except Exception as error:
            log_error("Voice output failed.", error)
        finally:
            _speech_queue.task_done()


def _safe_console_message(message: str) -> None:
    stream = getattr(sys, "stdout", None)
    if stream is not None:
        try:
            print(message, file=stream, flush=True)
        except Exception:
            pass


def speak(message: str) -> None:
    """Post a message to the GUI and queue voice output without blocking it."""
    text = str(message)
    _safe_console_message(f"\n{APP_NAME}: {text}")

    callback = ui_message_callback
    if callback is not None:
        try:
            callback(text)
        except Exception as error:
            log_error("Could not send a message to the GUI.", error)

    if voice_enabled:
        global _speech_thread
        with _speech_lock:
            if _speech_thread is None or not _speech_thread.is_alive():
                _speech_thread = threading.Thread(
                    target=_speech_worker, name="JARVIS-Speech", daemon=True
                )
                _speech_thread.start()
        try:
            _speech_queue.put_nowait(text)
        except queue.Full:
            log_error("Speech queue is full; the newest spoken response was skipped.")


# ==========================================
# TEXT ARGUMENT NORMALIZATION
# ==========================================

_IGNORED_ARGUMENT_VALUES = {
    "", "function", "tool", "none", "null", "search_edge", "search_web", "type_text"
}
_IGNORED_ARGUMENT_KEYS = {"function", "tool", "name", "action", "tool_name"}


def first_real_text_argument(
    values: dict[str, Any], preferred_keys: tuple[str, ...]
) -> str:
    """Get a useful string from tool arguments, ignoring wrapper metadata."""
    if not isinstance(values, dict):
        return ""

    # Some integrations wrap the actual JSON arguments in another dictionary.
    for wrapper_key in ("arguments", "args", "params", "parameters"):
        nested = values.get(wrapper_key)
        if isinstance(nested, dict):
            found = first_real_text_argument(nested, preferred_keys)
            if found:
                return found

    for key in preferred_keys:
        value = values.get(key)
        # A value under a semantic key such as query/text is user data even if
        # it happens to equal a word used by tool wrappers (for example "function").
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key, value in values.items():
        if str(key).lower() in _IGNORED_ARGUMENT_KEYS:
            continue
        if isinstance(value, str) and value.strip() and value.strip().lower() not in _IGNORED_ARGUMENT_VALUES:
            return value.strip()
    return ""


# ==========================================
# APP / WEBSITE / SEARCH TOOLS
# ==========================================

_APP_ALIASES: dict[str, tuple[str, str]] = {
    "notepad": ("process", "notepad.exe"),
    "calculator": ("process", "calc.exe"),
    "calc": ("process", "calc.exe"),
    "paint": ("process", "mspaint.exe"),
    "file explorer": ("process", "explorer.exe"),
    "explorer": ("process", "explorer.exe"),
    "task manager": ("process", "taskmgr.exe"),
    "edge": ("browser", "https://www.bing.com"),
    "microsoft edge": ("browser", "https://www.bing.com"),
    "chrome": ("browser", "https://www.google.com"),
    "google chrome": ("browser", "https://www.google.com"),
    "youtube": ("browser", "https://www.youtube.com"),
    "spotify": ("browser", "https://open.spotify.com"),
    "google docs": ("browser", "https://docs.google.com"),
    "google sheets": ("browser", "https://sheets.google.com"),
    "google slides": ("browser", "https://slides.google.com"),
    "word": ("browser", "https://word.new"),
    "excel": ("browser", "https://excel.new"),
    "powerpoint": ("browser", "https://powerpoint.new"),
    "docs": ("browser", "https://docs.google.com"),
    "sheets": ("browser", "https://sheets.google.com"),
    "slides": ("browser", "https://slides.google.com"),
    "spreadsheet": ("browser", "https://sheets.google.com"),
    "presentation": ("browser", "https://slides.google.com"),
    "discord": ("browser", "https://discord.com/app"),
    "gmail": ("browser", "https://mail.google.com"),
    "google drive": ("browser", "https://drive.google.com"),
    "google calendar": ("browser", "https://calendar.google.com"),
    "github": ("browser", "https://github.com"),
    "chatgpt": ("browser", "https://chatgpt.com"),
    "reddit": ("browser", "https://www.reddit.com"),
    "steam": ("browser", "https://store.steampowered.com"),
}


def _open_browser_url(url: str) -> bool:
    """Open a URL with the default browser and return a truthful success flag."""
    try:
        return webbrowser.open(url) is not False
    except Exception as error:
        log_error(f"Could not open browser URL: {url}", error)
        return False


def open_app(app_name: str = "", **kwargs: Any) -> str:
    """Open a supported desktop app or website, with safe search fallback."""
    if not isinstance(app_name, str) or not app_name.strip():
        app_name = first_real_text_argument(
            kwargs, ("app_name", "application", "app", "name", "target", "value", "text")
        )
    name = str(app_name).strip().lower()
    name = re.sub(r"^(?:my|the|a|an)\s+", "", name)
    if not name or name in _IGNORED_ARGUMENT_VALUES:
        return "Which app or website should I open?"

    # Prefer installed desktop apps where there is a stable Windows executable.
    desktop_candidates: dict[str, list[str]] = {
        "edge": [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
        "microsoft edge": [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
        "chrome": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
        "google chrome": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
        "spotify": [str(Path.home() / "AppData/Roaming/Spotify/Spotify.exe")],
    }
    if name in desktop_candidates:
        for candidate_path in desktop_candidates[name]:
            if Path(candidate_path).is_file():
                try:
                    subprocess.Popen([candidate_path])
                    return f"Opened {name.title()}."
                except OSError as error:
                    log_error(f"Could not launch {name} desktop app.", error)
        # Continue to the browser alternative if the desktop app isn't installed.

    # A request for a new workspace should open its creation URL.
    create_new = bool(re.search(r"\b(new|create|blank)\b", name))
    if "google doc" in name or name in {"docs", "google docs"}:
        url = "https://docs.new" if create_new else "https://docs.google.com"
        if not _open_browser_url(url):
            return "I couldn't open Google Docs in your browser."
        return "Opened a new Google Doc." if create_new else "Opened Google Docs."
    if "google sheet" in name or "spreadsheet" in name or name == "sheets":
        url = "https://sheets.new" if create_new else "https://sheets.google.com"
        if not _open_browser_url(url):
            return "I couldn't open Google Sheets in your browser."
        return "Opened a new Google Sheet." if create_new else "Opened Google Sheets."
    if "google slide" in name or "presentation" in name or name == "slides":
        url = "https://slides.new" if create_new else "https://slides.google.com"
        if not _open_browser_url(url):
            return "I couldn't open Google Slides in your browser."
        return "Opened a new Google Slides presentation." if create_new else "Opened Google Slides."

    if name in {"settings", "windows settings", "system settings"}:
        try:
            if hasattr(os, "startfile"):
                os.startfile("ms-settings:")  # type: ignore[attr-defined]
                return "Opened Windows Settings."
        except OSError as error:
            log_error("Could not open Windows Settings.", error)
        return "I couldn't open Windows Settings on this device."

    if name in _APP_ALIASES:
        kind, target = _APP_ALIASES[name]
        if kind == "browser":
            if not _open_browser_url(target):
                return f"I couldn't open {name.title()} in your browser."
            return f"Opened {name.title()}."
        try:
            subprocess.Popen([target])
            return f"Opened {name.title()}."
        except OSError as error:
            log_error(f"Could not open {name}.", error)
            return f"I couldn't open {name}. Check that it is installed."

    # Allow a user to ask to open a URL without passing it through a shell.
    candidate = app_name.strip()
    if re.fullmatch(r"(?:https?://)?[\w.-]+(?:\.[A-Za-z]{2,})(?:/[\w./?%&=+#-]*)?", candidate):
        url = candidate if candidate.startswith(("http://", "https://")) else "https://" + candidate
        if not _open_browser_url(url):
            return f"I couldn't open {url}."
        return f"Opened {url}."

    search_url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": candidate})
    if not _open_browser_url(search_url):
        return f"I couldn't identify that app or open a browser search for '{candidate}'."
    return f"I couldn't identify that app, so I searched for '{candidate}'."


def close_app(app_name: str = "", **kwargs: Any) -> str:
    """Close only a small allowlist of common apps; never build a shell command."""
    if not isinstance(app_name, str) or not app_name.strip():
        app_name = first_real_text_argument(kwargs, ("app_name", "application", "app", "name", "target", "text"))
    name = str(app_name).strip().lower()
    process_map = {
        "edge": "msedge.exe", "microsoft edge": "msedge.exe",
        "chrome": "chrome.exe", "google chrome": "chrome.exe",
        "spotify": "Spotify.exe", "notepad": "notepad.exe",
    }
    for key, process_name in process_map.items():
        if name == key:
            try:
                completed = subprocess.run(
                    ["taskkill", "/im", process_name, "/t"],
                    capture_output=True, text=True, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if completed.returncode == 0:
                    return f"Closed {key.title()}."
                return f"{key.title()} doesn't appear to be running."
            except OSError as error:
                log_error(f"Could not close {key}.", error)
                return f"I couldn't close {key}."
    return "I can currently close Edge, Chrome, Spotify or Notepad. Which one did you mean?"


def find_edge_executable() -> Path | None:
    """Return a known Microsoft Edge executable path, or None when not found."""
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Microsoft/Edge/Application/msedge.exe")
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def search_edge(query: str = "", **kwargs: Any) -> str:
    """Search Bing for the supplied phrase, correctly ignoring tool metadata."""
    preferred = ("query", "search_query", "search_term", "term", "q", "keywords", "text", "prompt", "input", "value")
    if isinstance(query, dict):
        query = first_real_text_argument(query, preferred)
    if not isinstance(query, str) or not query.strip():
        query = first_real_text_argument(kwargs, preferred)
    phrase = str(query).strip()
    if not phrase:
        return "What would you like me to search for?"

    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": phrase})
    edge_path = find_edge_executable()
    if edge_path is not None:
        try:
            subprocess.Popen([str(edge_path), url])
            return f"Searching the web for '{phrase}' in Microsoft Edge."
        except OSError as error:
            # A stale Edge path or launch issue should not block a web search.
            log_error("Microsoft Edge could not be launched; trying the default browser.", error)

    if not _open_browser_url(url):
        return f"I couldn't open the browser for '{phrase}'."
    return f"Searching the web for '{phrase}'."


def extract_search_query(user_input: str) -> str | None:
    """Return a search phrase for explicit search commands, or None if unrelated."""
    text = str(user_input).strip()
    if not text:
        return None
    patterns = (
        r"^(?:(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?)?search(?:\s+(?:the\s+)?(?:web|internet|edge|bing))?(?:\s+for)?(?:\s+(.+?))?\s*[.!?]*$",
        r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?look\s+up(?:\s+(.+?))?\s*[.!?]*$",
        r"^(?:please\s+)?google(?:\s+(.+?))?\s*[.!?]*$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            query = (match.group(1) or "").strip()
            if len(query) >= 2 and (query[0], query[-1]) in {
                ("'", "'"), ('"', '"'), ("“", "”"), ("‘", "’")
            }:
                query = query[1:-1].strip()
            return query
    return None


def extract_open_target(user_input: str) -> str | None:
    match = re.match(
        r"^\s*(?:please\s+)?(?:open|launch|start|run)\s+(?:the\s+)?(.+?)\s*[.!?]*\s*$",
        str(user_input), flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def extract_close_target(user_input: str) -> str | None:
    match = re.match(
        r"^\s*(?:please\s+)?(?:close|quit|exit)\s+(?:the\s+)?(.+?)\s*[.!?]*\s*$",
        str(user_input), flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


# ==========================================
# SAFE BIDMAS CALCULATOR
# ==========================================

_ALLOWED_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_MATH_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}
_ALLOWED_CONSTANTS = {"pi": math.pi, "e": math.e}


def _evaluate_math_node(node: ast.AST, depth: int = 0) -> int | float:
    """Evaluate only explicitly allowed arithmetic AST nodes; Python code cannot run."""
    if depth > 30:
        raise ValueError("That calculation is too deeply nested.")

    if isinstance(node, ast.Expression):
        return _evaluate_math_node(node.body, depth + 1)
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Only numbers are allowed.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("That number is outside the supported range.")
        if abs(value) > 1e100:
            raise ValueError("That number is too large.")
        return value
    if isinstance(node, ast.Name) and node.id in _ALLOWED_CONSTANTS:
        return _ALLOWED_CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPERATORS:
        return _ALLOWED_UNARY_OPERATORS[type(node.op)](_evaluate_math_node(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY_OPERATORS:
        left = _evaluate_math_node(node.left, depth + 1)
        right = _evaluate_math_node(node.right, depth + 1)
        if isinstance(node.op, ast.Pow):
            if abs(right) > 100 or abs(left) > 1e6:
                raise ValueError("For safety, keep powers between -100 and 100 with a base no larger than one million.")
        result = _ALLOWED_BINARY_OPERATORS[type(node.op)](left, right)
        if isinstance(result, complex) or not isinstance(result, (int, float)):
            raise ValueError("The result is not a real number.")
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("The result is outside the supported range.")
        if abs(result) > 1e100:
            raise ValueError("The result is too large.")
        return result
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = _ALLOWED_MATH_FUNCTIONS.get(node.func.id)
        if function is None or node.keywords:
            raise ValueError("That maths function isn't supported.")
        if len(node.args) > 5:
            raise ValueError("Too many arguments for that maths function.")
        arguments = [_evaluate_math_node(argument, depth + 1) for argument in node.args]
        result = function(*arguments)
        if isinstance(result, complex) or not isinstance(result, (int, float)):
            raise ValueError("The result is not a real number.")
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("The result is outside the supported range.")
        if abs(result) > 1e100:
            raise ValueError("The result is too large.")
        return result
    raise ValueError("Only arithmetic, brackets, constants and approved maths functions are supported.")


def calculate(expression: str = "", **kwargs: Any) -> str:
    """Calculate an arithmetic expression using BIDMAS and a safe AST parser."""
    if not isinstance(expression, str) or not expression.strip():
        expression = first_real_text_argument(
            kwargs, ("expression", "calculation", "maths", "math", "query", "input", "text", "value")
        )
    expression = str(expression).strip()
    if not expression or len(expression) > MAX_MATH_LENGTH:
        return f"Please give me a calculation of {MAX_MATH_LENGTH} characters or fewer."

    # The caret is familiar in school maths; Python's AST uses ** for powers.
    expression = expression.replace("^", "**")
    # Implied multiplication: 2(3 + 4), (2 + 3)4 and (2)(3).
    expression = re.sub(r"(?<=[0-9.)])\s*(?=\()", "*", expression)
    expression = re.sub(r"(?<=\))\s*(?=[0-9.(])", "*", expression)

    try:
        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 120:
            return "That calculation is too complicated for me to evaluate safely."
        result = _evaluate_math_node(tree)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        displayed = f"{result:.12g}" if isinstance(result, float) else str(result)
        return f"The result is {displayed}."
    except ZeroDivisionError:
        return "You can't divide by zero."
    except (SyntaxError, TypeError, ValueError, OverflowError, ArithmeticError) as error:
        log_error(f"Rejected or failed maths expression: {expression!r}", error)
        return "I couldn't calculate that. Check the brackets and operators, then try again."


def extract_math_expression(user_input: str) -> str | None:
    """Translate common spoken/written maths into a BIDMAS expression."""
    candidate = str(user_input).strip().lower()
    if not candidate:
        return None

    candidate = re.sub(r"^\s*(?:using\s+)?bidmas\s*[, :]\s*", "", candidate)
    candidate = re.sub(r"^\s*according\s+to\s+bidmas\s*[, :]\s*", "", candidate)
    candidate = re.sub(r"\s+(?:using\s+)?bidmas\s*$", "", candidate)

    prefixes = (
        r"^(?:please\s+)?what(?:'s|\s+is)\s+",
        r"^(?:please\s+)?(?:calculate|compute|work\s+out|solve)\s+",
        r"^(?:please\s+)?how\s+much\s+is\s+",
        r"^(?:can|could|would)\s+you\s+(?:please\s+)?(?:calculate|compute|work\s+out|solve)\s+",
        r"^(?:can|could|would)\s+you\s+(?:please\s+)?tell\s+me\s+",
    )
    for prefix in prefixes:
        candidate, count = re.subn(prefix, "", candidate, count=1, flags=re.IGNORECASE)
        if count:
            break

    candidate = re.sub(r"\s+please\s*$", "", candidate)
    candidate = candidate.strip().rstrip("?!. ")
    candidate = re.sub(r"^the\s+", "", candidate)
    candidate = (candidate
                 .replace("×", "*").replace("÷", "/")
                 .replace("−", "-").replace("–", "-")
                 .replace("²", "**2").replace("³", "**3"))

    # Percentages: "20 percent of 50" -> (20/100)*50.
    candidate = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:percent|per cent|%)\s+of\s+", r"(\1/100)*", candidate)

    def _square_root_replacement(match: re.Match[str]) -> str:
        operand = match.group(1).strip()
        if operand.startswith("(") and operand.endswith(")"):
            return "sqrt" + operand
        return "sqrt(" + operand + ")"

    candidate = re.sub(r"\bsquare\s+root\s+of\s+(.+)$", _square_root_replacement, candidate)

    replacements = (
        (r"\braised\s+to\s+the\s+power\s+of\b", "**"),
        (r"\bto\s+the\s+power\s+of\b", "**"),
        (r"\bto\s+the\s+power\b", "**"),
        (r"\bmultiplied\s+by\b", "*"),
        (r"\bdivided\s+by\b", "/"),
        (r"\bplus\b", "+"), (r"\bminus\b", "-"),
        (r"\btimes\b", "*"), (r"\bover\b", "/"),
        (r"\bmodulo\b|\bmod\b", "%"),
        (r"\bsquared\b", "**2"), (r"\bcubed\b", "**3"),
    )
    for pattern, replacement in replacements:
        candidate = re.sub(pattern, replacement, candidate)
    candidate = re.sub(r"(?<=[0-9)])\s*x\s*(?=[0-9(])", "*", candidate)
    candidate = re.sub(r"(?<=[0-9.)])\s*(?=\()", "*", candidate)
    candidate = re.sub(r"(?<=\))\s*(?=[0-9.(])", "*", candidate)
    candidate = candidate.strip()

    if not candidate or not re.fullmatch(r"[0-9a-zA-Z_\s()+\-*/%.^,]+", candidate):
        return None
    if not re.search(r"[+\-*/%^]", candidate) and not candidate.startswith("sqrt("):
        return None
    # Do not route arbitrary prose containing arithmetic-looking tokens.
    if re.search(r"\b(?:and|or|the|of|to|with|about)\b", candidate):
        return None
    return candidate


# ==========================================
# TIME, NOTES, TIMERS, AND SYSTEM STATUS
# ==========================================

def get_current_time(**kwargs: Any) -> str:
    now = _datetime.datetime.now().astimezone()
    return "The current time is " + now.strftime("%I:%M %p on %A, %B %d, %Y") + "."


def is_time_request(user_input: str) -> bool:
    text = re.sub(r"[!?.,]+$", "", str(user_input).strip().lower())
    patterns = (
        r"^(?:please\s+)?what(?:'s|\s+is)\s+the\s+(?:current\s+)?time$",
        r"^(?:(?:please\s+)?(?:can|could|would)\s+you\s+)?tell\s+me\s+the\s+(?:current\s+)?time$",
        r"^(?:please\s+)?what\s+time\s+is\s+it$",
        r"^(?:please\s+)?what(?:'s|\s+is)\s+today(?:'s)?\s+date$",
    )
    return any(re.fullmatch(pattern, text) for pattern in patterns)


def notes_file() -> Path:
    """Return the user's notes file; Documents is a fallback if Desktop is unavailable."""
    home = Path.home()
    desktop = home / "Desktop"
    documents = home / "Documents"
    base = desktop if desktop.exists() else documents
    base.mkdir(parents=True, exist_ok=True)
    return base / "jarvis_notes.txt"


def take_note(note_text: str = "", **kwargs: Any) -> str:
    if not isinstance(note_text, str) or not note_text.strip():
        note_text = first_real_text_argument(
            kwargs, ("note_text", "note", "text", "content", "message", "value", "input")
        )
    note_text = str(note_text).strip()
    if not note_text:
        return "What would you like me to write in the note?"
    if len(note_text) > MAX_INPUT_LENGTH:
        return f"Please keep each note under {MAX_INPUT_LENGTH} characters."
    try:
        path = notes_file()
        stamp = _datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"[{stamp}] {note_text}\n")
        return f"I've saved your note to {path}."
    except OSError as error:
        log_error("Could not save the note.", error)
        return "I couldn't save your note. Check that your Desktop or Documents folder is writable."


def extract_note_text(user_input: str) -> str | None:
    match = re.match(
        r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+(?:please\s+)?)?"
        r"(?:take|save|write|make)\s+(?:a\s+)?note"
        r"(?:\s+(?:that|saying))?\s*(?::|,|-)?\s*(.*?)\s*$",
        str(user_input), flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return match.group(1).strip().strip('"“”')


def read_notes(**kwargs: Any) -> str:
    try:
        path = notes_file()
        if not path.exists():
            return "You don't have any saved notes yet."
        # Keep memory use bounded even if the notes file has grown very large.
        with path.open("r", encoding="utf-8") as handle:
            latest = list(deque(handle, maxlen=15))
    except OSError as error:
        log_error("Could not read the notes file.", error)
        return "I couldn't read your notes file."
    if not latest:
        return "Your notes file is empty."
    return "Your 15 most recent notes are:\n" + "".join(latest).rstrip()


def open_notes(**kwargs: Any) -> str:
    path: Path | None = None
    try:
        path = notes_file()
        path.touch(exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif not _open_browser_url(path.as_uri()):
            return f"I couldn't open your notes. They're stored at {path}."
        return "Opened your J.A.R.V.I.S. notes."
    except OSError as error:
        log_error("Could not open the notes file.", error)
        if path is None:
            return "I couldn't locate a writable folder for your notes."
        return f"I couldn't open your notes. They're stored at {path}."


_active_timers: set[threading.Timer] = set()
_timer_lock = threading.Lock()
MAX_ACTIVE_TIMERS = 25


def set_timer_sound_enabled(enabled: bool, *, persist: bool = True) -> None:
    """Enable/disable the Windows timer-completion chime."""
    global timer_sound_enabled
    if not isinstance(enabled, bool):
        raise ValueError("timer_sound_enabled must be a boolean.")
    timer_sound_enabled = enabled
    if persist:
        try:
            save_settings(timer_sound_enabled=enabled)
        except OSError as error:
            log_error("Could not save the timer sound preference.", error)


def play_timer_sound(*, force: bool = False) -> bool:
    """Play a short system notification as soon as a timer completes.

    On Windows, MessageBeep uses the user's configured system sound and
    returns immediately. A console bell is a best-effort fallback elsewhere.
    """
    if not force and not timer_sound_enabled:
        return False
    try:
        import winsound  # Windows standard library; imported only when needed.

        # MessageBeep is asynchronous and avoids delaying the timer callback.
        result = winsound.MessageBeep(getattr(winsound, "MB_ICONASTERISK", -1))
        return result is not False
    except Exception as error:
        # Keep timer completion reliable even on systems without audio support.
        try:
            _safe_console_message("\a")
        except Exception:
            pass
        log_error("The timer notification sound could not be played.", error)
        return False


def set_timer(seconds: float, label: str = "Timer") -> str:
    if isinstance(seconds, bool):
        return "Please give me a timer duration in seconds."
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "Please give me a timer duration in seconds."
    if not math.isfinite(seconds) or seconds <= 0 or seconds > 7 * 24 * 60 * 60:
        return "Please choose a timer between 1 second and 7 days."
    safe_label = str(label).strip()[:60] or "Timer"
    # Anchor the countdown to monotonic time before thread setup so a short
    # timer is not extended by bookkeeping or scheduler startup overhead.
    deadline = time.monotonic() + seconds
    holder: dict[str, threading.Timer] = {}

    def finished() -> None:
        try:
            # The chime is triggered before queued speech, so it is audible
            # even when the text-to-speech queue is busy. MessageBeep returns
            # immediately and runs independently of the GUI thread.
            play_timer_sound()
        except Exception as error:
            log_error("Timer completion sound failed.", error)
        try:
            speak(f"Your {safe_label} has finished.")
        finally:
            with _timer_lock:
                timer = holder.get("timer")
                if timer is not None:
                    _active_timers.discard(timer)

    timer = threading.Timer(max(0.0, deadline - time.monotonic()), finished)
    timer.daemon = True
    holder["timer"] = timer
    with _timer_lock:
        if len(_active_timers) >= MAX_ACTIVE_TIMERS:
            return f"You already have {MAX_ACTIVE_TIMERS} active timers. Cancel some before adding another."
        _active_timers.add(timer)
    try:
        timer.start()
    except RuntimeError as error:
        with _timer_lock:
            _active_timers.discard(timer)
        log_error("Could not start the timer.", error)
        return "I couldn't start that timer. Please try again."
    return f"I've set a {safe_label.lower()} for {format_duration(seconds)}."


def cancel_timers(**kwargs: Any) -> str:
    with _timer_lock:
        timers = list(_active_timers)
        _active_timers.clear()
    for timer in timers:
        timer.cancel()
    return f"Cancelled {len(timers)} active timer(s)." if timers else "There are no active timers."


def format_duration(seconds: float) -> str:
    total = max(1, int(round(seconds)))
    parts = []
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)):
        amount, total = divmod(total, size)
        if amount:
            parts.append(f"{amount} {unit}{'' if amount == 1 else 's'}")
    return " ".join(parts)


def extract_timer_seconds(user_input: str) -> float | None:
    """Parse common timer phrasing without treating unrelated durations as timers."""
    text = str(user_input).strip().lower()
    duration = r"(\d+(?:\.\d+)?)\s*-?\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)"
    patterns = (
        rf"(?:please\s+)?(?:set|start|create)\s+(?:a\s+)?timer\s+(?:for|in)\s+{duration}\s*[.!]?",
        rf"(?:please\s+)?(?:set|start|create)\s+(?:a\s+)?{duration}\s+timer\s*[.!]?",
        rf"(?:please\s+)?timer\s+(?:for|in)\s+{duration}\s*[.!]?",
    )
    match = None
    for pattern in patterns:
        match = re.fullmatch(pattern, text)
        if match:
            break
    if match is None:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    multiplier = (
        1 if unit.startswith(("second", "sec"))
        else 60 if unit.startswith(("minute", "min"))
        else 3600 if unit.startswith(("hour", "hr"))
        else 86400
    )
    # Preserve out-of-range/overflowing values so set_timer() can give a
    # clear local rejection instead of letting the language model guess.
    return value * multiplier


def _normalise_ollama_host(host: str) -> str:
    """Normalise OLLAMA_HOST and replace wildcard bind addresses with loopback."""
    value = str(host or "").strip().strip('"\'')
    if not value:
        value = "http://localhost:11434"
    if "://" not in value:
        value = "http://" + value
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("OLLAMA_HOST must be a valid HTTP or HTTPS address, such as localhost:11434.")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    hostname = parsed.hostname
    if address is not None and address.is_unspecified:
        hostname = "::1" if address.version == 6 else "127.0.0.1"
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"OLLAMA_HOST contains an invalid port: {error}") from error
    if port is None:
        port = 443 if parsed.scheme == "https" else 11434
    if not 1 <= port <= 65535:
        raise ValueError("OLLAMA_HOST port must be between 1 and 65535.")
    netloc = f"[{hostname}]:{port}" if ":" in hostname else f"{hostname}:{port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def _ollama_api_base() -> str:
    """Return the best known Ollama host, respecting OLLAMA_HOST."""
    with _OLLAMA_HOST_LOCK:
        if _OLLAMA_ACTIVE_HOST:
            return _OLLAMA_ACTIVE_HOST
    configured = os.environ.get("OLLAMA_HOST", "").strip()
    return _normalise_ollama_host(configured or "http://localhost:11434")


def _ollama_api_candidates() -> list[str]:
    """Try common Windows loopback names if no custom Ollama host is configured."""
    configured = os.environ.get("OLLAMA_HOST", "").strip()
    primary = _normalise_ollama_host(configured or "http://localhost:11434")
    candidates = [primary]
    if not configured:
        candidates.extend((
            "http://127.0.0.1:11434",
            "http://[::1]:11434",
        ))
    else:
        parsed = urllib.parse.urlsplit(primary)
        host = parsed.hostname or ""
        try:
            local = host.casefold() == "localhost" or ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
        if local and (parsed.port or 11434) == 11434:
            candidates.extend((
                "http://localhost:11434",
                "http://127.0.0.1:11434",
                "http://[::1]:11434",
            ))
    return list(dict.fromkeys(candidates))


def _ollama_urlopen(request: urllib.request.Request, timeout: float, base: str):
    """Avoid workstation HTTP proxies for loopback Ollama traffic."""
    hostname = urllib.parse.urlsplit(base).hostname or ""
    try:
        local = hostname.casefold() == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        local = False
    if local:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def _fetch_ollama_json(path: str, timeout: float = 3.0) -> tuple[dict[str, Any], str]:
    """Fetch JSON from Ollama, trying loopback variants and reporting each failure."""
    global _OLLAMA_ACTIVE_HOST
    errors: list[str] = []
    for base in _ollama_api_candidates():
        request = urllib.request.Request(
            base + path,
            headers={"Accept": "application/json", "User-Agent": f"JARVIS/{APP_VERSION}"},
        )
        try:
            with _ollama_urlopen(request, min(float(timeout), 10.0), base) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("Ollama returned an unexpectedly large response.")
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Ollama returned JSON in an unexpected format.")
            with _OLLAMA_HOST_LOCK:
                _OLLAMA_ACTIVE_HOST = base
            return payload, base
        except Exception as error:
            errors.append(f"{base}: {type(error).__name__}: {error}")
    raise ConnectionError("Could not reach the Ollama API. Tried " + " | ".join(errors[-3:]))


def get_installed_ollama_models(timeout: float = 3.0) -> list[str]:
    """Return exact model tags installed in Ollama, or raise a useful error."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("The Ollama timeout must be positive.")
    payload, _base = _fetch_ollama_json("/api/tags", timeout=timeout)
    if not isinstance(payload.get("models", []), list):
        raise ValueError("Ollama returned an invalid model list.")
    names: set[str] = set()
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return sorted(names, key=str.casefold)


def create_ollama_client():
    """Create an SDK client pinned to the API host that passed our health check.

    trust_env=False prevents machine-wide HTTP_PROXY settings from accidentally
    routing local Ollama traffic through a web proxy on Windows.
    """
    import ollama

    with _OLLAMA_HOST_LOCK:
        active_host = _OLLAMA_ACTIVE_HOST
    if not active_host:
        # Resolve the host before creating the SDK client. This also ensures
        # the initial chat uses the same loopback address as the status check.
        get_installed_ollama_models(timeout=3.0)
        with _OLLAMA_HOST_LOCK:
            active_host = _OLLAMA_ACTIVE_HOST
    host = active_host or _ollama_api_base()
    return ollama.Client(host=host, trust_env=False)


def _fetch_ollama_post_json(
    path: str, body: dict[str, Any], timeout: float = 2.0
) -> tuple[dict[str, Any], str]:
    """POST a small JSON request to the active local Ollama endpoint."""
    errors: list[str] = []
    candidates = [_ollama_api_base()] + [
        candidate for candidate in _ollama_api_candidates() if candidate != _ollama_api_base()
    ]
    for base in candidates:
        request = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": f"JARVIS/{APP_VERSION}",
            },
            method="POST",
        )
        try:
            with _ollama_urlopen(request, min(max(float(timeout), 0.2), 5.0), base) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("Ollama returned an unexpectedly large response.")
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Ollama returned JSON in an unexpected format.")
            with _OLLAMA_HOST_LOCK:
                global _OLLAMA_ACTIVE_HOST
                _OLLAMA_ACTIVE_HOST = base
            return payload, base
        except Exception as error:
            errors.append(f"{base}: {type(error).__name__}: {error}")
    raise ConnectionError("Ollama model metadata could not be read. " + " | ".join(errors[-3:]))


def get_preferred_think_mode(model: str | None = None, timeout: float = 1.5) -> bool | str | None:
    """Choose the model's lightest documented thinking mode, caching metadata.

    Ollama's /api/show response advertises supported thinking values. Prefer
    `False` when available, otherwise `low`; omit the field when the server or
    model does not advertise a supported control.
    """
    selected_model = str(model or MODEL_NAME).strip()
    if not selected_model:
        return None
    now = time.monotonic()
    with _OLLAMA_THINK_CACHE_LOCK:
        cached = _OLLAMA_THINK_CACHE.get(selected_model.casefold())
        if cached and now - cached[0] < _OLLAMA_THINK_CACHE_SECONDS:
            return cached[1]
    chosen: bool | str | None = None
    try:
        payload, _base = _fetch_ollama_post_json(
            "/api/show", {"model": selected_model}, timeout=timeout
        )
        thinking = payload.get("thinking")
        values = thinking.get("values") if isinstance(thinking, dict) else None
        if isinstance(values, list):
            if False in values:
                chosen = False
            elif "low" in values:
                chosen = "low"
    except Exception as error:
        # Older Ollama servers may not expose thinking metadata. Ordinary chat
        # still works; simply leave the model's default thinking behaviour.
        log_error("Could not discover model thinking controls; using model default.", error)
    with _OLLAMA_THINK_CACHE_LOCK:
        _OLLAMA_THINK_CACHE[selected_model.casefold()] = (now, chosen)
    return chosen


def _client_supports_parameter(method: Any, parameter_name: str) -> bool:
    """Check optional SDK keyword support without making a failing chat call."""
    try:
        parameters = inspect.signature(method).parameters.values()
        return any(
            item.name == parameter_name or item.kind is inspect.Parameter.VAR_KEYWORD
            for item in parameters
        )
    except (TypeError, ValueError):
        return False


def _request_may_need_tools(user_input: str) -> bool:
    """Only include tool schemas when the wording plausibly requests an action."""
    text = str(user_input).strip().casefold()
    action_start = re.compile(
        r"^(?:(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?)?"
        r"(?:open|launch|start|run|close|quit|search|google|look\s+up|browse|"
        r"type|paste|take\s+(?:a\s+)?note|save\s+(?:a\s+)?note|"
        r"read\s+(?:my\s+)?notes?|open\s+(?:my\s+)?notes?|"
        r"set\s+(?:a\s+)?timer|cancel\s+(?:all\s+)?timers?|"
        r"show\s+(?:my\s+)?(?:desktop|downloads|documents|pictures|music|videos)|"
        r"check\s+(?:the\s+)?ollama|convert|analyse|analyze|clean\s+text|"
        r"format\s+json|validate\s+json|base64|sha-?256|sha-?512|hash\s+text|"
        r"generate\s+(?:a\s+)?(?:uuid|guid|\d+\s+character\s+password)|"
        r"pick\s+randomly|roll\s+\d*d|split\s+(?:a\s+)?(?:bill\s+of\s+)?"
        r"add\s+task|complete\s+task|delete\s+task|add\s+reminder|remind\s+me|dismiss\s+reminder|"
        r"save\s+bookmark|search\s+bookmarks?|delete\s+bookmark|save\s+snippet|"
        r"list\s+my\s+(?:tasks|reminders|bookmarks|snippets)|"
        r"show\s+system\s+health|system\s+health|create\s+a\s+\d+\s+minute\s+pomodoro)\b"
    )
    if action_start.match(text):
        return True
    # Some natural-language action requests put the verb after an opener.
    return bool(re.match(
        r"^(?:i want you to|i need you to|could you help me|can you help me)\s+"
        r"(?:open|launch|start|run|close|search|google|look up|type|paste|save|take)\b",
        text,
    ))


def check_ollama_status() -> tuple[bool, str]:
    """Check the Ollama API and configured model using resilient local endpoints."""
    try:
        installed = get_installed_ollama_models(timeout=3.0)
        host = _ollama_api_base()
        installed_lookup = {name.casefold() for name in installed}
        configured = MODEL_NAME.casefold()
        if configured in installed_lookup:
            return True, f"Ollama online · {MODEL_NAME} ready · {NUM_CTX:,} context"
        available = ", ".join(installed[:4]) if installed else "none installed"
        return False, (
            f"Ollama online · {MODEL_NAME} missing · installed: {available}. "
            f"Run: ollama pull {MODEL_NAME}"
        )
    except Exception as error:
        log_error("Ollama status check failed; all candidate endpoints were tried.", error)
        return False, f"Ollama offline · {type(error).__name__} · see jarvis.log"


def open_folder(folder_name: str = "", **kwargs: Any) -> str:
    """Open a known personal folder; arbitrary paths are deliberately not accepted."""
    if not isinstance(folder_name, str) or not folder_name.strip():
        folder_name = first_real_text_argument(kwargs, ("folder_name", "folder", "name", "target", "text"))
    key = str(folder_name).strip().lower().replace("my ", "")
    folders = {
        "desktop": Path.home() / "Desktop",
        "downloads": Path.home() / "Downloads",
        "documents": Path.home() / "Documents",
        "pictures": Path.home() / "Pictures",
        "music": Path.home() / "Music",
        "videos": Path.home() / "Videos",
    }
    path = folders.get(key)
    if path is None:
        return "I can open your Desktop, Downloads, Documents, Pictures, Music or Videos folder."
    if not path.exists():
        return f"Your {key} folder wasn't found at {path}."
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif not _open_browser_url(path.as_uri()):
            return f"I couldn't open your {key} folder in a browser."
        return f"Opened your {key} folder."
    except OSError as error:
        log_error(f"Could not open the {key} folder.", error)
        return f"I couldn't open your {key} folder."


def get_system_info(**kwargs: Any) -> str:
    """Return basic, non-sensitive app/runtime information for troubleshooting."""
    return (
        f"J.A.R.V.I.S. version {get_app_version()}. "
        f"Running on {platform.system()} {platform.release()} with Python {platform.python_version()}. "
        f"Configured Ollama model: {MODEL_NAME} with {NUM_CTX:,} context tokens. "
        f"Log file: {user_data_dir() / 'jarvis.log'}"
    )


def get_help(**kwargs: Any) -> str:
    return (
        "I can calculate using BIDMAS, search the web, open apps and websites, "
        "take/read notes, paste exact text, set timers, and open common folders. "
        "Workspace adds 25 local tools: world clocks, timezone and date tools, unit/percentage/bill calculators, "
        "text analysis and cleanup, case conversion, URL/JSON/Base64 tools, hashes, UUID/password generation, "
        "random picker, dice, stopwatch, Pomodoro planner, tasks, reminders, bookmarks, snippets and system health. "
        "Open Workspace in the sidebar to browse them, or ask me directly."
    )


def extract_open_url(user_input: str) -> str | None:
    match = re.match(r"^\s*(?:please\s+)?(?:open|visit|go\s+to)\s+(?:website\s+)?(https?://\S+|www\.\S+|[\w.-]+\.[A-Za-z]{2,}(?:/\S*)?)\s*$", str(user_input), flags=re.IGNORECASE)
    if not match:
        return None
    url = match.group(1).rstrip(".,!?;)")
    return url if url.startswith(("http://", "https://")) else "https://" + url


def open_url(url: str = "", **kwargs: Any) -> str:
    url = str(url or first_real_text_argument(kwargs, ("url", "website", "address", "link", "text"))).strip()
    if len(url) > 2048 or not re.fullmatch(r"https?://[^\s]+", url, flags=re.IGNORECASE):
        return "Please provide a valid http or https website address."
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return "Please provide a valid http or https website address."
    except ValueError:
        return "Please provide a valid http or https website address."
    if not _open_browser_url(url):
        return "I couldn't find a browser to open that website."
    return f"Opened {url}."


# ==========================================
# TEXT INPUT TOOL
# ==========================================

def type_text(text: str = "", **kwargs: Any) -> str:
    """Paste exact text into the focused application using the system clipboard."""
    if not isinstance(text, str) or not text.strip():
        text = first_real_text_argument(
            kwargs, ("text", "content", "message", "value", "input", "text_to_type")
        )
    if not text.strip():
        return "What would you like me to type?"
    if len(text) > 20000:
        return "That text is too long to paste in one go (20,000 characters maximum)."

    try:
        import pyautogui
        import pyperclip

        pyperclip.copy(text)
        if pyperclip.paste() != text:
            return "I couldn't verify the clipboard contents, so I didn't paste anything."
        speak("Click where you want the text. Pasting in three seconds.")
        time.sleep(3)
        pyautogui.hotkey("ctrl", "v", interval=0.08)
        return f"Paste command sent for {len(text)} characters."
    except Exception as error:
        log_error("Text paste failed.", error)
        return f"Typing error: {error}"


# ==========================================
# TOOL REGISTRY + REQUEST ROUTING
# ==========================================

available_tools = {
    "open_app": open_app,
    "close_app": close_app,
    "open_url": open_url,
    "search_edge": search_edge,
    "calculate": calculate,
    "get_current_time": get_current_time,
    "take_note": take_note,
    "read_notes": read_notes,
    "open_notes": open_notes,
    "open_folder": open_folder,
    "get_system_info": get_system_info,
    "get_help": get_help,
    "type_text": type_text,
    "cancel_timers": cancel_timers,
    "workspace_action": workspace.workspace_action,
}

# Pass explicit JSON schemas to Ollama instead of Python callables. The Ollama
# SDK normally introspects callable annotations and builds temporary Pydantic
# models. With Python 3.14 + postponed annotations + recent Pydantic, that
# introspection can leave `Any` as an unresolved ForwardRef and fail before
# the request reaches Ollama (the user's log showed this for `open_app`).
# Explicit schemas are stable across Python/Pydantic versions and keep runtime
# dispatch separate from the model-facing tool contract.
def _ollama_tool(
    name: str,
    description: str,
    properties: dict[str, dict[str, str]],
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(required),
                "additionalProperties": False,
            },
        },
    }


OLLAMA_TOOL_SCHEMAS: list[dict[str, Any]] = [
    _ollama_tool("open_app", "Open a supported desktop app, website, or web service.",
                 {"app_name": {"type": "string", "description": "Name of the app or website to open."}}, ("app_name",)),
    _ollama_tool("close_app", "Close a supported running desktop app.",
                 {"app_name": {"type": "string", "description": "Name of the app to close."}}, ("app_name",)),
    _ollama_tool("open_url", "Open a valid HTTP or HTTPS website address.",
                 {"url": {"type": "string", "description": "Complete website URL."}}, ("url",)),
    _ollama_tool("search_edge", "Search the web for the supplied phrase.",
                 {"query": {"type": "string", "description": "The complete search phrase, without tool metadata."}}, ("query",)),
    _ollama_tool("calculate", "Evaluate a basic arithmetic expression using BIDMAS.",
                 {"expression": {"type": "string", "description": "Arithmetic expression, including brackets and powers."}}, ("expression",)),
    _ollama_tool("get_current_time", "Get the computer's current local date and time.", {}),
    _ollama_tool("take_note", "Save a note to the user's notes file.",
                 {"note_text": {"type": "string", "description": "The exact note text to save."}}, ("note_text",)),
    _ollama_tool("read_notes", "Read the user's saved notes.", {}),
    _ollama_tool("open_notes", "Open the user's notes file.", {}),
    _ollama_tool("open_folder", "Open one of the supported user folders.",
                 {"folder_name": {"type": "string", "description": "Desktop, Downloads, Documents, Pictures, Music, or Videos."}}, ("folder_name",)),
    _ollama_tool("get_system_info", "Show basic information about this computer.", {}),
    _ollama_tool("get_help", "List the assistant's supported commands and features.", {}),
    _ollama_tool("type_text", "Paste the exact supplied text into the currently focused application.",
                 {"text": {"type": "string", "description": "The complete exact text to paste."}}, ("text",)),
    _ollama_tool("cancel_timers", "Cancel all active timers.", {}),
    _ollama_tool("workspace_action", "Use one of J.A.R.V.I.S.'s 25 deterministic Workspace utilities. Pass the user's action as a concise command, preserving any exact text or values.",
                 {"command": {"type": "string", "description": "A Workspace command such as 'Convert 5 miles to km', 'Generate a UUID', or 'List my tasks'."}}, ("command",)),
]


def _append_history(history: list[dict[str, Any]], message: dict[str, Any]) -> None:
    history.append(message)
    if len(history) > MAX_HISTORY_MESSAGES:
        system_message = history[0] if history and history[0].get("role") == "system" else None
        recent = history[-(MAX_HISTORY_MESSAGES - (1 if system_message else 0)):]
        # Start on a user turn so an old tool result is never left without the
        # assistant tool-call message that introduced it.
        first_user = next((i for i, item in enumerate(recent) if item.get("role") == "user"), None)
        if first_user is not None:
            recent = recent[first_user:]
        history[:] = ([system_message] if system_message else []) + recent


def _normalise_tool_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if hasattr(arguments, "model_dump"):
        dumped = arguments.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(arguments, "dict"):
        dumped = arguments.dict()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _handle_direct_request(user_input: str) -> str | None:
    """Return a direct result for deterministic tasks; None means ask the AI."""
    cleaned = user_input.strip()
    lowered = cleaned.lower()

    # The Workspace catalogue runs deterministic local utilities before the
    # language model, keeping arithmetic, text and productivity actions fast.
    try:
        workspace_result = workspace.dispatch_command(cleaned)
    except (ValueError, OSError) as error:
        return f"I couldn't complete that Workspace action: {error}"
    if workspace_result is not None:
        return workspace_result

    if re.fullmatch(r"(?:please\s+)?(?:check|test)\s+(?:the\s+)?ollama(?:\s+connection)?[.!]?", lowered):
        _ok, status = check_ollama_status()
        return status
    if lowered.strip(" .!?") in {"help", "what can you do", "what are your features"}:
        return get_help()
    if lowered.strip(" .!?") in {"system info", "system information", "about jarvis", "about j.a.r.v.i.s."}:
        return get_system_info()

    greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "sup", "greetings"}
    if lowered.strip(" .!?") in greetings:
        return "Hello! All systems are ready. What can I help you with?"

    social_text = re.sub(r"\s+", " ", re.sub(r"[^\w\s']", "", lowered)).strip()
    if social_text in {
        "how are you", "how are you doing", "how are things", "how is it going",
        "how's it going", "hows it going", "you alright", "you all right",
        "are you alright", "are you all right", "you good", "what's up", "whats up",
    }:
        return "I'm doing well, thanks for asking. I'm ready to help — what are we working on?"
    if social_text in {"thanks", "thank you", "cheers", "thanks jarvis", "thank you jarvis"}:
        return "You're welcome. Glad I could help."
    if social_text in {"who are you", "what are you"}:
        return "I'm J.A.R.V.I.S., your local desktop assistant. I can answer questions and help with tasks on your PC."

    math_expression = extract_math_expression(cleaned)
    if math_expression is not None:
        return calculate(expression=math_expression)

    if is_time_request(cleaned):
        return get_current_time()

    timer_seconds = extract_timer_seconds(cleaned)
    if timer_seconds is not None:
        return set_timer(timer_seconds)
    if re.fullmatch(r"\s*(?:please\s+)?cancel\s+(?:all\s+)?timers?\s*[.!]?\s*", lowered):
        return cancel_timers()

    if re.fullmatch(r"\s*(?:please\s+)?open\s+(?:my\s+)?notes?\s*[.!]?\s*", lowered):
        return open_notes()
    folder_match = re.fullmatch(r"\s*(?:please\s+)?(?:open|show)\s+(?:my\s+)?(desktop|downloads|documents|pictures|music|videos)\s*[.!]?\s*", lowered)
    if folder_match:
        return open_folder(folder_name=folder_match.group(1))
    if re.fullmatch(r"\s*(?:please\s+)?(?:read|list|show)\s+(?:my\s+)?notes?\s*[.!]?\s*", lowered):
        return read_notes()

    note_text = extract_note_text(cleaned)
    if note_text is not None:
        return take_note(note_text=note_text)

    typing_command = re.match(
        r"^\s*(?:(?:j\.?a\.?r\.?v\.?i\.?s\.?)\s*[, :]\s*)?"
        r"(?:(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?)?"
        r"(?:type|paste)\b",
        cleaned, flags=re.IGNORECASE,
    )
    if typing_command:
        quoted = re.search(r'"(.*?)"|“(.*?)”|\'(.*?)\'|‘(.*?)’', cleaned, flags=re.DOTALL)
        if quoted:
            text_to_type = next((part for part in quoted.groups() if part is not None), "")
        else:
            text_to_type = cleaned[typing_command.end():].strip()
            text_to_type = re.sub(
                r"\s+into\s+(?:(?:the|my)\s+)?(?:document|doc|google\s+docs?|word|notepad|text\s+editor|active\s+window)\s*[.!?]*$",
                "", text_to_type, flags=re.IGNORECASE,
            ).strip()
        return type_text(text=text_to_type) if text_to_type else "What would you like me to type?"

    search_query = extract_search_query(cleaned)
    if search_query is not None:
        return search_edge(query=search_query) if search_query else "What would you like me to search for?"

    url = extract_open_url(cleaned)
    if url:
        return open_url(url=url)

    open_target = extract_open_target(cleaned)
    if open_target:
        return open_app(app_name=open_target)
    close_target = extract_close_target(cleaned)
    if close_target:
        return close_app(app_name=close_target)

    return None


def process_user_request(user_input: str, history: list[dict[str, Any]]) -> None:
    """Handle deterministic commands locally, otherwise ask the configured Ollama model."""
    user_text = str(user_input).strip()
    if not user_text:
        return
    if len(user_text) > MAX_INPUT_LENGTH:
        speak(f"Please keep each message under {MAX_INPUT_LENGTH} characters.")
        return

    try:
        direct_result = _handle_direct_request(user_text)
    except Exception as error:
        log_error("A direct command failed.", error)
        direct_result = "I couldn't complete that command. Details have been saved to the J.A.R.V.I.S. log."
    if direct_result is not None:
        _append_history(history, {"role": "user", "content": user_text})
        _append_history(history, {"role": "assistant", "content": direct_result})
        speak(direct_result)
        return

    _append_history(history, {"role": "user", "content": user_text})
    try:
        client = create_ollama_client()
        needs_tools = _request_may_need_tools(user_text)
        chat_kwargs: dict[str, Any] = {
            "model": MODEL_NAME,
            "messages": history,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": ollama_chat_options(224 if not needs_tools else 320),
        }
        if needs_tools:
            chat_kwargs["tools"] = OLLAMA_TOOL_SCHEMAS
        think_mode = get_preferred_think_mode(MODEL_NAME)
        if think_mode is not None and _client_supports_parameter(client.chat, "think"):
            chat_kwargs["think"] = think_mode
        response = client.chat(**chat_kwargs)

        # Execute at most three tool rounds to avoid loops from small models.
        for _round in range(3):
            calls = getattr(response.message, "tool_calls", None) or []
            if not calls:
                content = str(getattr(response.message, "content", "") or "").strip()
                if content:
                    _append_history(history, {"role": "assistant", "content": content})
                    speak(content)
                else:
                    fallback = "I'm not sure how to help with that. Could you rephrase it?"
                    _append_history(history, {"role": "assistant", "content": fallback})
                    speak(fallback)
                return

            assistant_tool_message: dict[str, Any] = {"role": "assistant", "content": "", "tool_calls": []}
            tool_results: list[str] = []
            for tool_call in calls:
                function = getattr(tool_call, "function", None)
                function_name = getattr(function, "name", "")
                arguments = _normalise_tool_arguments(getattr(function, "arguments", {}))
                assistant_tool_message["tool_calls"].append({
                    "function": {"name": function_name, "arguments": arguments}
                })
            _append_history(history, assistant_tool_message)

            for tool_call in calls:
                function = getattr(tool_call, "function", None)
                function_name = getattr(function, "name", "")
                arguments = _normalise_tool_arguments(getattr(function, "arguments", {}))
                if function_name not in available_tools:
                    result = f"Unknown tool requested: {function_name or 'unnamed tool'}."
                else:
                    try:
                        result = str(available_tools[function_name](**arguments))
                    except Exception as tool_error:
                        log_error(f"Tool {function_name} failed.", tool_error)
                        result = f"The {function_name} tool failed: {tool_error}"
                tool_results.append(result)
                _append_history(history, {"role": "tool", "name": function_name or "unknown", "content": result})

            # If another Ollama call fails, at least show the actual tool results.
            try:
                followup_kwargs: dict[str, Any] = {
                    "model": MODEL_NAME,
                    "messages": history,
                    "tools": OLLAMA_TOOL_SCHEMAS,
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "options": ollama_chat_options(192),
                }
                if think_mode is not None and _client_supports_parameter(client.chat, "think"):
                    followup_kwargs["think"] = think_mode
                response = client.chat(**followup_kwargs)
            except Exception:
                combined = "\n".join(tool_results)
                _append_history(history, {"role": "assistant", "content": combined})
                speak(combined)
                return

        message = "I've reached the limit for tool actions in one request. Please split that into a couple of steps."
        _append_history(history, {"role": "assistant", "content": message})
        speak(message)

    except Exception as error:
        log_error("Ollama request failed.", error)
        error_text = str(error).strip() or type(error).__name__
        if "not found" in error_text.casefold() and "model" in error_text.casefold():
            friendly = f"Ollama is reachable, but the model '{MODEL_NAME}' was not found. Run: ollama pull {MODEL_NAME}"
        elif any(word in error_text.casefold() for word in ("connect", "connection", "refused", "timed out", "timeout")):
            friendly = (
                f"I couldn't reach Ollama at {_ollama_api_base()}. Check that its local API is available at "
                "http://localhost:11434/api/tags. The exact error was saved to jarvis.log."
            )
        else:
            friendly = f"Ollama returned an error ({type(error).__name__}): {error_text[:240]}. Details are in jarvis.log."
        _append_history(history, {"role": "assistant", "content": friendly})
        speak(friendly)


if __name__ == "__main__":
    # Keep the module useful when run directly for quick diagnostics.
    default_history = [{"role": "system", "content": "You are J.A.R.V.I.S., a helpful local assistant."}]
    speak("J.A.R.V.I.S. core is ready. Use JARVIS_GUI.py to open the desktop app.")
    while True:
        try:
            prompt = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if prompt.lower() in {"quit", "exit", "goodbye"}:
            break
        process_user_request(prompt, default_history)
