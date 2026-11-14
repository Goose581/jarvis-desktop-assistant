## v1.7.0 — Accurate clock, five new Workspace tools and custom icon

- Time/date questions are answered locally from the Windows system clock, including seconds, weekday, calendar date and local timezone abbreviation; Ollama is not asked to estimate these facts.
- Expanded deterministic date/time question recognition to cover weekday and date phrasing.
- Added CSV insights (headers, row/column counts, empty cells and duplicate rows).
- Added Markdown table generation from CSV-formatted text.
- Added HEX/RGB/HSL colour conversion.
- Added unified text comparison.
- Added integer conversion between bases 2–36.
- Added a generated blue/turquoise J.A.R.V.I.S. icon for the desktop executable, application window, installer, Start Menu and desktop shortcuts.
- Added 300 new focused tests: 50 clock/date cases and 50 cases for each of the five new tools, plus validation and integration checks.
- Updated app, launcher, installer, build and release metadata to v1.7.0.
- The existing Windows launcher automatically checks the latest GitHub Release at startup. When a newer release contains both the update ZIP and SHA-256 file, it downloads the package, verifies the checksum, stages it, swaps the app folder with rollback protection, and relaunches J.A.R.V.I.S. If checking/downloading fails, the installed version still starts. Settings and Ollama model data remain in the per-user data folders.
## v1.6.4 — Automatic Ollama startup and connection recovery

- Automatically checks the local Ollama API during application startup.
- Locates installed `ollama.exe` through PATH and standard Windows install locations.
- Starts `ollama.exe serve` silently when the local API is offline.
- Retries API readiness for up to 12 seconds without blocking the GUI.
- Rechecks and recovers Ollama before chat and model-manager actions.
- Respects remote `OLLAMA_HOST` values and never starts a local daemon for remote configurations.
- Writes diagnostic server output to `%LOCALAPPDATA%\JARVIS\ollama-server.log` when possible.

## v1.6.3 — Spotify controls and Spotify-only volume

- Added direct Spotify-only volume control using Windows Core Audio audio sessions via Pycaw.
- Added a Spotify volume slider, current-volume readout, five-percent up/down buttons, mute and unmute controls, and automatic refresh in Spotify Controls.
- Added natural-language commands: set Spotify volume to a percentage, turn Spotify volume up/down, raise/lower by a chosen percentage, check Spotify volume, mute Spotify, and unmute Spotify.
- Volume operations target sessions whose process is `Spotify.exe`; they do not change Windows master volume or other applications.
- Added Pycaw to build requirements and included it in the PyInstaller bundle.
- Kept Spotify opening, search, play/pause, next and previous controls.
- Added tests for audio-session filtering, COM lifecycle, percentage validation/clamping, slider wiring, command routing, tool schema and packaging.
- Documented that a Spotify audio session may not appear until playback starts.
