@echo off
REM Cree un raccourci "SQ Mixer" sur le Bureau, pointant sur ce dossier.
REM A lancer une seule fois.

setlocal
cd /d "%~dp0"

if not exist "demarrer_cache.vbs" (
    echo [ERREUR] demarrer_cache.vbs introuvable dans %CD%
    pause
    exit /b 1
)

set "CIBLE=%~dp0demarrer_cache.vbs"
set "ICONE=%~dp0icone.ico"
set "DOSSIER=%~dp0"

REM Lance via demarrer_cache.vbs (wscript), pas demarrer.bat directement :
REM meme ici, pas de console visible ni d'icone fermable par megarde.
powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\SQ Mixer.lnk');" ^
  "$s.TargetPath = (Join-Path $env:WINDIR 'System32\wscript.exe');" ^
  "$s.Arguments = '\"%CIBLE%\"';" ^
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
