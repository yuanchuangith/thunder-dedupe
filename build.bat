@echo off
chcp 936 >nul
echo ========================================
echo Thunder Dedupe - Build Script
echo ========================================
echo.

REM Get project directory
set PROJECT_DIR=%~dp0
set DIST_DIR=%PROJECT_DIR%dist
set SRC_DIR=%PROJECT_DIR%src
set RUNTIME_HOOKS=%PROJECT_DIR%runtime_hooks\pyi_rth_sqlite3.py

REM Conda environment path
set PYTHON_ENV=D:\Anaconda\envs\checkcode
set PYINSTALLER=%PYTHON_ENV%\Scripts\pyinstaller.exe
set PYTHON_EXE=%PYTHON_ENV%\python.exe
set LIB_BIN=%PYTHON_ENV%\Library\bin

REM Check PyInstaller exists
if not exist "%PYINSTALLER%" (
    echo [ERROR] PyInstaller not found at: %PYINSTALLER%
    echo Please check your Python environment.
    pause
    exit /b 1
)

echo Python: %PYTHON_EXE%
echo PyInstaller: %PYINSTALLER%
echo Project: %PROJECT_DIR%
echo.

REM Clean old build files
echo [1/4] Cleaning old build files...
if exist "%PROJECT_DIR%build" rmdir /s /q "%PROJECT_DIR%build"
if exist "%DIST_DIR%\ThunderDedupe.exe" del /f /q "%DIST_DIR%\ThunderDedupe.exe"

REM Ensure dist directory exists
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

echo [2/4] Building...
echo.

REM Run pyinstaller
"%PYINSTALLER%" ^
    --onefile ^
    --windowed ^
    --name "ThunderDedupe" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%PROJECT_DIR%build" ^
    --specpath "%PROJECT_DIR%build" ^
    --runtime-hook "%RUNTIME_HOOKS%" ^
    --clean ^
    --add-binary "%LIB_BIN%\sqlite3.dll;." ^
    --add-binary "%LIB_BIN%\liblzma.dll;." ^
    --add-binary "%LIB_BIN%\LIBBZ2.dll;." ^
    --add-binary "%LIB_BIN%\libmpdec-4.dll;." ^
    --add-binary "%LIB_BIN%\libexpat.dll;." ^
    --add-binary "%LIB_BIN%\ffi.dll;." ^
    "%SRC_DIR%\main.py"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo [3/4] Build completed!
echo.

REM Show output file info
echo [4/4] Output file:
echo ----------------------------------------
dir "%DIST_DIR%\ThunderDedupe.exe" | findstr "ThunderDedupe"
echo ----------------------------------------
echo.
echo Output directory: %DIST_DIR%
echo.

pause