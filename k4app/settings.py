"""Ajustes del usuario (idioma, nota de prueba) en un JSON por usuario.

Windows: %APPDATA%\\Kalima\\settings.json
macOS:   ~/Library/Application Support/Kalima/settings.json
Linux:   ~/.config/kalima/settings.json  (o $XDG_CONFIG_HOME)
Si no existe, se leen los ajustes de la carpeta antigua (K4Librarian / k4librarian).
La variable K4_SETTINGS permite usar otro archivo (tests).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _base(name: str) -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / name
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / name.lower()


def path() -> Path:
    if os.environ.get("K4_SETTINGS"):
        return Path(os.environ["K4_SETTINGS"])
    return _base("Kalima") / "settings.json"


def _legacy_path() -> Path | None:
    """Ajustes de cuando la aplicación se llamaba K4 Librarian."""
    if os.environ.get("K4_SETTINGS"):
        return None
    return _base("K4Librarian") / "settings.json"


def load() -> dict:
    p = path()
    legacy = _legacy_path()
    if not p.exists() and legacy is not None and legacy.exists():
        p = legacy
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass                      # los ajustes no son imprescindibles
