from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import JARVIS as jarvis


class OllamaAutoStartTests(unittest.TestCase):
    def setUp(self):
        self.old_process = jarvis._OLLAMA_SERVER_PROCESS
        jarvis._OLLAMA_SERVER_PROCESS = None

    def tearDown(self):
        jarvis._OLLAMA_SERVER_PROCESS = self.old_process

    def test_uses_existing_server_without_starting_a_process(self):
        with patch.object(jarvis, "get_installed_ollama_models", return_value=["gemma4:e2b"]), \
             patch.object(jarvis, "_start_ollama_server") as start:
            result = jarvis.ensure_ollama_available(timeout=1)
        self.assertEqual(result, ["gemma4:e2b"])
        start.assert_not_called()

    def test_starts_server_when_local_api_is_offline_then_retries(self):
        responses = [ConnectionError("offline"), ["gemma4:e2b"]]
        fake_process = Mock()
        fake_process.poll.return_value = None
        with patch.object(jarvis, "get_installed_ollama_models", side_effect=responses), \
             patch.object(jarvis, "_start_ollama_server", return_value=True) as start, \
             patch.object(jarvis.time, "sleep"):
            result = jarvis.ensure_ollama_available(timeout=1, poll_interval=0.01)
        self.assertEqual(result, ["gemma4:e2b"])
        start.assert_called_once_with()

    def test_does_not_start_local_server_for_remote_ollama_host(self):
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://192.0.2.10:11434"}), \
             patch.object(jarvis, "get_installed_ollama_models", side_effect=ConnectionError("offline")), \
             patch.object(jarvis, "_start_ollama_server") as start:
            with self.assertRaisesRegex(ConnectionError, "remote Ollama server"):
                jarvis.ensure_ollama_available(timeout=0.1)
        start.assert_not_called()

    def test_reports_missing_local_ollama_executable(self):
        with patch.object(jarvis, "get_installed_ollama_models", side_effect=ConnectionError("offline")), \
             patch.object(jarvis, "find_ollama_executable", return_value=None):
            with self.assertRaisesRegex(ConnectionError, "could not be started automatically"):
                jarvis.ensure_ollama_available(timeout=0.1)

    def test_finds_standard_per_user_windows_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            exe = Path(temporary) / "Programs" / "Ollama" / "ollama.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"fake executable")
            with patch("JARVIS.shutil.which", return_value=None), \
                 patch.dict(os.environ, {"LOCALAPPDATA": temporary, "ProgramFiles": "", "ProgramFiles(x86)": ""}, clear=False):
                found = jarvis.find_ollama_executable()
        self.assertEqual(found, exe.resolve())

    def test_start_command_uses_serve_and_suppresses_console(self):
        with tempfile.TemporaryDirectory() as temporary:
            exe = Path(temporary) / "ollama.exe"
            exe.write_bytes(b"fake executable")
            fake_process = Mock()
            fake_process.pid = 4321
            with patch.object(jarvis, "find_ollama_executable", return_value=exe), \
                 patch.object(jarvis, "_ollama_target_is_local", return_value=True), \
                 patch.object(jarvis, "user_data_dir", return_value=Path(temporary)), \
                 patch.object(jarvis.subprocess, "Popen", return_value=fake_process) as popen, \
                 patch.object(jarvis.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                 patch.object(jarvis.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, create=True), \
                 patch.object(jarvis.sys, "platform", "win32"):
                started = jarvis._start_ollama_server()
            self.assertTrue(started)
            args, kwargs = popen.call_args
            self.assertEqual(args[0], [str(exe), "serve"])
            self.assertNotEqual(kwargs["creationflags"], 0)
            self.assertEqual(kwargs["stdin"], jarvis.subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], jarvis.subprocess.STDOUT)

    def test_reuses_managed_server_process_instead_of_spawning_twice(self):
        process = Mock()
        process.poll.return_value = None
        jarvis._OLLAMA_SERVER_PROCESS = process
        with patch.object(jarvis, "find_ollama_executable") as find_exe, \
             patch.object(jarvis.subprocess, "Popen") as popen:
            self.assertFalse(jarvis._start_ollama_server())
        find_exe.assert_not_called()
        popen.assert_not_called()

    def test_ollama_status_uses_autostart_recovery(self):
        with patch.object(jarvis, "ensure_ollama_available", return_value=["gemma4:e2b"]) as ensure, \
             patch.object(jarvis, "MODEL_NAME", "gemma4:e2b"), \
             patch.object(jarvis, "NUM_CTX", 8192):
            ok, message = jarvis.check_ollama_status()
        self.assertTrue(ok)
        self.assertIn("Ollama online", message)
        ensure.assert_called_once_with(timeout=12.0)

    def test_create_client_recovers_server_before_connecting(self):
        import types
        fake_client = object()
        fake_ollama = types.SimpleNamespace(Client=Mock(return_value=fake_client))
        with patch.dict("sys.modules", {"ollama": fake_ollama}), \
             patch.object(jarvis, "ensure_ollama_available", return_value=["gemma4:e2b"]) as ensure, \
             patch.object(jarvis, "_OLLAMA_ACTIVE_HOST", "http://127.0.0.1:11434"):
            result = jarvis.create_ollama_client()
        self.assertIs(result, fake_client)
        ensure.assert_called_once_with(timeout=12.0)
        fake_ollama.Client.assert_called_once_with(host="http://127.0.0.1:11434", trust_env=False)

    def test_invalid_startup_timeout_is_rejected(self):
        for value in (0, -1, True, "5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                jarvis.ensure_ollama_available(timeout=value)

    def test_invalid_poll_interval_is_rejected(self):
        for value in (0, -1, True, "0.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                jarvis.ensure_ollama_available(timeout=1, poll_interval=value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
