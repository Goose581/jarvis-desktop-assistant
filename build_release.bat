
@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================================
REM J.A.R.V.I.S. BUILD SYSTEM
REM Version 1.6.2
REM Designed to build without administrator privileges.
REM ============================================================

set "APP_VERSION=1.6.2"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "BUILD_LOG=%~dp0build.log"
set "BUILD_STAGE=initial checks"

REM Prevent pip from using the shared Windows wheel cache.
REM This fixes the permission error seen on your computer.
set "PIP_NO_CACHE_DIR=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_INPUT=1"
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"

> "%BUILD_LOG%" echo J.A.R.V.I.S. build log - version %APP_VERSION%
echo.
echo ============================================================
echo             J.A.R.V.I.S. BUILD SYSTEM
echo                    VERSION %APP_VERSION%
echo ============================================================
echo.
echo Build log: %BUILD_LOG%
echo.

REM ------------------------------------------------------------
REM 1. CHECK PYTHON
REM ------------------------------------------------------------

where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python launcher was not found.
    echo Install Python 3.10 or newer, 64-bit.
    echo Python launcher not found.>>"%BUILD_LOG%"
    goto :failed
)

REM ------------------------------------------------------------
REM 2. CREATE VIRTUAL ENVIRONMENT
REM ------------------------------------------------------------

if not exist "%PYTHON%" (
    echo Creating project virtual environment...
    py -3 -m venv "%~dp0.venv" >>"%BUILD_LOG%" 2>&1
    if errorlevel 1 goto :failed
)

if not exist "%PYTHON%" (
    echo ERROR: Virtual environment Python was not created.
    goto :failed
)

"%PYTHON%" -c "import struct,sys; print('Python:',sys.version); print('Architecture:',struct.calcsize('P')*8,'bit'); raise SystemExit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 else 1)" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.10+ 64-bit is required.
    goto :failed
)

REM ------------------------------------------------------------
REM 3. INSTALL BUILD DEPENDENCIES
REM ------------------------------------------------------------

echo [1/6] Installing build dependencies...
set "BUILD_STAGE=dependency installation"

REM Upgrade pip without using the shared cache.
call "%PYTHON%" -m pip install --upgrade pip --no-cache-dir --disable-pip-version-check >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

REM Install required packages without accessing the shared cache.
call "%PYTHON%" -m pip install --no-cache-dir --disable-pip-version-check -r "%~dp0requirements-build.txt" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

echo Dependency installation complete.

REM ------------------------------------------------------------
REM 4. PYTHON SYNTAX CHECK
REM ------------------------------------------------------------

echo.
echo [2/6] Checking Python syntax...
set "BUILD_STAGE=Python syntax check"

call "%PYTHON%" -m compileall -q JARVIS.py JARVIS_GUI.py jarvis_workspace.py jarvis_model_manager.py launcher.py pyi_rth_stdio.py tests >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

echo Python syntax checks passed.

REM ------------------------------------------------------------
REM 5. AUTOMATED TESTS
REM ------------------------------------------------------------

echo.
echo [3/6] Running automated tests...
set "BUILD_STAGE=automated tests"

call "%PYTHON%" -m unittest discover -s tests -v >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

echo Automated tests passed.

REM ------------------------------------------------------------
REM 6. DOWNLOAD AND VERIFY OLLAMA RUNTIME
REM ------------------------------------------------------------

echo.
echo [4/6] Preparing Ollama runtime...
set "BUILD_STAGE=Ollama runtime download and verification"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download_ollama.ps1" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

if not exist "%~dp0vendor" (
    echo ERROR: Ollama vendor directory was not created.
    goto :failed
)

echo Ollama runtime preparation complete.

REM ------------------------------------------------------------
REM 7. CLEAN OLD BUILD FILES
REM ------------------------------------------------------------

echo.
echo Cleaning previous build files...

if exist "%~dp0build" rmdir /s /q "%~dp0build"
if errorlevel 1 goto :failed

if exist "%~dp0dist" rmdir /s /q "%~dp0dist"
if errorlevel 1 goto :failed

if exist "%~dp0output" rmdir /s /q "%~dp0output"
if errorlevel 1 goto :failed

if exist "%~dp0JARVIS.spec" del /q "%~dp0JARVIS.spec"
if exist "%~dp0JARVIS-Launcher.spec" del /q "%~dp0JARVIS-Launcher.spec"

REM ------------------------------------------------------------
REM 8. BUILD DESKTOP APPLICATION
REM ------------------------------------------------------------

echo.
echo [5/6] Building desktop application...
set "BUILD_STAGE=desktop application packaging"

call "%PYTHON%" -m PyInstaller --noconfirm --clean --onedir --windowed --name JARVIS --runtime-hook pyi_rth_stdio.py --collect-all pyttsx3 --collect-all comtypes --collect-all ollama --collect-all pyautogui --collect-all pyperclip --collect-all tzdata --hidden-import winsound --hidden-import pyttsx3.drivers.sapi5 --add-data "assets\jarvis_timer_alarm.wav;assets" JARVIS_GUI.py >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

if not exist "%~dp0dist\JARVIS\JARVIS.exe" (
    echo ERROR: JARVIS.exe was not created.
    goto :failed
)

> "%~dp0dist\JARVIS\version.txt" echo %APP_VERSION%

echo Desktop application created.

REM ------------------------------------------------------------
REM 9. BUILD UPDATER
REM ------------------------------------------------------------

echo.
echo [6/6] Building updater and release assets...
set "BUILD_STAGE=updater packaging"

call "%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --name JARVIS-Launcher --runtime-hook pyi_rth_stdio.py --hidden-import tkinter --hidden-import tkinter.ttk launcher.py >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

if not exist "%~dp0dist\JARVIS-Launcher.exe" (
    echo ERROR: JARVIS-Launcher.exe was not created.
    goto :failed
)

REM Copy updater configuration.
copy /y "%~dp0update_config.json" "%~dp0dist\update_config.json" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

REM ------------------------------------------------------------
REM 10. CREATE UPDATE ZIP
REM ------------------------------------------------------------

set "BUILD_STAGE=update ZIP creation"

echo Creating update ZIP...

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%~dp0dist\JARVIS\*' -DestinationPath '%~dp0dist\JARVIS-Windows.zip' -Force" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

if not exist "%~dp0dist\JARVIS-Windows.zip" (
    echo ERROR: Update ZIP was not created.
    goto :failed
)

REM ------------------------------------------------------------
REM 11. GENERATE SHA-256 CHECKSUM
REM ------------------------------------------------------------

set "BUILD_STAGE=SHA-256 generation"

call "%PYTHON%" -c "import hashlib,pathlib; p=pathlib.Path(r'dist/JARVIS-Windows.zip'); h=hashlib.sha256(); f=p.open('rb'); [h.update(b) for b in iter(lambda:f.read(1024*1024),b'')]; f.close(); pathlib.Path(str(p)+'.sha256').write_text(h.hexdigest() + '  JARVIS-Windows.zip\n',encoding='ascii')" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

REM ------------------------------------------------------------
REM 12. VERIFY RELEASE ASSETS
REM ------------------------------------------------------------

echo Verifying release assets...
set "BUILD_STAGE=release asset verification"

call "%PYTHON%" -c "import hashlib,pathlib,zipfile; p=pathlib.Path(r'dist/JARVIS-Windows.zip'); z=zipfile.ZipFile(p); names=set(z.namelist()); required={'JARVIS.exe','version.txt'}; missing=required-names; assert not missing,f'Missing ZIP root entries: {sorted(missing)}'; expected=pathlib.Path(str(p)+'.sha256').read_text(encoding='ascii').split()[0]; h=hashlib.sha256(); f=p.open('rb'); [h.update(b) for b in iter(lambda:f.read(1024*1024),b'')]; f.close(); assert expected==h.hexdigest(),'Checksum mismatch'; print('ZIP and SHA-256 verified successfully.')" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :failed

REM ------------------------------------------------------------
REM 13. FIND INNO SETUP
REM ------------------------------------------------------------

set "ISCC_PATH="

for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC_PATH set "ISCC_PATH=%%I"

if not defined ISCC_PATH if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"

if not defined ISCC_PATH if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC_PATH if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

REM ------------------------------------------------------------
REM 14. BUILD ONE-FILE INSTALLER
REM ------------------------------------------------------------

if defined ISCC_PATH (
    echo.
    echo Compiling Windows installer...
    set "BUILD_STAGE=Inno Setup installer compilation"

    call "%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% "%~dp0installer.iss" >>"%BUILD_LOG%" 2>&1
    if errorlevel 1 goto :failed

    if not exist "%~dp0output\JARVIS-Setup.exe" (
        echo ERROR: Installer compilation finished but the installer is missing.
        goto :failed
    )

    echo Installer created successfully.
) else (
    echo.
    echo WARNING: Inno Setup compiler was not detected.
    echo The desktop application and update ZIP are ready.
    echo Open installer.iss in Inno Setup and press F9 to compile.
)

REM ------------------------------------------------------------
REM 15. BUILD SUMMARY
REM ------------------------------------------------------------

echo.
echo ============================================================
echo                 BUILD COMPLETE
echo ============================================================
echo Version:       %APP_VERSION%
echo.
echo Desktop app:   dist\JARVIS\JARVIS.exe
echo Launcher:      dist\JARVIS-Launcher.exe
echo Update ZIP:    dist\JARVIS-Windows.zip
echo Checksum:      dist\JARVIS-Windows.zip.sha256

if exist "%~dp0output\JARVIS-Setup.exe" echo Installer:      output\JARVIS-Setup.exe

echo.
echo Build log:     %BUILD_LOG%
echo.
echo IMPORTANT:
echo Test the installer before publishing the release.
echo ============================================================
echo.

pause
exit /b 0

REM ------------------------------------------------------------
REM ERROR HANDLER
REM ------------------------------------------------------------

:failed

echo.
echo ============================================================
echo BUILD FAILED during: %BUILD_STAGE%
echo.
echo Log file: %BUILD_LOG%
echo ============================================================
echo.

if exist "%BUILD_LOG%" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%BUILD_LOG%' -Tail 100"
)

echo.
echo Please check build.log for the full error.
echo Do not publish an incomplete build.
echo.

pause
exit /b 1
