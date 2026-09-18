@echo off
REM Met a jour ce dossier depuis GitHub (tshibanda/sq-mixer).
REM Ne touche jamais config.json ni presets\*.json : ils sont ignores par
REM git (etat propre a cette machine de regie).
setlocal
cd /d "%~dp0"

git --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] git est introuvable. Installez-le depuis git-scm.com
    pause
    exit /b 1
)

if not exist ".git" (
    echo Premiere mise a jour : rattachement au depot GitHub...
    git init
    git remote add origin https://github.com/tshibanda/sq-mixer.git
) else (
    echo Depot deja rattache.
)

echo Recuperation des dernieres modifications...
git fetch origin main
if errorlevel 1 (
    echo.
    echo [ERREUR] Impossible de contacter GitHub. Verifiez la connexion internet.
    goto :fin
)

git checkout -f -B main origin/main
git branch --set-upstream-to=origin/main main >nul 2>&1

echo.
echo Mise a jour terminee. Relancez demarrer.bat.

:fin
echo.
pause
endlocal
