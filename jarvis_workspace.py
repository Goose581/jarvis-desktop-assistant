"""Deterministic local workspace utilities for J.A.R.V.I.S.

All utilities are offline-first. Persistent data lives under the per-user
JARVIS data directory. Functions validate inputs and avoid shell execution.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import string
import time
import threading
import unicodedata
import urllib.parse
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_TEXT = 100_000
MAX_RECORDS = 5_000
MAX_STORE_BYTES = 5_000_000


def _text(value: Any, label: str = "Text", limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    if len(value) > limit:
        raise ValueError(f"{label} must be no longer than {limit:,} characters.")
    return value


def _number(value: Any, label: str = "Value") -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    return result


def _zone(name: str) -> ZoneInfo:
    name = _text(name, "Timezone", 100).strip()
    if not name or ".." in name or name.startswith(("/", "\\")):
        raise ValueError("Enter a valid IANA timezone such as Europe/London.")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


# 01. World clock

def world_clock(timezone_name: str, now: datetime | None = None) -> dict[str, str]:
    zone = _zone(timezone_name)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(zone)
    return {"timezone": timezone_name, "iso": local.isoformat(), "display": local.strftime("%A, %d %B %Y · %I:%M:%S %p")}


# 02. Timezone conversion

def convert_timezone(value: str, from_timezone: str, to_timezone: str) -> str:
    raw = _text(value, "Date and time", 80).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Use an ISO date/time, for example 2026-11-13T09:30:00.") from exc
    source = _zone(from_timezone)
    target = _zone(to_timezone)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source)
    return parsed.astimezone(target).isoformat()


# 03. Date difference

def date_difference(start: str, end: str) -> dict[str, int]:
    try:
        delta = date.fromisoformat(_text(end, "End date", 20)) - date.fromisoformat(_text(start, "Start date", 20))
    except ValueError as exc:
        raise ValueError("Dates must use YYYY-MM-DD format.") from exc
    return {"days": delta.days, "weeks": math.trunc(delta.days / 7), "absolute_days": abs(delta.days)}


# 04. Date calculator

def shift_date(value: str, days: int = 0, weeks: int = 0, months: int = 0) -> str:
    try:
        base = date.fromisoformat(_text(value, "Date", 20))
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc
    for item, label in ((days, "Days"), (weeks, "Weeks"), (months, "Months")):
        if isinstance(item, bool) or not isinstance(item, int) or abs(item) > 100_000:
            raise ValueError(f"{label} must be a whole number within 100,000.")
    # Month arithmetic clamps to the final valid day of the destination month.
    month_index = base.year * 12 + (base.month - 1) + months
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    import calendar
    day = min(base.day, calendar.monthrange(year, month)[1])
    result = date(year, month, day) + timedelta(days=days + weeks * 7)
    return result.isoformat()


# 05. Unit converter
_UNIT_TABLE: dict[str, tuple[str, float]] = {
    "mm": ("length", 0.001), "cm": ("length", 0.01), "m": ("length", 1.0),
    "km": ("length", 1000.0), "in": ("length", 0.0254), "ft": ("length", 0.3048),
    "yd": ("length", 0.9144), "mi": ("length", 1609.344),
    "mg": ("mass", 0.000001), "g": ("mass", 0.001), "kg": ("mass", 1.0),
    "t": ("mass", 1000.0), "oz": ("mass", 0.028349523125), "lb": ("mass", 0.45359237),
    "ml": ("volume", 0.001), "l": ("volume", 1.0), "tsp": ("volume", 0.00492892159),
    "tbsp": ("volume", 0.0147867648), "cup": ("volume", 0.2365882365),
    "m/s": ("speed", 1.0), "km/h": ("speed", 1 / 3.6), "mph": ("speed", 0.44704),
    "b": ("data", 1.0), "kb": ("data", 1000.0), "mb": ("data", 1_000_000.0),
    "gb": ("data", 1_000_000_000.0), "kib": ("data", 1024.0),
    "mib": ("data", 1024.0**2), "gib": ("data", 1024.0**3),
}

_UNIT_ALIASES = {
    "millimetres": "mm", "millimeters": "mm", "millimetre": "mm", "millimeter": "mm",
    "centimetres": "cm", "centimeters": "cm", "centimetre": "cm", "centimeter": "cm",
    "metres": "m", "meters": "m", "metre": "m", "meter": "m",
    "kilometres": "km", "kilometers": "km", "kilometre": "km", "kilometer": "km",
    "inches": "in", "inch": "in", "feet": "ft", "foot": "ft", "yards": "yd", "yard": "yd",
    "miles": "mi", "mile": "mi", "milligrams": "mg", "milligram": "mg", "grams": "g", "gram": "g",
    "kilograms": "kg", "kilogram": "kg", "tonnes": "t", "tonne": "t", "ounces": "oz", "ounce": "oz",
    "pounds": "lb", "pound": "lb", "millilitres": "ml", "milliliters": "ml", "millilitre": "ml", "milliliter": "ml",
    "litres": "l", "liters": "l", "litre": "l", "liter": "l", "teaspoons": "tsp", "teaspoon": "tsp",
    "tablespoons": "tbsp", "tablespoon": "tbsp", "cups": "cup", "cupfuls": "cup",
    "bytes": "b", "byte": "b", "kilobytes": "kb", "kilobyte": "kb", "megabytes": "mb", "megabyte": "mb",
    "gigabytes": "gb", "gigabyte": "gb", "kibibytes": "kib", "mebibytes": "mib", "gibibytes": "gib",
    "kmh": "km/h", "kph": "km/h", "mps": "m/s",
}

def convert_units(value: float, source_unit: str, target_unit: str) -> float:
    amount = _number(value)
    source = _UNIT_ALIASES.get(source_unit.strip().lower(), source_unit.strip().lower())
    target = _UNIT_ALIASES.get(target_unit.strip().lower(), target_unit.strip().lower())
    if source in {"c", "°c", "celsius"} and target in {"f", "°f", "fahrenheit"}:
        return amount * 9 / 5 + 32
    if source in {"f", "°f", "fahrenheit"} and target in {"c", "°c", "celsius"}:
        return (amount - 32) * 5 / 9
    if source in {"c", "°c", "celsius"} and target in {"k", "kelvin"}:
        return amount + 273.15
    if source in {"k", "kelvin"} and target in {"c", "°c", "celsius"}:
        return amount - 273.15
    if source not in _UNIT_TABLE or target not in _UNIT_TABLE:
        raise ValueError("One of those units is not supported.")
    if _UNIT_TABLE[source][0] != _UNIT_TABLE[target][0]:
        raise ValueError("Those units belong to different measurement categories.")
    return amount * _UNIT_TABLE[source][1] / _UNIT_TABLE[target][1]


# 06. Percentage calculator

def percentage(part: float, whole: float) -> float:
    numerator, denominator = _number(part, "Part"), _number(whole, "Whole")
    if denominator == 0:
        raise ValueError("The whole cannot be zero.")
    return numerator / denominator * 100


# 07. Bill splitter / tip calculator

def split_bill(total: float, people: int, tip_percent: float = 0) -> dict[str, float]:
    amount, tip = _number(total, "Total"), _number(tip_percent, "Tip percentage")
    if amount < 0 or tip < 0 or tip > 1000:
        raise ValueError("Total and tip must be non-negative; tip must not exceed 1000%.")
    if isinstance(people, bool) or not isinstance(people, int) or not 1 <= people <= 1000:
        raise ValueError("People must be a whole number from 1 to 1000.")
    gratuity = round(amount * tip / 100, 2)
    grand = round(amount + gratuity, 2)
    return {"subtotal": round(amount, 2), "tip": gratuity, "total": grand, "per_person": round(grand / people, 2)}


# 08. Text analytics

def text_statistics(text: str) -> dict[str, int | float]:
    value = _text(text)
    words = re.findall(r"\b[\w’'-]+\b", value, flags=re.UNICODE)
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", value.strip()) if part] if value.strip() else []
    return {"characters": len(value), "characters_no_spaces": sum(not c.isspace() for c in value),
            "words": len(words), "lines": len(value.splitlines()), "sentences": len(sentences),
            "reading_minutes": round(len(words) / 200, 2)}


# 09. Case conversion

def convert_case(text: str, mode: str) -> str:
    value = _text(text)
    key = mode.strip().lower()
    words = re.findall(r"[A-Za-z0-9]+", value)
    if key == "upper": return value.upper()
    if key == "lower": return value.lower()
    if key == "title": return value.title()
    if key in {"sentence", "sentence case"}:
        lowered = value.lower()
        return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), lowered)
    if key == "camel": return (words[0].lower() + "".join(w.title() for w in words[1:])) if words else ""
    if key == "snake": return "_".join(w.lower() for w in words)
    if key == "kebab": return "-".join(w.lower() for w in words)
    if key == "pascal": return "".join(w.title() for w in words)
    raise ValueError("Choose upper, lower, title, sentence, camel, snake, kebab or pascal.")


# 10. Text cleaner

def clean_text(text: str, collapse_spaces: bool = True, remove_blank_lines: bool = False, strip_lines: bool = True) -> str:
    value = _text(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = value.split("\n")
    if strip_lines:
        lines = [line.strip() for line in lines]
    if remove_blank_lines:
        lines = [line for line in lines if line]
    if collapse_spaces:
        lines = [re.sub(r"[ \t]+", " ", line) for line in lines]
    return "\n".join(lines)


# 11. URL encoder / decoder

def url_encode(text: str) -> str:
    return urllib.parse.quote(_text(text), safe="")


def url_decode(text: str) -> str:
    value = _text(text)
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise ValueError("The URL contains an incomplete percent-encoding sequence.")
    try:
        return urllib.parse.unquote(value, errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("The URL contains invalid encoded text.") from exc


# 12. JSON formatter / validator

def format_json(text: str, compact: bool = False) -> str:
    value = _text(text)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    return json.dumps(parsed, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None)


# 13. Base64 codec

def base64_encode(text: str) -> str:
    return base64.b64encode(_text(text).encode("utf-8")).decode("ascii")


def base64_decode(value: str) -> str:
    raw = _text(value).strip()
    try:
        return base64.b64decode(raw, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("That is not valid UTF-8 Base64 text.") from exc


# 14. Text hashing

def hash_text(text: str, algorithm: str = "sha256") -> str:
    key = algorithm.strip().lower().replace("-", "")
    if key not in {"sha256", "sha512", "sha1", "md5"}:
        raise ValueError("Choose SHA-256, SHA-512, SHA-1 or MD5.")
    return hashlib.new(key, _text(text).encode("utf-8")).hexdigest()


# 15. UUID generator

def generate_uuid() -> str:
    return str(uuid.uuid4())


# 16. Password generator

def generate_password(length: int = 20, use_symbols: bool = True) -> str:
    if isinstance(length, bool) or not isinstance(length, int) or not 8 <= length <= 128:
        raise ValueError("Password length must be a whole number from 8 to 128.")
    if not isinstance(use_symbols, bool):
        raise ValueError("use_symbols must be true or false.")
    alphabet = string.ascii_letters + string.digits + ("!@#$%^&*()-_=+[]{}?" if use_symbols else "")
    # Guarantee at least one letter and one digit, then shuffle with a CSPRNG.
    chars = [secrets.choice(string.ascii_lowercase), secrets.choice(string.digits)]
    if use_symbols:
        chars.append(secrets.choice("!@#$%^&*()-_=+[]{}?"))
    chars.extend(secrets.choice(alphabet) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


# 17. Random picker

def random_choice(items: Iterable[Any]) -> Any:
    if isinstance(items, (str, bytes)) or not isinstance(items, Iterable):
        raise ValueError("Give me a list of at least two choices.")
    choices = list(items)
    if not 2 <= len(choices) <= 1000:
        raise ValueError("Give me between 2 and 1000 choices.")
    return secrets.choice(choices)


# 18. Dice roller

def roll_dice(count: int = 1, sides: int = 6) -> dict[str, Any]:
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (count, sides)):
        raise ValueError("Dice count and sides must be whole numbers.")
    if not 1 <= count <= 100 or not 2 <= sides <= 1000:
        raise ValueError("Roll 1–100 dice with 2–1000 sides each.")
    rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
    return {"rolls": rolls, "total": sum(rolls), "count": count, "sides": sides}


# 19. Stopwatch engine
class Stopwatch:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._started: float | None = None
        self._elapsed = 0.0
        self._laps: list[float] = []
    def start(self) -> bool:
        if self._started is not None: return False
        self._started = self._clock(); return True
    def stop(self) -> float:
        if self._started is not None:
            self._elapsed += max(0.0, self._clock() - self._started); self._started = None
        return self._elapsed
    def reset(self) -> None:
        self._started = None; self._elapsed = 0.0; self._laps.clear()
    def elapsed(self) -> float:
        return self._elapsed + (max(0.0, self._clock() - self._started) if self._started is not None else 0.0)
    def lap(self) -> float:
        current = self.elapsed(); previous = self._laps[-1] if self._laps else 0.0
        self._laps.append(current); return current - previous
    def laps(self) -> list[float]: return list(self._laps)


# 20. Pomodoro planner

def pomodoro_plan(work_minutes: int = 25, short_break_minutes: int = 5, long_break_minutes: int = 15, cycles: int = 4) -> list[dict[str, Any]]:
    values = (work_minutes, short_break_minutes, long_break_minutes, cycles)
    if any(isinstance(v, bool) or not isinstance(v, int) for v in values):
        raise ValueError("Pomodoro settings must be whole minutes/cycles.")
    if not 1 <= work_minutes <= 180 or not 1 <= short_break_minutes <= 60 or not 1 <= long_break_minutes <= 120 or not 1 <= cycles <= 24:
        raise ValueError("Pomodoro settings are outside the supported range.")
    result: list[dict[str, Any]] = []
    for cycle in range(1, cycles + 1):
        result.append({"type": "work", "cycle": cycle, "minutes": work_minutes})
        if cycle < cycles:
            kind = "long_break" if cycle % 4 == 0 else "short_break"
            result.append({"type": kind, "cycle": cycle, "minutes": long_break_minutes if kind == "long_break" else short_break_minutes})
    return result


# Local, atomic JSON record stores used by Tasks, Reminders, Bookmarks and Snippets.
_STORE_LOCKS_GUARD = threading.Lock()
_STORE_LOCKS: dict[str, threading.RLock] = {}


class JsonRecordStore:
    def __init__(self, path: str | Path, max_records: int = MAX_RECORDS) -> None:
        self.path = Path(path)
        self.max_records = max_records
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_key = str(self.path.resolve())
        with _STORE_LOCKS_GUARD:
            self._lock = _STORE_LOCKS.setdefault(lock_key, threading.RLock())
    def _read(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self.path.exists(): return []
            if self.path.stat().st_size > MAX_STORE_BYTES: raise ValueError("The local data file is too large to read safely.")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
                raise ValueError("The local data file has an invalid format.")
            return data
    def _write(self, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            if len(rows) > self.max_records: raise ValueError("The local collection has reached its record limit.")
            temp = self.path.with_name(self.path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
                if temp.stat().st_size > MAX_STORE_BYTES: raise ValueError("The local data file would exceed its size limit.")
                temp.replace(self.path)
            finally:
                temp.unlink(missing_ok=True)
    def list(self) -> list[dict[str, Any]]:
        with self._lock: return self._read()
    def get(self, record_id: str) -> dict[str, Any] | None:
        with self._lock: return next((row for row in self._read() if row.get("id") == record_id), None)
    def add(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            rows = self._read()
            if len(rows) >= self.max_records: raise ValueError("The local collection is full.")
            item = {"id": str(uuid.uuid4()), **record}
            rows.append(item); self._write(rows); return item
    def update(self, record_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            rows = self._read()
            for row in rows:
                if row.get("id") == record_id:
                    row.update(changes); self._write(rows); return row
            return None
    def delete(self, record_id: str) -> bool:
        with self._lock:
            rows = self._read(); new_rows = [row for row in rows if row.get("id") != record_id]
            if len(new_rows) == len(rows): return False
            self._write(new_rows); return True


def default_data_path(filename: str) -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home()) / "JARVIS"
    return root / filename


# 21. Task manager
class TaskManager:
    def __init__(self, path: str | Path | None = None): self.store = JsonRecordStore(path or default_data_path("tasks.json"))
    def add(self, title: str, priority: str = "normal", due: str | None = None) -> dict[str, Any]:
        title = _text(title, "Task title", 300).strip(); priority = priority.lower().strip()
        if not title: raise ValueError("Task title cannot be empty.")
        if priority not in {"low", "normal", "high", "urgent"}: raise ValueError("Priority must be low, normal, high or urgent.")
        if due is not None:
            try: datetime.fromisoformat(_text(due, "Due date", 80).replace("Z", "+00:00"))
            except ValueError as exc: raise ValueError("Due date must be an ISO date or datetime.") from exc
        return self.store.add({"title": title, "priority": priority, "due": due, "completed": False, "created": datetime.now(timezone.utc).isoformat()})
    def list(self, include_completed: bool = True) -> list[dict[str, Any]]:
        rows = self.store.list(); return rows if include_completed else [r for r in rows if not r.get("completed")]
    def _resolve_id(self, task_id: str) -> str | None:
        value = _text(task_id, "Task ID", 36).strip().casefold()
        matches = [row["id"] for row in self.store.list() if str(row.get("id", "")).casefold().startswith(value)]
        return matches[0] if len(matches) == 1 else None
    def complete(self, task_id: str) -> bool:
        resolved = self._resolve_id(task_id)
        return self.store.update(resolved, {"completed": True, "completed_at": datetime.now(timezone.utc).isoformat()}) is not None if resolved else False
    def delete(self, task_id: str) -> bool:
        resolved = self._resolve_id(task_id)
        return self.store.delete(resolved) if resolved else False


# 22. Reminder manager (stores reminders; GUI scheduler can poll due items).
class ReminderManager:
    def __init__(self, path: str | Path | None = None): self.store = JsonRecordStore(path or default_data_path("reminders.json"))
    def add(self, title: str, due: str) -> dict[str, Any]:
        title = _text(title, "Reminder", 300).strip()
        if not title: raise ValueError("Reminder text cannot be empty.")
        try:
            parsed = datetime.fromisoformat(_text(due, "Reminder date", 80).replace("Z", "+00:00"))
        except ValueError as exc: raise ValueError("Reminder time must be an ISO date or datetime.") from exc
        return self.store.add({"title": title, "due": parsed.isoformat(), "dismissed": False})
    def due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        moment = now or datetime.now().astimezone()
        if moment.tzinfo is None:
            moment = moment.astimezone()
        result = []
        for row in self.store.list():
            if row.get("dismissed"):
                continue
            when = datetime.fromisoformat(row["due"])
            if when.tzinfo is None:
                when = when.astimezone()
            if when <= moment:
                result.append(row)
        return result
    def dismiss(self, reminder_id: str) -> bool: return self.store.update(reminder_id, {"dismissed": True}) is not None
    def list(self) -> list[dict[str, Any]]: return self.store.list()


# 23. Bookmarks manager
class BookmarkManager:
    def __init__(self, path: str | Path | None = None): self.store = JsonRecordStore(path or default_data_path("bookmarks.json"))
    def add(self, title: str, url: str, tags: Iterable[str] = ()) -> dict[str, Any]:
        title = _text(title, "Bookmark title", 200).strip(); url = _text(url, "URL", 2048).strip()
        parsed = urllib.parse.urlsplit(url)
        if not title or parsed.scheme not in {"http", "https"} or not parsed.hostname: raise ValueError("A bookmark needs a title and valid HTTP/HTTPS URL.")
        clean_tags = sorted({str(t).strip().lower()[:40] for t in tags if str(t).strip()})
        return self.store.add({"title": title, "url": url, "tags": clean_tags})
    def search(self, query: str = "") -> list[dict[str, Any]]:
        needle = _text(query, "Search", 200).strip().casefold()
        rows = self.store.list()
        if not needle: return rows
        return [r for r in rows if needle in r.get("title", "").casefold() or needle in r.get("url", "").casefold() or any(needle in t for t in r.get("tags", []))]
    def delete(self, bookmark_id: str) -> bool:
        value = _text(bookmark_id, "Bookmark ID", 36).strip().casefold()
        matches = [row["id"] for row in self.store.list() if str(row.get("id", "")).casefold().startswith(value)]
        return self.store.delete(matches[0]) if len(matches) == 1 else False


# 24. Text snippets manager
class SnippetManager:
    def __init__(self, path: str | Path | None = None): self.store = JsonRecordStore(path or default_data_path("snippets.json"))
    def save(self, name: str, content: str) -> dict[str, Any]:
        key = _text(name, "Snippet name", 80).strip().casefold(); text = _text(content, "Snippet content", 20_000)
        if not key or not text.strip(): raise ValueError("Snippet name and content are required.")
        rows = self.store.list(); existing = next((r for r in rows if r.get("name") == key), None)
        if existing:
            return self.store.update(existing["id"], {"content": text, "updated": datetime.now(timezone.utc).isoformat()}) or existing
        return self.store.add({"name": key, "content": text, "updated": datetime.now(timezone.utc).isoformat()})
    def get(self, name: str) -> str | None:
        key = _text(name, "Snippet name", 80).strip().casefold()
        row = next((r for r in self.store.list() if r.get("name") == key), None)
        return row.get("content") if row else None
    def list(self) -> list[dict[str, Any]]: return self.store.list()
    def delete(self, name: str) -> bool:
        key = _text(name, "Snippet name", 80).strip().casefold()
        row = next((r for r in self.store.list() if r.get("name") == key), None)
        return self.store.delete(row["id"]) if row else False


# 25. System health dashboard

def system_health(disk_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(disk_path or Path.home())
    usage = shutil.disk_usage(path)
    memory_total = memory_available = None
    # Windows memory metrics without an extra dependency.
    if os.name == "nt":
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            state = MEMORYSTATUSEX(); state.dwLength = ctypes.sizeof(state)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
                memory_total, memory_available = int(state.ullTotalPhys), int(state.ullAvailPhys)
        except Exception:
            pass
    elif Path("/proc/meminfo").exists():
        try:
            info = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, rest = line.split(":", 1); info[key] = int(rest.strip().split()[0]) * 1024
            memory_total = info.get("MemTotal"); memory_available = info.get("MemAvailable")
        except (OSError, ValueError, IndexError):
            pass
    return {"disk_total": usage.total, "disk_used": usage.used, "disk_free": usage.free,
            "disk_percent": round(usage.used / usage.total * 100, 1) if usage.total else 0.0,
            "memory_total": memory_total, "memory_available": memory_available,
            "memory_percent": round((memory_total - memory_available) / memory_total * 100, 1) if memory_total and memory_available is not None else None,
            "platform": os.name}


FEATURE_CATALOG = [
    {"id": "world_clock", "category": "Time & dates", "title": "World clock", "description": "Show current time in any IANA timezone.", "command": "What time is it in Europe/London?", "keywords": "time timezone clock city"},
    {"id": "timezone_convert", "category": "Time & dates", "title": "Timezone converter", "description": "Convert a date and time between timezones.", "command": "Convert 2026-11-13T09:30 from Europe/London to America/New_York", "keywords": "convert timezone time zone"},
    {"id": "date_difference", "category": "Time & dates", "title": "Date difference", "description": "Count the days between two dates.", "command": "How many days between 2026-01-01 and 2026-12-31?", "keywords": "date difference days between"},
    {"id": "date_shift", "category": "Time & dates", "title": "Date calculator", "description": "Add or subtract days, weeks or months.", "command": "Add 30 days to 2026-11-13", "keywords": "add subtract date days weeks months"},
    {"id": "unit_convert", "category": "Calculators", "title": "Unit converter", "description": "Convert length, mass, volume, speed and data units.", "command": "Convert 5 miles to km", "keywords": "convert units miles km kg metres"},
    {"id": "percentage", "category": "Calculators", "title": "Percentage calculator", "description": "Find what percentage one value is of another.", "command": "What percentage is 25 of 200?", "keywords": "percent percentage calculator"},
    {"id": "bill_split", "category": "Calculators", "title": "Bill splitter", "description": "Split an amount between people with an optional tip.", "command": "Split 48.50 between 3 people with 10% tip", "keywords": "split bill tip people"},
    {"id": "text_stats", "category": "Text & data", "title": "Text analyser", "description": "Count words, characters, lines and estimated reading time.", "command": "Analyse text: JARVIS helps me work smarter.", "keywords": "text analyse word count characters"},
    {"id": "case_convert", "category": "Text & data", "title": "Case converter", "description": "Convert text to title, camel, snake, kebab or other case styles.", "command": "Convert to snake case: Hello World Example", "keywords": "text case upper lower title snake camel"},
    {"id": "text_clean", "category": "Text & data", "title": "Text cleaner", "description": "Trim lines and collapse repeated spaces.", "command": "Clean text:   Hello     world  ", "keywords": "clean text whitespace spaces"},
    {"id": "url_encode", "category": "Text & data", "title": "URL encoder", "description": "Percent-encode text for safe URL query strings.", "command": "URL encode: hello world & goodbye", "keywords": "url encode decode percent"},
    {"id": "json_format", "category": "Text & data", "title": "JSON formatter", "description": "Validate and pretty-print JSON.", "command": 'Format JSON: {"name":"JARVIS","ready":true}', "keywords": "json format validate pretty print"},
    {"id": "base64", "category": "Text & data", "title": "Base64 codec", "description": "Encode or decode UTF-8 Base64 text.", "command": "Base64 encode: Hello JARVIS", "keywords": "base64 encode decode"},
    {"id": "hash", "category": "Text & data", "title": "Text hash", "description": "Create SHA-256 or SHA-512 checksums of text.", "command": "SHA256 text: Hello JARVIS", "keywords": "hash sha256 checksum"},
    {"id": "uuid", "category": "Developer tools", "title": "UUID generator", "description": "Generate a random version-4 UUID.", "command": "Generate a UUID", "keywords": "uuid guid identifier"},
    {"id": "password", "category": "Developer tools", "title": "Password generator", "description": "Generate a random password locally using secure randomness.", "command": "Generate a 24 character password", "keywords": "password secure generate random"},
    {"id": "random_choice", "category": "Fun & focus", "title": "Random picker", "description": "Choose one option from a comma-separated list.", "command": "Pick randomly: red, blue, green", "keywords": "random choose pick option"},
    {"id": "dice", "category": "Fun & focus", "title": "Dice roller", "description": "Roll one or more dice.", "command": "Roll 3d6", "keywords": "dice roll d6 random"},
    {"id": "stopwatch", "category": "Fun & focus", "title": "Stopwatch", "description": "Use the workspace stopwatch controls.", "command": "Open the stopwatch", "keywords": "stopwatch lap timer"},
    {"id": "pomodoro", "category": "Fun & focus", "title": "Pomodoro planner", "description": "Plan focused work and break cycles.", "command": "Create a 25 minute Pomodoro plan", "keywords": "pomodoro focus break study"},
    {"id": "tasks", "category": "Productivity", "title": "Task manager", "description": "Save, list, complete and remove local tasks.", "command": "Add task: Finish my project", "keywords": "task todo to-do list complete"},
    {"id": "reminders", "category": "Productivity", "title": "Reminders", "description": "Save scheduled reminders and review due items.", "command": "Add reminder: Review JARVIS at 2026-11-14T18:00:00", "keywords": "reminder remind me schedule"},
    {"id": "bookmarks", "category": "Personal library", "title": "Bookmarks", "description": "Save and search useful websites.", "command": "Save bookmark: Python Docs | https://docs.python.org | python,reference", "keywords": "bookmark save website link"},
    {"id": "snippets", "category": "Personal library", "title": "Text snippets", "description": "Store reusable text and retrieve it by name.", "command": "Save snippet greeting: Hello! How can I help you today?", "keywords": "snippet template reusable text"},
    {"id": "system_health", "category": "System", "title": "System health", "description": "Inspect available disk and memory capacity.", "command": "Show system health", "keywords": "system health memory disk storage status"},
]



def _format_number(value: float) -> str:
    if not math.isfinite(value):
        return str(value)
    return f"{value:,.6f}".rstrip("0").rstrip(".") if value % 1 else f"{int(value):,}"


def _workspace_list(rows: list[dict[str, Any]], empty: str, render) -> str:
    if not rows:
        return empty
    return "\n".join(render(row) for row in rows[-20:])


def dispatch_command(command: str) -> str | None:
    """Handle the workspace's deterministic natural-language commands locally.

    Returns None when the command does not belong to the workspace so the AI
    can handle it. No shell commands or arbitrary file paths are accepted.
    """
    text = _text(command, "Command", 5_000).strip()
    low = text.casefold().strip()
    if not low:
        return None

    m = re.fullmatch(r"(?:what time is it|time) in ([a-z_+-]+(?:/[a-z0-9_+.-]+)+)[.!?]?", text, re.I)
    if m:
        result = world_clock(m.group(1))
        return f"It's {result['display']} ({result['timezone']})."

    m = re.fullmatch(r"convert\s+(\d{4}-\d\d-\d\d[t ]\d\d:\d\d(?::\d\d)?)\s+from\s+([a-z_+-]+(?:/[a-z0-9_+.-]+)+)\s+to\s+([a-z_+-]+(?:/[a-z0-9_+.-]+)+)[.!?]?", text, re.I)
    if m:
        result = convert_timezone(m.group(1).replace(" ", "T"), m.group(2), m.group(3))
        return f"That time in {m.group(3)} is {result}."

    m = re.fullmatch(r"(?:how many days between|date difference between)\s+(\d{4}-\d\d-\d\d)\s+and\s+(\d{4}-\d\d-\d\d)[.!?]?", low)
    if m:
        result = date_difference(m.group(1), m.group(2))
        return f"There are {result['days']} days between those dates ({result['absolute_days']} days apart)."

    m = re.fullmatch(r"(add|subtract)\s+(\d+)\s+(days?|weeks?|months?)\s+(?:to|from)\s+(\d{4}-\d\d-\d\d)[.!?]?", low)
    if m:
        action, amount, unit, value = m.groups()
        signed = int(amount) * (-1 if action == "subtract" else 1)
        args = {"days": 0, "weeks": 0, "months": 0}
        args[unit.rstrip("s") + "s"] = signed
        return f"The resulting date is {shift_date(value, **args)}."

    m = re.fullmatch(r"convert\s+(-?\d+(?:\.\d+)?)\s+([a-z°/]+)\s+to\s+([a-z°/]+)[.!?]?", low)
    if m:
        result = convert_units(float(m.group(1)), m.group(2), m.group(3))
        return f"{m.group(1)} {m.group(2)} = {_format_number(result)} {m.group(3)}."

    m = re.fullmatch(r"(?:what percentage is|what percent is)\s+(-?\d+(?:\.\d+)?)\s+of\s+(-?\d+(?:\.\d+)?)[.!?]?", low)
    if m:
        result = percentage(float(m.group(1)), float(m.group(2)))
        return f"{_format_number(float(m.group(1)))} is {_format_number(result)}% of {_format_number(float(m.group(2)))}."

    m = re.fullmatch(r"split\s+(?:a\s+)?(?:bill\s+of\s+)?£?(-?\d+(?:\.\d+)?)\s+between\s+(\d+)\s+(?:people|persons?)(?:\s+with\s+(\d+(?:\.\d+)?)%?\s+tip)?[.!?]?", low)
    if m:
        result = split_bill(float(m.group(1)), int(m.group(2)), float(m.group(3) or 0))
        return f"Total including tip: {result['total']:.2f}. Each person pays {result['per_person']:.2f}."

    m = re.fullmatch(r"(?:analyse|analyze|analyse text|analyze text|text stats|word count)\s*:\s*(.*)", text, re.I | re.S)
    if m:
        result = text_statistics(m.group(1))
        return (f"Words: {result['words']} · Characters: {result['characters']} · "
                f"Lines: {result['lines']} · Sentences: {result['sentences']} · "
                f"Reading time: {result['reading_minutes']} min.")

    m = re.fullmatch(r"convert to (upper|lower|title|sentence|camel|snake|kebab|pascal) case\s*:\s*(.*)", text, re.I | re.S)
    if m:
        return convert_case(m.group(2), m.group(1))

    m = re.fullmatch(r"clean text\s*:\s*(.*)", text, re.I | re.S)
    if m:
        return clean_text(m.group(1))

    m = re.fullmatch(r"url (encode|decode)\s*:\s*(.*)", text, re.I | re.S)
    if m:
        return (url_encode if m.group(1).lower() == "encode" else url_decode)(m.group(2))

    m = re.fullmatch(r"(?:format|validate) json\s*:\s*(.*)", text, re.I | re.S)
    if m:
        return format_json(m.group(1))

    m = re.fullmatch(r"base64 (encode|decode)\s*:\s*(.*)", text, re.I | re.S)
    if m:
        return (base64_encode if m.group(1).lower() == "encode" else base64_decode)(m.group(2))

    m = re.fullmatch(r"(?:sha256|sha-256|sha512|sha-512)(?:\s+text)?\s*:\s*(.*)|hash text\s*:\s*(.*)", text, re.I | re.S)
    if m:
        payload = m.group(1) if m.group(1) is not None else m.group(2)
        algorithm = re.match(r"sha-?512", low)
        return hash_text(payload, "sha512" if algorithm else "sha256")

    if re.fullmatch(r"(?:generate|make) (?:a )?(?:uuid|guid)[.!]?", low):
        return generate_uuid()

    m = re.fullmatch(r"(?:generate|make) (?:a )?(?:(\d{1,3}) character )?password[.!]?", low)
    if m:
        return generate_password(int(m.group(1) or 20))

    m = re.fullmatch(r"pick randomly\s*:\s*(.+)", text, re.I)
    if m:
        items = [part.strip() for part in m.group(1).split(",") if part.strip()]
        return f"I picked: {random_choice(items)}."

    m = re.fullmatch(r"roll\s+(\d{1,3})?d(\d{1,4})[.!]?", low)
    if m:
        result = roll_dice(int(m.group(1) or 1), int(m.group(2)))
        return f"Rolls: {', '.join(map(str, result['rolls']))}. Total: {result['total']}."

    if low in {"open the stopwatch", "show stopwatch", "stopwatch"}:
        return "Open Workspace and choose Stopwatch to use the interactive stopwatch."

    m = re.fullmatch(r"(?:create|make) a (\d{1,3}) minute pomodoro plan[.!]?", low)
    if m:
        plan = pomodoro_plan(work_minutes=int(m.group(1)))
        summary = ", ".join(f"{row['type'].replace('_', ' ')} {row['minutes']}m" for row in plan)
        return f"Your Pomodoro plan: {summary}."

    m = re.fullmatch(r"add task\s*:\s*(.+)", text, re.I | re.S)
    if m:
        item = TaskManager().add(m.group(1))
        return f"Added task: {item['title']} (ID {item['id'][:8]})."
    if low in {"list my tasks", "show my tasks", "list tasks"}:
        rows = TaskManager().list(include_completed=False)
        return _workspace_list(rows, "You have no open tasks.", lambda r: f"• {r['title']} [{r['priority']}] (ID {r['id'][:8]})")

    m = re.fullmatch(r"complete task\s+([a-f0-9-]{8,36})[.!]?", low)
    if m:
        done = TaskManager().complete(m.group(1))
        return "Task marked complete." if done else "I couldn't find that task ID."

    m = re.fullmatch(r"(?:add reminder\s*:\s*|remind me to\s+)(.+?)\s+at\s+(\d{4}-\d\d-\d\d(?:t\d\d:\d\d(?::\d\d)?(?:z|[+-]\d\d:\d\d)?)?)", text, re.I)
    if m:
        item = ReminderManager().add(m.group(1), m.group(2))
        return f"Reminder saved: {item['title']} at {item['due']}."

    m = re.fullmatch(r"save bookmark\s*:\s*(.+?)\s*\|\s*(https?://\S+)(?:\s*\|\s*(.*))?", text, re.I)
    if m:
        tags = [tag.strip() for tag in (m.group(3) or "").split(",") if tag.strip()]
        item = BookmarkManager().add(m.group(1), m.group(2), tags)
        return f"Bookmark saved: {item['title']}."

    m = re.fullmatch(r"search bookmarks?\s*:\s*(.+)", text, re.I)
    if m:
        rows = BookmarkManager().search(m.group(1))
        return _workspace_list(rows, "No matching bookmarks found.", lambda r: f"• {r['title']} — {r['url']}")

    m = re.fullmatch(r"delete bookmark\s+([a-f0-9-]{8,36})[.!]?", low)
    if m:
        return "Bookmark deleted." if BookmarkManager().delete(m.group(1)) else "I couldn't find that bookmark ID."

    m = re.fullmatch(r"save snippet\s+([^:]{1,80})\s*:\s*(.*)", text, re.I | re.S)
    if m:
        item = SnippetManager().save(m.group(1), m.group(2))
        return f"Snippet '{item['name']}' saved."
    m = re.fullmatch(r"(?:get|show) snippet\s+(.+)", text, re.I)
    if m:
        content = SnippetManager().get(m.group(1))
        return content if content is not None else "I couldn't find that snippet."
    m = re.fullmatch(r"delete snippet\s+(.+)", text, re.I)
    if m:
        return "Snippet deleted." if SnippetManager().delete(m.group(1)) else "I couldn't find that snippet."

    m = re.fullmatch(r"delete task\s+([a-f0-9-]{8,36})[.!]?", low)
    if m:
        return "Task deleted." if TaskManager().delete(m.group(1)) else "I couldn't find that task ID."

    m = re.fullmatch(r"dismiss reminder\s+([a-f0-9-]{8,36})[.!]?", low)
    if m:
        manager = ReminderManager()
        return "Reminder dismissed." if manager.dismiss(m.group(1)) else "I couldn't find that reminder ID."

    if low in {"list my reminders", "show my reminders", "list reminders"}:
        rows = [r for r in ReminderManager().list() if not r.get("dismissed")]
        return _workspace_list(rows, "You have no active reminders.", lambda r: f"• {r['title']} — {r['due']} (ID {r['id'][:8]})")

    if low in {"list my bookmarks", "show my bookmarks", "list bookmarks"}:
        rows = BookmarkManager().search()
        return _workspace_list(rows, "You have no saved bookmarks.", lambda r: f"• {r['title']} — {r['url']}")

    if low in {"list my snippets", "show my snippets", "list snippets"}:
        rows = SnippetManager().list()
        return _workspace_list(rows, "You have no saved snippets.", lambda r: f"• {r['name']}")

    if low in {"show system health", "system health", "check system health"}:
        result = system_health()
        ram = "unavailable" if result["memory_total"] is None else f"{result['memory_percent']}% used"
        return f"Disk: {result['disk_percent']}% used · {result['disk_free'] / (1024**3):.1f} GB free. Memory: {ram}."

    return None


def workspace_action(command: str = "", **kwargs: Any) -> str:
    """Tool-facing wrapper for a specific J.A.R.V.I.S. Workspace command."""
    value = _text(command, "Workspace command", 5_000).strip()
    if not value:
        return "Please describe the Workspace action."
    try:
        result = dispatch_command(value)
    except (ValueError, OSError) as error:
        return f"I couldn't complete that Workspace action: {error}"
    return result if result is not None else "That Workspace command isn't recognised yet. Please use the Workspace to explore available tools."
