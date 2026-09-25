@echo off
REM Active ou desactive le lancement automatique de SQ Mixer a l'ouverture
REM de session Windows, via une tache planifiee (declenchement "a l'ouverture
REM de session"). Plus fiable qu'un raccourci dans le dossier Demarrage :
REM Windows (ou un antivirus) peut desactiver ces raccourcis en silence,
REM sans le moindre message, et ca ne se voit que dans l'onglet Demarrage
REM du Gestionnaire des taches. Une tache planifiee, elle, a un historique
REM consultable (Planificateur de taches > SQ Mixer > onglet Historique).
REM Ne necessite pas de droits administrateur (/rl limited).
REM   demarrage_auto.bat        -> active
REM   demarrage_auto.bat /off   -> desactive
setlocal
cd /d "%~dp0"

set "NOM_TACHE=SQ Mixer"

REM Nettoyage d'un raccourci pose par une version precedente de ce script.
set "LIEN=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SQ Mixer.lnk"
if exist "%LIEN%" del "%LIEN%"

if /i "%~1"=="/off" (
    schtasks /delete /tn "%NOM_TACHE%" /f >nul 2>&1
    echo SQ Mixer retire du demarrage de Windows.
    goto :fin
)

if not exist "demarrer.bat" (
    echo [ERREUR] demarrer.bat introuvable dans %CD%
    goto :fin
)

set "CIBLE=%~dp0demarrer.bat"

schtasks /create /tn "%NOM_TACHE%" /tr "\"%CIBLE%\"" /sc onlogon /rl limited /f
if errorlevel 1 (
    echo.
    echo [ERREUR] Impossible de creer la tache planifiee.
) else (
    echo.
    echo SQ Mixer demarrera desormais automatiquement a l'ouverture de session.
    echo Verifiable dans le Planificateur de taches Windows ^(taskschd.msc^),
    echo Bibliotheque du Planificateur, tache "%NOM_TACHE%".
    echo Pour annuler : demarrage_auto.bat /off
)

:fin
echo.
pause
endlocal
