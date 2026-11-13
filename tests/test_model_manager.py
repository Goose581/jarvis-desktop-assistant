from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import jarvis_model_manager as manager


class FakeResponse:
    def __init__(self, lines=None, status=200):
        self.lines = list(lines or [])
        self.status = status
        self.read_called = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)

    def read(self, _size=-1):
        self.read_called = True
        return b"{}"


class ModelTagValidationTests(unittest.TestCase):
    def test_accepts_common_model_tags(self):
        for tag in ("gemma4:e2b", "llama3.2:1b", "qwen2.5:3b", "namespace/model:tag", "model_name-v2"):
            with self.subTest(tag=tag):
                self.assertEqual(manager.validate_model_tag(tag), tag)

    def test_trims_surrounding_whitespace(self):
        self.assertEqual(manager.validate_model_tag("  gemma4:e2b  "), "gemma4:e2b")

    def test_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            manager.validate_model_tag(" ")

    def test_rejects_spaces(self):
        with self.assertRaises(ValueError):
            manager.validate_model_tag("gemma 4")

    def test_rejects_shell_metacharacters(self):
        for tag in ("model;whoami", "model|x", "model&x", "model`x", "model$(x)", "model\\x"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                manager.validate_model_tag(tag)

    def test_rejects_leading_slash(self):
        with self.assertRaises(ValueError):
            manager.validate_model_tag("/model:latest")

    def test_rejects_leading_dot(self):
        with self.assertRaises(ValueError):
            manager.validate_model_tag(".model:latest")

    def test_rejects_double_dot(self):
        with self.assertRaises(ValueError):
            manager.validate_model_tag("model..tag")

    def test_rejects_overlong_name(self):
        with self.assertRaises(ValueError):
            manager.validate_model_tag("m" * 101)

    def test_catalogue_entries_are_valid_tags(self):
        for item in manager.MODEL_CATALOGUE:
            with self.subTest(model=item["name"]):
                self.assertEqual(manager.validate_model_tag(item["name"]), item["name"])


class ModelDisplayTests(unittest.TestCase):
    def test_format_bytes_zero(self):
        self.assertEqual(manager.format_bytes(0), "0 B")

    def test_format_bytes_kilobytes(self):
        self.assertEqual(manager.format_bytes(2048), "2 KB")

    def test_format_bytes_megabytes(self):
        self.assertEqual(manager.format_bytes(8 * 1024 * 1024), "8 MB")

    def test_format_bytes_gigabytes(self):
        self.assertEqual(manager.format_bytes(5 * 1024 ** 3), "5.0 GB")

    def test_format_bytes_fractional_gigabytes(self):
        self.assertEqual(manager.format_bytes(int(1.5 * 1024 ** 3)), "1.5 GB")

    def test_format_bytes_negative_clamped(self):
        self.assertEqual(manager.format_bytes(-100), "0 B")

    def test_format_bytes_invalid_value_is_safe(self):
        self.assertEqual(manager.format_bytes("bad"), "0 B")

    def test_list_models_sorts_and_extracts_metadata(self):
        payload = {"models": [
            {"name": "zeta:latest", "size": 2048, "details": {"parameter_size": "3B", "quantization_level": "Q4_K_M", "family": "llama"}},
            {"model": "alpha:latest", "size": 1024, "details": {"parameter_size": "2B", "quantization_level": "Q8_0", "family": "gemma"}},
        ]}
        with patch.object(manager.assistant, "_fetch_ollama_json", return_value=(payload, "http://127.0.0.1:11434")):
            rows = manager.list_models()
        self.assertEqual([row["name"] for row in rows], ["alpha:latest", "zeta:latest"])
        self.assertEqual(rows[1]["parameter_size"], "3B")
        self.assertEqual(rows[1]["size"], 2048)

    def test_list_models_skips_malformed_rows(self):
        payload = {"models": [None, {}, {"name": 7}, {"name": "valid:model", "details": "bad"}]}
        with patch.object(manager.assistant, "_fetch_ollama_json", return_value=(payload, "http://127.0.0.1:11434")):
            rows = manager.list_models()
        self.assertEqual([row["name"] for row in rows], ["valid:model"])
        self.assertEqual(rows[0]["parameter_size"], "")

    def test_list_models_rejects_non_list_payload(self):
        with patch.object(manager.assistant, "_fetch_ollama_json", return_value=({"models": {}}, "http://127.0.0.1:11434")):
            with self.assertRaises(ValueError):
                manager.list_models()


class ModelPullTests(unittest.TestCase):
    def setUp(self):
        self.host_patch = patch.object(manager.assistant, "_ollama_api_base", return_value="http://127.0.0.1:11434")
        self.host_patch.start()
        self.addCleanup(self.host_patch.stop)

    def test_pull_sends_model_and_stream_flag(self):
        response = FakeResponse([json.dumps({"status": "success"}).encode() + b"\n"])
        with patch.object(manager.assistant, "_ollama_urlopen", return_value=response) as open_url:
            self.assertEqual(manager.pull_model("gemma4:e2b"), "gemma4:e2b")
        request = open_url.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/pull")
        self.assertEqual(body, {"model": "gemma4:e2b", "stream": True})
        self.assertEqual(request.get_method(), "POST")

    def test_pull_reports_progress_percent(self):
        lines = [
            b'{"status":"pulling manifest"}\n',
            b'{"status":"downloading","completed":250,"total":1000}\n',
            b'{"status":"success"}\n',
        ]
        events = []
        with patch.object(manager.assistant, "_ollama_urlopen", return_value=FakeResponse(lines)):
            manager.pull_model("gemma4:e2b", progress_callback=events.append)
        self.assertTrue(any(event.get("percent") == 25 for event in events))
        self.assertEqual(events[-1]["status"], "success")

    def test_pull_reports_status_without_total(self):
        events = []
        lines = [b'{"status":"verifying sha256 digest"}\n', b'{"status":"success"}\n']
        with patch.object(manager.assistant, "_ollama_urlopen", return_value=FakeResponse(lines)):
            manager.pull_model("model:tag", progress_callback=events.append)
        self.assertEqual(events[0]["percent"], 0)

    def test_pull_surfaces_server_error(self):
        response = FakeResponse([b'{"error":"model not found"}\n'])
        with patch.object(manager.assistant, "_ollama_urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "model not found"):
                manager.pull_model("missing:model")

    def test_pull_rejects_invalid_timeout(self):
        for timeout in (0, -1, True, "bad"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                manager.pull_model("gemma4:e2b", timeout=timeout)

    def test_pull_rejects_invalid_model_before_network(self):
        with patch.object(manager.assistant, "_ollama_urlopen") as open_url:
            with self.assertRaises(ValueError):
                manager.pull_model("bad model")
            open_url.assert_not_called()

    def test_pull_fallback_verifies_model_if_stream_has_no_success_marker(self):
        response = FakeResponse([b'{"status":"pulling manifest"}\n'])
        with patch.object(manager.assistant, "_ollama_urlopen", return_value=response), \
             patch.object(manager, "list_models", return_value=[{"name": "model:tag"}]):
            self.assertEqual(manager.pull_model("model:tag"), "model:tag")

    def test_pull_missing_success_and_missing_model_raises(self):
        response = FakeResponse([b'{"status":"pulling manifest"}\n'])
        with patch.object(manager.assistant, "_ollama_urlopen", return_value=response), \
             patch.object(manager, "list_models", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "ended the download stream"):
                manager.pull_model("model:tag")

    def test_pull_invalid_json_line_is_reported(self):
        response = FakeResponse([b"not-json\n"])
        with patch.object(manager.assistant, "_ollama_urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "unreadable download-progress"):
                manager.pull_model("model:tag")

    def test_pull_error_object_without_message_is_safe(self):
        response = FakeResponse([b'{"error":"" ,"status":"success"}\n'])
        with patch.object(manager.assistant, "_ollama_urlopen", return_value=response):
            self.assertEqual(manager.pull_model("model:tag"), "model:tag")


class ModelDeleteTests(unittest.TestCase):
    def test_delete_uses_delete_method_and_model_field(self):
        response = FakeResponse(status=200)
        with patch.object(manager.assistant, "_ollama_api_base", return_value="http://127.0.0.1:11434"), \
             patch.object(manager.assistant, "_ollama_urlopen", return_value=response) as open_url:
            self.assertEqual(manager.delete_model("old:model"), "old:model")
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), "DELETE")
        self.assertEqual(json.loads(request.data.decode("utf-8")), {"model": "old:model"})
        self.assertTrue(response.read_called)

    def test_delete_rejects_invalid_tag_before_network(self):
        with patch.object(manager.assistant, "_ollama_urlopen") as open_url:
            with self.assertRaises(ValueError):
                manager.delete_model("bad model")
            open_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
