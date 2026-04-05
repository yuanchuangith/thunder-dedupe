@echo off
chcp 65001 >nul
echo ========================================
echo 迅雷去重助手 - 打包脚本
echo ========================================
echo.

REM 设置变量
set PYTHON_ENV=D:\Anaconda\envs\checkcode
set PYINSTALLER=%PYTHON_ENV%\Scripts\pyinstaller.exe
set PROJECT_DIR=%~dp0
set DIST_DIR=%PROJECT_DIR%dist
set SRC_DIR=%PROJECT_DIR%src

REM 清理旧的构建文件
echo [1/4] 清理旧的构建文件...
if exist "%PROJECT_DIR%build" rmdir /s /q "%PROJECT_DIR%build"
if exist "%DIST_DIR%\ThunderDedupe.exe" del /f /q "%DIST_DIR%\ThunderDedupe.exe"

REM 确保dist目录存在
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

echo [2/4] 开始打包...
echo.

REM 执行打包命令
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
    echo [错误] 打包失败！
    pause
    exit /b 1
)

echo.
echo [3/4] 打包完成！
echo.

REM 显示文件信息
echo [4/4] 输出文件信息:
echo ----------------------------------------
dir "%DIST_DIR%\ThunderDedupe.exe" | findstr "ThunderDedupe"
echo ----------------------------------------
echo.
echo 输出目录: %DIST_DIR%
echo.

pause