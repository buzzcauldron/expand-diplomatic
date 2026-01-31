@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "SH_NAME=build-windows-msi.sh"

:: Find bash (Git for Windows, or WSL, or any bash in PATH)
set "BASH="
where bash >nul 2>&1 && set "BASH=bash"
if not defined BASH if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH=%ProgramFiles%\Git\bin\bash.exe"
if not defined BASH if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH=%ProgramFiles(x86)%\Git\bin\bash.exe"

if not defined BASH (
  echo.
  echo [ERROR] Git for Windows ^(bash^) was not found. It is required to run the build script.
  echo.
  echo If Git is already installed but you see this, do NOT double-click the .sh file
  echo in Explorer^—Windows may open it in Notepad. Run this .bat file instead, or open
  echo "Git Bash" from the Start menu, cd to this project folder, and run:
  echo   ./scripts/build-windows-msi.sh
  echo.
  winget --version >nul 2>&1
  if %errorlevel% equ 0 (
    echo Attempting to install Git via winget...
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    echo.
    echo After installation, close this window, open a new Command Prompt or PowerShell,
    echo cd to this project folder, and run: scripts\build-windows-msi.bat
    exit /b 1
  ) else (
    echo Install Git for Windows from: https://git-scm.com/download/win
    echo Then run this .bat file again.
    exit /b 1
  )
)

:: Path for bash: forward slashes
set "SH_PATH=%SCRIPT_DIR:\=/%"
set "SH_PATH=%SH_PATH%%SH_NAME%"

cd /d "%PROJECT_ROOT%"
"%BASH%" -e "%SH_PATH%" %*
exit /b %errorlevel%
