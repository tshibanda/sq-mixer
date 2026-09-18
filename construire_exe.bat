@echo off
REM Compile SQ Mixer en un executable autonome : dist\SQ Mixer.exe
REM A lancer une fois, sur cette machine. Necessite une connexion internet.

setlocal
cd /d "%~dp0"
title Construction de SQ Mixer.exe

echo ================================================
echo   Construction de l'executable
echo ================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python introuvable. Reinstallez-le en cochant
    echo "Add python.exe to PATH".
    goto :fin
)

echo Installation des outils de compilation...
python -m pip install --upgrade pip --quiet
python -m pip install pyinstaller numpy sounddevice fastapi uvicorn websockets
if errorlevel 1 (
    echo [ERREUR] Installation des dependances impossible.
    goto :fin
)

echo.
echo Compilation en cours, comptez deux a quatre minutes...
echo.

set "OPT_ICONE="
if exist "icone.ico" set "OPT_ICONE=--icon icone.ico"

python -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --console ^
  --name "SQ Mixer" ^
  %OPT_ICONE% ^
  --add-data "ui.html;." ^
  --collect-all sounddevice ^
  --collect-all _sounddevice_data ^
  --hidden-import websockets ^
  --hidden-import uvicorn.protocols.websockets.websockets_impl ^
  --hidden-import uvicorn.protocols.http.h11_impl ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import uvicorn.loops.asyncio ^
  sq_mixer.py

if errorlevel 1 (
    echo.
    echo [ERREUR] La compilation a echoue.
    goto :fin
)

if not exist "dist\SQ Mixer.exe" (
    echo [ERREUR] L'executable n'a pas ete produit.
    goto :fin
)

REM La config et les presets vivent a cote de l'exe
if exist "config.json" copy /y "config.json" "dist\config.json" >nul
if not exist "dist\presets" mkdir "dist\presets"
if exist "icone.ico" copy /y "icone.ico" "dist\icone.ico" >nul

echo.
echo ================================================
echo   Termine : dist\SQ Mixer.exe
echo ================================================
echo.
echo Copiez tout le dossier "dist" ou vous voulez.
echo Clic droit sur l'exe ^> Envoyer vers ^> Bureau
echo pour avoir votre raccourci en un clic.
echo.

explorer "%~dp0dist"

:fin
echo.
pause
endlocal
