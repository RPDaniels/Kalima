# -*- mode: python ; coding: utf-8 -*-
# Especificación de PyInstaller para Kalima.exe (un único archivo, sin consola).
# Uso:  pyinstaller packaging/Kalima.spec   (desde la carpeta del proyecto)
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(SPECPATH, "kalima.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "k4app", "data"), os.path.join("k4app", "data"))],
    # mido elige el backend MIDI en tiempo de ejecución: hay que incluirlo a mano
    hiddenimports=["mido.backends.rtmidi", "rtmidi", "k4lib.fake", "k4app.editor",
                   # los catálogos de traducción se importan con importlib
                   "k4lib.locales.en", "k4lib.locales.fr"],
    excludes=["pytest", "numpy", "PIL", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Kalima",
    icon=os.path.join(ROOT, "k4app", "data", "k4.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
    console=False,
    upx=False,
    strip=False,
    debug=False,
    runtime_tmpdir=None,
)
