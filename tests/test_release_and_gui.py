from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

import JARVIS as jarvis
from JARVIS_GUI import JarvisApp

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_versions_stay_in_sync(self):
        version = jarvis.APP_VERSION
        files_and_patterns = {
            "build_release.bat": rf'^set "APP_VERSION={re.escape(version)}"$',
            "launcher.py": rf'^USER_AGENT = "JARVIS-Windows-Updater/{re.escape(version)}"$',
            "installer.iss": rf'^  #define MyAppVersion "{re.escape(version)}"$',
            "README.md": rf"tag and title to `v{re.escape(version)}`",
            "CHANGELOG.md": rf"^## v{re.escape(version)} — ",
        }
        for filename, pattern in files_and_patterns.items():
            with self.subTest(filename=filename):
                contents = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
                self.assertIsNotNone(re.search(pattern, contents, flags=re.MULTILINE), f"{filename} does not match the version {version}")

    def test_windows_ci_workflow_runs_on_windows_and_executes_tests(self):
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "windows-ci.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: windows-latest", workflow)
        self.assertIn("actions/checkout@v7", workflow)
        self.assertIn("actions/setup-python@v7", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)

    def test_update_config_contains_repository_owner_and_name(self):
        import json

        config = json.loads((PROJECT_ROOT / "update_config.json").read_text(encoding="utf-8"))
        self.assertRegex(config.get("github_repo", ""), r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GuiShutdownTests(unittest.TestCase):
    class FakeRoot:
        def __init__(self, geometry_error: Exception | None = None):
            self.geometry_error = geometry_error
            self.unbound = False
            self.destroyed = False

        def geometry(self):
            if self.geometry_error:
                raise self.geometry_error
            return "1180x790+0+0"

        def unbind_all(self, _sequence):
            self.unbound = True

        def destroy(self):
            self.destroyed = True

    def _new_app(self, root):
        app = JarvisApp.__new__(JarvisApp)
        app.root = root
        app.closing = False
        return app

    def test_close_still_destroys_window_when_settings_save_fails(self):
        root = self.FakeRoot()
        app = self._new_app(root)
        callback_before = jarvis.ui_message_callback
        try:
            with patch("JARVIS_GUI.assistant.save_settings", side_effect=RuntimeError("simulated settings failure")), \
                 patch("JARVIS_GUI.assistant.log_error") as log_error:
                app.close()
                self.assertTrue(app.closing)
                self.assertTrue(root.unbound)
                self.assertTrue(root.destroyed)
                log_error.assert_called_once()
        finally:
            jarvis.ui_message_callback = callback_before

    def test_close_still_destroys_window_when_geometry_lookup_fails(self):
        root = self.FakeRoot(geometry_error=RuntimeError("simulated Tk geometry failure"))
        app = self._new_app(root)
        callback_before = jarvis.ui_message_callback
        try:
            with patch("JARVIS_GUI.assistant.log_error") as log_error:
                app.close()
                self.assertTrue(app.closing)
                self.assertTrue(root.unbound)
                self.assertTrue(root.destroyed)
                log_error.assert_called_once()
        finally:
            jarvis.ui_message_callback = callback_before

    def test_close_is_idempotent(self):
        root = self.FakeRoot()
        app = self._new_app(root)
        app.closing = True
        with patch("JARVIS_GUI.assistant.save_settings") as save_settings:
            app.close()
            save_settings.assert_not_called()
            self.assertFalse(root.destroyed)


class GuiVisualDesignTests(unittest.TestCase):
    def test_blue_turquoise_theme_palette_is_defined(self):
        import JARVIS_GUI as gui

        self.assertEqual(gui.BG, "#071426")
        self.assertEqual(gui.ACCENT, "#38E0D0")
        self.assertEqual(gui.BLUE, "#398BFF")
        self.assertEqual(gui.SIDEBAR, "#091B31")

    def test_command_centre_dashboard_sections_are_present(self):
        source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        for marker in (
            "Command Centre", "YOUR PERSONAL AI IS READY", "QUICK LAUNCH",
            "SYSTEM SNAPSHOT", "LOCAL AI CORE", "Conversation", "Explore tools",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_chat_messages_use_distinct_user_and_assistant_identity_styles(self):
        source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        self.assertIn('"YOU  ·  MESSAGE"', source)
        self.assertIn('"J.A.R.V.I.S.  ·  LOCAL INTELLIGENCE"', source)
        self.assertIn('"#10375B"', source)
        self.assertIn('"#0E2B43"', source)

    def test_window_default_is_large_enough_for_dashboard(self):
        gui_source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        assistant_source = (PROJECT_ROOT / "JARVIS.py").read_text(encoding="utf-8")
        self.assertIn('settings.get("window_geometry", "1360x860")', gui_source)
        self.assertIn('"window_geometry": "1360x860"', assistant_source)
        self.assertIn("self.root.minsize(1080, 700)", gui_source)


class GuiThemeTests(unittest.TestCase):
    def test_six_named_palettes_are_available(self):
        import JARVIS_GUI as gui

        self.assertEqual(set(gui.THEMES), set(jarvis.SUPPORTED_THEMES))
        self.assertEqual(len(gui.THEME_NAMES), 6)
        self.assertEqual(len(set(gui.THEME_NAMES.values())), 6)

    def test_all_palettes_define_the_same_semantic_roles(self):
        import JARVIS_GUI as gui

        roles = set(gui.THEMES["midnight"])
        self.assertGreaterEqual(len(roles), 50)
        for name, palette in gui.THEMES.items():
            with self.subTest(theme=name):
                self.assertEqual(set(palette), roles)
                for colour in palette.values():
                    self.assertRegex(colour, r"^#[0-9A-Fa-f]{6}$")
                self.assertEqual(len(set(palette.values())), len(palette), "Palette colours must be unique so semantic recolouring stays stable")

    def test_original_gui_literals_are_all_theme_mapped(self):
        import JARVIS_GUI as gui

        source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        colours = {value.lower() for value in re.findall(r"#[0-9A-Fa-f]{6}", source)}
        known = {value.lower() for value in gui._BASE_COLOR_TO_ROLE}
        self.assertTrue(colours.intersection(known))
        self.assertTrue({"#071426", "#0d233a", "#38e0d0", "#eaf7ff"}.issubset(known))

    def test_theme_selector_is_inside_assistant_settings(self):
        source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        self.assertIn('text="Appearance theme"', source)
        self.assertIn('theme_combo.bind("<<ComboboxSelected>>", preview_theme)', source)
        self.assertIn("assistant.save_settings(", source)
        self.assertIn("theme=self.theme_name", source)

    def test_theme_preview_cancel_restores_previous_theme(self):
        source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        self.assertIn("original_theme = self.theme_name", source)
        self.assertIn("self.apply_theme(original_theme)", source)

    def test_theme_applies_to_workspace_and_new_chat_messages(self):
        source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        self.assertIn('self._apply_theme_tree(window, THEMES[self.theme_name])', source)
        self.assertIn('self._apply_theme_tree(row, THEMES[self.theme_name])', source)
        self.assertIn('self._apply_theme_tree(cards_frame, THEMES[self.theme_name])', source)

    def test_theme_tree_recolours_nested_fake_widgets_and_remembers_roles(self):
        import JARVIS_GUI as gui

        class FakeWidget:
            def __init__(self, **options):
                self.options = options
                self.children = []
            def winfo_children(self):
                return self.children
            def keys(self):
                return tuple(self.options)
            def cget(self, key):
                return self.options[key]
            def configure(self, **changes):
                self.options.update(changes)

        child = FakeWidget(background="#0D223B", foreground="#EAF7FF")
        root = FakeWidget(background="#071426", foreground="#38E0D0")
        root.children.append(child)
        app = JarvisApp.__new__(JarvisApp)
        app._apply_theme_tree(root, gui.THEMES["midnight"])
        app._apply_theme_tree(root, gui.THEMES["violet"])
        self.assertEqual(root.options["background"], gui.THEMES["violet"]["BG"])
        self.assertEqual(root.options["foreground"], gui.THEMES["violet"]["ACCENT"])
        self.assertEqual(child.options["background"], gui.THEMES["violet"]["PANEL"])
        self.assertEqual(child.options["foreground"], gui.THEMES["violet"]["TEXT"])
        app._apply_theme_tree(root, gui.THEMES["arctic"])
        self.assertEqual(root.options["background"], gui.THEMES["arctic"]["BG"])
        self.assertEqual(child.options["foreground"], gui.THEMES["arctic"]["TEXT"])



class TimerSoundGuiTests(unittest.TestCase):
    def test_settings_include_timer_sound_toggle_and_test_button(self):
        source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        self.assertIn('text="Play a custom 10-second alarm when a timer finishes"', source)
        self.assertIn('text="Test 10-second alarm"', source)
        self.assertIn('text="Stop sound"', source)
        self.assertIn('command=assistant.stop_timer_sound', source)
        self.assertIn('timer_sound_enabled=timer_sound_var.get()', source)
        self.assertIn('assistant.play_timer_sound(force=True)', source)

    def test_build_bundles_the_custom_ten_second_alarm_asset(self):
        build = (PROJECT_ROOT / "build_release.bat").read_text(encoding="utf-8")
        asset = PROJECT_ROOT / "assets" / "jarvis_timer_alarm.wav"
        self.assertTrue(asset.is_file())
        self.assertIn('--add-data "assets\\jarvis_timer_alarm.wav;assets"', build)
        self.assertIn("--hidden-import winsound", build)


class AllInOneInstallerTests(unittest.TestCase):
    def test_build_downloads_and_signature_checks_ollama_before_packaging(self):
        build = (PROJECT_ROOT / "build_release.bat").read_text(encoding="utf-8")
        script = (PROJECT_ROOT / "download_ollama.ps1").read_text(encoding="utf-8")
        self.assertIn("download_ollama.ps1", build)
        self.assertIn("https://ollama.com/download/OllamaSetup.exe", script)
        self.assertIn("Get-AuthenticodeSignature", script)
        self.assertIn("Ollama Inc", script)

    def test_inno_installer_embeds_ollama_setup(self):
        installer = (PROJECT_ROOT / "installer.iss").read_text(encoding="utf-8")
        self.assertIn('Source: "vendor\\OllamaSetup.exe"', installer)
        self.assertIn('DestDir: "{tmp}"', installer)

    def test_inno_installer_silently_installs_runtime_when_missing(self):
        installer = (PROJECT_ROOT / "installer.iss").read_text(encoding="utf-8")
        self.assertIn('/VERYSILENT /NORESTART /SUPPRESSMSGBOXES', installer)
        self.assertIn('Check: not IsOllamaInstalled', installer)
        self.assertIn('function IsOllamaInstalled(): Boolean;', installer)

    def test_existing_standard_ollama_installation_is_detected(self):
        installer = (PROJECT_ROOT / "installer.iss").read_text(encoding="utf-8")
        self.assertIn("{localappdata}\\Programs\\Ollama\\ollama.exe", installer)
        self.assertIn("where.exe", installer)

    def test_ollama_models_are_downloaded_in_app_not_embedded_in_setup(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not embed multi-gigabyte model weights", readme)
        self.assertIn("downloaded in the app", readme)

    def test_ai_model_manager_is_exposed_from_sidebar_and_settings(self):
        source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        self.assertIn('"▦   AI model manager", self.open_model_manager', source)
        self.assertIn('text="Manage / download models…"', source)

    def test_model_manager_supports_pull_select_and_delete(self):
        source = (PROJECT_ROOT / "JARVIS_GUI.py").read_text(encoding="utf-8")
        for marker in ("model_manager.pull_model(", "assistant.set_model_name(tag)", "model_manager.delete_model(tag)"):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_model_manager_download_progress_is_streamed(self):
        source = (PROJECT_ROOT / "jarvis_model_manager.py").read_text(encoding="utf-8")
        self.assertIn('host + "/api/pull"', source)
        self.assertIn('"completed": completed_value', source)
        self.assertIn('"total": total_value', source)

    def test_model_manager_delete_uses_ollama_delete_endpoint(self):
        source = (PROJECT_ROOT / "jarvis_model_manager.py").read_text(encoding="utf-8")
        self.assertIn('host + "/api/delete"', source)
        self.assertIn('method="DELETE"', source)

    def test_new_model_manager_module_is_compiled_and_in_ci(self):
        build = (PROJECT_ROOT / "build_release.bat").read_text(encoding="utf-8")
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "windows-ci.yml").read_text(encoding="utf-8")
        self.assertIn("jarvis_model_manager.py", build)
        self.assertIn("jarvis_model_manager.py", workflow)



if __name__ == "__main__":
    unittest.main()
