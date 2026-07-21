@echo off
REM ============================================================
REM  MT Desk — Windows Build Script
REM  Usage: Double-click this file or run from command line
REM  Prerequisites: Python 3.11+ with tkinter support
REM ============================================================

echo ========================================
echo   MT Desk — Windows EXE Builder
echo ========================================
echo.

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

echo [1/3] Installing PyInstaller...
pip install pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install PyInstaller
    pause
    exit /b 1
)

echo.
echo [2/3] Building MT_Desk.exe...
pyinstaller --onefile --noconsole ^
    --name "MT_Desk" ^
    --hidden-import tkinter ^
    --hidden-import tkinter.filedialog ^
    --hidden-import tkinter.messagebox ^
    --hidden-import mt_desk ^
    --hidden-import mt_desk.parser ^
    --hidden-import mt_desk.analysis ^
    mt_desk/main.py

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed
    pause
    exit /b 1
)

echo.
echo [3/3] Verifying build...
if exist "dist\MT_Desk.exe" (
    for %%A in ("dist\MT_Desk.exe") do echo [OK] MT_Desk.exe built successfully: %%~zA bytes
    echo.
    echo Build complete! The EXE is at: dist\MT_Desk.exe
) else (
    echo [ERROR] dist\MT_Desk.exe not found
    pause
    exit /b 1
)

pause
