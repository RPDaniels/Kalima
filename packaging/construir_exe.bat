@echo off
rem Genera dist\Kalima.exe. Necesita Python 3.12 (py -3.12) instalado.
rem Ejecutar con doble clic o desde la carpeta del proyecto.
setlocal
cd /d "%~dp0.."

py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo No se encuentra Python 3.12. Instalalo desde python.org y vuelve a intentarlo.
    pause
    exit /b 1
)

echo Instalando dependencias...
py -3.12 -m pip install --upgrade pyinstaller mido python-rtmidi || goto error

echo Construyendo Kalima.exe...
py -3.12 -m PyInstaller --noconfirm --clean packaging\Kalima.spec || goto error

echo.
echo Listo: dist\Kalima.exe
pause
exit /b 0

:error
echo.
echo Ha fallado la construccion. Revisa los mensajes de arriba.
pause
exit /b 1
