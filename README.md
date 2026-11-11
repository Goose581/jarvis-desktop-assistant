# J.A.R.V.I.S. Windows EXE + auto-updates

This project keeps your current `JARVIS.py` assistant as the app. It adds a separate Windows launcher that checks a **public GitHub repository's latest Release**, verifies the update ZIP with SHA-256, and replaces the app folder automatically. Users install once; later app releases do not require running the installer again.

## What is included

- `JARVIS.py` — your current assistant code, kept as-is.
- `launcher.py` — checks GitHub Releases and safely applies a downloaded update.
- `update_config.json` — set your GitHub `owner/repository` here.
- `build_release.bat` — builds the PyInstaller app, launcher, update ZIP, and checksum on Windows.
- `installer.iss` — Inno Setup recipe for the first-time installer.
- `requirements-build.txt` — Python packages needed on the build computer.

## One-time setup

1. Create a **public** GitHub repository for J.A.R.V.I.S.
2. Edit `update_config.json` and replace `Goose581/jarvis-desktop-assistant` with your actual GitHub `owner/repository`, (`Goose581/jarvis-desktop-assistant`).
3. On a Windows 10/11 build computer, install 64-bit Python 3.10 or newer. During setup, enable **Add Python to PATH**.
4. Install [Inno Setup](https://jrsoftware.org/isinfo.php) if you want the one-time `JARVIS-Setup.exe` installer.
5. Double-click `build_release.bat`. It creates:
   - `dist\JARVIS\` — the app files
   - `dist\JARVIS-Launcher.exe` — the update-aware launcher
   - `dist\JARVIS-Windows.zip` — the update package for GitHub Releases
   - `dist\JARVIS-Windows.zip.sha256` — the integrity checksum
   - `output\JARVIS-Setup.exe` — the initial installer, if Inno Setup is installed

## First release

1. Run the build script.
2. In GitHub, create a Release with tag `v1.0.0` (not a draft or prerelease).
3. Attach **both** `dist\JARVIS-Windows.zip` and `dist\JARVIS-Windows.zip.sha256` to that release.
4. Attach `output\JARVIS-Setup.exe` too, so users can install J.A.R.V.I.S. for the first time.
5. Install using `JARVIS-Setup.exe`. The shortcut opens the launcher, which starts the app.

## Publishing an update later

1. Edit `JARVIS.py` with your changes.
2. Open `build_release.bat` and increase `APP_VERSION` (for example, from `1.0.0` to `1.0.1`).
3. Run `build_release.bat` again.
4. Create a new GitHub Release with the matching tag, e.g. `v1.0.1`.
5. Attach the new `JARVIS-Windows.zip` and `JARVIS-Windows.zip.sha256`.

The next time an installed user opens J.A.R.V.I.S., the launcher sees the newer version, downloads it, checks the checksum, swaps the app files, and starts the updated app. They do **not** need to reinstall the setup EXE for normal app updates.

## Important notes

- The GitHub repository must be public for this starter updater, and releases must be published as normal stable releases.
- Keep the asset names exactly `JARVIS-Windows.zip` and `JARVIS-Windows.zip.sha256`.
- The ZIP must contain the **contents** of the PyInstaller `dist\JARVIS` folder at its root. The build script creates it this way.
- The first-time installer places the app under `%LOCALAPPDATA%\Programs\JARVIS`, so updates do not require administrator rights.
- Ollama and the `llama3.2:1b` model remain separate prerequisites on each PC. The EXE bundles your Python code and Python packages, not the Ollama runtime/model.
- Build the Windows EXEs on Windows. A Linux build cannot produce a proper Windows PyInstaller executable.
- This starter updater updates the assistant app, not the launcher. If the launcher/updater itself needs changing later, publish a new installer for that one-time launcher change.
- Users should only install releases from a GitHub repository they trust. SHA-256 catches corrupted or mismatched downloads; it is not a code-signing certificate.
