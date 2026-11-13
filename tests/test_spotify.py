from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import JARVIS as jarvis
import jarvis_spotify as spotify


class SpotifyMediaControlTests(unittest.TestCase):
    def test_supported_actions_are_documented(self):
        self.assertIn("play_pause", spotify._MEDIA_KEYS)
        self.assertIn("next", spotify._MEDIA_KEYS)
        self.assertIn("previous", spotify._MEDIA_KEYS)

    def test_play_pause_uses_windows_media_virtual_key(self):
        self.assertEqual(spotify._MEDIA_KEYS["play_pause"], 0xB3)

    def test_next_uses_windows_media_virtual_key(self):
        self.assertEqual(spotify._MEDIA_KEYS["next"], 0xB0)

    def test_previous_uses_windows_media_virtual_key(self):
        self.assertEqual(spotify._MEDIA_KEYS["previous"], 0xB1)

    def test_media_key_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            spotify._send_media_key("volume_up")

    def test_media_key_rejects_non_windows_platform(self):
        with patch.object(spotify.os, "name", "posix"):
            with self.assertRaises(OSError):
                spotify._send_media_key("next")

    def test_media_key_sends_key_down_and_key_up(self):
        fake_user32 = SimpleNamespace(keybd_event=Mock())
        with patch.object(spotify.os, "name", "nt"), \
             patch.object(spotify.ctypes, "windll", SimpleNamespace(user32=fake_user32), create=True):
            spotify._send_media_key("next")
        self.assertEqual(fake_user32.keybd_event.call_count, 2)
        self.assertEqual(fake_user32.keybd_event.call_args_list[0].args, (0xB0, 0, 0x0001, 0))
        self.assertEqual(fake_user32.keybd_event.call_args_list[1].args, (0xB0, 0, 0x0003, 0))

    def test_find_spotify_executable_checks_roaming_install(self):
        candidate = Path("C:/Users/test/AppData/Roaming/Spotify/Spotify.exe")
        with patch.object(spotify, "_spotify_candidates", return_value=[candidate]), \
             patch.object(Path, "is_file", return_value=True):
            self.assertEqual(spotify.find_spotify_executable(), candidate)

    def test_find_spotify_executable_returns_none_when_missing(self):
        with patch.object(spotify, "_spotify_candidates", return_value=[Path("missing.exe")]), \
             patch.object(Path, "is_file", return_value=False):
            self.assertIsNone(spotify.find_spotify_executable())

    def test_spotify_candidates_include_appdata_location(self):
        appdata = r"C:\Users\test\AppData\Roaming"
        localappdata = r"C:\Users\test\AppData\Local"
        with patch.dict(os.environ, {"APPDATA": appdata, "LOCALAPPDATA": localappdata}):
            candidates = spotify._spotify_candidates()
            expected = Path(appdata) / "Spotify" / "Spotify.exe"
        # Compare Path objects rather than hard-coding forward slashes: Windows
        # renders Path strings with backslashes, while POSIX uses forward slashes.
        self.assertIn(expected, candidates)

    def test_open_spotify_launches_desktop_executable(self):
        executable = Path("C:/Spotify/Spotify.exe")
        with patch.object(spotify, "find_spotify_executable", return_value=executable), \
             patch.object(spotify.subprocess, "Popen") as popen:
            result = spotify.open_spotify()
        self.assertEqual(result, "Opened Spotify.")
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], [str(executable)])

    def test_open_spotify_falls_back_to_protocol_or_web(self):
        with patch.object(spotify, "find_spotify_executable", return_value=None), \
             patch.object(spotify, "_open_uri", return_value=True) as opener:
            result = spotify.open_spotify()
        self.assertEqual(result, "Opened Spotify.")
        opener.assert_called_once_with("spotify:", "https://open.spotify.com/")

    def test_open_spotify_reports_failure_truthfully(self):
        with patch.object(spotify, "find_spotify_executable", return_value=None), \
             patch.object(spotify, "_open_uri", return_value=False):
            result = spotify.open_spotify()
        self.assertIn("couldn't open Spotify", result)

    def test_open_spotify_handles_process_launch_error_with_fallback(self):
        with patch.object(spotify, "find_spotify_executable", return_value=Path("Spotify.exe")), \
             patch.object(spotify.subprocess, "Popen", side_effect=OSError("blocked")), \
             patch.object(spotify, "_open_uri", return_value=True):
            self.assertEqual(spotify.open_spotify(), "Opened Spotify.")

    def test_search_requires_query(self):
        self.assertIn("What would you like", spotify.search_spotify(""))

    def test_search_trims_query(self):
        with patch.object(spotify, "_open_uri", return_value=True) as opener:
            result = spotify.search_spotify("  Daft Punk  ")
        self.assertIn("Daft Punk", result)
        self.assertEqual(opener.call_args.args[0], "spotify:search:Daft%20Punk")

    def test_search_encodes_spaces_and_ampersands(self):
        with patch.object(spotify, "_open_uri", return_value=True) as opener:
            spotify.search_spotify("AC DC & Queen")
        self.assertEqual(opener.call_args.args[0], "spotify:search:AC%20DC%20%26%20Queen")

    def test_search_encodes_unicode(self):
        with patch.object(spotify, "_open_uri", return_value=True) as opener:
            spotify.search_spotify("Björk")
        self.assertIn("Bj%C3%B6rk", opener.call_args.args[0])

    def test_search_allows_track_artist_and_playlist_phrases(self):
        for phrase in ("track: Around the World", "artist: Daft Punk", "playlist: Focus"):
            with self.subTest(phrase=phrase), patch.object(spotify, "_open_uri", return_value=True):
                self.assertIn("Opened Spotify search", spotify.search_spotify(phrase))

    def test_search_enforces_maximum_length(self):
        self.assertIn("300 characters", spotify.search_spotify("x" * 301))

    def test_search_rejects_non_string_query(self):
        self.assertIn("Tell me what", spotify.search_spotify(None))

    def test_search_reports_uri_and_browser_failure(self):
        with patch.object(spotify, "_open_uri", return_value=False):
            self.assertIn("couldn't open Spotify search", spotify.search_spotify("Daft Punk"))

    def test_spotify_running_false_on_non_windows(self):
        with patch.object(spotify.os, "name", "posix"):
            self.assertFalse(spotify.spotify_is_running())

    def test_spotify_running_detects_tasklist_entry(self):
        fake = SimpleNamespace(returncode=0, stdout='"Spotify.exe","1234","Console","1","50,000 K"')
        with patch.object(spotify.os, "name", "nt"), patch.object(spotify.subprocess, "run", return_value=fake):
            self.assertTrue(spotify.spotify_is_running())

    def test_spotify_running_does_not_match_other_process(self):
        fake = SimpleNamespace(returncode=0, stdout='"SpotifyWebHelper.exe","1234","Console","1","50,000 K"')
        with patch.object(spotify.os, "name", "nt"), patch.object(spotify.subprocess, "run", return_value=fake):
            self.assertFalse(spotify.spotify_is_running())

    def test_spotify_running_handles_tasklist_error(self):
        with patch.object(spotify.os, "name", "nt"), patch.object(spotify.subprocess, "run", side_effect=OSError("tasklist missing")):
            self.assertFalse(spotify.spotify_is_running())

    def test_play_pause_sends_media_key_when_spotify_is_running(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), \
             patch.object(spotify, "_send_media_key") as key:
            result = spotify.spotify_control("play_pause")
        key.assert_called_once_with("play_pause")
        self.assertIn("play/pause", result)

    def test_next_sends_next_media_key_when_spotify_is_running(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), \
             patch.object(spotify, "_send_media_key") as key:
            result = spotify.spotify_control("next")
        key.assert_called_once_with("next")
        self.assertIn("next track", result)

    def test_previous_sends_previous_media_key_when_spotify_is_running(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), \
             patch.object(spotify, "_send_media_key") as key:
            result = spotify.spotify_control("previous")
        key.assert_called_once_with("previous")
        self.assertIn("previous track", result)

    def test_control_opens_spotify_if_not_running_without_sending_key(self):
        with patch.object(spotify, "spotify_is_running", return_value=False), \
             patch.object(spotify, "open_spotify", return_value="Opened Spotify.") as opener, \
             patch.object(spotify, "_send_media_key") as key:
            result = spotify.spotify_control("next")
        opener.assert_called_once()
        key.assert_not_called()
        self.assertIn("haven't sent a playback key", result)

    def test_control_reports_media_key_failure(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), \
             patch.object(spotify, "_send_media_key", side_effect=OSError("not supported")):
            self.assertIn("couldn't control Spotify", spotify.spotify_control("next"))

    def test_unknown_action_is_rejected(self):
        self.assertIn("not recognised", spotify.spotify_control("delete"))

    def test_open_action_delegates_to_open_spotify(self):
        with patch.object(spotify, "open_spotify", return_value="Opened Spotify.") as opener:
            self.assertEqual(spotify.spotify_control("open"), "Opened Spotify.")
        opener.assert_called_once()

    def test_search_action_delegates_to_search_spotify(self):
        with patch.object(spotify, "search_spotify", return_value="Search opened") as search:
            self.assertEqual(spotify.spotify_control("search", "Daft Punk"), "Search opened")
        search.assert_called_once_with("Daft Punk")

    def test_action_alias_pause_maps_to_toggle(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), patch.object(spotify, "_send_media_key") as key:
            spotify.spotify_control("pause")
        key.assert_called_once_with("play_pause")

    def test_action_alias_resume_maps_to_toggle(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), patch.object(spotify, "_send_media_key") as key:
            spotify.spotify_control("resume")
        key.assert_called_once_with("play_pause")

    def test_action_alias_skip_maps_to_next(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), patch.object(spotify, "_send_media_key") as key:
            spotify.spotify_control("skip")
        key.assert_called_once_with("next")

    def test_action_alias_back_maps_to_previous(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), patch.object(spotify, "_send_media_key") as key:
            spotify.spotify_control("back")
        key.assert_called_once_with("previous")

    def test_search_command_is_recognised(self):
        with patch.object(spotify, "spotify_control", return_value="searched") as action:
            self.assertEqual(spotify.handle_spotify_command("search Spotify for Daft Punk"), "searched")
        action.assert_called_once_with("search", "Daft Punk")

    def test_find_spotify_command_is_recognised(self):
        with patch.object(spotify, "spotify_control", return_value="searched") as action:
            spotify.handle_spotify_command("find Spotify for jazz")
        action.assert_called_once_with("search", "jazz")

    def test_play_track_on_spotify_becomes_search_not_false_play_claim(self):
        with patch.object(spotify, "spotify_control", return_value="search result") as action:
            result = spotify.handle_spotify_command("play Instant Crush by Daft Punk on Spotify")
        action.assert_called_once_with("search", "Instant Crush by Daft Punk")
        self.assertEqual(result, "search result")

    def test_search_phrase_with_question_mark_is_preserved(self):
        with patch.object(spotify, "spotify_control", return_value="searched") as action:
            spotify.handle_spotify_command("search Spotify for songs like this?")
        self.assertEqual(action.call_args.args[1], "songs like this")

    def test_pause_spotify_is_recognised(self):
        with patch.object(spotify, "spotify_control", return_value="paused") as action:
            spotify.handle_spotify_command("pause Spotify")
        action.assert_called_once_with("play_pause")

    def test_resume_spotify_is_recognised(self):
        with patch.object(spotify, "spotify_control", return_value="resumed") as action:
            spotify.handle_spotify_command("resume my Spotify music")
        action.assert_called_once_with("play_pause")

    def test_skip_song_on_spotify_is_recognised(self):
        with patch.object(spotify, "spotify_control", return_value="next") as action:
            spotify.handle_spotify_command("skip song on Spotify")
        action.assert_called_once_with("next")

    def test_next_track_on_spotify_is_recognised(self):
        with patch.object(spotify, "spotify_control", return_value="next") as action:
            spotify.handle_spotify_command("next track on Spotify")
        action.assert_called_once_with("next")

    def test_previous_track_on_spotify_is_recognised(self):
        with patch.object(spotify, "spotify_control", return_value="previous") as action:
            spotify.handle_spotify_command("previous track on Spotify")
        action.assert_called_once_with("previous")

    def test_back_on_spotify_is_recognised(self):
        with patch.object(spotify, "spotify_control", return_value="previous") as action:
            spotify.handle_spotify_command("Spotify back")
        action.assert_called_once_with("previous")

    def test_open_spotify_is_recognised(self):
        with patch.object(spotify, "open_spotify", return_value="opened") as opener:
            self.assertEqual(spotify.handle_spotify_command("open Spotify"), "opened")
        opener.assert_called_once()

    def test_unrelated_command_is_not_claimed(self):
        self.assertIsNone(spotify.handle_spotify_command("What is the weather?"))

    def test_empty_command_is_ignored(self):
        self.assertIsNone(spotify.handle_spotify_command("   "))

    def test_jarvis_wake_prefix_is_accepted(self):
        with patch.object(spotify, "spotify_control", return_value="paused") as action:
            spotify.handle_spotify_command("Jarvis, pause Spotify")
        action.assert_called_once_with("play_pause")

    def test_direct_request_routes_spotify_before_ollama(self):
        with patch.object(jarvis.spotify, "handle_spotify_command", return_value="Spotify handled"):
            self.assertEqual(jarvis._handle_direct_request("pause Spotify"), "Spotify handled")

    def test_spotify_tool_is_registered_for_model_actions(self):
        self.assertIn("spotify_control", jarvis.available_tools)
        self.assertIs(jarvis.available_tools["spotify_control"], spotify.spotify_control)

    def test_spotify_schema_is_present_for_tool_calling(self):
        names = [item["function"]["name"] for item in jarvis.OLLAMA_TOOL_SCHEMAS]
        self.assertIn("spotify_control", names)

    def test_tool_detection_includes_spotify_requests(self):
        self.assertTrue(jarvis._request_may_need_tools("Please search Spotify for ambient music"))

    def test_get_help_mentions_spotify(self):
        self.assertIn("Spotify", jarvis.get_help())

    def test_spotify_tool_schema_requires_action(self):
        item = next(item for item in jarvis.OLLAMA_TOOL_SCHEMAS if item["function"]["name"] == "spotify_control")
        self.assertEqual(item["function"]["parameters"]["required"], ["action"])

    def test_spotify_tool_schema_has_optional_query(self):
        item = next(item for item in jarvis.OLLAMA_TOOL_SCHEMAS if item["function"]["name"] == "spotify_control")
        self.assertIn("query", item["function"]["parameters"]["properties"])

    def test_control_action_is_case_insensitive(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), patch.object(spotify, "_send_media_key") as key:
            spotify.spotify_control("NEXT")
        key.assert_called_once_with("next")

    def test_control_action_accepts_spaces_and_hyphens(self):
        for action in ("play pause", "play-pause"):
            with self.subTest(action=action), patch.object(spotify, "spotify_is_running", return_value=True), patch.object(spotify, "_send_media_key") as key:
                spotify.spotify_control(action)
                key.assert_called_once_with("play_pause")

    def test_missing_query_argument_can_be_read_from_kwargs(self):
        with patch.object(spotify, "search_spotify", return_value="searched") as search:
            spotify.spotify_control(action="search", search="chill electronic")
        search.assert_called_once_with("chill electronic")

    def test_return_message_warns_about_other_active_media_sessions(self):
        with patch.object(spotify, "spotify_is_running", return_value=True), patch.object(spotify, "_send_media_key"):
            result = spotify.spotify_control("next")
        self.assertIn("another media app", result)


if __name__ == "__main__":
    unittest.main()


class SpotifyAppVolumeTests(unittest.TestCase):
    class FakeAudio:
        def __init__(self, volume=0.5, muted=False):
            self.volume = float(volume)
            self.muted = bool(muted)
            self.set_calls = []
            self.mute_calls = []

        def GetMasterVolume(self):
            return self.volume

        def SetMasterVolume(self, value, _event_context):
            self.set_calls.append(value)
            self.volume = float(value)

        def GetMute(self):
            return self.muted

        def SetMute(self, value, _event_context):
            self.mute_calls.append(value)
            self.muted = bool(value)

    class FakeSession:
        def __init__(self, process_name="Spotify.exe", volume=0.5, muted=False):
            self.Process = SimpleNamespace(name=lambda: process_name)
            self.SimpleAudioVolume = SpotifyAppVolumeTests.FakeAudio(volume, muted)

    def _with_sessions(self, sessions):
        return patch.object(spotify, "_run_on_spotify_audio_sessions",
                            side_effect=lambda operation: operation(sessions) if sessions else None)

    def test_volume_percentage_accepts_common_values(self):
        for value in (0, 1, 5, 10, 25, 33, 50, 66, 75, 90, 99, 100, "42", 42.5):
            with self.subTest(value=value):
                self.assertGreaterEqual(spotify._valid_volume_percent(value), 0)
                self.assertLessEqual(spotify._valid_volume_percent(value), 100)

    def test_volume_percentage_clamps_low_and_high_values(self):
        self.assertEqual(spotify._valid_volume_percent(-20), 0)
        self.assertEqual(spotify._valid_volume_percent(140), 100)

    def test_volume_percentage_rejects_invalid_values(self):
        for value in (None, "loud", object(), True, False, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                spotify._valid_volume_percent(value)

    def test_get_state_reads_spotify_session_only_and_averages_duplicates(self):
        sessions = [self.FakeSession(volume=0.4), self.FakeSession(volume=0.6)]
        with self._with_sessions(sessions):
            state = spotify.get_spotify_audio_state()
        self.assertEqual(state["volume"], 50)
        self.assertFalse(state["muted"])
        self.assertEqual(state["sessions"], 2)

    def test_get_state_reports_muted_when_any_spotify_session_is_muted(self):
        sessions = [self.FakeSession(volume=0.4), self.FakeSession(volume=0.6, muted=True)]
        with self._with_sessions(sessions):
            state = spotify.get_spotify_audio_state()
        self.assertTrue(state["muted"])

    def test_get_state_returns_none_without_spotify_session(self):
        with self._with_sessions([]):
            self.assertIsNone(spotify.get_spotify_audio_state())

    def test_get_volume_percent_returns_integer(self):
        sessions = [self.FakeSession(volume=0.735)]
        with self._with_sessions(sessions):
            self.assertEqual(spotify.get_spotify_volume_percent(), 74)

    def test_get_volume_percent_returns_none_without_session(self):
        with self._with_sessions([]):
            self.assertIsNone(spotify.get_spotify_volume_percent())

    def test_set_volume_targets_all_spotify_sessions(self):
        sessions = [self.FakeSession("Spotify.exe", 0.2), self.FakeSession("Spotify.exe", 0.8)]
        with self._with_sessions(sessions):
            result = spotify.set_spotify_volume_percent(35)
        self.assertEqual(result, 35)
        for session in sessions:
            self.assertEqual(session.SimpleAudioVolume.set_calls, [0.35])

    def test_set_volume_never_touches_non_spotify_session(self):
        spotify_session = self.FakeSession("Spotify.exe", 0.2)
        other_session = self.FakeSession("chrome.exe", 0.9)
        # The enumerator filters app sessions before calling this operation.
        with self._with_sessions([spotify_session]):
            spotify.set_spotify_volume_percent(25)
        self.assertEqual(spotify_session.SimpleAudioVolume.volume, 0.25)
        self.assertEqual(other_session.SimpleAudioVolume.volume, 0.9)
        self.assertEqual(other_session.SimpleAudioVolume.set_calls, [])

    def test_set_volume_clamps_to_zero(self):
        session = self.FakeSession()
        with self._with_sessions([session]):
            self.assertEqual(spotify.set_spotify_volume_percent(-4), 0)
        self.assertEqual(session.SimpleAudioVolume.volume, 0.0)

    def test_set_volume_clamps_to_one_hundred(self):
        session = self.FakeSession()
        with self._with_sessions([session]):
            self.assertEqual(spotify.set_spotify_volume_percent(140), 100)
        self.assertEqual(session.SimpleAudioVolume.volume, 1.0)

    def test_set_volume_returns_none_when_spotify_has_no_session(self):
        with self._with_sessions([]):
            self.assertIsNone(spotify.set_spotify_volume_percent(30))

    def test_adjust_volume_increases_by_default_five_percent(self):
        session = self.FakeSession(volume=0.5)
        with self._with_sessions([session]):
            result = spotify.adjust_spotify_volume_percent()
        self.assertEqual(result, 55)
        self.assertAlmostEqual(session.SimpleAudioVolume.volume, 0.55)

    def test_adjust_volume_decreases_by_negative_delta(self):
        session = self.FakeSession(volume=0.5)
        with self._with_sessions([session]):
            result = spotify.adjust_spotify_volume_percent(-10)
        self.assertEqual(result, 40)
        self.assertAlmostEqual(session.SimpleAudioVolume.volume, 0.4)

    def test_adjust_volume_clamps_at_maximum(self):
        session = self.FakeSession(volume=0.98)
        with self._with_sessions([session]):
            result = spotify.adjust_spotify_volume_percent(10)
        self.assertEqual(result, 100)
        self.assertEqual(session.SimpleAudioVolume.volume, 1.0)

    def test_adjust_volume_clamps_at_minimum(self):
        session = self.FakeSession(volume=0.02)
        with self._with_sessions([session]):
            result = spotify.adjust_spotify_volume_percent(-10)
        self.assertEqual(result, 0)
        self.assertEqual(session.SimpleAudioVolume.volume, 0.0)

    def test_adjust_volume_rejects_non_numeric_delta(self):
        with self.assertRaises(ValueError):
            spotify.adjust_spotify_volume_percent("a lot")

    def test_adjust_volume_rejects_boolean_delta(self):
        with self.assertRaises(ValueError):
            spotify.adjust_spotify_volume_percent(True)

    def test_adjust_volume_returns_none_without_session(self):
        with self._with_sessions([]):
            self.assertIsNone(spotify.adjust_spotify_volume_percent(5))

    def test_mute_targets_spotify_session(self):
        session = self.FakeSession()
        with self._with_sessions([session]):
            self.assertTrue(spotify.set_spotify_muted(True))
        self.assertEqual(session.SimpleAudioVolume.mute_calls, [1])

    def test_unmute_targets_spotify_session(self):
        session = self.FakeSession(muted=True)
        with self._with_sessions([session]):
            self.assertFalse(spotify.set_spotify_muted(False))
        self.assertEqual(session.SimpleAudioVolume.mute_calls, [0])

    def test_mute_returns_none_without_spotify_session(self):
        with self._with_sessions([]):
            self.assertIsNone(spotify.set_spotify_muted(True))

    def test_mute_rejects_non_boolean_value(self):
        with self.assertRaises(ValueError):
            spotify.set_spotify_muted(1)

    def test_session_helper_requires_windows(self):
        with patch.object(spotify.os, "name", "posix"):
            with self.assertRaises(OSError):
                spotify._run_on_spotify_audio_sessions(lambda sessions: len(sessions))

    def test_session_helper_initializes_and_uninitializes_com(self):
        import sys
        from types import ModuleType

        comtypes = ModuleType("comtypes")
        comtypes.CoInitialize = Mock()
        comtypes.CoUninitialize = Mock()
        pycaw = ModuleType("pycaw")
        pycaw.__path__ = []
        pycaw_module = ModuleType("pycaw.pycaw")
        pycaw_module.AudioUtilities = SimpleNamespace(GetAllSessions=Mock(return_value=[self.FakeSession()]))
        with patch.object(spotify.os, "name", "nt"), patch.dict(sys.modules, {
            "comtypes": comtypes, "pycaw": pycaw, "pycaw.pycaw": pycaw_module,
        }):
            result = spotify._run_on_spotify_audio_sessions(lambda sessions: len(sessions))
        self.assertEqual(result, 1)
        comtypes.CoInitialize.assert_called_once()
        comtypes.CoUninitialize.assert_called_once()

    def test_session_helper_filters_non_spotify_processes(self):
        import sys
        from types import ModuleType

        comtypes = ModuleType("comtypes")
        comtypes.CoInitialize = Mock()
        comtypes.CoUninitialize = Mock()
        pycaw = ModuleType("pycaw")
        pycaw.__path__ = []
        pycaw_module = ModuleType("pycaw.pycaw")
        spotify_session = self.FakeSession("Spotify.exe")
        chrome_session = self.FakeSession("chrome.exe")
        pycaw_module.AudioUtilities = SimpleNamespace(GetAllSessions=Mock(return_value=[spotify_session, chrome_session]))
        with patch.object(spotify.os, "name", "nt"), patch.dict(sys.modules, {
            "comtypes": comtypes, "pycaw": pycaw, "pycaw.pycaw": pycaw_module,
        }):
            result = spotify._run_on_spotify_audio_sessions(lambda sessions: sessions)
        self.assertEqual(result, [spotify_session])

    def test_session_helper_uses_all_devices_enumerator_when_available(self):
        import sys
        from types import ModuleType

        comtypes = ModuleType("comtypes")
        comtypes.CoInitialize = Mock()
        comtypes.CoUninitialize = Mock()
        pycaw = ModuleType("pycaw")
        pycaw.__path__ = []
        pycaw_module = ModuleType("pycaw.pycaw")
        all_devices = Mock(return_value=[self.FakeSession()])
        default_device = Mock(return_value=[])
        pycaw_module.AudioUtilities = SimpleNamespace(
            GetSessionsFromAllDevices=all_devices, GetAllSessions=default_device,
        )
        with patch.object(spotify.os, "name", "nt"), patch.dict(sys.modules, {
            "comtypes": comtypes, "pycaw": pycaw, "pycaw.pycaw": pycaw_module,
        }):
            result = spotify._run_on_spotify_audio_sessions(lambda sessions: len(sessions))
        self.assertEqual(result, 1)
        all_devices.assert_called_once()
        default_device.assert_not_called()

    def test_session_helper_uninitializes_com_after_operation_error(self):
        import sys
        from types import ModuleType

        comtypes = ModuleType("comtypes")
        comtypes.CoInitialize = Mock()
        comtypes.CoUninitialize = Mock()
        pycaw = ModuleType("pycaw")
        pycaw.__path__ = []
        pycaw_module = ModuleType("pycaw.pycaw")
        pycaw_module.AudioUtilities = SimpleNamespace(GetAllSessions=Mock(return_value=[self.FakeSession()]))
        with patch.object(spotify.os, "name", "nt"), patch.dict(sys.modules, {
            "comtypes": comtypes, "pycaw": pycaw, "pycaw.pycaw": pycaw_module,
        }):
            with self.assertRaises(RuntimeError):
                spotify._run_on_spotify_audio_sessions(lambda _sessions: (_ for _ in ()).throw(RuntimeError("test")))
        comtypes.CoUninitialize.assert_called_once()

    def test_set_volume_action_reports_spotify_only_scope(self):
        with patch.object(spotify, "set_spotify_volume_percent", return_value=30):
            result = spotify.spotify_control("set_volume", level=30)
        self.assertIn("Spotify's own volume to 30%", result)
        self.assertIn("other apps were not changed", result)

    def test_volume_up_action_uses_default_step(self):
        with patch.object(spotify, "adjust_spotify_volume_percent", return_value=55) as adjust:
            result = spotify.spotify_control("volume_up")
        adjust.assert_called_once_with(5.0)
        self.assertIn("55%", result)

    def test_volume_down_action_uses_default_step(self):
        with patch.object(spotify, "adjust_spotify_volume_percent", return_value=45) as adjust:
            result = spotify.spotify_control("volume_down")
        adjust.assert_called_once_with(-5.0)
        self.assertIn("45%", result)

    def test_volume_up_action_accepts_custom_delta(self):
        with patch.object(spotify, "adjust_spotify_volume_percent", return_value=60) as adjust:
            spotify.spotify_control("volume_up", level=10)
        adjust.assert_called_once_with(10.0)

    def test_volume_down_action_accepts_custom_delta(self):
        with patch.object(spotify, "adjust_spotify_volume_percent", return_value=40) as adjust:
            spotify.spotify_control("volume_down", level=10)
        adjust.assert_called_once_with(-10.0)

    def test_get_volume_action_formats_current_state(self):
        with patch.object(spotify, "get_spotify_audio_state", return_value={"volume": 42, "muted": False, "sessions": 1}):
            result = spotify.spotify_control("get_volume")
        self.assertIn("42%", result)
        self.assertIn("master volume and other apps are unchanged", result)

    def test_get_volume_action_explains_missing_audio_session(self):
        with patch.object(spotify, "get_spotify_audio_state", return_value=None):
            self.assertIn("Start playing something in Spotify", spotify.spotify_control("get_volume"))

    def test_set_volume_action_requires_level(self):
        self.assertIn("Tell me the Spotify volume", spotify.spotify_control("set_volume"))

    def test_set_volume_action_rejects_bad_level_truthfully(self):
        with patch.object(spotify, "set_spotify_volume_percent", side_effect=ValueError("invalid")):
            self.assertIn("couldn't change Spotify's app volume", spotify.spotify_control("set_volume", level="bad"))

    def test_mute_action_targets_spotify_only(self):
        with patch.object(spotify, "set_spotify_muted", return_value=True) as mute:
            result = spotify.spotify_control("mute")
        mute.assert_called_once_with(True)
        self.assertIn("Muted Spotify only", result)

    def test_unmute_action_targets_spotify_only(self):
        with patch.object(spotify, "set_spotify_muted", return_value=False) as unmute:
            result = spotify.spotify_control("unmute")
        unmute.assert_called_once_with(False)
        self.assertIn("Unmuted Spotify only", result)

    def test_volume_command_set_spotify_volume_to_percent(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            self.assertEqual(spotify.handle_spotify_command("set Spotify volume to 35%"), "ok")
        action.assert_called_once_with("set_volume", level="35")

    def test_volume_command_set_volume_without_percent_symbol(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("set Spotify's volume to 35")
        action.assert_called_once_with("set_volume", level="35")

    def test_volume_command_turn_spotify_volume_up(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("turn Spotify volume up")
        action.assert_called_once_with("volume_up")

    def test_volume_command_turn_spotify_volume_down(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("turn Spotify volume down")
        action.assert_called_once_with("volume_down")

    def test_volume_command_turn_volume_of_spotify_down(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("turn the volume of Spotify down")
        action.assert_called_once_with("volume_down")

    def test_volume_command_increase_by_custom_percentage(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("increase Spotify volume by 12 percent")
        action.assert_called_once_with("volume_up", level="12")

    def test_volume_command_decrease_by_custom_percentage(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("lower Spotify's volume by 8%")
        action.assert_called_once_with("volume_down", level="8")

    def test_volume_command_query_current_volume(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("what's Spotify's volume?")
        action.assert_called_once_with("get_volume")

    def test_volume_command_mute_spotify(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("mute Spotify")
        action.assert_called_once_with("mute")

    def test_volume_command_unmute_spotify(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("unmute my Spotify")
        action.assert_called_once_with("unmute")

    def test_volume_command_volume_up_alias(self):
        with patch.object(spotify, "spotify_control", return_value="ok") as action:
            spotify.handle_spotify_command("Spotify volume up")
        action.assert_called_once_with("volume_up")

    def test_volume_commands_do_not_claim_unqualified_system_volume(self):
        self.assertIsNone(spotify.handle_spotify_command("turn the volume up"))

    def test_volume_tool_schema_has_optional_level(self):
        item = next(item for item in jarvis.OLLAMA_TOOL_SCHEMAS if item["function"]["name"] == "spotify_control")
        properties = item["function"]["parameters"]["properties"]
        self.assertIn("level", properties)
        self.assertEqual(properties["level"]["type"], "number")
        self.assertEqual(item["function"]["parameters"]["required"], ["action"])

    def test_help_mentions_spotify_only_volume(self):
        self.assertIn("Spotify-only volume", jarvis.get_help())

    def test_gui_has_dedicated_spotify_volume_slider(self):
        source = (Path(__file__).resolve().parents[1] / "JARVIS_GUI.py").read_text(encoding="utf-8")
        self.assertIn('text="SPOTIFY APP VOLUME"', source)
        self.assertIn('from_=0, to=100, orient="horizontal"', source)
        self.assertIn("Only changes Spotify", source)

    def test_build_requirements_include_pycaw(self):
        requirements = (Path(__file__).resolve().parents[1] / "requirements-build.txt").read_text(encoding="utf-8")
        self.assertRegex(requirements, r"(?m)^pycaw>=")

    def test_pyinstaller_collects_pycaw(self):
        build = (Path(__file__).resolve().parents[1] / "build_release.bat").read_text(encoding="utf-8")
        self.assertIn("--collect-all pycaw", build)

