@echo off
REM Deploie les fichiers web (dashboard, defilement, styles) vers le service
REM installe et redemarre le service. Copie boulangerie_web_pro\static ->
REM C:\Program Files\Boulangerie Lomoto\_internal\boulangerie_web_pro\static.
REM Demande automatiquement les droits administrateur (invite Windows / UAC).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\mettre-a-jour-web-lomoto-installe.ps1"
echo.
echo Termine. Fermez cette fenetre, puis rechargez la page (Ctrl+F5) ou l'application.
pause
