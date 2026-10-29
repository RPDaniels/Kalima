"""Comprueba que todos los textos marcados para traducir tienen traducción
en inglés y francés, con los mismos marcadores {…}."""
import ast
import string
from pathlib import Path

import pytest

from k4lib import i18n
from k4lib.locales import en, fr

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted([*ROOT.glob("k4lib/*.py"), *ROOT.glob("k4app/*.py")])
CATALOGS = {"en": en.MESSAGES, "fr": fr.MESSAGES}


def _marked():
    """{texto: (es_plural, singular, plural, dónde)} de todas las llamadas _(), N_() y _n()."""
    found = {}
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            name = node.func.id
            if name not in ("_", "N_", "_n") or not node.args:
                continue
            first = node.args[0]
            where = f"{path.name}:{node.lineno}"
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                if name == "_":
                    continue          # _(variable): el texto se marcó con N_ en otro sitio
                pytest.fail(f"{where}: {name}() necesita un texto literal")
            if name == "_n":
                second = node.args[1]
                assert isinstance(second, ast.Constant), f"{where}: plural no literal"
                found[first.value] = (True, first.value, second.value, where)
            else:
                found.setdefault(first.value, (False, first.value, None, where))
    return found


def _fields(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


MARKED = _marked()


def test_there_are_marked_texts():
    assert len(MARKED) > 150


@pytest.mark.parametrize("lang", CATALOGS)
def test_every_text_is_translated(lang):
    missing = [f"{where}: {key!r}" for key, (_, _, _, where) in MARKED.items() if key not in CATALOGS[lang]]
    assert not missing, f"faltan {len(missing)} traducciones al {lang}:\n" + "\n".join(missing)


@pytest.mark.parametrize("lang", CATALOGS)
def test_no_unused_translations(lang):
    unused = [k for k in CATALOGS[lang] if k not in MARKED]
    assert not unused, f"traducciones sin uso en {lang}: {unused}"


@pytest.mark.parametrize("lang", CATALOGS)
def test_placeholders_and_plurals_match(lang):
    problems = []
    for key, (is_plural, singular, plural, where) in MARKED.items():
        value = CATALOGS[lang].get(key)
        if value is None:
            continue
        if is_plural:
            if not (isinstance(value, tuple) and len(value) == 2):
                problems.append(f"{where}: el plural necesita (singular, plural)")
                continue
            for src, dst in ((singular, value[0]), (plural, value[1])):
                if _fields(src) != _fields(dst):
                    problems.append(f"{where}: marcadores distintos en {dst!r}")
        else:
            if isinstance(value, tuple):
                problems.append(f"{where}: no es un plural")
            elif _fields(key) != _fields(value):
                problems.append(f"{where}: marcadores distintos en {value!r}")
    assert not problems, "\n".join(problems)


def test_language_switch_and_plurals():
    try:
        i18n.set_language("en")
        assert i18n._n("{n} sección activa", "{n} secciones activas", 1) == "1 active section"
        assert i18n._n("{n} sección activa", "{n} secciones activas", 0) == "0 active sections"
        assert i18n._("Guardar") == "Save"
        assert i18n._("Abierto {name}", name="x.syx") == "Opened x.syx"
        i18n.set_language("fr")
        assert i18n._n("{n} sección activa", "{n} secciones activas", 0) == "0 section active"   # 0 en singular
        assert i18n._n("{n} sección activa", "{n} secciones activas", 2) == "2 sections actives"
        assert i18n.translate_to("en", "Guardar") == "Save" and i18n.get_language() == "fr"
        i18n.set_language("es")
        assert i18n._("Guardar") == "Guardar"
    finally:
        i18n.set_language("es")


def test_detect_language(monkeypatch):
    monkeypatch.setenv("K4_LANG", "fr_FR")
    assert i18n.detect_language() == "fr"
    monkeypatch.setenv("K4_LANG", "de_DE")
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    monkeypatch.setenv("LC_ALL", "")
    monkeypatch.setenv("LC_MESSAGES", "")
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("de_DE", "UTF-8"))
    assert i18n.detect_language() == "en"       # no soportado → inglés
