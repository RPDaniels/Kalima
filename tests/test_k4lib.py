"""Tests de k4lib con el banco de fábrica A401 (volcado completo, 15123 bytes)."""
from pathlib import Path

import pytest

from k4lib import Bank, Effect, K4Error, Location, Message, Single, read_syx
from k4lib.params import encode
from k4lib.patches import ALL_DUMP_SIZE, Drum, Multi
from k4lib.sysex import (Function, all_dump_request, block_dump_request, checksum,
                         edit_buffer_dump, one_dump_request, parameter_send, split_sysex)

A401 = Path(__file__).parent / "A401.SYX"


@pytest.fixture(scope="module")
def bank():
    return Bank.from_file(A401)


# ---------------------------------------------------------------- lectura

def test_file_is_one_all_dump():
    msgs = read_syx(A401)
    assert len(msgs) == 1
    assert msgs[0].function == Function.ALL_DATA_DUMP
    assert len(msgs[0].data) == ALL_DUMP_SIZE == 15114


def test_known_names(bank):
    assert bank.singles[0].name == "Melo Vox 1"
    assert bank.multis[0].name == "Fatt!Anna5"
    assert bank.multis[0].volume == 0x50
    assert bank.drum.volume == 100
    assert bank.effects[0].type_name == "Reverb 1"
    assert bank.is_complete


def test_original_checksums_are_valid():
    d = read_syx(A401)[0].data
    for i in range(64):
        raw = d[i * 131:(i + 1) * 131]
        assert raw[130] == checksum(raw[:130]), f"Single {i}"
    off = 64 * 131
    for i in range(64):
        raw = d[off + i * 77: off + (i + 1) * 77]
        assert raw[76] == checksum(raw[:76]), f"Multi {i}"


def test_source_mute_semantics(bank):
    # En modo Normal solo suenan S1 y S2: las fuentes 3 y 4 aparecen silenciadas.
    normals = [s for s in bank.singles if s.source_mode == 0]
    assert sum(1 for s in normals if not s.source_active(2) and not s.source_active(3)) > len(normals) * 0.7


# ---------------------------------------------------------------- escritura

def test_bank_roundtrip_is_byte_exact(bank):
    original = A401.read_bytes()
    assert bank.to_all_dump().to_bytes() == original


@pytest.mark.parametrize("cls,size", [(Single, 131), (Multi, 77), (Drum, 682), (Effect, 35)])
def test_default_patches_have_right_size_and_checksum(cls, size):
    b = cls().to_bytes()
    assert len(b) == size
    if cls is not Drum:
        assert b[-1] == checksum(b[:-1])


def test_single_roundtrip_after_edit(bank):
    s = Single.from_bytes(bank.singles[5].to_bytes())
    s.name = "Mi Sonido"
    s.sources[1].wave = 200          # usa el bit alto de la onda
    s.filters[1].env_depth = -37
    s.wheel_depth = 12
    again = Single.from_bytes(s.to_bytes())
    assert again.name == "Mi Sonido "
    assert again.sources[1].wave == 200
    assert again.filters[1].env_depth == -37
    assert again.wheel_depth == 12
    assert again.to_bytes() == s.to_bytes()


def test_individual_messages_rebuild_same_bank(bank):
    rebuilt = Bank.from_messages(bank.to_messages())
    assert rebuilt.to_all_dump().to_bytes() == bank.to_all_dump().to_bytes()


def test_save_and_reload(bank, tmp_path):
    p = tmp_path / "copia.syx"
    bank.save(p)
    assert p.read_bytes() == A401.read_bytes()


# ---------------------------------------------------------------- mensajes

def test_request_messages():
    assert one_dump_request(0, "single", Location.parse("A-1")).to_bytes() == \
        bytes.fromhex("F0 40 00 00 00 04 00 00 F7")
    assert one_dump_request(0, "multi", Location.parse("A-1")).to_bytes() == \
        bytes.fromhex("F0 40 00 00 00 04 00 40 F7")
    assert one_dump_request(2, "drum").to_bytes() == bytes.fromhex("F0 40 02 00 00 04 01 20 F7")
    assert block_dump_request(0, "single", external=True).to_bytes() == \
        bytes.fromhex("F0 40 00 01 00 04 02 00 F7")
    assert all_dump_request(0).to_bytes() == bytes.fromhex("F0 40 00 02 00 04 00 00 F7")


def test_parameter_send():
    # cutoff del filtro 1 = 50
    n, v = encode("filter_cutoff", 50)
    assert parameter_send(0, n, v).to_bytes() == bytes.fromhex("F0 40 00 10 00 04 37 00 32 F7")
    # onda de S2 = 201 en el panel (índice 200 = 0xC8): bit alto en el byte de sección
    n, v = encode("src_wave", 201)
    assert parameter_send(0, n, v, section=1).to_bytes() == bytes.fromhex("F0 40 00 10 00 04 24 03 48 F7")
    with pytest.raises(ValueError):
        encode("wheel_depth", 60)


def test_edit_buffer_dump(bank):
    m = edit_buffer_dump(0, bank.singles[0].to_bytes())
    raw = m.to_bytes()
    assert raw[:8] == bytes.fromhex("F0 40 00 23 00 04 00 00") and len(raw) == 140


def test_split_and_parse_mixed_stream():
    stream = b"\xF0\x43\x10\x00\xF7" + all_dump_request(0).to_bytes() + b"\x90\x3C\x40"
    parts = split_sysex(stream)
    assert len(parts) == 2
    assert Message.parse(parts[1]).function == Function.ALL_DUMP_REQUEST


def test_location_parsing():
    assert Location.parse("A-1") == Location(False, 0)
    assert Location.parse("d16") == Location(False, 63)
    assert Location.parse("E-B-3") == Location(True, 18)
    assert Location.parse("64").name == "D-16"
    assert Location.parse("E-17") == Location(True, 16)     # número 1..64 externo
    for bad in ("A-17", "F-1", "0", "65"):
        with pytest.raises(ValueError):
            Location.parse(bad)


# ---------------------------------------------------------------- gestión

def test_references_and_swap_keep_multis_intact(bank):
    b = Bank.from_file(A401)
    users = b.single_users()
    target = next(iter(users))                 # un Single usado por algún Multi
    multi_idx, sec_idx = users[target][0]
    name_before = b.singles[b.multis[multi_idx].sections[sec_idx].single].name

    other = 63 if target != 63 else 0
    b.swap_singles(target, other)
    sec = b.multis[multi_idx].sections[sec_idx]
    assert sec.single == other
    assert b.singles[sec.single].name == name_before


def test_move_single_keeps_multis_intact():
    b = Bank.from_file(A401)
    names = [[b.singles[s.single].name for s in m.sections] for m in b.multis]
    b.move_single(0, 40)
    assert b.singles[40].name == "Melo Vox 1"
    assert [[b.singles[s.single].name for s in m.sections] for m in b.multis] == names


def test_swap_effects_keeps_singles_intact():
    b = Bank.from_file(A401)
    before = [b.effects[s.effect].summary() for s in b.singles]
    b.swap_effects(0, 31)
    assert [b.effects[s.effect].summary() for s in b.singles] == before


def test_import_single_brings_its_effect():
    src, dst = Bank.from_file(A401), Bank.from_file(A401)
    for s in dst.singles:                      # dejamos el efecto 32 libre
        if s.effect == 31:
            s.effect = 0
    dst.effects[31] = Effect()                 # y distinto de todos
    eff = Effect(type=8, param1=3, param2=-2, param3=20)
    single = Single.from_bytes(src.singles[2].to_bytes())
    dst.import_single(single, 10, effect=eff)
    assert dst.effects[dst.singles[10].effect].summary() == eff.summary()


def test_fingerprint_ignores_name_and_reserved_bits(bank):
    a = Single.from_bytes(bank.singles[3].to_bytes())
    b = Single.from_bytes(bank.singles[3].to_bytes())
    b.name, b.s11_reserved = "Otro nombr", 0
    assert a.fingerprint() == b.fingerprint()
    b.filters[0].cutoff += 1
    assert a.fingerprint() != b.fingerprint()


def test_find_and_validate(bank):
    assert ("single", 0, "Melo Vox 1") in bank.find("melo")
    assert bank.validate() == []


def test_cli_list_runs(capsys):
    from k4lib.cli import main
    main(["list", str(A401), "--all"])
    out = capsys.readouterr().out
    assert "Melo Vox 1" in out and "Fatt!Anna5" in out and "Reverb 1" in out


# ---------------------------------------------------------------- archivos .mid

def test_midi_file_roundtrip(bank, tmp_path):
    pytest.importorskip("mido")
    p = tmp_path / "banco.mid"
    bank.save(p)
    assert p.read_bytes()[:4] == b"MThd"
    again = Bank.from_file(p)
    assert again.to_all_dump().to_bytes() == A401.read_bytes()


def test_midi_file_spaces_messages(bank, tmp_path):
    mido = pytest.importorskip("mido")
    p = tmp_path / "patches.mid"
    from k4lib.sysex import write_midi_file
    write_midi_file(p, [bank.patch_message("single", i) for i in range(3)])
    events = [e for e in mido.MidiFile(p).tracks[0] if e.type == "sysex"]
    assert len(events) == 3
    assert events[0].time == 0 and events[1].time > 0   # hay pausa entre volcados


# ---------------------------------------------------------------- simulador

@pytest.fixture
def fake(bank):
    from k4lib.fake import FakeK4
    return FakeK4(Bank.from_file(A401))


def test_fake_downloads(fake):
    b = fake.get_bank()
    assert b.to_all_dump().to_bytes() == A401.read_bytes()
    assert fake.get_single("A-1").name == "Melo Vox 1"
    assert fake.get_multi("A-1").name == "Fatt!Anna5"
    assert fake.get_effect(1).type_name == "Reverb 1"
    assert fake.get_drum().volume == 100
    assert fake.get_block("multi").multis[0].name == "Fatt!Anna5"


def test_fake_write_and_errors(fake, bank):
    from k4lib import K4Error
    s = Single.from_bytes(bank.singles[0].to_bytes())
    s.name = "Escrito   "
    assert fake.write_single(s, "D-16") == "escritura completada"
    assert fake.get_single("D-16").name == "Escrito   "
    with pytest.raises(K4Error, match="tarjeta"):
        fake.write_single(s, "E-A-1")
    fake.write_protect = True
    with pytest.raises(K4Error, match="protegida"):
        fake.write_single(s, "A-1")


def test_fake_bad_checksum_is_rejected(fake, bank):
    from k4lib import K4Error
    from k4lib.sysex import one_data_dump
    data = bytearray(bank.singles[0].to_bytes())
    data[-1] ^= 0x01
    reply = fake.request(one_data_dump(0, "single", Location(False, 0), bytes(data)),
                         {Function.WRITE_COMPLETE, Function.WRITE_ERROR})
    assert reply.function == Function.WRITE_ERROR


def test_fake_write_bank_and_edit_buffer(fake, bank):
    b = Bank.from_file(A401)
    b.move_single(0, 63)
    fake.write_bank(b)
    assert fake.banks[False].singles[63].name == "Melo Vox 1"
    fake.send_to_edit_buffer(b.singles[3])
    assert fake.edit_buffer.name == b.singles[3].name
    fake.set_parameter("filter_cutoff", 60, section=2)
    assert fake.parameters[-1] == (55, 4, 60)


# ---------------------------------------------------------------- recepción troceada (Windows)

class _FakeRt:
    """Imita rtmidi.MidiIn: entrega lo que se le encole, trozo a trozo."""
    def __init__(self):
        self.queue = []

    def ignore_types(self, **kw):
        self.ignore = kw

    def get_message(self):
        return (self.queue.pop(0), 0.0) if self.queue else None

    def close_port(self):
        pass


class _FakeOut:
    """Salida que, al recibir una petición, hace 'responder' al K4 por la entrada."""
    def __init__(self, rt, reply_for):
        self.rt, self.reply_for = rt, reply_for

    def send(self, mido_msg):
        req = Message.parse([0xF0, *mido_msg.data, 0xF7])
        self.rt.queue.extend(self.reply_for(req))

    def close(self):
        pass


def _chunks(raw: bytes, size: int = 1024):
    """Como WinMM: trozos de 1 KB, con active sensing (FE) entre medias."""
    out = []
    for i in range(0, len(raw), size):
        out.append(list(raw[i:i + size]))
        out.append([0xFE])
    return out


def _k4_with(reply_for, timeout=0.5):
    from k4lib.midi import K4Midi, SysexInput
    pytest.importorskip("mido")
    rt = _FakeRt()
    return K4Midi.with_ports(SysexInput(rt=rt), _FakeOut(rt, reply_for), timeout=timeout), rt


def test_fragmented_bank_dump_is_reassembled(bank):
    full = A401.read_bytes()
    k4, rt = _k4_with(lambda req: _chunks(full))
    got = k4.get_bank()
    assert got.to_all_dump().to_bytes() == full
    assert rt.ignore["sysex"] is False
    assert k4.inp.chunks == len(_chunks(full)) and k4.inp.sysex_received == 1


def test_fragmented_single_and_noise(bank):
    single_msg = bank.patch_message("single", 0).to_bytes()
    noise = [[0x90, 60, 100], [0xF8], [0xF0, 0x43, 0x10, 0xF7]]       # nota, clock, SysEx de Yamaha
    k4, _ = _k4_with(lambda req: noise + _chunks(single_msg, 50))
    assert k4.get_single("A-1").name == "Melo Vox 1"


def test_no_reply_messages_explain_what_happened(bank):
    from k4lib import K4Error
    k4, _ = _k4_with(lambda req: [], timeout=0.2)
    with pytest.raises(K4Error, match="ningún dato MIDI"):
        k4.get_single("A-1")
    truncated = A401.read_bytes()[:3000]                               # sin F7
    k4, _ = _k4_with(lambda req: _chunks(truncated), timeout=0.2)
    with pytest.raises(K4Error, match="ningún mensaje SysEx completo"):
        k4.get_bank()
    other = bank.patch_message("multi", 0).to_bytes()                  # respuesta inesperada
    k4, _ = _k4_with(lambda req: [list(other)], timeout=0.2)
    with pytest.raises(K4Error, match="no la respuesta esperada"):
        k4.get_bank()


# ---------------------------------------------------------------- escuchar

def test_edit_buffer_dump_multi(bank):
    raw = edit_buffer_dump(0, bank.multis[0].to_bytes(), "multi").to_bytes()
    assert raw[:8] == bytes.fromhex("F0 40 00 23 00 04 00 40") and len(raw) == 86


def test_test_note_plan_single_and_solo(bank):
    from k4lib.midi import test_note_plan
    s = Single.from_bytes(bank.singles[0].to_bytes())
    assert test_note_plan(s, "chord", 3) == [(3, 60, 100), (3, 64, 100), (3, 67, 100)]
    assert test_note_plan(s, "note", 3) == [(3, 60, 100)]
    assert test_note_plan(s, "none", 3) == []
    s.poly_mode = 2                                   # Solo 1: una sola nota
    assert test_note_plan(s, "chord", 3) == [(3, 60, 100)]


def test_test_note_plan_multi_respects_sections(bank):
    from k4lib.midi import test_note_plan
    m = Multi.from_bytes(bank.multis[0].to_bytes())
    for sec in m.sections:
        sec.muted = True
    a, b, c = m.sections[0], m.sections[1], m.sections[2]
    a.muted, a.channel, a.play_mode, a.low_key, a.high_key, a.vel_switch = False, 0, 2, 0, 127, 2
    b.muted, b.channel, b.play_mode, b.low_key, b.high_key, b.vel_switch = False, 1, 1, 72, 84, 1
    c.muted, c.channel, c.play_mode = False, 2, 0     # modo Keyboard: no responde a MIDI
    plan = test_note_plan(m, "chord", 0)
    assert (0, 60, 100) in plan and (0, 67, 100) in plan
    assert (1, 72, 115) in plan and (1, 79, 115) in plan       # dentro de su zona, velocidad Loud
    assert all(ch != 2 for ch, _, _ in plan)
    for sec in m.sections:
        sec.play_mode = 0
    assert test_note_plan(m, "chord", 0) == []


def test_fake_audition_single_and_multi(fake, bank):
    notes = fake.audition(bank.singles[5], "A-6", test_notes="chord")
    assert fake.current_program == (False, 5)                  # modo Single en su posición
    assert fake.edit_buffer.name == bank.singles[5].name
    assert [n for n in fake.notes if n[0]] == [(True, 0, 60, 100), (True, 0, 64, 100), (True, 0, 67, 100)]
    assert sum(1 for n in fake.notes if not n[0]) == 3          # todas se sueltan
    assert notes

    fake.notes.clear()
    fake.audition(bank.multis[0], "A-1", test_notes="note")
    assert fake.current_program == (False, 64)                 # programa 64 = Multi A-1
    assert fake.edit_buffer_multi.name == bank.multis[0].name
    assert any(n[0] for n in fake.notes)


def test_velocity_switch_order_matches_factory_bank(bank):
    from k4lib import constants as C
    from collections import Counter
    counts = Counter(sec.vel_switch for m in bank.multis for sec in m.sections)
    # en fábrica casi todas las secciones responden a cualquier velocidad
    assert counts.most_common(1)[0][0] == 2 and C.VELOCITY_SWITCHES[2] == "All"


# ---------------------------------------------------------------- archivos sin F7

def _blocks_without_f7(bank: Bank) -> bytes:
    """Como algunos archivos antiguos: tres volcados de bloque (Singles, Multis,
    efectos) y solo el último cerrado con F7."""
    b = Bank.from_messages([bank.to_all_dump()])
    b.drum = None
    raw = b"".join(m.to_bytes() for m in b.to_file_messages())
    return raw.replace(b"\xF7\xF0", b"\xF0")


def test_dumps_without_final_f7_are_read(tmp_path, bank):
    raw = _blocks_without_f7(bank)
    assert raw.count(0xF0) == 3 and raw.count(0xF7) == 1
    p = tmp_path / "sin-f7.syx"
    p.write_bytes(raw)
    msgs = read_syx(p)
    assert [(m.function, m.sub1, m.sub2, len(m.data)) for m in msgs] == [
        (Function.BLOCK_DATA_DUMP, 0, 0x00, 8384),
        (Function.BLOCK_DATA_DUMP, 0, 0x40, 4928),
        (Function.BLOCK_DATA_DUMP, 1, 0x00, 1120)]
    b = Bank.from_file(p)
    assert [s.name for s in b.singles] == [s.name for s in bank.singles]
    assert b.drum is None and not b.is_complete and b.validate() == []


# Archivo real con este problema; no se distribuye con el proyecto: copia el tuyo aquí.
ZAIDA = Path(__file__).parent / "ZAIDA3.SYX"


@pytest.mark.skipif(not ZAIDA.exists(), reason="sin tests/ZAIDA3.SYX")
def test_real_file_without_f7():
    b = Bank.from_file(ZAIDA)
    assert all(s is not None for s in b.singles + b.multis + b.effects) and b.drum is None


def test_split_sysex_edge_cases():
    assert split_sysex(b"\xF0\x40\x01\xF0\x40\x02\xF7") == [b"\xF0\x40\x01\xF7", b"\xF0\x40\x02\xF7"]
    assert split_sysex(b"\xF0\x40\x01\x02") == [b"\xF0\x40\x01\x02\xF7"]      # sin F7 al final
    assert split_sysex(b"\xF0\xF0\x40\xF7") == [b"\xF0\x40\xF7"]              # F0 vacío
    assert split_sysex(b"\x90\x3C\x40") == []


def test_partial_bank_is_saved_as_blocks(tmp_path, bank):
    p0 = tmp_path / "sin-f7.syx"
    p0.write_bytes(_blocks_without_f7(bank))
    b = Bank.from_file(p0)
    msgs = b.to_file_messages()
    assert [m.function for m in msgs] == [Function.BLOCK_DATA_DUMP] * 3
    p = tmp_path / "copia.syx"
    b.save(p)
    again = Bank.from_file(p)
    assert [s.to_bytes() for s in again.singles] == [s.to_bytes() for s in b.singles]
    assert p.read_bytes().count(0xF7) == 3               # ahora cada volcado va cerrado
    b.singles[5] = None                                  # grupo incompleto: volcados sueltos
    funcs = [m.function for m in b.to_file_messages()]
    assert funcs.count(Function.ONE_DATA_DUMP) == 63 and funcs.count(Function.BLOCK_DATA_DUMP) == 2


def test_fake_audition_drum(fake, bank):
    d = bank.drum
    assert fake.audition_drum(d, 2) is True                    # mismo Drum en el K4
    assert [n for n in fake.notes if n[0]] == [(True, d.channel, 38, 100)]   # D1 en el canal del Drum
    assert sum(1 for n in fake.notes if not n[0]) == 1
    other = Drum.from_bytes(d.to_bytes())
    other.volume = (d.volume + 1) % 100
    assert fake.audition_drum(other, 0) is False               # el K4 tiene otro Drum
    assert fake.audition_drum(other, 0, compare=False) is None


# ---------------------------------------------------------------- archivos dañados

def _all_dump_bytes(bank) -> bytes:
    return bank.to_all_dump().to_bytes()


def test_text_mode_transfer_is_repaired(tmp_path, bank):
    """Un banco pasado por FTP/BBS en modo texto: un 0D delante de cada 0A."""
    raw = _all_dump_bytes(bank)
    damaged = raw.replace(b"\n", b"\r\n")
    assert len(damaged) > len(raw)
    p = tmp_path / "texto.syx"
    p.write_bytes(damaged)
    b = Bank.from_file(p)
    assert b.repaired and len(b.warnings) == 1 and "0D" in b.warnings[0]
    assert _all_dump_bytes(b) == raw                      # idéntico al original


def test_damaged_patch_is_reported(tmp_path, bank):
    raw = bytearray(_all_dump_bytes(bank))
    raw[8 + 131 * 5 + 20] ^= 0x01                        # un bit cambiado en el Single A-6
    p = tmp_path / "danado.syx"
    p.write_bytes(bytes(raw))
    b = Bank.from_file(p)
    assert not b.repaired
    assert len(b.warnings) == 1 and "Single A-6" in b.warnings[0]


def test_zeroed_patches_are_left_empty(tmp_path, bank):
    """Algunos programas guardan a cero lo que no tienen (Multis, efectos, Drum)."""
    raw = bytearray(_all_dump_bytes(bank))
    start = 8 + 64 * 131
    raw[start:-1] = bytes(len(raw) - 1 - start)
    p = tmp_path / "solo-singles.syx"
    p.write_bytes(bytes(raw))
    b = Bank.from_file(p)
    assert all(s is not None for s in b.singles)
    assert all(m is None for m in b.multis) and b.drum is None and all(e is None for e in b.effects)
    assert len(b.warnings) == 1 and "97" in b.warnings[0]


def test_request_only_file_is_explained(tmp_path):
    p = tmp_path / "peticion.syx"
    p.write_bytes(all_dump_request(0).to_bytes())
    with pytest.raises(K4Error, match="peticiones"):
        Bank.from_file(p)


def test_undocumented_bits_of_multi_sections_survive(bank):
    """Algunos bancos de terceros usan bits que el manual no describe en las secciones."""
    m = bank.multis[0]
    raw = bytearray(m.to_bytes())
    raw[12 + 4] |= 0x20                       # sección 1, byte 4, bit 5
    raw[12 + 8] |= 0x40                       # sección 2, byte 0, bit 6
    raw[-1] = checksum(bytes(raw[:-1]))
    again = Multi.from_bytes(bytes(raw))
    assert again.to_bytes() == bytes(raw)
    assert again.sections[1].single == m.sections[1].single


def test_name_keeps_the_arrow_character(bank):
    s = Single.from_bytes(bank.singles[0].to_bytes())
    raw = bytearray(s.to_bytes())
    raw[9] = 0x7F
    raw[-1] = checksum(bytes(raw[:-1]))
    again = Single.from_bytes(bytes(raw))
    assert again.name.endswith("←") and again.to_bytes() == bytes(raw)
