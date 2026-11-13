@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Keep this version in sync with APP_VERSION in JARVIS.py.
set "APP_VERSION=1.6.2"
set "PYTHON=.venv\Scripts\python.exe"
set "BUILD_LOG=%~dp0build.log"
set "BUILD_STAGE=initial checks"

> "%BUILD_LOG%" echo J.A.R.V.I.S. build log - version %APP_VERSION%
echo.
echo ==============================================================
echo Building J.A.R.V.I.S. v%APP_VERSION%
echo Full build output will be saved to:
echo %BUILD_LOG%
echo ==============================================================

where py >nul 2>nul
if errorlevel 1 (
    echo Python launcher 'py' was not found. Install Python 3.10+ 64-bit from python.org.
    echo Python launcher 'py' was not found.>>"%BUILD_LOG%"
    goto :failed
)

if not exist "%PYTHON%" (
    echo Creating the project virtual environment...
    py -3 -m venv .venv >>"%BUILD_LOG%" 2>&1
    if errorlevel 1 goto :failed
)

"%PYTHON%" -c "import struct,sys; raise SystemExit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 else 1)" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 (
    echo The project environment needs 64-bit Python 3.10 or newer.
    echo Unsupported Python version or architecture.>>"%BUILD_LOG%"
    goto :failed
)

"%PYTHON%" --version >>"%BUILD_LOG%" 2>&1

echo.
echo [1/6] Installing build dependencies...
set "BUILD_STAGE=dependency installation"
call "%PYTHON%" -m pip install --upgrade pip >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed
call "%PYTHON%" -m pip install -r requirements-build.txt >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

echo.
echo [2/6] Checking Python syntax...
set "BUILD_STAGE=Python syntax check"
call "%PYTHON%" -m compileall -q JARVIS.py JARVIS_GUI.py jarvis_workspace.py jarvis_model_manager.py launcher.py pyi_rth_stdio.py tests >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

echo.
echo [3/6] Running automated tests...
set "BUILD_STAGE=automated tests"
call "%PYTHON%" -m unittest discover -s tests -v >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

echo.
echo [4/6] Preparing the signed Ollama runtime for the one-file installer...
set "BUILD_STAGE=Ollama runtime download and signature verification"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download_ollama.ps1" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

REM Remove old generated files so stale builds cannot be mistaken for this release.
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist output rmdir /s /q output
if exist JARVIS.spec del /q JARVIS.spec
if exist JARVIS-Launcher.spec del /q JARVIS-Launcher.spec

echo.
echo [5/6] Building the J.A.R.V.I.S. desktop application...
set "BUILD_STAGE=desktop application packaging"
call "%PYTHON%" -m PyInstaller --noconfirm --clean --onedir --windowed --name JARVIS --runtime-hook pyi_rth_stdio.py --collect-all pyttsx3 --collect-all comtypes --collect-all ollama --collect-all pyautogui --collect-all pyperclip --collect-all tzdata --hidden-import winsound --hidden-import pyttsx3.drivers.sapi5 --add-data "assets\jarvis_timer_alarm.wav;assets" JARVIS_GUI.py >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

if not exist "dist\JARVIS\JARVIS.exe" (
    echo PyInstaller did not produce dist\JARVIS\JARVIS.exe.
    echo Missing dist\JARVIS\JARVIS.exe after PyInstaller.>>"%BUILD_LOG%"
    goto :failed
)
> "dist\JARVIS\version.txt" echo %APP_VERSION%

echo.
echo [6/6] Building updater and release assets...
set "BUILD_STAGE=updater packaging"
call "%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --name JARVIS-Launcher --runtime-hook pyi_rth_stdio.py --hidden-import tkinter --hidden-import tkinter.ttk launcher.py >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

if not exist "dist\JARVIS-Launcher.exe" (
    echo PyInstaller did not produce dist\JARVIS-Launcher.exe.
    echo Missing dist\JARVIS-Launcher.exe after PyInstaller.>>"%BUILD_LOG%"
    goto :failed
)
copy /y update_config.json dist\update_config.json >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

REM ZIP the contents of dist\JARVIS; executable and version file remain at the ZIP root.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\JARVIS\*' -DestinationPath 'dist\JARVIS-Windows.zip' -Force" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

"%PYTHON%" -c "import hashlib,pathlib; p=pathlib.Path(r'dist/JARVIS-Windows.zip'); pathlib.Path(str(p)+'.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest() + '  JARVIS-Windows.zip\n', encoding='ascii')" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

echo Verifying update ZIP contents and SHA-256...
set "BUILD_STAGE=release asset verification"
call "%PYTHON%" -c "import hashlib,pathlib,zipfile; p=pathlib.Path(r'dist/JARVIS-Windows.zip'); names=set(zipfile.ZipFile(p).namelist()); required={'JARVIS.exe','version.txt'}; missing=required-names; assert not missing, f'Missing ZIP root entries: {sorted(missing)}'; expected=pathlib.Path(str(p)+'.sha256').read_text(encoding='ascii').split()[0]; actual=hashlib.sha256(p.read_bytes()).hexdigest(); assert expected==actual, 'SHA-256 file does not match the ZIP'; print('Release ZIP and checksum verified.')" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

REM Locate Inno Setup even if its install folder is not on PATH.
set "ISCC_PATH="
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC_PATH set "ISCC_PATH=%%I"
if not defined ISCC_PATH if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if defined ISCC_PATH (
    set "BUILD_STAGE=Inno Setup installer compilation"
    call "%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% installer.iss >>"%BUILD_LOG%" 2>&1
    if errorlevel 1 goto :failed
) else (
    echo.
    echo Inno Setup compiler was not found automatically.
    echo The app and update ZIP are ready; open installer.iss and press F9.
)

echo.
echo BUILD COMPLETE - VERSION %APP_VERSION%
echo Desktop app:  dist\JARVIS\JARVIS.exe
echo Update ZIP:   dist\JARVIS-Windows.zip
echo Checksum:     dist\JARVIS-Windows.zip.sha256
echo Launcher:    dist\JARVIS-Launcher.exe
if exist output\JARVIS-Setup.exe echo One-file installer: output\JARVIS-Setup.exe (J.A.R.V.I.S. + signed Ollama runtime)
echo Build log:    %BUILD_LOG%
echo.
echo Do not publish until the new installer has been tested locally.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED during: %BUILD_STAGE%.
echo Full log: %BUILD_LOG%
echo --------------------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%BUILD_LOG%' -Tail 100"
echo --------------------------------------------------------------
echo Fix the reported step before publishing this version.
echo You can send build.log to ChatGPT for help.
pause
exit /b 1
