@echo off
setlocal

echo.
echo  Stats++ Launcher
echo  =================
echo.

:: Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    where python3 >nul 2>nul
    if %errorlevel% neq 0 (
        echo  [ERROR] Python not found.
        echo.
        echo  Stats++ requires Python 3.10 or newer.
        echo  Download it from: https://www.python.org/downloads/
        echo.
        echo  During installation, make sure to check "Add Python to PATH".
        echo.
        pause
        exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)

:: Verify Python version
%PYTHON% -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if %errorlevel% neq 0 (
    echo  [ERROR] Python 3.10+ required.
    echo.
    %PYTHON% --version
    echo.
    echo  Download the latest version from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: Guard the most common mis-extract: the unzip tool created a nested
:: statsplusplus-vX.Y.Z\ folder, so the real files sit one level down and the
:: launcher is running in the wrong place. Give a clear fix instead of a
:: cryptic "No module named statsplusplus" later.
if not exist "pyproject.toml" goto :misextract
if not exist "web\app.py" goto :misextract
goto :files_ok
:misextract
echo.
echo  [ERROR] Stats++ files aren't where the launcher expects them.
echo          It looks like the zip may have extracted into a subfolder.
echo          Move everything from that subfolder up into THIS folder
echo          (so start.bat sits next to pyproject.toml and the web folder),
echo          then re-run start.bat.
echo.
pause
exit /b 1
:files_ok

:: Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo  Creating virtual environment...
    %PYTHON% -m venv .venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Install/update the package (editable). Installs Flask AND puts the
:: statsplusplus package (src/ layout) on the path — required, or the app
:: fails with "No module named 'statsplusplus'".
::
:: Version-aware: pip skips reinstalling an editable package it thinks is
:: already satisfied, so after extracting a new zip the registered metadata can
:: lag the shipped code. Compare the version pip last registered against the
:: freshly-extracted pyproject.toml and force a clean reinstall when they differ.
echo  Checking dependencies...
set "INSTALLED_VER=none"
for /f "delims=" %%v in ('.venv\Scripts\python -c "from importlib.metadata import version; print(version('statsplusplus'))" 2^>nul') do set "INSTALLED_VER=%%v"
set "SHIPPED_VER="
for /f "tokens=2 delims== " %%v in ('findstr /r /c:"^ *version *=" pyproject.toml') do if not defined SHIPPED_VER set "SHIPPED_VER=%%~v"

if "%INSTALLED_VER%"=="%SHIPPED_VER%" (
    .venv\Scripts\pip install -q -e . >nul 2>nul
    echo  Already up to date: v%SHIPPED_VER%
) else (
    .venv\Scripts\pip install -e . >"%TEMP%\spp_install.log" 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo  [ERROR] Update install failed. The extracted files may be incomplete.
        echo          Try re-extracting the release zip over this folder, then re-run.
        echo          Details: %TEMP%\spp_install.log
        echo.
        pause
        exit /b 1
    )
    if "%INSTALLED_VER%"=="none" (
        echo  Installed Stats++ v%SHIPPED_VER%.
    ) else (
        echo  Updated: v%INSTALLED_VER% -^> v%SHIPPED_VER%
    )
)

:: Prune stale files left over from a previous version (manifest-based; no-op in
:: dev checkouts that lack MANIFEST.txt). See prune_stale.py.
.venv\Scripts\python prune_stale.py 2>nul

:: Launch the app
echo.
echo  Starting Stats++...
echo  Open your browser to: http://localhost:5001
echo.
echo  Press Ctrl+C to stop the server.
echo.

:: Open browser after a short delay
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5001"

:: Run the server
.venv\Scripts\python web\app.py

pause
