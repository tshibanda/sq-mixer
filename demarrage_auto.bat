@echo off
REM Active ou desactive le lancement automatique de SQ Mixer a l'ouverture
REM de session Windows, via un raccourci dans le dossier Demarrage de
REM l'utilisateur courant (aucun droit administrateur requis).
REM   demarrage_auto.bat        -> active
REM   demarrage_auto.bat /off   -> desactive
setlocal
cd /d "%~dp0"

if not exist "demarrer.bat" (
    echo [ERREUR] demarrer.bat introuvable dans %CD%
    goto :fin
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LIEN=%STARTUP%\SQ Mixer.lnk"

if /i "%~1"=="/off" (
    if exist "%LIEN%" (
        del "%LIEN%"
        echo SQ Mixer retire du demarrage de Windows.
    ) else (
        echo SQ Mixer n'etait pas dans le demarrage de Windows.
    )
    goto :fin
)

set "CIBLE=%~dp0demarrer.bat"
set "ICONE=%~dp0icone.ico"
set "DOSSIER=%~dp0"

REM WindowStyle 7 = fenetre reduite : le moteur demarre en tache de fond,
REM le navigateur s'ouvre normalement par-dessus. La console reste
REM accessible depuis la barre des taches pour surveiller tampon/coupures.
powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%LIEN%');" ^
  "$s.TargetPath = '%CIBLE%';" ^
  "$s.WorkingDirectory = '%DOSSIER%';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Lance SQ Mixer au demarrage de Windows';" ^
  "if (Test-Path '%ICONE%') { $s.IconLocation = '%ICONE%' };" ^
  "$s.Save()"

if errorlevel 1 (
    echo [ERREUR] Impossible de creer le raccourci de demarrage.
) else (
    echo.
    echo SQ Mixer demarrera desormais automatiquement a l'ouverture de session.
    echo Pour annuler : demarrage_auto.bat /off
)

:fin
echo.
pause
endlocal
