@echo off
REM Ejecutar como administrador (clic derecho > Ejecutar como administrador).
REM Permite que el telefono llegue a PhoneCam en redes privadas (TCP 8765 + UDP de WebRTC).
REM Funciona tanto en la carpeta receiver\ como junto a PhoneCam.exe (descarga de GitHub).
net session >nul 2>&1 || (echo Ejecuta este archivo como administrador. & pause & exit /b 1)
cd /d "%~dp0"
netsh advfirewall firewall delete rule name="PhoneCam" >nul 2>&1
set FOUND=0
if exist "%~dp0PhoneCam.exe" (
    netsh advfirewall firewall add rule name="PhoneCam" dir=in action=allow profile=private program="%~dp0PhoneCam.exe" enable=yes
    set FOUND=1
)
if exist dist\PhoneCam\PhoneCam.exe (
    netsh advfirewall firewall add rule name="PhoneCam" dir=in action=allow profile=private program="%~dp0dist\PhoneCam\PhoneCam.exe" enable=yes
    set FOUND=1
)
if exist .venv\Scripts\python.exe (
    netsh advfirewall firewall add rule name="PhoneCam" dir=in action=allow profile=private program="%~dp0.venv\Scripts\python.exe" enable=yes
    set FOUND=1
)
if "%FOUND%"=="0" (
    echo No encontre PhoneCam.exe ni .venv junto a este archivo. No se agrego ninguna regla.
    pause
    exit /b 1
)
echo.
echo Listo. Asegurate de que tu red Wi-Fi este marcada como "Privada" en Windows
echo (Configuracion ^> Red e Internet ^> Wi-Fi ^> tu red ^> Tipo de perfil: Privada).
pause
