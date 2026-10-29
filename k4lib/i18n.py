"""Traducción de los textos visibles (español, inglés, francés).

El texto en español escrito en el código es la clave; los catálogos
`k4lib/locales/en.py` y `fr.py` lo traducen. Uso:

    from k4lib.i18n import _, N_, _n
    _("Guardado {name}", name=path.name)     # traduce y rellena
    N_("Singles")                            # solo marca (se traduce luego con _())
    _n("{n} sección", "{n} secciones", n)    # plural

`N_` sirve para textos definidos a nivel de módulo: se evalúan al importar,
antes de saber el idioma, así que se traducen al mostrarlos con `_(texto)`.

El idioma se fija una vez al arrancar (set_language); el cambio desde el
menú se aplica al reiniciar. tests/test_i18n.py comprueba que todos los
textos marcados tienen traducción y que los marcadores {…} coinciden.
"""
from __future__ import annotations

import importlib
import locale
import os
import sys

LANGUAGES = {"es": "Español", "en": "English", "fr": "Français"}
SOURCE_LANGUAGE = "es"
DEFAULT_LANGUAGE = "en"          # si el sistema está en un idioma no soportado

_language = SOURCE_LANGUAGE
_catalog: dict = {}


def set_language(code: str | None) -> str:
    """Fija el idioma ('es', 'en', 'fr'); None o uno desconocido → detectar."""
    global _language, _catalog
    if code not in LANGUAGES:
        code = detect_language()
    _language = code
    if code == SOURCE_LANGUAGE:
        _catalog = {}
    else:
        _catalog = importlib.import_module(f"k4lib.locales.{code}").MESSAGES
    return code


def get_language() -> str:
    return _language


def detect_language() -> str:
    """Idioma del sistema: variable K4_LANG, idioma de Windows o locale; si no
    es uno de los soportados, inglés."""
    candidates = [os.environ.get("K4_LANG", "")]
    if sys.platform == "win32":
        try:
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            candidates.append(locale.windows_locale.get(lcid, ""))
        except Exception:  # noqa: BLE001
            pass
    try:
        candidates.append(locale.getlocale()[0] or "")
    except ValueError:
        pass
    candidates += [os.environ.get(v, "") for v in ("LC_ALL", "LC_MESSAGES", "LANG")]
    for c in candidates:
        code = c.lower()[:2]
        if code in LANGUAGES:
            return code
    return DEFAULT_LANGUAGE


def _(text: str, /, **values) -> str:
    """Traduce `text` al idioma activo y rellena los marcadores {…}."""
    result = _catalog.get(text, text) if _catalog else text
    if isinstance(result, tuple):
        result = result[0]
    return result.format(**values) if values else result


def translate_to(code: str, text: str, /, **values) -> str:
    """Traduce a un idioma concreto sin cambiar el activo (p. ej. para avisar en el
    idioma recién elegido de que el cambio se aplicará al reiniciar)."""
    previous = _language
    try:
        set_language(code)
        return _(text, **values)
    finally:
        set_language(previous)


def N_(text: str) -> str:
    """Marca un texto para traducirlo más tarde (devuelve el texto tal cual)."""
    return text


def _n(singular: str, plural: str, n: int, /, **values) -> str:
    """Traducción con plural. En el catálogo, la clave es el singular en español
    y el valor una tupla (singular, plural) en el idioma destino."""
    if _catalog and singular in _catalog:
        entry = _catalog[singular]
        singular, plural = entry if isinstance(entry, tuple) else (entry, entry)
    one = n <= 1 if _language == "fr" else n == 1      # en francés 0 y 1 van en singular
    return (singular if one else plural).format(n=n, **values)


# Al importar: idioma del sistema (o el de la variable K4_LANG). La aplicación
# y la línea de órdenes lo vuelven a fijar según sus ajustes.
set_language(None)
