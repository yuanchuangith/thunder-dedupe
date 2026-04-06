@echo off
chcp 936 >nul
echo ========================================
echo Thunder Dedupe - Build Script
echo ========================================
echo.

REM Set variables
set PYTHON_ENV=D:\Anaconda\envs\checkcode
set PYINSTALLER=%PYTHON_ENV%\Scripts\pyinstaller.exe
set PROJECT_DIR=%~dp0
set DIST_DIR=%PROJECT_DIR%dist
set SRC_DIR=%PROJECT_DIR%src

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
    --clean ^
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/sqlite3.dll;." ^
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/liblzma.dll;." ^
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/LIBBZ2.dll;." ^
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/libmpdec-4.dll;." ^
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/libexpat.dll;." ^
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/ffi.dll;." ^
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