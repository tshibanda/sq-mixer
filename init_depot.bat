@echo off
REM Initialise le depot git du projet. A lancer une seule fois.
setlocal
cd /d "%~dp0"

git --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] git est introuvable. Installez-le depuis git-scm.com
    pause
    exit /b 1
)

if exist ".git" (
    echo Le depot existe deja.
) else (
    git init
    git add .
    git commit -m "SQ Mixer : mixage 32 canaux ASIO vers OBS"
    echo.
    echo Depot cree. Pour l'envoyer sur GitHub :
    echo   git remote add origin https://github.com/VOTRE-COMPTE/sq-mixer.git
    echo   git branch -M main
    echo   git push -u origin main
)

echo.
pause
endlocal
