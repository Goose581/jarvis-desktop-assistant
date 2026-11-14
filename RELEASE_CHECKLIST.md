# v1.7.0 release checklist

- [ ] Confirm GitHub Actions passes on Python 3.13 and 3.14 / Windows.
- [ ] Run `build_release.bat` on Windows 10/11 x64 and confirm the icon generator creates `assets\\jarvis.ico` and `assets\\jarvis.png`.
- [ ] Confirm the app executable, app window, installer, Start Menu shortcut and desktop shortcut display the blue/turquoise J.A.R.V.I.S. icon.
- [ ] Ask J.A.R.V.I.S. for the current time, today's date and weekday; compare all three with the Windows clock/calendar.
- [ ] Test the five new Workspace tools: CSV insights, Markdown table, colour conversion, text comparison and number-base conversion.
- [ ] Confirm all 30 Workspace examples launch locally without sending those commands to Ollama.
- [ ] Install over v1.6.4 and confirm existing Ollama models, settings, notes and user data remain intact.
- [ ] Verify the update ZIP and SHA-256 checksum, then test the prompted updater from v1.6.4.
- [ ] Publish tag `v1.7.0` only after the Windows installer and update package have been tested.

# v1.6.4 Ollama automatic startup checks

- [ ] Commit and push v1.6.4 source.
- [ ] Confirm GitHub Actions passes on Windows.
- [ ] Build the installer and update ZIP on Windows.
- [ ] Close Ollama from the system tray so the local API is stopped.
- [ ] Launch J.A.R.V.I.S. using its normal desktop shortcut.
- [ ] Confirm J.A.R.V.I.S. starts `ollama.exe serve` and reaches the local API.
- [ ] Confirm the selected model is reported ready and a chat request succeeds.
- [ ] Stop Ollama while J.A.R.V.I.S. remains open; send another request and confirm it recovers.
- [ ] Confirm remote `OLLAMA_HOST` is not changed or replaced.
- [ ] If startup fails, inspect `%LOCALAPPDATA%\JARVIS\ollama-server.log` and `jarvis.log`.
- [ ] Test the user-approved update from v1.6.3, then publish tag `v1.6.4` with installer, update ZIP and checksum.

# v1.6.3 release checklist — Spotify-only volume

- [ ] Confirm Python syntax and the full automated suite pass.
- [ ] Build on Windows 10/11 x64 with `build_release.bat`.
- [ ] Confirm PyInstaller includes `pycaw` and `comtypes` in `dist\JARVIS`.
- [ ] Install over the existing version and retain Ollama models/settings.
- [ ] Open Spotify and start playback so Windows creates its audio session.
- [ ] Open J.A.R.V.I.S. → Spotify Controls and verify the current Spotify volume is displayed.
- [ ] Move the slider and verify only Spotify changes; check Windows master volume and another app remain unchanged.
- [ ] Test +5%, -5%, mute, unmute and refresh.
- [ ] Test chat commands: `set Spotify volume to 30%`, `turn Spotify volume down`, `increase Spotify volume by 10%`, `what's Spotify's volume?`, `mute Spotify`, `unmute Spotify`.
- [ ] Confirm play/pause, next, previous and search still work.
- [ ] Build and verify `dist\JARVIS-Windows.zip` and its `.sha256` file.
- [ ] Test update flow from v1.6.2, then publish GitHub Release tag `v1.6.3` with the installer, update ZIP and checksum.
