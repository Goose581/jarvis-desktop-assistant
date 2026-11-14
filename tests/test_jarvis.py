from __future__ import annotations

import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import JARVIS as jarvis
import launcher


class TimerSoundTests(unittest.TestCase):
    def test_timer_sound_enabled_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=missing):
                self.assertTrue(jarvis.load_settings()["timer_sound_enabled"])

    def test_timer_sound_preference_persists(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=path):
                jarvis.save_settings(timer_sound_enabled=False)
                self.assertFalse(jarvis.load_settings()["timer_sound_enabled"])
                jarvis.save_settings(timer_sound_enabled=True)
                self.assertTrue(jarvis.load_settings()["timer_sound_enabled"])

    def test_timer_sound_setting_rejects_non_boolean_values(self):
        with self.assertRaises(ValueError):
            jarvis.save_settings(timer_sound_enabled="yes")
        with self.assertRaises(ValueError):
            jarvis.set_timer_sound_enabled(1, persist=False)

    def test_timer_sound_can_be_disabled_without_playing(self):
        original = jarvis.timer_sound_enabled
        try:
            jarvis.set_timer_sound_enabled(False, persist=False)
            self.assertFalse(jarvis.play_timer_sound())
        finally:
            jarvis.set_timer_sound_enabled(original, persist=False)

    def test_resource_path_uses_pyinstaller_bundle_root_when_frozen(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(jarvis.sys, "_MEIPASS", temporary, create=True):
                self.assertEqual(
                    jarvis.resource_path(jarvis.TIMER_SOUND_RELATIVE_PATH),
                    Path(temporary) / jarvis.TIMER_SOUND_RELATIVE_PATH,
                )

    def test_custom_timer_wav_is_exactly_ten_seconds(self):
        import wave
        sound_path = jarvis.resource_path(jarvis.TIMER_SOUND_RELATIVE_PATH)
        self.assertTrue(sound_path.is_file())
        with wave.open(str(sound_path), "rb") as sound:
            duration = sound.getnframes() / sound.getframerate()
            self.assertEqual(sound.getnchannels(), 1)
            self.assertEqual(sound.getsampwidth(), 2)
            self.assertAlmostEqual(duration, 10.0, places=6)

    def test_timer_sound_uses_bundled_custom_wav_async(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        fake_play = Mock(return_value=None)
        fake = SimpleNamespace(
            SND_FILENAME=0x00020000,
            SND_ASYNC=0x0001,
            SND_NODEFAULT=0x0002,
            PlaySound=fake_play,
        )
        with patch.dict("sys.modules", {"winsound": fake}), \
             patch.object(jarvis, "timer_sound_enabled", True):
            self.assertTrue(jarvis.play_timer_sound())
        path, flags = fake_play.call_args.args
        self.assertTrue(path.endswith("jarvis_timer_alarm.wav"))
        self.assertEqual(flags, 0x00020000 | 0x0001 | 0x0002)
        self.assertFalse(hasattr(fake, "MessageBeep"))

    def test_forced_test_sound_bypasses_disabled_preference(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        fake_play = Mock(return_value=None)
        fake = SimpleNamespace(SND_FILENAME=2, SND_ASYNC=1, SND_NODEFAULT=4, PlaySound=fake_play)
        with patch.dict("sys.modules", {"winsound": fake}), \
             patch.object(jarvis, "timer_sound_enabled", False):
            self.assertTrue(jarvis.play_timer_sound(force=True))
        fake_play.assert_called_once()

    def test_stop_timer_sound_stops_custom_audio(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        fake_play = Mock(return_value=None)
        fake = SimpleNamespace(PlaySound=fake_play)
        with patch.dict("sys.modules", {"winsound": fake}):
            self.assertTrue(jarvis.stop_timer_sound())
        fake_play.assert_called_once_with(None, 0)

    def test_timer_sound_disabled_does_not_import_or_play_audio(self):
        with patch.object(jarvis, "timer_sound_enabled", False), \
             patch.dict("sys.modules", {"winsound": None}):
            self.assertFalse(jarvis.play_timer_sound())

    def test_timer_sound_failure_is_logged_without_system_sound_fallback(self):
        from types import SimpleNamespace
        fake = SimpleNamespace(
            SND_FILENAME=2, SND_ASYNC=1, SND_NODEFAULT=4,
            PlaySound=lambda *_args: (_ for _ in ()).throw(OSError("audio unavailable")),
        )
        with patch.dict("sys.modules", {"winsound": fake}), \
             patch.object(jarvis, "timer_sound_enabled", True), \
             patch.object(jarvis, "log_error") as log_error:
            self.assertFalse(jarvis.play_timer_sound())
            log_error.assert_called_once()

    def test_timer_uses_monotonic_deadline_to_avoid_setup_delay(self):
        captured = {}
        class RecordingTimer:
            def __init__(self, interval, function):
                captured["interval"] = interval
                self.daemon = False
            def start(self):
                return None
            def cancel(self):
                return None
        with patch.object(jarvis.threading, "Timer", RecordingTimer), \
             patch.object(jarvis.time, "monotonic", side_effect=[100.0, 100.35]), \
             patch.object(jarvis, "_active_timers", set()):
            jarvis.set_timer(2.0)
        self.assertAlmostEqual(captured["interval"], 1.65, places=3)

    def test_timer_completion_alarm_starts_before_voice_announcement(self):
        order = []
        class ImmediateTimer:
            def __init__(self, interval, function):
                self.interval = interval
                self.function = function
                self.daemon = False
            def start(self):
                self.function()
            def cancel(self):
                return None
        with patch.object(jarvis.threading, "Timer", ImmediateTimer), \
             patch.object(jarvis, "play_timer_sound", side_effect=lambda: order.append("sound") or True), \
             patch.object(jarvis, "speak", side_effect=lambda _message: order.append("voice")), \
             patch.object(jarvis, "_active_timers", set()):
            result = jarvis.set_timer(0.25, "test")
        self.assertIn("test", result.lower())
        self.assertEqual(order, ["sound", "voice"])

    def test_timer_announcement_is_scheduled_after_full_ten_second_alarm(self):
        created = []
        class ControlledTimer:
            def __init__(self, interval, function):
                self.interval = interval
                self.function = function
                self.daemon = False
                created.append(self)
            def start(self):
                if len(created) == 1:
                    self.function()  # fire the countdown; retain delayed announcement
            def cancel(self):
                return None
        active = set()
        with patch.object(jarvis.threading, "Timer", ControlledTimer), \
             patch.object(jarvis, "play_timer_sound", return_value=True), \
             patch.object(jarvis, "speak") as speak, \
             patch.object(jarvis, "_active_timers", active):
            jarvis.set_timer(1.0)
            self.assertEqual(len(created), 2)
            self.assertAlmostEqual(created[1].interval, 10.0)
            speak.assert_not_called()
            self.assertEqual(len(active), 0)
            created[1].function()
            speak.assert_called_once_with("Your Timer has finished.")

    def test_cancelled_timer_does_not_play_sound_or_speak(self):
        class RecordingTimer:
            def __init__(self, interval, function):
                self.function = function
                self.cancelled = False
                self.daemon = False
            def start(self):
                return None
            def cancel(self):
                self.cancelled = True
        active = set()
        with patch.object(jarvis.threading, "Timer", RecordingTimer), \
             patch.object(jarvis, "_active_timers", active), \
             patch.object(jarvis, "play_timer_sound") as sound, \
             patch.object(jarvis, "speak") as speak:
            jarvis.set_timer(20)
            self.assertEqual(len(active), 1)
            jarvis.cancel_timers()
        sound.assert_not_called()
        speak.assert_not_called()

    def test_sound_disabled_still_announces_timer_completion_immediately(self):
        class ImmediateTimer:
            def __init__(self, interval, function):
                self.function = function
                self.daemon = False
            def start(self):
                self.function()
            def cancel(self):
                return None
        with patch.object(jarvis.threading, "Timer", ImmediateTimer), \
             patch.object(jarvis, "timer_sound_enabled", False), \
             patch.object(jarvis, "play_timer_sound", return_value=False), \
             patch.object(jarvis, "speak") as speak, \
             patch.object(jarvis, "_active_timers", set()):
            jarvis.set_timer(0.1)
        speak.assert_called_once()

    def test_short_timer_keeps_fractional_deadline(self):
        captured = {}
        class RecordingTimer:
            def __init__(self, interval, function):
                captured["interval"] = interval
                self.function = function
                self.daemon = False
            def start(self):
                return None
            def cancel(self):
                return None
        active = set()
        with patch.object(jarvis.threading, "Timer", RecordingTimer), \
             patch.object(jarvis, "_active_timers", active):
            self.assertIn("1 second", jarvis.set_timer(0.25))
            self.assertGreater(captured["interval"], 0)
            self.assertLessEqual(captured["interval"], 0.25)
        for timer in list(active):
            timer.cancel()


class CalculatorTests(unittest.TestCase):
    def test_bidmas_precedence(self):
        cases = {
            "12 + 2 * 3": "The result is 18.",
            "(12 + 2) * 3": "The result is 42.",
            "2 + 3 * 4": "The result is 14.",
            "20 / 5 * 2": "The result is 8.",
            "10 - 3 - 2": "The result is 5.",
            "2 ** 3 + 4": "The result is 12.",
            "2(3 + 4)": "The result is 14.",
            "2 * (3 + 4)": "The result is 14.",
            "sqrt(9 + 16)": "The result is 5.",
            "(2 + 3)(4 + 5)": "The result is 45.",
            "-3 + 5": "The result is 2.",
            "sqrt(81)": "The result is 9.",
            "round(2.345, 2)": "The result is 2.35.",
            "abs(-7)": "The result is 7.",
            "pi * 2": "The result is 6.28318530718.",
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(jarvis.calculate(expression), expected)

    def test_250_generated_bidmas_cases(self):
        """Exercise 250 mixed-operation expressions, not just hand-picked examples."""
        checked = 0
        for index in range(1, 251):
            a = index % 11 + 1
            b = index % 7 + 2
            c = index % 5 + 2
            d = index % 9 + 1
            e = index % 4 + 1
            expression = f"({a} + {b}) * {c} - {d} / {e}"
            expected = (a + b) * c - d / e
            expected_text = f"{expected:.12g}"
            actual = jarvis.calculate(expression)
            self.assertEqual(actual, f"The result is {expected_text}.", msg=expression)
            checked += 1
        self.assertEqual(checked, 250)

    def test_zero_division_is_friendly(self):
        self.assertEqual(jarvis.calculate("5 / 0"), "You can't divide by zero.")

    def test_unsafe_python_is_rejected(self):
        result = jarvis.calculate("__import__('os').system('whoami')")
        self.assertIn("couldn't calculate", result)

    def test_math_extraction(self):
        cases = {
            "12+2": "12+2",
            "What is 12 plus 2?": "12 + 2",
            "Calculate 2 to the power of 3": "2 ** 3",
            "What is 2 squared plus 3?": "2 **2 + 3",
            "What is 20% of 50?": "(20/100)*50",
            "What is 20 percent of 50?": "(20/100)*50",
            "What is 10 divided by 2 times 3?": "10 / 2 * 3",
            "Square root of 81": "sqrt(81)",
            "Square root of (9 + 16)": "sqrt(9 + 16)",
            "What is 2 x (3 + 4)?": "2*(3 + 4)",
        }
        for request, expected in cases.items():
            with self.subTest(request=request):
                self.assertEqual(jarvis.extract_math_expression(request), expected)

    def test_math_extractor_does_not_capture_general_questions(self):
        self.assertIsNone(jarvis.extract_math_expression("How many people live in London?"))
        self.assertIsNone(jarvis.extract_math_expression("Can you explain BIDMAS?"))

    def test_extracted_math_gives_correct_answers(self):
        for request, answer in (
            ("12+2", "The result is 14."),
            ("What is 12 plus 2 times 3?", "The result is 18."),
            ("What is 20 percent of 50?", "The result is 10."),
            ("What is the square root of 81?", "The result is 9."),
            ("What is the square root of (9 + 16)?", "The result is 5."),
        ):
            expression = jarvis.extract_math_expression(request)
            self.assertIsNotNone(expression)
            self.assertEqual(jarvis.calculate(expression or ""), answer)


class RoutingTests(unittest.TestCase):
    def test_search_parser(self):
        self.assertEqual(jarvis.extract_search_query("Search the web for Python tutorials"), "Python tutorials")
        self.assertEqual(jarvis.extract_search_query("Can you please search for Python docs"), "Python docs")
        self.assertEqual(jarvis.extract_search_query('Search for "weather tomorrow"'), "weather tomorrow")
        self.assertEqual(jarvis.extract_search_query("Google pandas dataframe"), "pandas dataframe")
        self.assertIsNone(jarvis.extract_search_query("I searched my files earlier"))

    def test_search_tool_ignores_metadata_and_uses_query(self):
        # Force the fallback branch so this test behaves identically on Windows
        # machines with Edge installed and on machines without Edge.
        with patch("JARVIS.find_edge_executable", return_value=None), patch("JARVIS.webbrowser.open") as open_browser:
            result = jarvis.search_edge(function="function", query="best Python tutorials")
        self.assertIn("best Python tutorials", result)
        open_browser.assert_called_once()
        self.assertIn("best+Python+tutorials", open_browser.call_args.args[0])
        self.assertNotIn("function", open_browser.call_args.args[0])

    def test_search_tool_can_search_the_word_function(self):
        with patch("JARVIS.find_edge_executable", return_value=None), patch("JARVIS.webbrowser.open") as open_browser:
            jarvis.search_edge(query="function")
        open_browser.assert_called_once()
        self.assertIn("q=function", open_browser.call_args.args[0])

    def test_search_tool_accepts_wrapped_arguments(self):
        with patch("JARVIS.find_edge_executable", return_value=None), patch("JARVIS.webbrowser.open") as open_browser:
            result = jarvis.search_edge(query={"function": "function", "arguments": {"search_query": "space news"}})
        self.assertIn("space news", result)
        open_browser.assert_called_once()
        self.assertIn("space+news", open_browser.call_args.args[0])

    def test_search_tool_uses_installed_edge(self):
        edge = Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
        with patch("JARVIS.find_edge_executable", return_value=edge), patch("JARVIS.subprocess.Popen") as launch_edge, patch("JARVIS.webbrowser.open") as open_browser:
            result = jarvis.search_edge(query="latest Python release")
        self.assertIn("Microsoft Edge", result)
        launch_edge.assert_called_once()
        self.assertEqual(launch_edge.call_args.args[0][0], str(edge))
        self.assertIn("latest+Python+release", launch_edge.call_args.args[0][1])
        open_browser.assert_not_called()

    def test_search_tool_falls_back_if_edge_launch_fails(self):
        edge = Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
        with patch("JARVIS.find_edge_executable", return_value=edge), patch("JARVIS.subprocess.Popen", side_effect=OSError("Edge launch failed")), patch("JARVIS.webbrowser.open") as open_browser:
            result = jarvis.search_edge(query="fallback browser test")
        self.assertIn("Searching the web", result)
        open_browser.assert_called_once()
        self.assertIn("fallback+browser+test", open_browser.call_args.args[0])

    def test_edge_installed_does_not_call_default_browser(self):
        edge = Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
        with patch("JARVIS.find_edge_executable", return_value=edge), patch("JARVIS.subprocess.Popen") as launch_edge, patch("JARVIS.webbrowser.open") as open_browser:
            result = jarvis.search_edge(query="windows regression test")
        launch_edge.assert_called_once()
        open_browser.assert_not_called()
        self.assertIn("Microsoft Edge", result)

    def test_search_fallback_handles_browser_exception(self):
        with patch("JARVIS.find_edge_executable", return_value=None), patch("JARVIS.webbrowser.open", side_effect=OSError("no browser")):
            result = jarvis.search_edge(query="browser exception test")
        self.assertIn("couldn't open the browser", result)

    def test_edge_resolver_returns_none_when_not_installed(self):
        with patch("JARVIS.Path.is_file", return_value=False), patch.dict("os.environ", {"LOCALAPPDATA": ""}):
            self.assertIsNone(jarvis.find_edge_executable())

    def test_open_close_and_url_parsers(self):
        self.assertEqual(jarvis.extract_open_target("Open Notepad"), "Notepad")
        self.assertEqual(jarvis.extract_close_target("Close Chrome"), "Chrome")
        self.assertEqual(jarvis.extract_open_url("Open website example.com"), "https://example.com")
        self.assertIsNone(jarvis.extract_open_target("How do I open Notepad?"))

    def test_open_app_reports_browser_failure(self):
        with patch("JARVIS.webbrowser.open", return_value=False):
            self.assertIn("couldn't open Discord", jarvis.open_app("Discord"))

    def test_open_google_docs_reports_browser_failure(self):
        with patch("JARVIS.webbrowser.open", return_value=False):
            self.assertIn("couldn't open Google Docs", jarvis.open_app("Google Docs"))

    def test_open_app_handles_browser_exception(self):
        with patch("JARVIS.webbrowser.open", side_effect=OSError("no browser")):
            self.assertIn("couldn't open", jarvis.open_app("Discord"))

    def test_url_tool_rejects_non_http_schemes(self):
        self.assertIn("valid http or https", jarvis.open_url("javascript:alert(1)"))

    def test_url_tool_rejects_missing_hostname(self):
        self.assertIn("valid http or https", jarvis.open_url("https://"))

    def test_url_tool_rejects_overlong_urls(self):
        self.assertIn("valid http or https", jarvis.open_url("https://example.com/" + "x" * 2050))

    def test_url_tool_reports_when_browser_does_not_open(self):
        with patch("JARVIS.webbrowser.open", return_value=False):
            self.assertIn("couldn't find a browser", jarvis.open_url("https://example.com"))

    def test_unknown_folder_is_not_opened(self):
        self.assertIn("can open your Desktop", jarvis.open_folder("C:/Windows/System32"))

    def test_supported_app_aliases_exist(self):
        for app in ("notepad", "calculator", "discord", "gmail", "github", "chatgpt", "google drive"):
            with self.subTest(app=app):
                self.assertIn(app, jarvis._APP_ALIASES)

    def test_notes_can_be_saved_and_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            note_path = Path(temporary) / "notes.txt"
            with patch.object(jarvis, "notes_file", return_value=note_path):
                self.assertIn("saved your note", jarvis.take_note("test note"))
                self.assertIn("test note", jarvis.read_notes())

    def test_open_notes_handles_path_resolution_failure(self):
        with patch("JARVIS.notes_file", side_effect=OSError("unavailable")):
            result = jarvis.open_notes()
        self.assertIn("couldn't locate a writable folder", result)

    def test_empty_note_prompts_for_text(self):
        self.assertIn("What would you like", jarvis.take_note("  "))

    def test_note_length_is_bounded(self):
        self.assertIn("under", jarvis.take_note("x" * (jarvis.MAX_INPUT_LENGTH + 1)))

    def test_note_save_failure_is_friendly(self):
        with patch("JARVIS.notes_file", side_effect=OSError("read-only")):
            self.assertIn("couldn't save your note", jarvis.take_note("test"))

    def test_timer_rejects_boolean_duration(self):
        self.assertIn("duration", jarvis.set_timer(True))

    def test_timer_limit_prevents_unbounded_timer_creation(self):
        with patch.object(jarvis, "_active_timers", set(range(jarvis.MAX_ACTIVE_TIMERS))):
            self.assertIn("active timers", jarvis.set_timer(60))

    def test_note_parser(self):
        self.assertEqual(jarvis.extract_note_text("Take a note: buy milk"), "buy milk")
        self.assertEqual(jarvis.extract_note_text("Save note saying call Alex"), "call Alex")
        self.assertEqual(jarvis.extract_note_text("Could you please take a note: pick up parcel"), "pick up parcel")
        self.assertIsNone(jarvis.extract_note_text("What is a note?"))

    def test_time_parser_is_specific(self):
        self.assertTrue(jarvis.is_time_request("What time is it?"))
        self.assertTrue(jarvis.is_time_request("Tell me the current time"))
        self.assertTrue(jarvis.is_time_request("Can you tell me the time?"))
        self.assertFalse(jarvis.is_time_request("What is 12 + 2?"))

    def test_direct_help_and_system_info(self):
        self.assertIn("BIDMAS", jarvis._handle_direct_request("help"))
        self.assertIn(jarvis.APP_VERSION, jarvis._handle_direct_request("system info"))

    def test_timer_parser_and_formatting(self):
        self.assertEqual(jarvis.extract_timer_seconds("Set a timer for 5 minutes"), 300)
        self.assertEqual(jarvis.extract_timer_seconds("Timer for 1.5 hours"), 5400)
        self.assertIsNone(jarvis.extract_timer_seconds("Remind me sometime"))
        self.assertEqual(jarvis.format_duration(3661), "1 hour 1 minute 1 second")

    def test_timer_parser_accepts_natural_variants(self):
        cases = {
            "start a timer in 30 seconds": 30,
            "create timer for 1.5 hours": 5400,
            "set a 5 minute timer": 300,
            "start a 2-day timer": 172800,
            "timer in 45 seconds": 45,
        }
        for request, expected in cases.items():
            with self.subTest(request=request):
                self.assertEqual(jarvis.extract_timer_seconds(request), expected)

    def test_timer_parser_ignores_unrelated_duration(self):
        self.assertIsNone(jarvis.extract_timer_seconds("I worked for 5 minutes"))
        self.assertIsNone(jarvis.extract_timer_seconds("remind me in 5 minutes"))

    def test_timer_parser_preserves_oversized_duration_for_clear_rejection(self):
        seconds = jarvis.extract_timer_seconds("set timer for 999999999999999999999999999999999999 days")
        self.assertIsNotNone(seconds)
        self.assertIn("between 1 second and 7 days", jarvis.set_timer(seconds))
        infinite = jarvis.extract_timer_seconds("set timer for 9" * 1 + "9" * 500 + " days")
        self.assertTrue(infinite is None or infinite == float("inf"))
        if infinite is not None:
            self.assertIn("between 1 second and 7 days", jarvis.set_timer(infinite))

    def test_argument_reader_skips_function_metadata(self):
        self.assertEqual(
            jarvis.first_real_text_argument(
                {"function": "function", "tool": "search_edge", "query": "actual phrase"},
                ("query", "text"),
            ),
            "actual phrase",
        )

    @patch("JARVIS.speak")
    def test_direct_math_routing_never_calls_ollama(self, speak):
        history = [{"role": "system", "content": "test"}]
        jarvis.process_user_request("12+2", history)
        self.assertEqual(history[-1]["content"], "The result is 14.")
        speak.assert_called_once_with("The result is 14.")

    def test_how_are_you_is_answered_locally_without_ollama(self):
        result = jarvis._handle_direct_request("How are you?")
        self.assertIsNotNone(result)
        self.assertIn("thanks for asking", result)

    @patch("JARVIS.speak")
    def test_how_are_you_never_creates_an_ollama_client(self, speak):
        history = [{"role": "system", "content": "test"}]
        with patch("JARVIS.create_ollama_client") as create_client:
            jarvis.process_user_request("How are you", history)
        create_client.assert_not_called()
        self.assertIn("I'm doing well", history[-1]["content"])
        speak.assert_called_once()

    def test_thanks_and_identity_have_local_answers(self):
        self.assertIn("welcome", jarvis._handle_direct_request("Thanks, JARVIS!").lower())
        self.assertIn("local desktop assistant", jarvis._handle_direct_request("Who are you?").lower())

    def test_tool_schemas_are_only_needed_for_action_requests(self):
        self.assertFalse(jarvis._request_may_need_tools("Explain how photosynthesis works"))
        self.assertFalse(jarvis._request_may_need_tools("How are you?"))
        self.assertTrue(jarvis._request_may_need_tools("Could you help me open Notepad?"))
        self.assertTrue(jarvis._request_may_need_tools("Search the web for Python tutorials"))

    def test_think_mode_discovery_prefers_false_when_advertised(self):
        with patch.object(jarvis, "_OLLAMA_THINK_CACHE", {}), \
             patch.object(jarvis, "_fetch_ollama_post_json", return_value=({"thinking": {"values": [True, False], "default": True}}, "http://localhost:11434")) as fetch:
            self.assertIs(jarvis.get_preferred_think_mode("gemma4:e2b"), False)
            self.assertEqual(fetch.call_count, 1)
            self.assertIs(jarvis.get_preferred_think_mode("gemma4:e2b"), False)
            self.assertEqual(fetch.call_count, 1)

    def test_think_mode_uses_low_when_false_is_not_advertised(self):
        with patch.object(jarvis, "_OLLAMA_THINK_CACHE", {}), \
             patch.object(jarvis, "_fetch_ollama_post_json", return_value=({"thinking": {"values": ["low", "medium", "high"], "default": "medium"}}, "http://localhost:11434")):
            self.assertEqual(jarvis.get_preferred_think_mode("gemma4:e2b"), "low")

    def test_think_mode_is_omitted_when_model_does_not_advertise_controls(self):
        with patch.object(jarvis, "_OLLAMA_THINK_CACHE", {}), \
             patch.object(jarvis, "_fetch_ollama_post_json", return_value=({}, "http://localhost:11434")):
            self.assertIsNone(jarvis.get_preferred_think_mode("llama3.2:1b"))


class SettingsTests(unittest.TestCase):
    def test_non_boolean_voice_setting_uses_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text('{"voice_enabled": 0}', encoding="utf-8")
            with patch.object(jarvis, "settings_path", return_value=path):
                self.assertTrue(jarvis.load_settings()["voice_enabled"])

    def test_boolean_false_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text('{"voice_enabled": false}', encoding="utf-8")
            with patch.object(jarvis, "settings_path", return_value=path):
                self.assertFalse(jarvis.load_settings()["voice_enabled"])

    def test_window_geometry_is_loaded_and_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(json.dumps({"window_geometry": "1440x900+20+30"}), encoding="utf-8")
            with patch.object(jarvis, "settings_path", return_value=path):
                self.assertEqual(jarvis.load_settings()["window_geometry"], "1440x900+20+30")
            path.write_text(json.dumps({"window_geometry": "10x10"}), encoding="utf-8")
            with patch.object(jarvis, "settings_path", return_value=path):
                self.assertEqual(jarvis.load_settings()["window_geometry"], "1360x860")

    def test_theme_defaults_to_midnight(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=path):
                self.assertEqual(jarvis.load_settings()["theme"], "midnight")

    def test_theme_setting_persists(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=path):
                jarvis.save_settings(theme="violet")
                self.assertEqual(jarvis.load_settings()["theme"], "violet")

    def test_all_supported_themes_can_be_saved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=path):
                for theme in jarvis.SUPPORTED_THEMES:
                    with self.subTest(theme=theme):
                        jarvis.save_settings(theme=theme)
                        self.assertEqual(jarvis.load_settings()["theme"], theme)

    def test_invalid_theme_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=path):
                with self.assertRaises(ValueError):
                    jarvis.save_settings(theme="ultraviolet-9000")

    def test_invalid_theme_in_settings_file_uses_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(json.dumps({"theme": "not-a-theme"}), encoding="utf-8")
            with patch.object(jarvis, "settings_path", return_value=path):
                self.assertEqual(jarvis.load_settings()["theme"], "midnight")

    def test_save_settings_persists_geometry_voice_and_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=path):
                jarvis.save_settings(window_geometry="1366x768+0+0", voice_enabled=False, num_ctx=4096)
                saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["window_geometry"], "1366x768+0+0")
            self.assertIs(saved["voice_enabled"], False)
            self.assertEqual(saved["num_ctx"], 4096)

    def test_legacy_default_model_migrates_to_gemma_e2b(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(json.dumps({"model": "llama3.2:1b"}), encoding="utf-8")
            with patch.object(jarvis, "settings_path", return_value=path):
                settings = jarvis.load_settings()
            self.assertEqual(settings["model"], "gemma4:e2b")
            self.assertEqual(settings["num_ctx"], 8192)

    def test_runtime_preferences_update_model_and_context_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=path), \
                 patch.object(jarvis, "MODEL_NAME", "llama3.2:1b"), \
                 patch.object(jarvis, "NUM_CTX", 32768):
                result = jarvis.set_runtime_preferences("gemma4:e2b", 4096)
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(result, ("gemma4:e2b", 4096))
                self.assertEqual(saved["model"], "gemma4:e2b")
                self.assertEqual(saved["num_ctx"], 4096)
                self.assertEqual(saved["settings_version"], jarvis.SETTINGS_VERSION)

    def test_saved_model_choice_is_not_migrated_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=path):
                jarvis.save_settings(model="llama3.2:1b")
                settings = jarvis.load_settings()
            self.assertEqual(settings["model"], "llama3.2:1b")
            self.assertEqual(settings["settings_version"], jarvis.SETTINGS_VERSION)

    def test_context_setting_is_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            with patch.object(jarvis, "settings_path", return_value=path):
                jarvis.save_settings(num_ctx=4096)
                self.assertEqual(jarvis.load_settings()["num_ctx"], 4096)
                with self.assertRaises(ValueError):
                    jarvis.save_settings(num_ctx=32768)
                with self.assertRaises(ValueError):
                    jarvis.save_settings(num_ctx=True)

    def test_save_settings_rejects_unknown_or_invalid_preferences(self):
        with self.assertRaises(ValueError):
            jarvis.save_settings(arbitrary_option="not allowed")
        with self.assertRaises(ValueError):
            jarvis.save_settings(window_geometry="1x1")
        with self.assertRaises(ValueError):
            jarvis.save_settings(voice_enabled="false")
        with self.assertRaises(ValueError):
            jarvis.save_settings(num_ctx=32768)

    def test_oversized_settings_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(" " * (jarvis.MAX_SETTINGS_BYTES + 1), encoding="utf-8")
            with patch.object(jarvis, "settings_path", return_value=path), patch.object(jarvis, "log_error"):
                settings = jarvis.load_settings()
            self.assertEqual(settings["model"], jarvis.DEFAULT_MODEL)
            self.assertEqual(settings["num_ctx"], jarvis.DEFAULT_NUM_CTX)
            self.assertTrue(settings["voice_enabled"])

    def test_log_rotation_keeps_latest_and_one_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            log_dir = Path(temporary)
            log_path = log_dir / "jarvis.log"
            log_path.write_text("x" * jarvis.MAX_LOG_BYTES, encoding="utf-8")
            with patch.object(jarvis, "user_data_dir", return_value=log_dir):
                jarvis.log_error("rotation check")
            self.assertTrue(log_path.with_suffix(".log.1").exists())
            self.assertIn("rotation check", log_path.read_text(encoding="utf-8"))


class OllamaConfigurationTests(unittest.TestCase):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit=-1):
            return json.dumps(self.payload).encode("utf-8")

    def test_installed_model_discovery_reads_exact_tags(self):
        payload = {"models": [
            {"name": "gemma4:e2b", "model": "gemma4:e2b"},
            {"name": "llama3.2:1b"},
        ]}
        with patch("JARVIS._OLLAMA_ACTIVE_HOST", None), \
             patch("JARVIS._ollama_urlopen", return_value=self.FakeResponse(payload)) as open_url:
            models = jarvis.get_installed_ollama_models()
        self.assertEqual(models, ["gemma4:e2b", "llama3.2:1b"])
        self.assertIn("localhost:11434/api/tags", open_url.call_args.args[0].full_url)

    def test_ollama_host_environment_is_respected(self):
        payload = {"models": [{"name": "gemma4:e2b"}]}
        with patch.object(jarvis, "_OLLAMA_ACTIVE_HOST", None), \
             patch.dict("os.environ", {"OLLAMA_HOST": "http://localhost:11435"}), \
             patch("JARVIS._ollama_urlopen", return_value=self.FakeResponse(payload)) as open_url:
            self.assertEqual(jarvis.get_installed_ollama_models(), ["gemma4:e2b"])
        self.assertIn("localhost:11435/api/tags", open_url.call_args.args[0].full_url)

    def test_loopback_api_requests_bypass_environment_proxy(self):
        from unittest.mock import Mock
        request = jarvis.urllib.request.Request("http://127.0.0.1:11434/api/tags")
        fake_opener = Mock()
        fake_opener.open.return_value = self.FakeResponse({"models": []})
        with patch("JARVIS.urllib.request.build_opener", return_value=fake_opener) as build_opener:
            jarvis._ollama_urlopen(request, 2.0, "http://127.0.0.1:11434")
        handlers = build_opener.call_args.args
        proxy_handlers = [handler for handler in handlers if isinstance(handler, jarvis.urllib.request.ProxyHandler)]
        self.assertEqual(len(proxy_handlers), 1)
        self.assertEqual(proxy_handlers[0].proxies, {})
        fake_opener.open.assert_called_once_with(request, timeout=2.0)

    def test_non_loopback_custom_host_keeps_normal_proxy_routing(self):
        from unittest.mock import Mock
        request = jarvis.urllib.request.Request("http://192.168.1.20:11434/api/tags")
        response = self.FakeResponse({"models": []})
        with patch("JARVIS.urllib.request.urlopen", return_value=response) as open_url:
            result = jarvis._ollama_urlopen(request, 2.0, "http://192.168.1.20:11434")
        self.assertIs(result, response)
        open_url.assert_called_once_with(request, timeout=2.0)

    def test_wildcard_ollama_host_is_converted_to_connectable_loopback(self):
        self.assertEqual(jarvis._normalise_ollama_host("0.0.0.0:11434"), "http://127.0.0.1:11434")
        self.assertEqual(jarvis._normalise_ollama_host("[::]:11434"), "http://[::1]:11434")

    def test_default_host_candidates_cover_windows_loopback_variants(self):
        with patch.dict("os.environ", {}, clear=True):
            candidates = jarvis._ollama_api_candidates()
        self.assertEqual(candidates, [
            "http://localhost:11434",
            "http://127.0.0.1:11434",
            "http://[::1]:11434",
        ])

    def test_api_discovery_falls_back_when_first_loopback_fails(self):
        payload = {"models": [{"name": "gemma4:e2b"}]}
        responses = [OSError("localhost did not resolve"), self.FakeResponse(payload)]
        with patch.object(jarvis, "_OLLAMA_ACTIVE_HOST", None), \
             patch.dict("os.environ", {}, clear=True), \
             patch("JARVIS._ollama_urlopen", side_effect=responses) as open_url:
            self.assertEqual(jarvis.get_installed_ollama_models(), ["gemma4:e2b"])
            self.assertEqual(open_url.call_count, 2)
            self.assertIn("127.0.0.1:11434/api/tags", open_url.call_args.args[0].full_url)
            self.assertEqual(jarvis._ollama_api_base(), "http://127.0.0.1:11434")

    def test_wildcard_ollama_host_uses_loopback_for_api_request(self):
        payload = {"models": [{"name": "gemma4:e2b"}]}
        with patch.object(jarvis, "_OLLAMA_ACTIVE_HOST", None), \
             patch.dict("os.environ", {"OLLAMA_HOST": "0.0.0.0:11434"}), \
             patch("JARVIS._ollama_urlopen", return_value=self.FakeResponse(payload)) as open_url:
            self.assertEqual(jarvis.get_installed_ollama_models(), ["gemma4:e2b"])
        self.assertIn("127.0.0.1:11434/api/tags", open_url.call_args.args[0].full_url)

    def test_ollama_status_requires_exact_model_match(self):
        with patch.object(jarvis, "MODEL_NAME", "gemma4:e2b"), \
             patch.object(jarvis, "NUM_CTX", 8192), \
             patch.object(jarvis, "get_installed_ollama_models", return_value=["gemma4:12b"]):
            ok, status = jarvis.check_ollama_status()
        self.assertFalse(ok)
        self.assertIn("gemma4:e2b missing", status)
        self.assertIn("gemma4:12b", status)

    def test_ollama_status_reports_configured_model_and_context(self):
        with patch.object(jarvis, "MODEL_NAME", "gemma4:e2b"), \
             patch.object(jarvis, "NUM_CTX", 8192), \
             patch.object(jarvis, "get_installed_ollama_models", return_value=["gemma4:e2b", "gemma4:12b"]):
            ok, status = jarvis.check_ollama_status()
        self.assertTrue(ok)
        self.assertIn("gemma4:e2b ready", status)
        self.assertIn("8,192 context", status)

    def test_ollama_options_use_conservative_context_and_output(self):
        with patch.object(jarvis, "NUM_CTX", 8192):
            options = jarvis.ollama_chat_options(384)
        self.assertEqual(options["num_ctx"], 8192)
        self.assertEqual(options["num_predict"], 384)
        self.assertEqual(options["temperature"], 0.25)
        self.assertEqual(options["top_p"], 0.9)

    def test_chat_requests_use_the_configured_context(self):
        import types
        from unittest.mock import Mock

        fake_response = types.SimpleNamespace(
            message=types.SimpleNamespace(content="A concise answer.", tool_calls=[])
        )
        fake_client = types.SimpleNamespace(chat=Mock(return_value=fake_response))
        fake_ollama = types.SimpleNamespace(Client=Mock(return_value=fake_client))
        history = [{"role": "system", "content": "test"}]
        with patch.dict("sys.modules", {"ollama": fake_ollama}), \
             patch.object(jarvis, "_OLLAMA_ACTIVE_HOST", "http://localhost:11434"), \
             patch.object(jarvis, "ensure_ollama_available", return_value=["gemma4:e2b"]), \
             patch.object(jarvis, "MODEL_NAME", "gemma4:e2b"), \
             patch.object(jarvis, "NUM_CTX", 8192), \
             patch.object(jarvis, "get_preferred_think_mode", return_value=False), \
             patch.object(jarvis, "speak"):
            jarvis.process_user_request("Explain why the sky looks blue", history)
        fake_ollama.Client.assert_called_once_with(host="http://localhost:11434", trust_env=False)
        call = fake_client.chat.call_args.kwargs
        self.assertEqual(call["model"], "gemma4:e2b")
        self.assertEqual(call["keep_alive"], jarvis.OLLAMA_KEEP_ALIVE)
        self.assertEqual(call["options"]["num_ctx"], 8192)
        self.assertEqual(call["options"]["num_predict"], 224)
        self.assertNotIn("tools", call, "ordinary knowledge questions should not send tool schemas")
        self.assertIs(call["think"], False)


class OllamaToolSchemaTests(unittest.TestCase):
    def test_every_dispatch_tool_has_an_explicit_json_schema(self):
        schema_names = [item["function"]["name"] for item in jarvis.OLLAMA_TOOL_SCHEMAS]
        self.assertEqual(schema_names, list(jarvis.available_tools))

    def test_tool_schemas_are_json_serialisable_and_do_not_use_callable_annotations(self):
        # Serialization proves that no function objects or Python-only types
        # are being handed to the Ollama SDK for Pydantic introspection.
        encoded = json.dumps(jarvis.OLLAMA_TOOL_SCHEMAS)
        self.assertIn('"name": "open_app"', encoded)
        self.assertNotIn("ForwardRef", encoded)
        for tool in jarvis.OLLAMA_TOOL_SCHEMAS:
            self.assertEqual(tool["type"], "function")
            function = tool["function"]
            self.assertTrue(function["name"])
            parameters = function["parameters"]
            self.assertEqual(parameters["type"], "object")
            self.assertIs(parameters["additionalProperties"], False)
            self.assertTrue(set(parameters["required"]).issubset(parameters["properties"]))
            for name, definition in parameters["properties"].items():
                self.assertTrue(name)
                self.assertIn(definition["type"], {"string", "number", "integer", "boolean", "object", "array"})

    def test_tool_call_and_followup_use_explicit_schemas(self):
        import types
        from unittest.mock import Mock

        tool_call = types.SimpleNamespace(
            function=types.SimpleNamespace(name="get_help", arguments={})
        )
        responses = [
            types.SimpleNamespace(message=types.SimpleNamespace(content="", tool_calls=[tool_call])),
            types.SimpleNamespace(message=types.SimpleNamespace(content="Here are the available features.", tool_calls=[])),
        ]
        fake_client = types.SimpleNamespace(chat=Mock(side_effect=responses))
        fake_ollama = types.SimpleNamespace(Client=Mock(return_value=fake_client))
        history = [{"role": "system", "content": "test"}]
        with patch.dict("sys.modules", {"ollama": fake_ollama}), \
             patch.object(jarvis, "_OLLAMA_ACTIVE_HOST", "http://localhost:11434"), \
             patch.object(jarvis, "ensure_ollama_available", return_value=["gemma4:e2b"]), \
             patch.object(jarvis, "MODEL_NAME", "gemma4:e2b"), \
             patch.object(jarvis, "get_preferred_think_mode", return_value=False), \
             patch("JARVIS.speak"):
            jarvis.process_user_request("Could you help me open Notepad?", history)

        self.assertEqual(fake_client.chat.call_count, 2)
        for call in fake_client.chat.call_args_list:
            self.assertEqual(call.kwargs["tools"], jarvis.OLLAMA_TOOL_SCHEMAS)
        self.assertTrue(any(item.get("role") == "tool" and item.get("name") == "get_help" for item in history))


class HistoryTests(unittest.TestCase):
    def test_history_limit_preserves_system_and_user_boundary(self):
        history = [{"role": "system", "content": "system"}]
        for number in range(40):
            jarvis._append_history(history, {"role": "user", "content": f"user {number}"})
            jarvis._append_history(history, {"role": "assistant", "content": f"assistant {number}"})
        self.assertEqual(history[0]["role"], "system")
        self.assertLessEqual(len(history), jarvis.MAX_HISTORY_MESSAGES)
        self.assertEqual(history[1]["role"], "user")


class UpdaterTests(unittest.TestCase):
    def test_version_comparison_pads_missing_components(self):
        self.assertEqual(launcher.version_tuple("v1.2"), launcher.version_tuple("1.2.0"))
        self.assertEqual(launcher.version_tuple("1.2.3.0"), launcher.version_tuple("1.2.3"))
        self.assertGreater(launcher.version_tuple("1.0.10"), launcher.version_tuple("1.0.9"))
        self.assertGreater(launcher.version_tuple("2.0.0"), launcher.version_tuple("1.99.99"))

    def test_invalid_version_text_is_not_parsed_as_a_release(self):
        self.assertEqual(launcher.version_tuple("release-1.2.3"), (0, 0, 0))
        self.assertEqual(launcher.version_tuple("1.2.bad"), (0, 0, 0))

    def test_extremely_long_version_is_rejected_safely(self):
        self.assertEqual(launcher.version_tuple("9" * 5000), (0, 0, 0))

    def test_http_json_rejects_non_https_before_network_access(self):
        with patch("launcher.urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                launcher.http_json("http://api.github.com/releases/latest")
            urlopen.assert_not_called()

    def test_find_asset_rejects_non_object_release(self):
        with self.assertRaisesRegex(ValueError, "release object"):
            launcher.find_asset(["not", "a", "dict"], "JARVIS-Windows.zip")

    def test_find_asset_rejects_non_https_asset_url(self):
        release = {"assets": [{"name": "JARVIS-Windows.zip", "browser_download_url": "http://example.com/a.zip"}]}
        with self.assertRaisesRegex(ValueError, "invalid download URL"):
            launcher.find_asset(release, "JARVIS-Windows.zip")

    def test_download_rejects_invalid_size_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "positive integer"):
                launcher.download("https://example.com/file.zip", Path(temporary) / "file.zip", max_bytes=0)
            with self.assertRaisesRegex(ValueError, "positive integer"):
                launcher.download("https://example.com/file.zip", Path(temporary) / "file.zip", max_bytes=True)

    def test_safe_extract_accepts_normal_update_zip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "update.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("JARVIS.exe", b"x" * 2048)
                archive.writestr("version.txt", "1.1.0")
            destination = root / "staging"
            destination.mkdir()
            launcher.safe_extract(archive_path, destination)
            self.assertTrue((destination / "JARVIS.exe").is_file())

    def test_safe_extract_rejects_file_directory_collision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "collision.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("cache", b"file")
                archive.writestr("cache/settings.json", b"child")
            destination = root / "staging"
            destination.mkdir()
            with self.assertRaisesRegex(ValueError, "file/directory path collision"):
                launcher.safe_extract(archive_path, destination)

    def test_safe_extract_rejects_symbolic_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "link.zip"
            link = zipfile.ZipInfo("link-to-outside")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(link, "../outside.txt")
            destination = root / "staging"
            destination.mkdir()
            with self.assertRaises(ValueError):
                launcher.safe_extract(archive_path, destination)

    @patch("launcher.wait_for_parent_exit")
    @patch("launcher.subprocess.Popen")
    def test_apply_update_installs_new_version(self, popen, wait_parent):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_dir = root / "app"
            app_dir.mkdir()
            (app_dir / "JARVIS.exe").write_bytes(b"old" * 700)
            (app_dir / "version.txt").write_text("1.0.0", encoding="utf-8")
            archive_path = root / "update.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("JARVIS.exe", b"new" * 800)
                archive.writestr("version.txt", "1.1.0")
            launcher.apply_update(archive_path, app_dir, 1234)
            self.assertEqual((app_dir / "version.txt").read_text(encoding="utf-8"), "1.1.0")
            self.assertFalse((root / "app.previous").exists())
            self.assertFalse(archive_path.exists())
            popen.assert_called_once()
            wait_parent.assert_called_once_with(1234)

    @patch("launcher.wait_for_parent_exit")
    @patch("launcher.subprocess.Popen", side_effect=OSError("simulated launch failure"))
    def test_apply_update_restores_previous_app_if_new_exe_wont_start(self, _popen, _wait_parent):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_dir = root / "app"
            app_dir.mkdir()
            (app_dir / "JARVIS.exe").write_bytes(b"old" * 700)
            (app_dir / "version.txt").write_text("1.0.0", encoding="utf-8")
            archive_path = root / "update.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("JARVIS.exe", b"new" * 800)
                archive.writestr("version.txt", "1.1.0")
            with self.assertRaises(OSError):
                launcher.apply_update(archive_path, app_dir, 1234)
            self.assertEqual((app_dir / "version.txt").read_text(encoding="utf-8"), "1.0.0")
            self.assertFalse((root / "app.previous").exists())

    def test_load_config_rejects_non_object_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "update_config.json"
            config_path.write_text('["not", "an", "object"]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                launcher.load_config(Path(temporary))

    def test_safe_extract_rejects_special_file_types(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "special.zip"
            special = zipfile.ZipInfo("device")
            special.create_system = 3
            special.external_attr = (stat.S_IFCHR | 0o600) << 16
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(special, b"not a regular file")
            destination = root / "staging"
            destination.mkdir()
            with self.assertRaisesRegex(ValueError, "special file type"):
                launcher.safe_extract(archive_path, destination)

    def test_download_requires_https(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                launcher.download("http://example.com/file.zip", Path(temporary) / "file.zip")

    def test_download_creates_parent_and_publishes_complete_file(self):
        import io

        class FakeResponse(io.BytesIO):
            headers = {"Content-Length": "7"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

            def geturl(self):
                return "https://example.com/file.bin"

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "new" / "nested" / "file.bin"
            with patch("launcher.urllib.request.urlopen", return_value=FakeResponse(b"payload")):
                launcher.download("https://example.com/file.bin", destination, max_bytes=20)
            self.assertEqual(destination.read_bytes(), b"payload")
            self.assertFalse(destination.with_suffix(".bin.part").exists())

    def test_download_removes_partial_file_after_failure(self):
        import io

        class FailingResponse(io.BytesIO):
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

            def geturl(self):
                return "https://example.com/file.bin"

            def read(self, _size=-1):
                raise OSError("simulated interrupted download")

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "file.bin"
            with patch("launcher.urllib.request.urlopen", return_value=FailingResponse(b"")):
                with self.assertRaisesRegex(OSError, "interrupted"):
                    launcher.download("https://example.com/file.bin", destination)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix(".bin.part").exists())

    def test_safe_extract_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "bad.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "not allowed")
            destination = root / "staging"
            destination.mkdir()
            with self.assertRaises(ValueError):
                launcher.safe_extract(archive_path, destination)
            self.assertFalse((root / "escape.txt").exists())

    def test_safe_extract_rejects_invalid_windows_characters(self):
        for unsafe_name in ("bad<name>.txt", "question?.txt", "pipe|name.txt", "folder\\bad*.txt", "."):
            with self.subTest(name=unsafe_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive_path = root / "bad.zip"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr(unsafe_name, "not allowed")
                destination = root / "staging"
                destination.mkdir()
                with self.assertRaises(ValueError):
                    launcher.safe_extract(archive_path, destination)

    def test_safe_extract_rejects_control_characters(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "bad.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("bad\x01name.txt", "not allowed")
            destination = root / "staging"
            destination.mkdir()
            with self.assertRaises(ValueError):
                launcher.safe_extract(archive_path, destination)

    def test_safe_extract_rejects_windows_device_aliases(self):
        for unsafe_name in ("CONIN$", "CONOUT$.txt", "COM¹.log", "LPT³"):
            with self.subTest(name=unsafe_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive_path = root / "bad.zip"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr(unsafe_name, "not allowed")
                destination = root / "staging"
                destination.mkdir()
                with self.assertRaises(ValueError):
                    launcher.safe_extract(archive_path, destination)

    def test_recover_interrupted_update_restores_previous_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_dir = root / "app"
            backup = root / "app.previous"
            staging = root / "app.new"
            backup.mkdir()
            staging.mkdir()
            (backup / "JARVIS.exe").write_bytes(b"x" * 2048)
            (backup / "version.txt").write_text("1.2.2", encoding="utf-8")
            result = launcher.recover_interrupted_update(app_dir)
            self.assertEqual(result, "restored-previous")
            self.assertTrue((app_dir / "JARVIS.exe").is_file())
            self.assertFalse(backup.exists())
            self.assertFalse(staging.exists())

    def test_recover_interrupted_update_discards_invalid_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_dir = root / "app"
            staging = root / "app.new"
            staging.mkdir()
            (staging / "incomplete.tmp").write_text("partial", encoding="utf-8")
            result = launcher.recover_interrupted_update(app_dir)
            self.assertEqual(result, "no-installation")
            self.assertFalse(staging.exists())

    def test_update_rejects_non_numeric_package_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_dir = root / "app"
            app_dir.mkdir()
            archive_path = root / "update.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("JARVIS.exe", b"x" * 2048)
                archive.writestr("version.txt", "latest")
            with patch("launcher.wait_for_parent_exit"):
                with self.assertRaisesRegex(ValueError, "invalid version"):
                    launcher.apply_update(archive_path, app_dir, 1234)

    def test_update_rejects_package_that_is_not_newer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_dir = root / "app"
            app_dir.mkdir()
            (app_dir / "JARVIS.exe").write_bytes(b"x" * 2048)
            (app_dir / "version.txt").write_text("1.2.3", encoding="utf-8")
            archive_path = root / "update.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("JARVIS.exe", b"y" * 2048)
                archive.writestr("version.txt", "1.2.3")
            with patch("launcher.wait_for_parent_exit"):
                with self.assertRaisesRegex(ValueError, "not newer"):
                    launcher.apply_update(archive_path, app_dir, 1234)

    def test_safe_extract_rejects_windows_reserved_names(self):
        for unsafe_name in ("CON.txt", "NUL", "folder/AUX.log"):
            with self.subTest(name=unsafe_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive_path = root / "bad.zip"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr(unsafe_name, "not allowed")
                destination = root / "staging"
                destination.mkdir()
                with self.assertRaises(ValueError):
                    launcher.safe_extract(archive_path, destination)

    def test_safe_extract_rejects_duplicate_case_insensitive_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "duplicate.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("JARVIS.exe", b"one")
                archive.writestr("jarvis.exe", b"two")
            destination = root / "staging"
            destination.mkdir()
            with self.assertRaises(ValueError):
                launcher.safe_extract(archive_path, destination)

    def test_update_helper_handles_invalid_pid_without_traceback(self):
        with patch("launcher.show_error"), patch("launcher.launch_app") as launch:
            result = launcher.run_update_helper(["--apply-update", "update.zip", "app", "not-a-pid"])
        self.assertEqual(result, 1)
        launch.assert_called_once_with(Path("app"))

    def test_update_helper_rejects_negative_pid(self):
        with patch("launcher.show_error"), patch("launcher.launch_app") as launch:
            result = launcher.run_update_helper(["--apply-update", "update.zip", "app", "-1"])
        self.assertEqual(result, 1)
        launch.assert_called_once_with(Path("app"))

    def test_build_script_reports_the_failing_stage_and_log(self):
        project_root = Path(__file__).resolve().parents[1]
        build_text = (project_root / "build_release.bat").read_text(encoding="utf-8")
        self.assertIn("BUILD FAILED during: %BUILD_STAGE%", build_text)
        self.assertIn("build.log", build_text)

    def test_application_and_build_versions_match(self):
        project_root = Path(__file__).resolve().parents[1]
        core_text = (project_root / "JARVIS.py").read_text(encoding="utf-8")
        build_text = (project_root / "build_release.bat").read_text(encoding="utf-8")
        installer_text = (project_root / "installer.iss").read_text(encoding="utf-8")
        self.assertIn(f'APP_VERSION = "{jarvis.APP_VERSION}"', core_text)
        self.assertIn(f'set "APP_VERSION={jarvis.APP_VERSION}"', build_text)
        self.assertIn(f'#define MyAppVersion "{jarvis.APP_VERSION}"', installer_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
