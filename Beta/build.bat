@echo off
setlocal enabledelayedexpansion
title StrangeCat Monitor - Builder

echo.
echo  ========================================
echo   STRANGECAT MONITOR  v1.1  -  Builder
echo  ========================================
echo.

:: Source directory (may contain spaces)
set "SRC=%~dp0"

:: Safe build directory WITHOUT spaces in path
set "BUILD_DIR=%TEMP%\StrangeCatBuild"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    pause & exit /b 1
)

:: Install deps
echo [1/4] Installing dependencies...
pip install pyinstaller psutil pillow pystray wmi pywin32 --quiet --upgrade 2>nul
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause & exit /b 1
)

:: Copy files to temp dir without spaces (preserve module structure)
echo [2/4] Copying to safe temp folder: %BUILD_DIR%
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
mkdir "%BUILD_DIR%"
xcopy /e /i /y /q "%SRC%base" "%BUILD_DIR%\base" >nul
xcopy /e /i /y /q "%SRC%ui"   "%BUILD_DIR%\ui"   >nul
copy /y "%SRC%make_icon_beta.py" "%BUILD_DIR%\make_icon_beta.py" >nul

:: Copy AMD Ryzen Master DLL if available
set HAS_AMD_DLL=0
if exist "%SRC%base\AMDRyzenMasterMonitoringDLL.dll" (
    copy /y "%SRC%base\AMDRyzenMasterMonitoringDLL.dll" "%BUILD_DIR%\base\" >nul
    echo [INFO] AMD Ryzen Master DLL found and will be included
    set HAS_AMD_DLL=1
) else (
    echo [INFO] AMD Ryzen Master DLL not found - AMD monitoring disabled
)

:: Generate icon in safe dir
echo [3/4] Generating icon.ico...
python "%BUILD_DIR%\make_icon_beta.py"
if not exist "%BUILD_DIR%\icon.ico" (
    echo [ERROR] icon.ico not generated.
    pause & exit /b 1
)

:: Build EXE from safe dir — no spaces anywhere in the paths passed to pyinstaller
echo [4/4] Building EXE...
cd /d "%BUILD_DIR%"

if %HAS_AMD_DLL%==1 (
    python -m PyInstaller --onefile --windowed --name StrangeCatMonitor --icon icon.ico ^
        --distpath dist --workpath build_tmp --specpath . ^
        --paths "%BUILD_DIR%" --paths "%BUILD_DIR%\base" ^
        --hidden-import config --hidden-import collector --hidden-import metrics ^
        --hidden-import http_server --hidden-import datastore ^
        --hidden-import ui.app --hidden-import ui.sidebar --hidden-import ui.performance ^
        --hidden-import ui.settings --hidden-import ui.graphs --hidden-import ui.widgets ^
        --hidden-import wmi --hidden-import win32com --hidden-import win32com.client ^
        --hidden-import pystray --hidden-import PIL.Image --hidden-import PIL.ImageDraw ^
        --hidden-import ryzen_master ^
        --add-data "base\ryzen_master.py;base" ^
        --add-data "base\AMDRyzenMasterMonitoringDLL.dll;base" ^
        "base\main.py"
) else (
    python -m PyInstaller --onefile --windowed --name StrangeCatMonitor --icon icon.ico ^
        --distpath dist --workpath build_tmp --specpath . ^
        --paths "%BUILD_DIR%" --paths "%BUILD_DIR%\base" ^
        --hidden-import config --hidden-import collector --hidden-import metrics ^
        --hidden-import http_server --hidden-import datastore ^
        --hidden-import ui.app --hidden-import ui.sidebar --hidden-import ui.performance ^
        --hidden-import ui.settings --hidden-import ui.graphs --hidden-import ui.widgets ^
        --hidden-import wmi --hidden-import win32com --hidden-import win32com.client ^
        --hidden-import pystray --hidden-import PIL.Image --hidden-import PIL.ImageDraw ^
        --add-data "base\ryzen_master.py;base" ^
        "base\main.py"
)

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. See output above.
    cd /d "%SRC%"
    pause & exit /b 1
)

:: Copy final EXE back, rename with spaces for display
if not exist "%SRC%dist" mkdir "%SRC%dist"
copy /y "%BUILD_DIR%\dist\StrangeCatMonitor.exe" "%SRC%dist\StrangeCat Monitor.exe" >nul

cd /d "%SRC%"

echo.
echo  ========================================
echo   SUCCESS!
echo   EXE: %SRC%dist\StrangeCat Monitor.exe
echo  ========================================
echo.

:: Launch the application
echo Starting StrangeCat Monitor...
start "" "%SRC%dist\StrangeCat Monitor.exe"

:: Close build window automatically
timeout /t 2 >nul
