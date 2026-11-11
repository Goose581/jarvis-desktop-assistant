@echo off
setlocal
cd /d "%~dp0"

REM Change this every time you publish a new J.A.R.V.I.S. release.
set APP_VERSION=1.0.0

where py >nul 2>nul
if errorlevel 1 (
    echo Python launcher 'py' was not found. Install Python 3.10+ from python.org.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto :failed
)

call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
call ".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :failed

REM Clean old build output.
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist JARVIS.spec del /q JARVIS.spec
if exist JARVIS-Launcher.spec del /q JARVIS-Launcher.spec

REM Build the existing assistant without changing its features.
call ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --console --name JARVIS --collect-all pyttsx3 --collect-all comtypes --collect-all ollama --collect-all pyautogui --collect-all pyperclip --hidden-import pyttsx3.drivers.sapi5 JARVIS.py
if errorlevel 1 goto :failed

> "dist\JARVIS\version.txt" echo %APP_VERSION%

REM Build the small launcher separately. It stays outside the app folder,
REM so it can replace the JARVIS application files while JARVIS is closed.
call ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name JARVIS-Launcher launcher.py
if errorlevel 1 goto :failed

copy /y update_config.json dist\update_config.json >nul

REM Zip the CONTENTS of dist\JARVIS (JARVIS.exe must be at the ZIP root).
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\JARVIS\*' -DestinationPath 'dist\JARVIS-Windows.zip' -Force"
if errorlevel 1 goto :failed

REM Create a plain SHA-256 checksum file that the launcher verifies before installing.
".venv\Scripts\python.exe" -c "import hashlib,pathlib; p=pathlib.Path(r'dist/JARVIS-Windows.zip'); pathlib.Path(str(p)+'.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest(), encoding='ascii')"
if errorlevel 1 goto :failed

REM Compile the first-time installer when Inno Setup is installed.
where ISCC.exe >nul 2>nul
if not errorlevel 1 (
    ISCC.exe installer.iss
) else (
    echo Inno Setup not found. The EXE build and update ZIP are ready; install Inno Setup to create JARVIS-Setup.exe.
)

echo.
echo BUILD COMPLETE.
echo App folder: dist\JARVIS
 echo Launcher: dist\JARVIS-Launcher.exe
 echo Update asset: dist\JARVIS-Windows.zip
 echo Checksum: dist\JARVIS-Windows.zip.sha256
 echo.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED. Read the error above.
pause
exit /b 1
