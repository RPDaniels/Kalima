"""Tabla de parámetros editables del Single, deshacer/rehacer y nombres."""
from dataclasses import fields
from pathlib import Path

import pytest

from k4lib import Bank, Single
from k4lib.editing import (DRUM_PARAM_LIST, EFFECT_PARAM_LIST, MULTI_PARAM_LIST, MULTI_PARAMS,
                           SINGLE_PARAM_LIST, SINGLE_PARAMS, TABLES, History, copy_patch, copy_single,
                           get_value, set_name, set_value)
from k4lib.params import PARAMETERS
from k4lib.patches import (Amp, Drum, DrumNote, DrumSource, Effect, Filter, Multi, Section, Source,
                           SubmixSetting)

A401 = Path(__file__).parent / "A401.SYX"


@pytest.fixture()
def single():
    return copy_single(Bank.from_file(A401).singles[0])


def test_every_model_field_is_editable():
    """Todos los campos del modelo tienen su parámetro (salvo nombre y bits reservados)."""
    covered = {(p.scope, p.attr) for p in SINGLE_PARAM_LIST}
    covered.add(("common", "source_mute_bits"))          # vía src.active
    expected = {("common", f.name) for f in fields(Single)
                if f.name not in ("name", "s11_reserved", "sources", "amps", "filters")}
    expected |= {("source", f.name) for f in fields(Source)}
    expected |= {("amp", f.name) for f in fields(Amp)}
    expected |= {("filter", f.name) for f in fields(Filter)}
    assert expected - covered == set()
    assert {(p.scope, p.attr) for p in SINGLE_PARAM_LIST} - expected == {("source", "active")}


@pytest.mark.parametrize("kind", list(TABLES))
def test_layout_lists_every_parameter_once(kind):
    params, layout = TABLES[kind]
    keys = [k for _title, ks, _how in layout for k in ks]
    assert sorted(keys) == sorted(params)
    for _title, ks, how in layout:
        assert how in ("pairs", "columns", "rows")
        assert len({params[k].scope for k in ks}) == 1     # una sección = un ámbito


@pytest.mark.parametrize("param", SINGLE_PARAM_LIST, ids=lambda p: p.key)
def test_extremes_survive_the_sysex_round_trip(single, param):
    """Los valores mínimo y máximo caben en los bits del formato y no tocan nada más."""
    for index in range(param.count):
        for value in (param.lo, param.hi):
            s = copy_single(single)
            before = {p.key: [get_value(s, p, i) for i in range(p.count)] for p in SINGLE_PARAM_LIST}
            set_value(s, param, value, index)
            again = Single.from_bytes(s.to_bytes())
            assert get_value(again, param, index) == value
            after = {p.key: [get_value(again, p, i) for i in range(p.count)] for p in SINGLE_PARAM_LIST}
            before[param.key][index] = value
            assert after == before
            assert again.s11_reserved == single.s11_reserved


@pytest.mark.parametrize("param", [p for p in SINGLE_PARAM_LIST if p.send], ids=lambda p: p.key)
def test_ranges_match_parameter_send(param):
    _number, _offset, lo, hi = PARAMETERS[param.send]
    shift = 1 if param.kind in ("wave", "effect") or param.send in ("src_vel_curve", "src_ks_curve") else 0
    assert (param.lo + shift, param.hi + shift) == (lo, hi)


def test_out_of_range_is_rejected(single):
    with pytest.raises(ValueError):
        set_value(single, SINGLE_PARAMS["dca.attack"], 101, 0)
    with pytest.raises(ValueError):
        set_value(single, SINGLE_PARAMS["src.coarse"], -25, 2)


def test_display_and_parse(single):
    p = SINGLE_PARAMS
    assert p["src.wave"].display(0) == "1 · Sin 1st" and p["src.wave"].parse("256") == 255
    assert p["src.wave"].parse("19 · Triangle") == 18
    assert p["effect"].display(0) == "1" and p["effect"].parse("32") == 31
    assert p["wheel_depth"].display(-20) == "-20" and p["wheel_depth"].parse("+7") == 7
    assert p["src.fixed_key"].parse("C4") == 60 and p["src.fixed_key"].parse("c#4") == 61
    assert p["submix"].parse("H") == 7 and p["dcf.lfo"].parse(p["dcf.lfo"].display(1)) == 1
    with pytest.raises(ValueError):
        p["dca.level"].parse("abc")
    with pytest.raises(ValueError):
        p["src.coarse"].parse("30")


def test_source_active_uses_the_inverted_mute_bit(single):
    a = SINGLE_PARAMS["src.active"]
    set_value(single, a, 0, 1)
    assert single.source_mute_bits & 0b10 and not single.source_active(1)
    set_value(single, a, 1, 1)
    assert not single.source_mute_bits & 0b10 and single.source_active(1)


def test_name_is_cleaned_and_padded(single):
    assert set_name(single, "Pad ñ") == "Pad       "
    assert set_name(single, "Muy largo nombre") == "Muy largo "
    assert Single.from_bytes(single.to_bytes()).name == "Muy largo "


def test_history_undo_redo_and_merge(single):
    h = History(single, merge_seconds=1.0)
    p = SINGLE_PARAMS["dcf.cutoff"]
    original = get_value(single, p, 0)
    for t, v in ((0.0, 10), (0.3, 11), (0.6, 12)):        # pulsación continua: un paso
        h.before_change("dcf.cutoff/0", t)
        set_value(single, p, v, 0)
    h.before_change("dca.attack/0", 0.7)
    set_value(single, SINGLE_PARAMS["dca.attack"], 5, 0)
    assert len(h.undo_stack) == 2 and h.changed
    assert h.undo() and get_value(single, p, 0) == 12
    assert h.undo() and get_value(single, p, 0) == original
    assert not h.undo() and not h.changed
    assert h.redo() and get_value(single, p, 0) == 12
    h.before_change("dcf.cutoff/0", 5.0)
    set_value(single, p, 50, 0)
    assert not h.redo_stack                               # un cambio nuevo borra el rehacer
    assert h.revert() and not h.changed
    assert h.undo() and get_value(single, p, 0) == 50     # volver al original se puede deshacer


def test_history_keeps_the_object_identity(single):
    """El editor guarda una referencia al Single del banco: deshacer no lo sustituye."""
    bank = Bank.from_file(A401)
    s = bank.singles[3]
    h = History(s)
    h.before_change("volume", 0)
    s.volume = 1
    h.undo()
    assert bank.singles[3] is s and s.volume != 1


# ---------------------------------------------------------------- Multi, efecto y Drum

BANK = Bank.from_file(A401)


def _covered(params, classes):
    have = {(p.scope, p.attr) for p in params}
    for scope, cls, skip in classes:
        need = {(scope, f.name) for f in fields(cls) if f.name not in skip}
        assert need - have == set(), (cls.__name__, need - have)


def test_multi_effect_drum_fields_are_editable():
    _covered(MULTI_PARAM_LIST, [("common", Multi, {"name", "sections"}), ("section", Section, ())])
    _covered(EFFECT_PARAM_LIST, [("common", Effect, {"reserved", "submixes"}), ("submix", SubmixSetting, ())])
    _covered(DRUM_PARAM_LIST, [("common", Drum, {"reserved", "notes"}), ("note", DrumNote, {"s1", "s2"}),
                               ("note_src", DrumSource, ())])


def _indexes(param):
    n = param.count
    return sorted({0, 1, n // 2, n - 2, n - 1} & set(range(n)))   # los extremos y alguno en medio


@pytest.mark.parametrize("patch,param", [(BANK.multis[3], p) for p in MULTI_PARAM_LIST]
                         + [(BANK.effects[5], p) for p in EFFECT_PARAM_LIST]
                         + [(BANK.drum, p) for p in DRUM_PARAM_LIST], ids=lambda x: getattr(x, "key", ""))
def test_other_extremes_survive_the_round_trip(patch, param):
    params = {Multi: MULTI_PARAM_LIST, Effect: EFFECT_PARAM_LIST, Drum: DRUM_PARAM_LIST}[type(patch)]

    def snapshot(p):
        return {q.key: [get_value(p, q, i) for i in range(q.count)] for q in params}
    base = snapshot(patch)
    for index in _indexes(param):
        for value in (param.lo, param.hi):
            p = copy_patch(patch)
            set_value(p, param, value, index)
            again = type(patch).from_bytes(p.to_bytes())
            expected = {k: list(v) for k, v in base.items()}
            expected[param.key][index] = value
            assert snapshot(again) == expected
            assert again.to_bytes()[-1] == p.to_bytes()[-1]             # checksum coherente
            if hasattr(patch, "reserved"):
                assert again.reserved == patch.reserved


def test_multi_section_single_is_shown_by_slot():
    p = MULTI_PARAMS["sec.single"]
    assert p.display(0) == "A-1" and p.display(63) == "D-16" and p.parse("b-3") == 18


def test_history_works_with_any_patch():
    d = copy_patch(BANK.drum)
    h = History(d)
    h.before_change("dsrc.level/10", 0)
    set_value(d, DRUM_PARAMS_LEVEL, 0, 10)
    assert d.notes[5].s1.level == 0 and h.changed
    h.undo()
    assert d.to_bytes() == BANK.drum.to_bytes()


DRUM_PARAMS_LEVEL = next(p for p in DRUM_PARAM_LIST if p.key == "dsrc.level")
