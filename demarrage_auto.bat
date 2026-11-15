@echo off
REM Active ou desactive le lancement automatique de SQ Mixer a l'ouverture
REM de session Windows.
REM
REM Essaie d'abord une tache planifiee (schtasks, declencheur onlogon).
REM Si ca echoue avec "Acces refuse" (politique ou antivirus qui bloque
REM la creation de taches, vu sur certains PC geres) : se rabat sur une
REM entree de demarrage dans le registre de l'utilisateur courant (HKCU),
REM qui ne demande jamais de droits admin et n'est quasiment jamais
REM bloquee.
REM
REM   demarrage_auto.bat        -> active
REM   demarrage_auto.bat /off   -> desactive
setlocal
cd /d "%~dp0"

set "NOM_TACHE=SQ Mixer"
set "CLE_REG=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"

REM Nettoyage d'un raccourci pose par une version encore plus ancienne de
REM ce script (methode abandonnee : desactivable en silence par Windows).
set "LIEN=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SQ Mixer.lnk"
if exist "%LIEN%" del "%LIEN%"

if /i "%~1"=="/off" (
    schtasks /delete /tn "%NOM_TACHE%" /f >nul 2>&1
    reg delete "%CLE_REG%" /v "%NOM_TACHE%" /f >nul 2>&1
    echo SQ Mixer retire du demarrage de Windows.
    goto :fin
)

if not exist "demarrer.bat" (
    echo [ERREUR] demarrer.bat introuvable dans %CD%
    goto :fin
)
if not exist "demarrer_cache.vbs" (
    echo [ERREUR] demarrer_cache.vbs introuvable dans %CD%
    goto :fin
)

set "VBS=%~dp0demarrer_cache.vbs"

REM On retire d'abord une eventuelle tache/entree precedente, pour ne pas
REM se retrouver avec les deux methodes actives (lancement en double).
schtasks /delete /tn "%NOM_TACHE%" /f >nul 2>&1
reg delete "%CLE_REG%" /v "%NOM_TACHE%" /f >nul 2>&1

REM Passe par demarrer_cache.vbs (WScript.Shell.Run ..., 0, False) : lance
REM demarrer.bat sans aucune fenetre ni icone dans la barre des taches,
REM impossible a fermer par megarde pendant un direct. Un simple
REM "start /min" laisse encore une icone cliquable-fermable ; ca ne
REM suffisait plus.
schtasks /create /tn "%NOM_TACHE%" /tr "wscript.exe \"%VBS%\"" /sc onlogon /rl limited /f >nul 2>&1
if not errorlevel 1 (
    echo.
    echo SQ Mixer demarrera desormais automatiquement en arriere-plan
    echo ^(sans fenetre^) a l'ouverture de session ^(tache planifiee
    echo "%NOM_TACHE%"^). Pour annuler : demarrage_auto.bat /off
    goto :fin
)

echo Tache planifiee refusee sur cette machine, methode de secours ^(registre^)...
reg add "%CLE_REG%" /v "%NOM_TACHE%" /t REG_SZ /d "wscript.exe \"%VBS%\"" /f
if errorlevel 1 (
    echo.
    echo [ERREUR] Les deux methodes ont echoue. Cette machine bloque
    echo probablement les demarrages automatiques ^(politique ou antivirus^).
    echo Contactez la personne qui gere ce PC.
) else (
    echo.
    echo SQ Mixer demarrera desormais automatiquement en arriere-plan
    echo ^(sans fenetre^) a l'ouverture de session ^(entree de registre,
    echo methode de secours^). Pour annuler : demarrage_auto.bat /off
)

:fin
echo.
pause
endlocal
