from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher


class StartupUpdateDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app_dir = self.root / "app"
        self.app_dir.mkdir()
        (self.app_dir / "version.txt").write_text("1.6.1", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def release(tag="v1.6.2"):
        return {
            "tag_name": tag,
            "name": "J.A.R.V.I.S. v1.6.2",
            "body": "## What's new\n\n- Better startup prompt\n- Safer updater",
            "html_url": "https://github.com/Goose581/jarvis-desktop-assistant/releases/tag/v1.6.2",
            "assets": [
                {"name": "JARVIS-Windows.zip", "browser_download_url": "https://github.com/example/app.zip"},
                {"name": "JARVIS-Windows.zip.sha256", "browser_download_url": "https://github.com/example/app.zip.sha256"},
            ],
        }

    def test_equal_version_does_not_offer_update(self):
        with patch("launcher.latest_release", return_value=self.release("v1.6.1")):
            self.assertIsNone(launcher.check_for_update(self.app_dir, "owner/repo"))

    def test_older_release_does_not_offer_update(self):
        with patch("launcher.latest_release", return_value=self.release("v1.6.0")):
            self.assertIsNone(launcher.check_for_update(self.app_dir, "owner/repo"))

    def test_newer_release_returns_prompt_details_and_assets(self):
        with patch("launcher.latest_release", return_value=self.release()):
            result = launcher.check_for_update(self.app_dir, "owner/repo")
        self.assertEqual(result["current_version"], "1.6.1")
        self.assertEqual(result["version"], "1.6.2")
        self.assertIn("Better startup prompt", result["body"])
        self.assertTrue(result["zip_url"].startswith("https://"))
        self.assertTrue(result["checksum_url"].startswith("https://"))

    def test_newer_release_check_does_not_download_before_consent(self):
        with patch("launcher.latest_release", return_value=self.release()), patch("launcher.download") as download:
            result = launcher.check_for_update(self.app_dir, "owner/repo")
        self.assertIsNotNone(result)
        download.assert_not_called()

    def test_missing_checksum_asset_prevents_update_offer(self):
        release = self.release()
        release["assets"] = release["assets"][:1]
        with patch("launcher.latest_release", return_value=release):
            with self.assertRaisesRegex(ValueError, "missing required asset"):
                launcher.check_for_update(self.app_dir, "owner/repo")

    def test_invalid_release_tag_is_rejected(self):
        with patch("launcher.latest_release", return_value=self.release("v1.6.beta")):
            with self.assertRaisesRegex(ValueError, "numeric version"):
                launcher.check_for_update(self.app_dir, "owner/repo")

    def test_release_notes_are_sanitised_and_bounded(self):
        cleaned = launcher._clean_release_notes("## Title\n\nSee [the page](https://example.com) <b>now</b>")
        self.assertIn("Title", cleaned)
        self.assertIn("the page", cleaned)
        self.assertNotIn("https://example.com", cleaned)
        self.assertNotIn("<b>", cleaned)
        self.assertLessEqual(len(launcher._clean_release_notes("x" * 4000, limit=120)), 150)


class StartupUpdateConsentFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "update_config.json").write_text(json.dumps({"github_repo": "owner/repo"}), encoding="utf-8")
        self.app_dir = self.root / "app"
        self.app_dir.mkdir()
        (self.app_dir / "version.txt").write_text("1.6.1", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def update_info():
        return {
            "version": "1.6.2",
            "current_version": "1.6.1",
            "name": "J.A.R.V.I.S. v1.6.2",
            "body": "Update prompt test",
            "zip_url": "https://example.com/app.zip",
            "checksum_url": "https://example.com/app.zip.sha256",
        }

    def _run_main(self, update, accepted=False):
        patchers = {
            "root": patch("launcher.install_root", return_value=self.root),
            "recover": patch("launcher.recover_interrupted_update"),
            "check": patch("launcher.check_for_update", return_value=update),
            "prompt": patch("launcher.prompt_for_update", return_value=accepted),
            "download": patch("launcher.show_download_progress", return_value=self.root / "update.zip"),
            "launch": patch("launcher.launch_app"),
            "popen": patch("launcher.subprocess.Popen"),
        }
        mocks = {}
        started = []
        try:
            for name, patcher in patchers.items():
                mocks[name] = patcher.start()
                started.append(patcher)
            result = launcher.main()
            return result, mocks["prompt"], mocks["download"], mocks["launch"], mocks["popen"]
        finally:
            for patcher in reversed(started):
                patcher.stop()

    def test_skipping_update_launches_current_app_without_downloading(self):
        update = self.update_info()
        result, prompt, download, launch, popen = self._run_main(update, accepted=False)
        self.assertEqual(result, 0)
        prompt.assert_called_once()
        download.assert_not_called()
        launch.assert_called_once_with(self.app_dir)
        popen.assert_not_called()

    def test_accepting_update_downloads_then_starts_helper(self):
        update = self.update_info()
        result, prompt, download, launch, popen = self._run_main(update, accepted=True)
        self.assertEqual(result, 0)
        prompt.assert_called_once()
        download.assert_called_once_with(update)
        launch.assert_not_called()
        popen.assert_called_once()
        command = popen.call_args.args[0]
        self.assertIn("--apply-update", command)

    def test_no_update_launches_current_app_without_prompt(self):
        result, prompt, download, launch, popen = self._run_main(None, accepted=True)
        self.assertEqual(result, 0)
        prompt.assert_not_called()
        download.assert_not_called()
        launch.assert_called_once_with(self.app_dir)
        popen.assert_not_called()

    def test_update_check_error_fails_open_to_current_app(self):
        launch_patch = patch("launcher.launch_app")
        with patch("launcher.install_root", return_value=self.root), \
             patch("launcher.recover_interrupted_update"), \
             patch("launcher.check_for_update", side_effect=OSError("offline")), \
             patch("launcher.show_error"), \
             launch_patch as launch:
            self.assertEqual(launcher.main(), 0)
            launch.assert_called_once_with(self.app_dir)



if __name__ == "__main__":
    unittest.main(verbosity=2)
