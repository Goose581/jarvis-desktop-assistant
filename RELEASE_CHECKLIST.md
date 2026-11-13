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
