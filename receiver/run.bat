@echo off
REM Ejecuta el receptor PhoneCam. La primera vez crea un entorno virtual e instala dependencias.
cd /d "%~dp0"
if not exist .venv (
    echo Creando entorno virtual...
    py -3 -m venv .venv || python -m venv .venv || goto :nopython
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\python -m pip install -r requirements.txt || goto :error
)
.venv\Scripts\python phonecam.py %*
goto :eof
:nopython
echo No se encontro Python. Instalalo desde https://www.python.org (marca "Add Python to PATH").
pause
goto :eof
:error
echo Fallo la instalacion de dependencias.
pause
