# v1.3.0 feature test matrix

| # | Feature | Category | Automated cases |
|---:|---|---|---:|
| 1 | World clock | Time & dates | 50 |
| 2 | Timezone converter | Time & dates | 50 |
| 3 | Date difference | Time & dates | 50 |
| 4 | Date calculator | Time & dates | 50 |
| 5 | Unit converter | Calculators | 50 |
| 6 | Percentage calculator | Calculators | 50 |
| 7 | Bill splitter | Calculators | 50 |
| 8 | Text analyser | Text & data | 50 |
| 9 | Case converter | Text & data | 50 |
| 10 | Text cleaner | Text & data | 50 |
| 11 | URL encoder | Text & data | 50 |
| 12 | JSON formatter | Text & data | 50 |
| 13 | Base64 codec | Text & data | 50 |
| 14 | Text hash | Text & data | 50 |
| 15 | UUID generator | Developer tools | 50 |
| 16 | Password generator | Developer tools | 50 |
| 17 | Random picker | Fun & focus | 50 |
| 18 | Dice roller | Fun & focus | 50 |
| 19 | Stopwatch | Fun & focus | 50 |
| 20 | Pomodoro planner | Fun & focus | 50 |
| 21 | Task manager | Productivity | 50 |
| 22 | Reminders | Productivity | 50 |
| 23 | Bookmarks | Personal library | 50 |
| 24 | Text snippets | Personal library | 50 |
| 25 | System health | System | 50 |

**Feature-specific cases:** 25 × 50 = 1,250.
**Additional regression, validation and integration cases:** 134.
**Total full-suite cases:** 1,384.

## v1.6.3 Spotify controls

Automated tests cover media-key mapping and key-up/key-down events, installed-app discovery, process detection, URI encoding, search validation, fallback behaviour, command recognition, tool registration, and honest error handling. Actual Spotify playback routing must still be confirmed on a Windows PC because the test environment has no Spotify desktop session.


## v1.6.3 Spotify-only volume coverage

Automated tests cover: Windows/unsupported-platform gating; COM initialize/uninitialize; session discovery across devices; Spotify.exe-only filtering; no-session behaviour; numeric parsing and bounds; set/get/adjust; upper/lower clamping; mute/unmute; error messages; natural-language routing; tool schema arguments; GUI slider wiring; dependency and PyInstaller bundling.

The full Windows integration check must still confirm that Spotify playback creates a session, the Spotify slider changes only that session, and the system master volume plus other apps remain unchanged.


## v1.6.4 system integration — Ollama automatic startup

Covered by `tests/test_ollama_autostart.py` (11 tests): API available, offline recovery, remote host protection, executable-not-found handling, standard per-user executable discovery, hidden server launch, duplicate-start prevention, status integration, chat integration, and timeout validation.
