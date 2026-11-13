## Spotify controls (v1.6.3)

The desktop app includes local Spotify controls: open Spotify, play/pause, next/previous track, and search. Search opens Spotify results rather than automatically selecting a specific track. Playback commands use Windows multimedia keys, which Windows routes to its active media session; another active media player can receive the command. No Spotify API credentials are required for these desktop controls.

# J.A.R.V.I.S. one-file Windows installer

## What the end user downloads

The intended first-time download is a single file:

`output\JARVIS-Setup.exe`

It contains the PyInstaller-built J.A.R.V.I.S. application, launcher, and the official Ollama Windows setup executable. Setup installs Ollama for the current Windows user if a standard per-user install is not already detected. The end user does not need to install Python or run a separate Ollama installer.

## Why model files are separate

Ollama models can be several gigabytes each, and users may want different models. Model weights are deliberately not packed into the setup executable. After installation, open the **AI model manager** in J.A.R.V.I.S. to:

- Refresh the installed model list.
- Download a recommended model or enter a custom Ollama model tag.
- Follow the live download status and percentage.
- Set an installed model as the active assistant model.
- Delete a model after confirmation (the active model cannot be deleted).

Models are stored by Ollama and remain in place when J.A.R.V.I.S. itself is updated.

## Build the one-file installer

The build computer needs 64-bit Python 3.10+, Inno Setup 6, and internet access. The person receiving `JARVIS-Setup.exe` does not need those build tools.

1. Run `build_release.bat` on Windows.
2. The script runs syntax checks and the test suite.
3. `download_ollama.ps1` downloads `https://ollama.com/download/OllamaSetup.exe` if not already cached under `vendor\`.
4. The script verifies the file's Authenticode signature and requires the Ollama Inc. publisher identity. A failed check stops the build.
5. PyInstaller builds the app and launcher.
6. Inno Setup embeds the verified Ollama installer into the single `output\JARVIS-Setup.exe`.

The `vendor\` directory is ignored by Git and excluded from the source project ZIP. It is generated as part of the build process.

## Existing Ollama installations

The installer checks the usual per-user location (`%LOCALAPPDATA%\Programs\Ollama\ollama.exe`) and `where.exe`. If it finds Ollama, the embedded runtime installer is skipped. Model files are not deleted or moved by J.A.R.V.I.S.

## Network and storage

Internet is required on the build computer to download Ollama if it is not cached. The end user's first-time model download also needs internet. Ollama itself needs several GB of disk space, and models require additional space depending on the model chosen. The app can work offline after the selected model has finished downloading, subject to any features that require the web.

## Windows validation before release

The current environment can test Python modules, API request construction and the Tk GUI under a virtual display. It cannot validate an actual Windows Authenticode result, run the real Ollama installer, or compile Inno Setup. Perform the checks in `RELEASE_CHECKLIST.md` on a Windows PC before publishing the installer.

## Startup update approval

The v1.6.2 launcher checks GitHub Releases before opening the main interface. If a newer release is available, it presents a branded prompt with release notes and asks the user to choose **Install update** or **Not now**. No update ZIP is downloaded until the user chooses Install update. Not now or closing the prompt starts the currently installed application. If the update check cannot reach GitHub, J.A.R.V.I.S. continues with the installed version. Existing v1.6.1 users must run the v1.6.2 installer once to replace the outer launcher; later app-only updates use the approval prompt automatically.


## Spotify volume dependency

The desktop bundle includes Pycaw and comtypes for per-application Windows Core Audio session control. The Spotify volume slider targets Spotify.exe audio sessions only; it does not adjust Windows master volume. No Spotify API credentials are required.
