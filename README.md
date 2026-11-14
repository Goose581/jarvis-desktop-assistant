## v1.6.4 — Automatic Ollama startup and connection recovery

J.A.R.V.I.S. checks the local Ollama API during startup. If the API is unavailable and `OLLAMA_HOST` is local/default, it locates the installed `ollama.exe`, starts `ollama.exe serve` invisibly in the background, and retries for up to 12 seconds. The same readiness check runs before chat and model-manager operations so Ollama can recover if it is closed while J.A.R.V.I.S. remains open. Remote `OLLAMA_HOST` configurations are not overridden. See `OLLAMA_AUTOSTART.md` for diagnostics.

For this project release, set the GitHub tag and title to `v1.6.4`. Attach `dist\JARVIS-Windows.zip` and `dist\JARVIS-Windows.zip.sha256` for prompted updates, plus `output\JARVIS-Setup.exe` for first-time installations.

## v1.6.3 — Spotify controls and Spotify-only volume

J.A.R.V.I.S. includes a Spotify Controls panel and natural-language commands for opening Spotify, play/pause, next/previous, searching, reading Spotify's app-session volume, setting a percentage, nudging volume up/down, and muting/unmuting Spotify. The volume slider and commands target Spotify's own Windows Core Audio session through Pycaw's `SimpleAudioVolume` interface. They do **not** change Windows master volume or the volume of other applications. If Spotify has not started playback yet, Windows may not have created its audio session; start a track and refresh the panel.

Playback buttons still use Windows global multimedia keys and may be delivered to another active media session. Spotify-only volume is separate from those keys. It does not require Spotify API credentials. The app bundles the Pycaw/comtypes dependencies in the desktop build; the source build installs `pycaw` from `requirements-build.txt`.

Example commands: “set Spotify volume to 30%”, “turn Spotify volume down”, “increase Spotify volume by 10%”, “what's Spotify's volume?”, “mute Spotify”, and “unmute Spotify”.

When ready, create a GitHub Release and set the tag and title to `v1.6.3`. Attach `dist\JARVIS-Windows.zip` and `dist\JARVIS-Windows.zip.sha256` for updates, plus `output\JARVIS-Setup.exe` for first-time installs.

## v1.6.2 — User-approved startup updates

The launcher checks GitHub Releases before opening the main J.A.R.V.I.S. window. When a newer release with both required assets is available, a branded blue/turquoise startup dialog displays the version and release notes. The user must choose **Install update** before anything is downloaded or installed. **Not now** (or closing the dialog) launches the currently installed version without changing it; the update is offered again next launch. After consent, a progress window downloads the app ZIP and SHA-256 file, verifies the checksum, and hands off to the existing safe updater/rollback flow. If GitHub is offline or the prompt cannot open, the current version launches and the reason is logged. The v1.6.2 installer must be run once over an existing v1.6.1 installation to replace the older launcher; later application updates can then use the prompted in-app startup flow.
When ready, create a GitHub Release and set the tag and title to `v1.6.2`. Attach `dist\JARVIS-Windows.zip` and `dist\JARVIS-Windows.zip.sha256` for updates, plus `output\JARVIS-Setup.exe` for first-time installs and the one-time launcher upgrade.

## v1.6.1 — Custom 10-second timer alarm

Timer completion plays a distinct J.A.R.V.I.S. alarm sound for exactly ten seconds. It is a bundled WAV file, not the Windows notification sound. The alarm plays asynchronously; the spoken completion message follows after the sound finishes. Assistant Settings offers a sound toggle, **Test 10-second alarm**, and **Stop sound** controls. The WAV is bundled into the app and update ZIP, so no extra audio library or separate download is needed.

When ready, create a GitHub Release and set the tag and title to `v1.6.1`.

## v1.6.0 — All-in-One Edition and AI Model Manager

When ready, create a GitHub Release and set the tag and title to `v1.6.0`.

The first-time Windows installer is now a single `JARVIS-Setup.exe` that includes J.A.R.V.I.S. and the official Ollama Windows installer. During the build, `download_ollama.ps1` downloads `https://ollama.com/download/OllamaSetup.exe`, validates its Authenticode signature, and checks that the publisher is Ollama Inc. The Inno Setup installer then installs Ollama silently for the current user if a standard per-user Ollama installation is not already detected. Python and application libraries are bundled by PyInstaller; users do not need to separately install Python or Ollama.

Open **AI model manager** from the left navigation rail or Assistant Settings to refresh installed models, download a recommended model or enter a custom Ollama tag, watch streamed download progress, activate an installed model, or remove a model after confirmation. Model files remain in Ollama's model store and are not re-downloaded by J.A.R.V.I.S. application updates. The recommended default remains `gemma4:e2b` for the original 16 GB PC profile. Available models depend on the Ollama registry and local hardware.

**Important distribution detail:** The single installer includes the Ollama runtime but does not embed multi-gigabyte model weights. A model is selected and downloaded in the app after setup. Internet access is required for the installer to download Ollama during the build and for first-time model downloads. The resulting end-user download is one `JARVIS-Setup.exe`; no separate Python or Ollama installer is needed.

## v1.5.1 — Faster timers and completion chime

Timers use monotonic deadlines and play a bundled custom J.A.R.V.I.S. alarm WAV for exactly ten seconds when they finish. It is not the Windows notification sound. Spoken completion is announced after the alarm; the sound can be switched off, tested or stopped in Assistant Settings → Timer sound.

## v1.5.0 — Switchable themes

Six selectable colour themes are available from Assistant Settings → Appearance theme: Midnight Blue, Arctic Light, Emerald, Nebula Violet, Crimson and Solar Amber. Theme previews apply immediately and are saved with Settings. The theme applies across the main dashboard and open Workspace/dialog windows.



# J.A.R.V.I.S. — Windows Desktop Assistant

A local-first Windows desktop assistant with a Tkinter chat interface, Ollama-powered conversation, voice responses, desktop tools, and an optional GitHub Releases updater.

## v1.5.0 appearance themes

The desktop interface now supports six switchable palettes (Midnight Blue, Arctic Light, Emerald, Nebula Violet, Crimson and Solar Amber). Choose a theme in Assistant Settings → Appearance theme; the preview updates immediately, Cancel restores the previous palette, and Save remembers the choice. All palettes apply across the main dashboard, chat messages, Workspace, settings, stopwatch and ttk controls. The default is Midnight Blue. The Command Centre design includes: a branded navigation rail, local AI core status card, large hero banner, conversation panel, quick-launch tiles, system snapshot and a redesigned message composer. Chat messages use distinct user/assistant cards with avatars and context labels. Workspace, settings, menus and scrollbars share the same palette. The default window size is 1360×860 (saved user window sizes are preserved).

## What's included in v1.5.0

- Faster everyday conversation: greetings, "How are you?", thanks and identity questions are answered locally without starting an AI request.
- Ordinary chat requests omit desktop-tool schemas; action requests retain the explicit JSON tool schemas needed for tool calling.
- Model-aware Ollama thinking control: uses the model's advertised `false` or `low` setting when `/api/show` exposes one, and caches that capability for 30 minutes.
- Shorter response budgets and a smaller recent-history window to reduce unnecessary generation and prompt work on older PCs.
- The default model remains `gemma4:e2b` with an 8,192-token context; custom model and context settings are preserved.
- Deterministic BIDMAS calculator, web search, app launch/close, notes, timers, folder opening and typing tools. Timer completion plays the bundled custom ten-second alarm by default; toggle, test or stop it in Assistant Settings. Timer deadlines use `time.monotonic()` so short timers are not extended by startup bookkeeping.
- Explicit JSON schemas for Ollama tools, avoiding the Python 3.14/Pydantic callable-annotation error.
- Resilient Ollama local connection discovery through localhost/IPv4/IPv6 and proxy bypass for loopback.
- Custom midnight-blue and turquoise Command Centre GUI, settings, voice switch, conversation export, copy support and updater.
- Six selectable app-wide themes with live preview and persistent preference.
- Searchable Workspace command centre with 25 built-in features, category filters, one-click examples and Ctrl+K command palette.
- Interactive stopwatch and scheduled reminder notifications.
- Local date/time, converters, text utilities, developer helpers, tasks, bookmarks and snippets in `jarvis_workspace.py`.

## Repository contents

- `JARVIS.py` — assistant logic, deterministic routing, calculator, tools and Ollama connection.
- `JARVIS_GUI.py` — desktop interface and searchable Workspace command centre.
- `jarvis_workspace.py` — 25 offline-first feature utilities and bounded persistent stores.
- `jarvis_model_manager.py` — Ollama model listing, streamed downloads, activation and deletion.
- `jarvis_spotify.py` — Spotify playback/search and Spotify-only Windows audio-session volume controls.
- `launcher.py` — GitHub Releases updater and application launcher.
- `update_config.json` — GitHub `owner/repository` setting.
- `build_release.bat` — test, build, ZIP, checksum and installer script.
- `Diagnose_Ollama.bat` — creates a text report containing Ollama CLI/model/API checks and recent app logs.
- `installer.iss` — Inno Setup installer definition.
- `requirements-build.txt` — build-time Python dependencies, including Pycaw for per-app audio volume.
- `tests/` — automated tests.
- `.github/workflows/windows-ci.yml` — Windows-hosted syntax and test checks on Python 3.13 and 3.14.
- `download_ollama.ps1` — official runtime download and Authenticode verification for the one-file installer.
- `CHANGELOG.md`, `CODE_AUDIT.md`, `RELEASE_CHECKLIST.md`, `ONE_FILE_INSTALLER.md` — release documentation.

## Requirements

1. Windows 10 22H2 or newer, 64-bit (Windows 11 is supported).
2. Internet connection for the first-time setup and first model download.
3. At least 4 GB of free disk space for the Ollama runtime, plus additional space for whichever model(s) you choose. Model files can be several GB each.

The single `JARVIS-Setup.exe` installs the Ollama runtime automatically when it is not already present. You do not need to separately install Python or Ollama. Model weights are intentionally not embedded in the installer: open AI Model Manager after setup and download the model you want. This keeps the installer independent of a particular AI model and lets you add/switch models later.

## Build on Windows

1. Install 64-bit Python 3.10+ and Inno Setup 6.
2. Ensure `update_config.json` points to `Goose581/jarvis-desktop-assistant` (or your repository).
3. Double-click `build_release.bat`.

The script creates a virtual environment, installs build dependencies, compiles Python, runs the full test suite, downloads the official Ollama installer, verifies its Authenticode signature/publisher, builds the app and updater, verifies the release ZIP/checksum and compiles the one-file installer when Inno Setup is detected. The Ollama setup binary is stored temporarily under `vendor\` and embedded in `output\JARVIS-Setup.exe`; it is excluded from the source ZIP and Git history.

Generated files:

- `dist\JARVIS\JARVIS.exe` — desktop app.
- `dist\JARVIS-Launcher.exe` — update-aware launcher.
- `dist\JARVIS-Windows.zip` — app update package.
- `dist\JARVIS-Windows.zip.sha256` — package checksum.
- `output\JARVIS-Setup.exe` — single first-time installer containing J.A.R.V.I.S. and the verified Ollama runtime. Model weights are downloaded later from AI Model Manager.

## Workspace features in v1.4.0

Open **Explore Workspace** in the sidebar or press **Ctrl+K**. Search by tool name, category or keyword, filter by category, then launch an example directly in chat or copy its command. The 25 new features are:

1. World clock for IANA timezones.
2. Timezone converter.
3. Date difference calculator.
4. Date calculator (days, weeks and months).
5. Unit converter (length, mass, volume, speed and data).
6. Percentage calculator.
7. Bill splitter and tip calculator.
8. Text analyser (characters, words, lines, sentences and reading estimate).
9. Case converter (upper, lower, title, sentence, camel, snake, kebab and Pascal).
10. Text cleaner.
11. URL encoder/decoder.
12. JSON formatter and validator.
13. Base64 encoder/decoder.
14. Text hash generator (SHA-256, SHA-512, SHA-1 and MD5).
15. UUID generator.
16. Secure password generator.
17. Random picker.
18. Dice roller.
19. Interactive stopwatch with laps.
20. Pomodoro planner.
21. Persistent task manager.
22. Persistent reminders with in-app notifications.
23. Persistent bookmarks with search.
24. Persistent reusable text snippets.
25. System disk and memory health snapshot.

The tools are grouped into Time & dates, Calculators, Text & data, Developer tools, Fun & focus, Productivity, Personal library and System. Tasks, reminders, bookmarks and snippets are stored locally under `%LOCALAPPDATA%\JARVIS` (or the per-user application data fallback). Password generation uses Python's cryptographically secure `secrets` API; generated passwords are not saved by J.A.R.V.I.S.

## Speed behaviour in v1.2.8

- "How are you?", greetings, thanks and "Who are you?" use local deterministic replies.
- Regular knowledge questions are sent without the tool catalogue, reducing prompt overhead.
- When the selected model advertises thinking controls through Ollama `/api/show`, the app chooses `false` when available or `low` otherwise. If no setting is advertised, it preserves the model's default behaviour.
- The model's thinking controls are cached for 30 minutes.
- Ordinary chat allows up to 224 generated tokens; tool follow-ups use a smaller budget. History is capped at 18 messages including the system prompt.
- Gemma 4 E2B remains the default. Actual tokens/second varies by CPU, GPU, drivers, model quantisation and background load.

## Ollama troubleshooting

- Check that `http://localhost:11434/api/tags` lists the configured model.
- The app tries localhost, IPv4 and IPv6 loopback and uses the same successful endpoint for the SDK client.
- Local requests bypass machine-wide HTTP proxy variables.
- Detailed app errors are stored at `%LOCALAPPDATA%\JARVIS\jarvis.log`.
- Use `Diagnose_Ollama.bat` to generate `ollama-diagnostic.txt` when needed.

## GitHub Releases and updates

For the current project, use tag and title `v1.6.4`. Build and test on Windows before publishing. Attach `dist\JARVIS-Windows.zip` and `dist\JARVIS-Windows.zip.sha256` for the prompted updater, plus `output\JARVIS-Setup.exe` for first-time installs. The repository must be public for the current unauthenticated updater design.

## Safety and notes

- The calculator uses a restricted AST evaluator, not `eval`.
- App closing is limited to a supported allowlist; the AI does not run arbitrary shell commands.
- Typing pastes exact text into the focused application after a countdown.
- Timers run only while J.A.R.V.I.S. remains open.
- Ollama chooses CPU/GPU placement automatically; J.A.R.V.I.S. does not force GPU offload.
- Settings/logs are stored under `%LOCALAPPDATA%\JARVIS`.
