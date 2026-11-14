"""Tests for the v1.7.0 automatic update policy."""

import unittest

import launcher


class AutomaticUpdatePolicyTests(unittest.TestCase):
    def test_explicit_true_enables_automatic_install(self):
        self.assertTrue(launcher.auto_install_enabled({"auto_install": True}))

    def test_missing_setting_keeps_prompted_updates(self):
        self.assertFalse(launcher.auto_install_enabled({"github_repo": "owner/repo"}))

    def test_explicit_false_keeps_prompted_updates(self):
        self.assertFalse(launcher.auto_install_enabled({"auto_install": False}))

    def test_string_true_does_not_enable_automatic_install(self):
        self.assertFalse(launcher.auto_install_enabled({"auto_install": "true"}))

    def test_non_dictionary_config_is_disabled(self):
        self.assertFalse(launcher.auto_install_enabled(None))
        self.assertFalse(launcher.auto_install_enabled([]))


if __name__ == "__main__":
    unittest.main()
