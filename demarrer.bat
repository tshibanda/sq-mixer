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

REM --- Resynchronisation silencieuse de l'auto-demarrage -----------------
REM Si une tache planifiee ou une entree de registre "SQ Mixer" existe
REM deja (quelle que soit la methode/version qui l'a posee), on la
REM reecrit avec la commande actuelle (demarrer_cache.vbs) a CHAQUE
REM lancement. Sans ca, une evolution du mecanisme de lancement cache ne
REM s'applique qu'apres avoir repense a relancer demarrage_auto.bat a la
REM main - ce qui arrive. Si rien n'est configure (jamais active, ou
REM desactive expres via demarrage_auto.bat /off), on ne touche a rien :
REM ca ne doit jamais activer l'auto-demarrage tout seul.
if exist "demarrer_cache.vbs" (
    schtasks /query /tn "SQ Mixer" >nul 2>&1
    if not errorlevel 1 (
        schtasks /create /tn "SQ Mixer" /tr "wscript.exe \"%~dp0demarrer_cache.vbs\"" /sc onlogon /rl limited /f >nul 2>&1
    )
    reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "SQ Mixer" >nul 2>&1
    if not errorlevel 1 (
        reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "SQ Mixer" /t REG_SZ /d "wscript.exe \"%~dp0demarrer_cache.vbs\"" /f >nul 2>&1
    )
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

REM sq_mixer.py reessaie deja lui-meme la detection audio pendant 2
REM minutes. S'il s'arrete quand meme (peripherique debranche en cours de
REM route, erreur inattendue), on relance tout le processus au lieu
REM d'abandonner : au lancement automatique (fenetre cachee), personne
REM n'est la pour le refaire a la main. Consultez journal.log pour le
REM detail de chaque tentative.
set TENTATIVE=0
:relancer
set /a TENTATIVE+=1
"%PY%" sq_mixer.py
if errorlevel 1 (
    echo.
    echo Le moteur s'est arrete de maniere inattendue ^(tentative %TENTATIVE%^).
    echo Nouvel essai dans 30s... ^(Ctrl+C pour annuler^)
    timeout /t 30 >nul
    goto :relancer
)

:fin
echo.
echo ------------------------------------------------
echo Appuyez sur une touche pour fermer cette fenetre.
pause >nul
endlocal
