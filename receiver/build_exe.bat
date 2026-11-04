@echo off
REM Genera dist\PhoneCam\PhoneCam.exe (no necesita Python instalado para ejecutarse).
cd /d "%~dp0"
if not exist .venv call run.bat --help >nul
.venv\Scripts\python -m pip install pyinstaller || exit /b 1
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name PhoneCam ^
  --collect-all aiortc --collect-all av --collect-all aioice --collect-all pylibsrtp ^
  --collect-all pyvirtualcam --collect-all zeroconf ^
  phonecam.py || exit /b 1
echo.
echo Listo: dist\PhoneCam\PhoneCam.exe
