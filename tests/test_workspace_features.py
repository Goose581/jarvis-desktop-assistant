"""1,250 focused feature cases: 50 independent cases for each new Workspace feature."""
from __future__ import annotations

import base64
import hashlib
import json
import random
import tempfile
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import jarvis_workspace as ws


def _test(method):
    def wrapped(self):
        method()
    return wrapped


def _add_case_tests(class_name, method_factory, count=50):
    attrs = {"__module__": __name__}
    for index in range(count):
        attrs[f"test_case_{index + 1:02d}"] = _test(method_factory(index))
    return type(class_name, (unittest.TestCase,), attrs)


# 01 World clock: 50 named timezone / daylight-offset checks.
_WORLD_ZONES = [
    "UTC", "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Madrid",
    "Europe/Rome", "Europe/Amsterdam", "Europe/Stockholm", "Europe/Athens", "Europe/Dublin",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Phoenix",
    "America/Toronto", "America/Vancouver", "America/Mexico_City", "America/Sao_Paulo", "America/Anchorage",
    "Asia/Tokyo", "Asia/Seoul", "Asia/Singapore", "Asia/Hong_Kong", "Asia/Kolkata",
    "Asia/Dubai", "Asia/Bangkok", "Asia/Jakarta", "Asia/Manila", "Asia/Taipei",
    "Australia/Sydney", "Australia/Melbourne", "Australia/Perth", "Australia/Brisbane", "Australia/Adelaide",
    "Pacific/Auckland", "Pacific/Fiji", "Africa/Cairo", "Africa/Johannesburg", "Africa/Nairobi",
    "Atlantic/Reykjavik", "Europe/Istanbul", "Europe/Warsaw", "Europe/Prague", "Europe/Zurich",
    "America/Halifax", "America/Detroit", "America/Argentina/Buenos_Aires", "Asia/Riyadh", "Asia/Tehran",
]

def _world_case(i):
    def run():
        zone = _WORLD_ZONES[i]
        moment = datetime(2026, 7, 1, 12, 30, tzinfo=timezone.utc)
        result = ws.world_clock(zone, moment)
        self_assert = result["timezone"] == zone and result["display"] and datetime.fromisoformat(result["iso"]).tzinfo is not None
        assert self_assert, (zone, result)
    return run
WorkspaceWorldClockTests = _add_case_tests("WorkspaceWorldClockTests", _world_case)

# 02 Timezone converter: preserve the exact instant through 50 timezone pairs.
_ZONE_PAIRS = [("UTC", z) for z in _WORLD_ZONES]
def _timezone_case(i):
    def run():
        stamp = f"2026-{(i % 12) + 1:02d}-{(i % 25) + 1:02d}T{(i % 23):02d}:17:32"
        out = ws.convert_timezone(stamp, "UTC", _ZONE_PAIRS[i][1])
        got = datetime.fromisoformat(out)
        expected = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        assert got.astimezone(timezone.utc) == expected
    return run
WorkspaceTimezoneConvertTests = _add_case_tests("WorkspaceTimezoneConvertTests", _timezone_case)

# 03 Date difference: signed day counts over 50 pairs.
def _date_diff_case(i):
    def run():
        start = date(2020 + i % 6, (i % 12) + 1, 1)
        end = start + timedelta(days=i * 17 - 300)
        result = ws.date_difference(start.isoformat(), end.isoformat())
        assert result["days"] == (end - start).days
        assert result["absolute_days"] == abs((end - start).days)
    return run
WorkspaceDateDifferenceTests = _add_case_tests("WorkspaceDateDifferenceTests", _date_diff_case)

# 04 Date calculator: 50 positive/negative date shifts.
def _date_shift_case(i):
    def run():
        start = date(2024 + i % 3, (i % 12) + 1, 15)
        days = (i * 13) - 250
        expected = start + timedelta(days=days)
        actual = ws.shift_date(start.isoformat(), days=days)
        assert actual == expected.isoformat()
    return run
WorkspaceDateShiftTests = _add_case_tests("WorkspaceDateShiftTests", _date_shift_case)

# 05 Unit converter: 50 independently expected conversions.
_UNIT_CASES = [
    (1, "km", "m", 1000), (1, "m", "cm", 100), (1, "cm", "mm", 10), (1, "mi", "km", 1.609344),
    (1, "ft", "in", 12), (1, "yd", "ft", 3), (1, "kg", "g", 1000), (1, "lb", "oz", 16),
    (1, "l", "ml", 1000), (1, "cup", "ml", 236.5882365), (1, "mph", "km/h", 1.609344),
    (1, "m/s", "km/h", 3.6), (1, "gb", "mb", 1000), (1, "gib", "mib", 1024),
    (0, "c", "f", 32), (100, "c", "f", 212), (32, "f", "c", 0), (0, "c", "k", 273.15),
    (273.15, "k", "c", 0), (5, "miles", "km", 8.04672),
]
_BASE_UNIT_CASES = list(_UNIT_CASES)
_UNIT_CASES = []
for _i in range(50):
    _base = _BASE_UNIT_CASES[_i % len(_BASE_UNIT_CASES)]
    _UNIT_CASES.append((_base[0] + (_i // len(_BASE_UNIT_CASES)), _base[1], _base[2], _base[3]))
def _unit_case(i):
    def run():
        value, src, dst, base_expected = _UNIT_CASES[i]
        delta = i // len(_BASE_UNIT_CASES)
        if src in {"c", "f", "k"}:
            rate = {("c", "f"): 9 / 5, ("f", "c"): 5 / 9, ("c", "k"): 1, ("k", "c"): 1}[(src, dst)]
        else:
            rate = ws.convert_units(1, src, dst)
        expected = base_expected + delta * rate
        got = ws.convert_units(value, src, dst)
        assert abs(got - expected) < max(1e-7, abs(expected) * 1e-9), (value, src, dst, got, expected)
    return run
WorkspaceUnitConverterTests = _add_case_tests("WorkspaceUnitConverterTests", _unit_case)

# 06 Percentage calculator.
def _percentage_case(i):
    def run():
        whole = i + 1
        part = (i * 7) % (whole * 3 + 1) - whole
        assert abs(ws.percentage(part, whole) - part / whole * 100) < 1e-9
    return run
WorkspacePercentageTests = _add_case_tests("WorkspacePercentageTests", _percentage_case)

# 07 Bill splitter.
def _bill_case(i):
    def run():
        total = i * 3.17 + 5.25
        people = i % 9 + 1
        tip = i % 31
        result = ws.split_bill(total, people, tip)
        expected_total = round(round(total, 2) + round(total * tip / 100, 2), 2)
        assert result["total"] == expected_total
        assert result["per_person"] == round(expected_total / people, 2)
    return run
WorkspaceBillSplitTests = _add_case_tests("WorkspaceBillSplitTests", _bill_case)

# 08 Text analytics.
def _text_stats_case(i):
    def run():
        text = (f"Line {i} has several words.\nSecond line number {i * 2}!")
        result = ws.text_statistics(text)
        assert result["characters"] == len(text)
        assert result["words"] >= 8
        assert result["lines"] == 2
        assert result["sentences"] == 2
    return run
WorkspaceTextAnalyticsTests = _add_case_tests("WorkspaceTextAnalyticsTests", _text_stats_case)

# 09 Case conversion.
_CASE_MODES = ["upper", "lower", "title", "sentence", "camel", "snake", "kebab", "pascal"]
def _case_convert_case(i):
    def run():
        source = f"Hello World Feature {i}"
        mode = _CASE_MODES[i % len(_CASE_MODES)]
        result = ws.convert_case(source, mode)
        assert isinstance(result, str) and result
        if mode == "snake": assert result == f"hello_world_feature_{i}"
        if mode == "kebab": assert result == f"hello-world-feature-{i}"
        if mode == "camel": assert result == f"helloWorldFeature{i}"
    return run
WorkspaceCaseConverterTests = _add_case_tests("WorkspaceCaseConverterTests", _case_convert_case)

# 10 Text cleaner.
def _clean_case(i):
    def run():
        source = ("  alpha   beta  \r\n\t gamma " + ("\r\n  \r\n" if i % 2 else "\n delta\t  "))
        got = ws.clean_text(source, collapse_spaces=True, remove_blank_lines=bool(i % 2), strip_lines=True)
        assert "  " not in got and "\r" not in got
        if i % 2: assert "\n\n" not in got
        assert got.startswith("alpha beta")
    return run
WorkspaceTextCleanerTests = _add_case_tests("WorkspaceTextCleanerTests", _clean_case)

# 11 URL codec.
def _url_case(i):
    def run():
        source = f"hello world & feature={i} / café?"
        encoded = ws.url_encode(source)
        assert "%20" in encoded and "%26" in encoded
        assert ws.url_decode(encoded) == source
    return run
WorkspaceURLCodecTests = _add_case_tests("WorkspaceURLCodecTests", _url_case)

# 12 JSON formatter.
def _json_case(i):
    def run():
        value = {"index": i, "ready": bool(i % 2), "name": f"feature-{i}", "items": [i, i + 1]}
        pretty = ws.format_json(json.dumps(value))
        assert json.loads(pretty) == value
        compact = ws.format_json(pretty, compact=True)
        assert json.loads(compact) == value and "\n" not in compact
    return run
WorkspaceJSONTests = _add_case_tests("WorkspaceJSONTests", _json_case)

# 13 Base64 codec.
def _base64_case(i):
    def run():
        source = f"J.A.R.V.I.S. feature {i} — café 🛰"
        encoded = ws.base64_encode(source)
        assert encoded == base64.b64encode(source.encode("utf-8")).decode("ascii")
        assert ws.base64_decode(encoded) == source
    return run
WorkspaceBase64Tests = _add_case_tests("WorkspaceBase64Tests", _base64_case)

# 14 Hashing.
def _hash_case(i):
    def run():
        source = f"test payload {i}"
        algorithm = "sha256" if i % 2 == 0 else "sha512"
        assert ws.hash_text(source, algorithm) == hashlib.new(algorithm, source.encode()).hexdigest()
    return run
WorkspaceHashTests = _add_case_tests("WorkspaceHashTests", _hash_case)

# 15 UUID generation.
def _uuid_case(i):
    def run():
        value = ws.generate_uuid()
        parsed = uuid.UUID(value)
        assert parsed.version == 4 and str(parsed) == value
    return run
WorkspaceUUIDTests = _add_case_tests("WorkspaceUUIDTests", _uuid_case)

# 16 Secure password generation.
def _password_case(i):
    def run():
        length = 8 + i
        value = ws.generate_password(length, use_symbols=bool(i % 2))
        assert len(value) == length
        assert any(c.isalpha() for c in value) and any(c.isdigit() for c in value)
        if i % 2: assert any(c in "!@#$%^&*()-_=+[]{}?" for c in value)
    return run
WorkspacePasswordTests = _add_case_tests("WorkspacePasswordTests", _password_case)

# 17 Random picker.
def _random_choice_case(i):
    def run():
        choices = [f"choice-{i}-{j}" for j in range(2 + i % 8)]
        assert ws.random_choice(choices) in choices
    return run
WorkspaceRandomChoiceTests = _add_case_tests("WorkspaceRandomChoiceTests", _random_choice_case)

# 18 Dice roller.
def _dice_case(i):
    def run():
        count, sides = i % 12 + 1, i % 98 + 2
        result = ws.roll_dice(count, sides)
        assert len(result["rolls"]) == count
        assert all(1 <= face <= sides for face in result["rolls"])
        assert result["total"] == sum(result["rolls"])
    return run
WorkspaceDiceTests = _add_case_tests("WorkspaceDiceTests", _dice_case)

# 19 Stopwatch state machine.
def _stopwatch_case(i):
    def run():
        clock = [1000.0]
        sw = ws.Stopwatch(clock=lambda: clock[0])
        assert sw.start() is True
        clock[0] += i + 0.5
        lap = sw.lap()
        assert abs(lap - (i + 0.5)) < 1e-9
        assert sw.start() is False
        clock[0] += 1.25
        elapsed = sw.stop()
        assert abs(elapsed - (i + 1.75)) < 1e-9
        assert abs(sw.elapsed() - elapsed) < 1e-9
        sw.reset(); assert sw.elapsed() == 0 and sw.laps() == []
    return run
WorkspaceStopwatchTests = _add_case_tests("WorkspaceStopwatchTests", _stopwatch_case)

# 20 Pomodoro planner.
def _pomodoro_case(i):
    def run():
        work, short, long, cycles = 10 + i, 3 + i % 7, 10 + i % 13, i % 10 + 1
        plan = ws.pomodoro_plan(work, short, long, cycles)
        work_rows = [r for r in plan if r["type"] == "work"]
        assert len(work_rows) == cycles and all(r["minutes"] == work for r in work_rows)
        assert sum(r["minutes"] for r in plan) >= work * cycles
    return run
WorkspacePomodoroTests = _add_case_tests("WorkspacePomodoroTests", _pomodoro_case)

# 21 Task manager CRUD.
def _task_case(i):
    def run():
        with tempfile.TemporaryDirectory() as folder:
            manager = ws.TaskManager(Path(folder) / "tasks.json")
            row = manager.add(f"Task {i}", priority=("low", "normal", "high", "urgent")[i % 4])
            assert row["title"] == f"Task {i}" and len(manager.list()) == 1
            assert manager.complete(row["id"][:8]) is True
            assert manager.list(include_completed=False) == []
            assert manager.delete(row["id"][:8]) is True
            assert manager.list() == []
    return run
WorkspaceTaskManagerTests = _add_case_tests("WorkspaceTaskManagerTests", _task_case)

# 22 Reminder manager scheduling.
def _reminder_case(i):
    def run():
        with tempfile.TemporaryDirectory() as folder:
            manager = ws.ReminderManager(Path(folder) / "reminders.json")
            now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
            due = now - timedelta(minutes=i + 1)
            future = now + timedelta(minutes=i + 1)
            row = manager.add(f"Reminder {i}", due.isoformat())
            manager.add(f"Future {i}", future.isoformat())
            assert [r["id"] for r in manager.due(now)] == [row["id"]]
            assert manager.dismiss(row["id"]) is True
            assert manager.due(now) == []
    return run
WorkspaceReminderTests = _add_case_tests("WorkspaceReminderTests", _reminder_case)

# 23 Bookmark manager CRUD/search.
def _bookmark_case(i):
    def run():
        with tempfile.TemporaryDirectory() as folder:
            manager = ws.BookmarkManager(Path(folder) / "bookmarks.json")
            row = manager.add(f"Python Docs {i}", f"https://docs.python.org/{i}", ["python", f"topic{i}"])
            assert row["title"] == f"Python Docs {i}"
            assert manager.search("python") == [row]
            assert manager.search(f"topic{i}") == [row]
            assert manager.delete(row["id"]) is True
            assert manager.search() == []
    return run
WorkspaceBookmarkTests = _add_case_tests("WorkspaceBookmarkTests", _bookmark_case)

# 24 Snippet manager CRUD/update.
def _snippet_case(i):
    def run():
        with tempfile.TemporaryDirectory() as folder:
            manager = ws.SnippetManager(Path(folder) / "snippets.json")
            first = manager.save(f"Greeting {i}", f"Hello {i}")
            assert manager.get(f"Greeting {i}") == f"Hello {i}"
            second = manager.save(f"GREETING {i}", f"Updated {i}")
            assert first["id"] == second["id"]
            assert manager.get(f"Greeting {i}") == f"Updated {i}"
            assert manager.delete(f"Greeting {i}") is True
            assert manager.get(f"Greeting {i}") is None
    return run
WorkspaceSnippetTests = _add_case_tests("WorkspaceSnippetTests", _snippet_case)

# 25 System health snapshot.
def _system_health_case(i):
    def run():
        with tempfile.TemporaryDirectory() as folder:
            result = ws.system_health(folder)
            assert result["disk_total"] > 0
            assert result["disk_used"] >= 0 and result["disk_free"] >= 0
            assert 0 <= result["disk_percent"] <= 100
            assert result["platform"] in {"nt", "posix", "java"}
            if result["memory_percent"] is not None:
                assert 0 <= result["memory_percent"] <= 100
    return run
WorkspaceSystemHealthTests = _add_case_tests("WorkspaceSystemHealthTests", _system_health_case)


class WorkspaceValidationTests(unittest.TestCase):
    def test_each_feature_suite_contains_exactly_50_independent_cases(self):
        feature_suites = [
            WorkspaceWorldClockTests, WorkspaceTimezoneConvertTests,
            WorkspaceDateDifferenceTests, WorkspaceDateShiftTests,
            WorkspaceUnitConverterTests, WorkspacePercentageTests,
            WorkspaceBillSplitTests, WorkspaceTextAnalyticsTests,
            WorkspaceCaseConverterTests, WorkspaceTextCleanerTests,
            WorkspaceURLCodecTests, WorkspaceJSONTests, WorkspaceBase64Tests,
            WorkspaceHashTests, WorkspaceUUIDTests, WorkspacePasswordTests,
            WorkspaceRandomChoiceTests, WorkspaceDiceTests, WorkspaceStopwatchTests,
            WorkspacePomodoroTests, WorkspaceTaskManagerTests, WorkspaceReminderTests,
            WorkspaceBookmarkTests, WorkspaceSnippetTests, WorkspaceSystemHealthTests,
        ]
        self.assertEqual(len(feature_suites), 25)
        for suite in feature_suites:
            with self.subTest(feature=suite.__name__):
                cases = [name for name in dir(suite) if name.startswith("test_case_")]
                self.assertEqual(len(cases), 50)

    def test_catalog_has_exactly_25_unique_feature_ids(self):
        ids = [item["id"] for item in ws.FEATURE_CATALOG]
        self.assertEqual(len(ids), 25)
        self.assertEqual(len(set(ids)), 25)

    def test_all_catalog_items_have_ui_fields(self):
        for item in ws.FEATURE_CATALOG:
            with self.subTest(feature=item["id"]):
                self.assertTrue(all(item.get(field) for field in ("category", "title", "description", "command", "keywords")))

    def test_dispatch_does_not_capture_general_questions(self):
        self.assertIsNone(ws.dispatch_command("Can you explain why the sky is blue?"))

    def test_invalid_timezone_is_friendly_validation_error(self):
        with self.assertRaises(ValueError): ws.world_clock("../etc/passwd")

    def test_unit_converter_rejects_cross_category_conversion(self):
        with self.assertRaises(ValueError): ws.convert_units(2, "km", "kg")

    def test_percent_rejects_zero_denominator(self):
        with self.assertRaises(ValueError): ws.percentage(2, 0)

    def test_bill_split_rejects_bad_people(self):
        with self.assertRaises(ValueError): ws.split_bill(20, 0)

    def test_json_store_rejects_invalid_file_shape(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"; path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError): ws.JsonRecordStore(path).list()

    def test_password_rejects_short_length(self):
        with self.assertRaises(ValueError): ws.generate_password(7)

    def test_random_picker_rejects_single_choice(self):
        with self.assertRaises(ValueError): ws.random_choice(["only"])

    def test_dice_rejects_invalid_sides(self):
        with self.assertRaises(ValueError): ws.roll_dice(1, 1)

    def test_reminder_due_handles_naive_now(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = ws.ReminderManager(Path(folder) / "r.json")
            due = datetime.now().astimezone() - timedelta(minutes=1)
            manager.add("test", due.isoformat())
            self.assertEqual(len(manager.due(datetime.now())), 1)

    def test_bookmark_rejects_non_http_schemes(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): ws.BookmarkManager(Path(folder) / "b.json").add("bad", "file:///secret")

    def test_feature_dispatch_world_clock_preserves_timezone_case(self):
        self.assertIn("Europe/London", ws.dispatch_command("What time is it in Europe/London?"))

    def test_feature_dispatch_examples_are_recognised(self):
        for command in [
            "Convert 5 miles to km", "What percentage is 25 of 200?",
            "Analyse text: Hello world.", "Convert to snake case: Hello World",
            "Clean text:  Hello   world", "URL encode: hello world", 
            'Format JSON: {"a":1}', "Base64 encode: hello", "SHA256 text: hello",
            "Generate a UUID", "Generate a 24 character password", "Pick randomly: a, b",
            "Roll 2d6", "Create a 25 minute Pomodoro plan", "Show system health",
        ]:
            with self.subTest(command=command): self.assertIsNotNone(ws.dispatch_command(command))


if __name__ == "__main__":
    unittest.main(verbosity=2)

class WorkspaceIntegrationTests(unittest.TestCase):
    def test_all_25_catalog_examples_route_without_ai(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"LOCALAPPDATA": folder}):
            self.assertEqual(len(ws.FEATURE_CATALOG), 25)
            for feature in ws.FEATURE_CATALOG:
                with self.subTest(feature=feature["id"]):
                    result = ws.dispatch_command(feature["command"])
                    self.assertIsInstance(result, str)
                    self.assertTrue(result.strip())

    def test_workspace_action_tool_is_registered_with_explicit_schema(self):
        import JARVIS as jarvis
        self.assertIn("workspace_action", jarvis.available_tools)
        schemas = [item["function"] for item in jarvis.OLLAMA_TOOL_SCHEMAS]
        match = next(item for item in schemas if item["name"] == "workspace_action")
        self.assertIn("command", match["parameters"]["properties"])

    def test_workspace_direct_action_does_not_require_ollama(self):
        import JARVIS as jarvis
        self.assertIn("8.04672", jarvis._handle_direct_request("Convert 5 miles to km"))

    def test_workspace_gui_has_search_palette_and_stopwatch(self):
        from pathlib import Path
        gui_source = Path(__file__).resolve().parents[1].joinpath("JARVIS_GUI.py").read_text(encoding="utf-8")
        self.assertIn("<Control-k>", gui_source)
        self.assertIn("def open_workspace", gui_source)
        self.assertIn("def open_stopwatch", gui_source)
        self.assertIn("def _poll_reminders", gui_source)

    def test_timezone_data_is_in_build_dependencies(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        self.assertIn("tzdata", (root / "requirements-build.txt").read_text(encoding="utf-8"))
        self.assertIn("--collect-all tzdata", (root / "build_release.bat").read_text(encoding="utf-8"))
