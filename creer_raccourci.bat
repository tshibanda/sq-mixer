@echo off
REM Cree un raccourci "SQ Mixer" sur le Bureau, pointant sur ce dossier.
REM A lancer une seule fois.

setlocal
cd /d "%~dp0"

if not exist "demarrer.bat" (
    echo [ERREUR] demarrer.bat introuvable dans %CD%
    pause
    exit /b 1
)

set "CIBLE=%~dp0demarrer.bat"
set "ICONE=%~dp0icone.ico"
set "DOSSIER=%~dp0"

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\SQ Mixer.lnk');" ^
  "$s.TargetPath = '%CIBLE%';" ^
  "$s.WorkingDirectory = '%DOSSIER%';" ^
  "$s.Description = 'Surface de mixage Allen & Heath SQ vers OBS';" ^
  "if (Test-Path '%ICONE%') { $s.IconLocation = '%ICONE%' };" ^
  "$s.Save()"

if errorlevel 1 (
    echo [ERREUR] Creation du raccourci impossible.
) else (
    echo Raccourci "SQ Mixer" cree sur le Bureau.
)

echo.
pause
endlocal
