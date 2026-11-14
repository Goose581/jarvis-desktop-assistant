# Code audit — v1.6.3 Spotify-only volume control

## Scope

- Spotify session discovery uses Pycaw/Core Audio and filters process names to `Spotify.exe` only.
- Volume and mute use each matching session's `SimpleAudioVolume` interface.
- The implementation does not call endpoint/master-volume APIs, so other apps and Windows master volume are not adjusted.
- COM is initialized and uninitialized around each operation; session references are cleared before COM teardown.
- If no Spotify audio session exists yet, the app gives a clear message rather than changing system volume.
- The GUI slider commits on release, has five-percent increment/decrement controls, mute/unmute, and refreshes the session status while open.
- Chat commands are handled locally before Ollama; tool schema includes optional numeric level for model-routed requests.
- Pycaw and comtypes are included in the build requirements and PyInstaller collection.

## Limitations and platform verification

- Spotify-only volume control is Windows-specific.
- Spotify must have an audio session. Starting playback once may be required before Windows exposes that session.
- Playback control still uses global Windows multimedia keys and may affect another active media player; app-specific volume is independent and targets Spotify.exe.
- The code and mock audio-session tests run in this environment. Actual Core Audio behaviour, Spotify process identification, and the built executable must be verified on Windows 11 with Spotify installed.


# v1.6.4 Ollama startup recovery audit

- Startup status checks run on a background thread.
- The readiness helper first probes the configured API, then starts only a discovered local `ollama.exe` when the API is unavailable.
- `ollama.exe serve` runs without a console window on Windows and writes output to a per-user diagnostic log when possible.
- A lock and retained process handle prevent duplicate starts within one J.A.R.V.I.S. process.
- Startup retries are bounded to 12 seconds.
- Chat client and model-manager operations repeat the readiness check.
- Remote OLLAMA_HOST values are never replaced by a local server.
- The full automated test suite and Python compilation passed in this environment; actual Windows process startup still requires user-PC verification.
