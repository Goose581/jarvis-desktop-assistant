## v1.6.2 — Ask before installing startup updates

- Replaced silent startup updates with a branded J.A.R.V.I.S. update prompt before the main interface opens.
- The prompt shows the installed version, available version and a cleaned, bounded excerpt of the GitHub release notes.
- Added **Install update** and **Not now** choices. Closing the prompt is treated as declining; no update files are downloaded unless the user explicitly accepts.
- Added a branded download/verification window after consent. The existing HTTPS validation, SHA-256 verification, safe ZIP extraction, backup/rollback and helper-process handoff remain in use.
- If the release check fails or the update is declined, the currently installed application still launches.
- Added explicit `urllib.parse` import and explicit Tkinter build imports for the windowed launcher.
- Existing v1.6.1 users must run the v1.6.2 installer once to replace the old outer launcher; subsequent updates are prompted at startup.

### Verification
- Added regression tests for newer/same/older release handling, missing assets, no download before consent, skip behaviour, accepted update handoff, and fail-open behaviour.
- Run the full Windows build and GUI checks on the target PC before publishing.

## v1.6.1 — Custom 10-second timer alarm

- Replaced the Windows system notification sound with a distinctive, bundled J.A.R.V.I.S. electronic alarm WAV.
- The custom alarm audio is exactly 10.0 seconds long and plays asynchronously, so the timer callback and GUI remain responsive.
- Timer completion speech is announced after the alarm finishes, avoiding speech/audio overlap. If audio cannot start or is disabled, the voice announcement still happens immediately.
- Added a Stop sound control beside the 10-second alarm preview in Assistant Settings.
- Bundled the alarm WAV into the PyInstaller app so it is included in the installer and automatic-update ZIP. No external audio package is required.
- Added tests for WAV duration/format, async playback flags, stop behaviour, disabled-sound behaviour, delayed voice announcement, and packaging inclusion.

## v1.6.0 — All-in-One Windows setup and AI Model Manager

- The first-time `JARVIS-Setup.exe` now embeds the official Ollama Windows installer. The build script downloads it from `https://ollama.com/download/OllamaSetup.exe` and verifies its Authenticode signature and Ollama Inc. publisher before bundling.
- Setup silently installs Ollama for the current Windows user when the standard per-user installation is not already detected. Existing standard Ollama installations are left in place.
- Added an in-app AI Model Manager in the sidebar and Assistant Settings. It lists installed models with parameter/size/quantisation metadata, downloads models with live progress, switches the active model, and deletes models after confirmation.
- Added a recommended model catalogue plus a custom Ollama model-tag field. Model weights are downloaded separately from Ollama so users can choose models and keep them when J.A.R.V.I.S. updates.
- The installer is one downloadable EXE for J.A.R.V.I.S. plus the Ollama runtime; first model download requires internet and sufficient disk space.
- Added coverage for model tag validation, model listing, streamed pull progress, server errors, deletion, and one-file installer metadata.

## v1.5.1 — Faster, audible timers

- Timer completion now plays the Windows system notification sound immediately, before queued voice output.
- Added an Assistant Settings toggle for timer-completion sounds, enabled by default, with a Test sound button.
- Timer scheduling now uses a monotonic deadline so setup overhead does not extend short countdowns.
- Existing timer parsing, cancellation, voice notification and maximum-active-timer safeguards are retained.
- Added timer sound preference persistence and validation (settings schema v4).

## v1.5.0 — 2026-11-13

- Added six in-app themes: Midnight Blue, Arctic Light, Emerald, Nebula Violet, Crimson and Solar Amber.
- Added instant theme preview in Assistant Settings, with Save and Cancel behaviour.
- Persisted theme preference and applied the chosen palette at startup.
- Recolours chat, sidebar, quick actions, dialogs, Workspace cards, stopwatch and ttk controls.
- Bumped settings schema and application version metadata to 1.5.0.

# J.A.R.V.I.S. changelog

## v1.4.0 — 2026-11-13

### Custom blue and turquoise Command Centre UI
- Replaced the previous chat-first layout with a fully redesigned dashboard inspired by the blue/turquoise concept: branded navigation rail, custom J emblem, local AI core card, Command Centre header, hero banner, quick-launch cards, system snapshot and docked composer.
- Redesigned user and assistant messages with separate blue/teal message cards, distinct identity markers, tighter typography and context labels.
- Applied a consistent midnight-blue, ocean-blue and turquoise palette to the Workspace, settings controls, menus, scrollbars and status elements.
- Added branded avatar marks, identity labels and more spacious message bubbles; simplified button borders and made scrolling controls match the dark theme.
- Increased the default window size to 1360×860 and minimum size to 1080×700 so the dashboard has room to breathe; saved user geometry remains respected.
- Improved initial assistant welcome copy and aligned model status text with the new local AI core card.

### Verification
- Existing application features, assistant request flow, settings, workspace tools, updater and release workflow retained.
- Python compilation, complete unit test suite and Tkinter GUI smoke test run for this release.
- Windows installer compilation and visual check on the user's PC remain required before publishing.

## v1.3.0 — 2026-11-13

### 25 new Workspace features
- World clock, timezone conversion, date difference and date calculator.
- Unit conversion, percentage calculation and bill splitting.
- Text statistics, case conversion, text cleanup, URL encode/decode and JSON formatting.
- Base64 encode/decode and SHA-256/SHA-512 text hashing.
- UUID and secure password generation, random choice and dice roller.
- Interactive stopwatch and Pomodoro planner.
- Persistent local tasks, reminders, bookmarks and reusable text snippets.
- System disk/memory health snapshot.

### Smarter desktop interface
- Added a searchable Workspace command centre with category filtering and 25 feature cards.
- Added one-click example launch and command-copy actions.
- Added Ctrl+K command-palette shortcut.
- Added an interactive stopwatch window and due-reminder notifications.
- Added Workspace buttons in the sidebar and top bar; retained the existing chat layout and settings.

### Compatibility and reliability
- Added explicit JSON workspace tool schema to keep Python 3.14/Pydantic compatibility.
- Added timezone database package for Windows zoneinfo support and bundled it in PyInstaller.
- Persistent tasks, reminders, bookmarks and snippets use bounded atomic JSON files in the per-user data folder.
- Added 50 independent tests for each of the 25 new feature areas (1,250 feature-specific test cases), plus a guard test that asserts all 25 suites keep exactly 50 cases.
- Windows CI now exercises Python 3.13 and 3.14.

### Verification
- The build runs compileall and the complete unittest suite before packaging.
- Final verification: 1,384 unittest cases passed, including all 1,250 feature-specific cases.
- Windows-specific EXE, Inno Setup, speech, clipboard and actual Ollama model behaviour still require validation on the target PC.

## v1.2.8 — 2026-11-13

### Faster everyday conversation
- Added a deterministic local response for "How are you?", common greetings, thanks, and identity questions. These no longer start Gemma or wait for an Ollama response.
- Ordinary knowledge and conversation requests no longer include the full desktop-tool schema catalogue. Tool schemas are sent only when a request plausibly asks J.A.R.V.I.S. to perform an action, reducing prompt overhead and avoiding unnecessary tool-planning work.
- Reduced the ordinary-chat output allowance to 224 tokens and action follow-up allowance to 192/320 tokens to avoid unnecessarily long generations on older PCs.
- Reduced retained conversation history from 26 to 18 messages while preserving the system message and a valid user-turn boundary.
- Added model-aware thinking-mode discovery through Ollama `/api/show`. When the model advertises `false`, J.A.R.V.I.S. requests no thinking output; when it advertises a `low` level, it selects that. If no control is advertised, the field is omitted and Ollama's model default is preserved.
- Cached thinking metadata per model for 30 minutes so it does not add a repeated metadata request to every conversation.

### Verification
- Added tests for local social responses, no-Ollama greeting routing, tool-schema omission on normal questions, action-intent tool inclusion, thinking-mode discovery/cache, and version metadata.
- Existing calculator tests continue to include 250 generated BIDMAS expressions.
- Python compilation and the full unit test suite must pass before building. Real response-time measurements still need to be checked on the user's Windows PC with Gemma 4 E2B.

## v1.2.7 — 2026-11-12

### Ollama tool-call compatibility fix
- Fixed the confirmed failure from the user's diagnostic log: `ollama.Client.chat()` failed before sending a request because the SDK tried to convert Python tool callables into Pydantic models and could not resolve postponed `Any` annotations on Python 3.14.
- Added explicit JSON function schemas for every assistant tool and kept a separate Python dispatch registry. This removes runtime introspection of Python annotations and is compatible with Python/Pydantic versions that support the Ollama chat API.
- Updated both initial and follow-up chat requests to send the explicit schemas.
- Added regression tests to ensure every dispatch function has a matching JSON schema, the schemas are JSON-serialisable, and the chat client receives schema dictionaries rather than Python callables.

### Diagnostic conclusion
- The user's diagnostic confirmed that `http://localhost:11434/api/tags` and `http://127.0.0.1:11434/api/tags` both respond and list `gemma4:e2b`, `llama3.2:1b`, and `gemma4:12b`. Therefore the reported chat failure was not an Ollama server connection failure; it occurred during client-side tool-schema generation.

### Verification
- Python compileall and automated regression tests are run before packaging. Live Gemma inference, Windows PyInstaller/Inno Setup build, and desktop integrations still require target-PC verification.

## v1.2.6 — 2026-11-12

### Ollama connection reliability
- Reworked local Ollama host discovery to try `localhost`, IPv4 loopback, and IPv6 loopback when no custom `OLLAMA_HOST` is configured.
- Converts wildcard bind addresses (`0.0.0.0` and `::`) to a connectable loopback address for client connections.
- Bypasses machine-wide HTTP proxy settings for loopback Ollama HTTP requests, avoiding local requests being sent through an unrelated proxy.
- Creates the Ollama Python SDK client with the exact host that passed the API health check and disables inherited proxy settings for the local client.
- Provides more actionable status and chat errors, including the actual exception detail in the per-user log.
- Added regression tests for Windows loopback variants, wildcard host normalisation, fallback when localhost resolution fails, and explicit SDK host/proxy configuration.

## v1.2.5 — 2026-11-12

### Tuned for Gemma 4 E2B and 16 GB PCs
- Changed the recommended default Ollama model to `gemma4:e2b`. Existing settings that still contain the previous default `llama3.2:1b` migrate automatically; other custom model selections are preserved.
- Added a persistent context-window setting with supported presets (2,048 / 4,096 / 8,192 / 12,288 / 16,384). The default is 8,192.
- Tuned inference options for local responsiveness and added installed-model discovery and model settings.

## v1.2.4 — 2026-11-12

### Reliability and release quality
- Made GUI shutdown resilient.
- Added automated checks that keep application, launcher, installer and documentation versions in sync.
- Added a Windows GitHub Actions workflow to run syntax and test checks on a Windows runner.

## v1.2.3 — 2026-11-12

### Reliability and preferences
- Added atomic settings writes, saved window geometry, log rotation and improved timer parsing.
- Hardened update ZIP extraction, interrupted-update recovery and version validation.

## v1.1.0 — 2026-11-12

### Desktop interface
- Added the Tkinter chat interface, model settings, voice controls, conversation export and message copy support.
- Added direct commands for math, time, timers, search, app opening, notes and common folders.
