# Code audit — v1.6.0 All-in-One Edition

## Single-file first-time installer

- `build_release.bat` calls `download_ollama.ps1` before packaging. The script downloads the official Windows `OllamaSetup.exe`, checks minimum file size, validates the Authenticode signature, and requires the Ollama Inc. publisher identity before allowing it into the installer.
- `installer.iss` embeds the verified Ollama setup binary inside `JARVIS-Setup.exe` and runs it silently before launching J.A.R.V.I.S. when the standard per-user Ollama executable is not already installed.
- Existing standard Ollama installs are detected via `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` or `where.exe`; in that case setup skips the runtime installation.
- Python and project dependencies remain bundled with the PyInstaller app. No separate Python or Ollama installer is required by the end user.
- Multi-gigabyte model files are not embedded. This is deliberate: the user selects models in the app, and Ollama stores them independently of J.A.R.V.I.S. updates.

## In-app model manager

- New `jarvis_model_manager.py` wraps Ollama's local list, streamed pull and delete APIs.
- Model tags are validated before API requests; no shell invocation is used for pulls or deletion.
- Streamed progress is posted to the GUI event queue; background workers do not update Tk widgets directly.
- The UI allows refresh, pull from recommended catalogue or a custom tag, choose installed model, and delete a non-active model after confirmation.
- Model files remain in the Ollama model store and are not packaged in application update ZIPs.

## Verification

- Python compilation passed for all modules and tests.
- Full automated suite: see `TEST_RESULTS.txt`.
- GUI smoke test under Xvfb opened the main window and Model Manager, populated one mocked installed model, processed queued events and closed cleanly.
- Model manager tests cover model-tag validation, model list parsing, human-readable sizes, streamed pull progress, server errors, incomplete streams, delete requests, and installer metadata.
- Windows-native Inno Setup compilation, Authenticode verification on Windows, runtime installation, model pulls and real Ollama inference still require target-PC testing. This source package is not a precompiled Windows installer.
# Code audit — v1.5.1

## Timer improvements

- Timer scheduling anchors the deadline with `time.monotonic()` before starting the worker, subtracting timer-thread setup overhead from the requested duration.
- Timer completion plays the Windows system notification sound first, before the queued text-to-speech message. `winsound.MessageBeep` is asynchronous, so it does not block the GUI thread.
- Timer sound preference defaults to enabled, is persisted as a boolean in settings schema v4, and can be switched off in Assistant Settings.
- Assistant Settings includes a Test sound button; it can preview the sound even when automatic timer sounds are disabled.
- If Windows audio is unavailable, the timer still completes and announces through the existing voice/message path; a console bell is attempted as a fallback and the audio error is logged.
- Timer cancellation remains supported, and cancelled timers do not play the completion sound.

## Verification

- Python compilation passed.
- Full automated suite: 1,413 tests passed.
- GUI smoke test exercised Settings, Test sound, the timer sound toggle, and persistence.
- A real short timer callback smoke test completed in approximately 0.15 seconds for a 0.15-second timer. Audio playback itself is mocked in this environment; the Windows system sound must be confirmed on the target PC.

---

# J.A.R.V.I.S. v1.3.0 — code audit

## New functionality

`jarvis_workspace.py` adds 25 offline-first features: world clock, timezone converter, date difference, date calculator, unit converter, percentage calculator, bill splitter, text analyser, case converter, text cleaner, URL encoder/decoder, JSON formatter, Base64 codec, text hashing, UUID generation, secure password generation, random picker, dice roller, interactive stopwatch, Pomodoro planner, task manager, reminders, bookmarks, reusable snippets and system health snapshot.

## Updated interface

The GUI adds a searchable two-column Workspace command centre, category filter, feature cards, copy-command actions, one-click example launch, Ctrl+K shortcut, interactive stopwatch and due-reminder notifications. The existing assistant chat and settings remain available.

## Verification evidence

- 1,250 feature-specific automated tests: exactly 50 per feature.
- 134 additional regression, validation and integration tests, including an explicit guard that checks all 25 generated suites contain exactly 50 cases.
- 1,384 total unittest tests passed.
- `compileall` passed for application, workspace, updater, runtime hook and tests.
- All 25 catalogue example commands were exercised through direct dispatch.
- GUI smoke test passed under a virtual display, including all 25 rendered cards, search filtering, stopwatch and safe close.
- See `FEATURE_TEST_MATRIX.md` and `TEST_RESULTS.txt` for the itemised count and scope.

## Safety and data handling

- No arbitrary shell execution was added to the AI tool catalogue.
- Bookmarks are restricted to HTTP/HTTPS URLs.
- Passwords are generated with the cryptographically secure `secrets` module and are not stored.
- Persistent task, reminder, bookmark and snippet stores are size/count bounded and use atomic file replacement with per-path thread locks.
- Reminders and stopwatch are app-local; they do not run when J.A.R.V.I.S. is closed.
- Ollama remains local-first; J.A.R.V.I.S. does not force CPU/GPU placement.

## Remaining target-PC checks

Windows PyInstaller, Inno Setup, install/upgrade, SAPI voice, clipboard, desktop automation and actual Gemma inference must be tested on the user's Windows PC. This ZIP is a source/build project; it is not itself a precompiled Windows installer.


## v1.4.0 — interface redesign audit

- Replaced the previous two-column chat layout with a dedicated Command Centre dashboard.
- Added a branded navigation rail with local AI core status, navigation actions and quick launch links.
- Added a hero banner, conversation card, quick-launch command cards and system snapshot panel.
- Redesigned composer, user/assistant message cards, message identity labels and context menus.
- Applied consistent navy/blue/turquoise styling to workspace, settings, comboboxes, scrollbars and menus.
- Improved narrow-size spacing and exercised 1360x860 and 1180x790 GUI geometries under Xvfb.
- Added four visual regression tests for palette, dashboard sections, message roles and default geometry.


## v1.4.0 final validation

- `python -m compileall -q JARVIS.py JARVIS_GUI.py jarvis_workspace.py launcher.py pyi_rth_stdio.py tests` completed successfully.
- `python -m unittest discover -s tests -v`: 1,388 tests passed, 0 failed.
- GUI smoke test passed at both 1360×860 and 1180×790 under Xvfb; verified required widgets and opened/closed Workspace.
- Visual preview saved as `UI_PREVIEW.png`.
- Windows-native packaging, display scaling and device-specific interactions remain to be checked by running `build_release.bat` on the user's PC.


## v1.5.0 theme audit

- Added six validated semantic palettes and theme preference persistence.
- Recolouring records each widget option's semantic role, so repeated theme switching does not progressively corrupt colours.
- Covered all original fixed GUI colour literals with a role map; future widgets created after a theme change are recoloured on creation.
- Theme changes apply to open child windows, Workspace card redraws and newly added chat messages.
- ttk Combobox styles are updated with each active palette.
- Tests check palette completeness, colour uniqueness, save/load validation, preview/cancel behaviour and nested-widget recolouring.
