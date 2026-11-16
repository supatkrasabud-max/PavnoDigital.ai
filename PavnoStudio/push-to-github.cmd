@echo off
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
set "REPO=%~dp0..\PavnoStudio-github"
echo === PAVNO: update website on GitHub ===
where git >nul 2>&1 || (echo Git not found. Please install Git for Windows. & pause & exit /b 1)
if not exist "%REPO%\.git" (
  echo Cloning GitHub repo into PavnoStudio-github ...
  git clone https://github.com/supatkrasabud-max/PavnoStudio.git "%REPO%" || (echo Clone failed & pause & exit /b 1)
)
cd /d "%REPO%"
git checkout main || (pause & exit /b 1)
git pull --ff-only origin main || (echo Pull failed & pause & exit /b 1)
git fetch "%HERE%pavno-update.bundle" site-update || (echo Bundle read failed & pause & exit /b 1)
git merge --ff-only FETCH_HEAD || (echo GitHub has newer changes - tell Claude & pause & exit /b 1)
echo.
echo === Latest commits ===
git log --oneline -6
echo.
echo Press any key to PUSH to GitHub (close this window to cancel)...
pause >nul
git push origin main || (echo Push failed - sign in to GitHub when the window pops up, then run again & pause & exit /b 1)
echo.
echo DONE. Vercel will update pavnodigital.com in 1-2 minutes.
pause
