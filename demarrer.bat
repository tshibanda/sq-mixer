@echo off
setlocal
title SQ Mixer
cd /d "%~dp0"

echo ================================================
echo   SQ Mixer - demarrage
echo ================================================
echo.

REM --- Python present ? -------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python est introuvable.
    echo.
    echo Reinstallez Python depuis python.org en cochant
    echo "Add python.exe to PATH" sur le premier ecran.
    goto :fin
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo Python detecte : %%v

REM --- Fichiers presents ? ----------------------------------------------
if not exist "sq_mixer.py" (
    echo [ERREUR] sq_mixer.py absent de %CD%
    goto :fin
)
if not exist "ui.html" (
    echo [ERREUR] ui.html absent de %CD%
    echo Le dossier est incomplet, recopiez tous les fichiers.
    goto :fin
)

REM --- Environnement virtuel --------------------------------------------
REM On teste l'executable, pas le dossier : un .venv a moitie cree
REM est la cause classique du "No module named numpy".
if not exist ".venv\Scripts\python.exe" (
    if exist ".venv" (
        echo Environnement precedent incomplet, reconstruction...
        rmdir /s /q ".venv"
    )
    echo Creation de l'environnement Python...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERREUR] Creation de l'environnement impossible.
        goto :fin
    )
)

set "PY=.venv\Scripts\python.exe"

REM --- Dependances ------------------------------------------------------
"%PY%" -c "import numpy, sounddevice, fastapi, uvicorn, websockets" >nul 2>&1
if errorlevel 1 (
    echo Installation des dependances, patientez une a deux minutes...
    echo.
    "%PY%" -m pip install --upgrade pip --quiet
    "%PY%" -m pip install numpy sounddevice fastapi uvicorn websockets
    echo.
    "%PY%" -c "import numpy, sounddevice, fastapi, uvicorn, websockets" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [ERREUR] Les dependances ne se sont pas installees.
        echo.
        echo Causes frequentes :
        echo   - pas de connexion internet
        echo   - un antivirus ou un proxy bloque pip
        echo.
        echo Essayez manuellement :
        echo   .venv\Scripts\python.exe -m pip install numpy sounddevice fastapi uvicorn websockets
        goto :fin
    )
    echo Dependances installees.
)

REM --- Lancement --------------------------------------------------------
echo.
echo Verifiez que la SQ est allumee et branchee en USB-B.
echo.
timeout /t 3 >nul

start "" http://localhost:8770
"%PY%" sq_mixer.py

:fin
echo.
echo ------------------------------------------------
echo Appuyez sur une touche pour fermer cette fenetre.
pause >nul
endlocal
