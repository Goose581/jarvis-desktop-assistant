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
