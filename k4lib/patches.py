"""Modelos de datos de los patches del K4: Single, Multi, Drum y Effect.

Cada clase sabe leerse desde los bytes de un volcado (from_bytes) y
serializarse (to_bytes, con checksum incluido). Los valores bipolares
(profundidades ±50, transposición ±24...) se guardan ya centrados en 0.

Al leer se enmascaran los bits sobrantes: el K4 a veces manda "basura"
en bits que no usa (p. ej. 0x20 en el byte del efecto), así que un
volcado re-serializado puede diferir del original solo en esos bits.
"""
from __future__ import annotations

from .i18n import _

import hashlib
from dataclasses import dataclass, field, fields, is_dataclass

from . import constants as C
from .sysex import checksum

# ------------------------------------------------------------------ helpers

def _bi(b: int, off: int = 50) -> int:
    """Decodifica un valor bipolar (0..2*off -> -off..+off)."""
    return (b & 0x7F) - off


def _enc(v: int, off: int = 50) -> int:
    return (v + off) & 0x7F


# El código 0x7F se ve en la pantalla del K4 como una flecha hacia la izquierda
# (como en los displays HD44780); en Python se representa con «←».
ARROW_LEFT = "\u2190"


def _name_from(data: bytes) -> str:
    chars = []
    for b in data[:C.NAME_LENGTH]:
        b &= 0x7F
        chars.append(ARROW_LEFT if b == 0x7F else chr(b) if b >= 32 else " ")
    return "".join(chars)


def _name_char(c: str) -> int:
    if c == ARROW_LEFT:
        return 0x7F
    return ord(c) if 32 <= ord(c) < 127 else 32


def _name_to(name: str) -> bytes:
    name = (name + " " * C.NAME_LENGTH)[:C.NAME_LENGTH]
    return bytes(_name_char(c) for c in name)


def _interleave(chunks: list[bytes]) -> bytes:
    """[a0 a1 ..], [b0 b1 ..] -> a0 b0 a1 b1 ... (como en el SysEx del K4)."""
    return bytes(b for group in zip(*chunks) for b in group)


def _deinterleave(data: bytes, n: int) -> list[bytes]:
    return [data[i::n] for i in range(n)]


def to_dict(obj):
    """Convierte un patch (dataclass anidada) en dict/list simples."""
    if is_dataclass(obj):
        return {f.name: to_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [to_dict(x) for x in obj]
    return obj


class _Patch:
    DATA_SIZE = 0

    def to_bytes(self) -> bytes:  # pragma: no cover - abstracto
        raise NotImplementedError

    _RESERVED: tuple[str, ...] = ()

    def canonical_bytes(self) -> bytes:
        """Bytes con los campos reservados a cero (para comparar patches)."""
        saved = {k: getattr(self, k) for k in self._RESERVED}
        try:
            for k, v in saved.items():
                setattr(self, k, type(v)(len(v)) if isinstance(v, bytes) else 0)
            return self.to_bytes()
        finally:
            for k, v in saved.items():
                setattr(self, k, v)

    def fingerprint(self, include_name: bool = False) -> str:
        """Huella para detectar duplicados (por defecto ignora el nombre)."""
        b = self.canonical_bytes()
        if not include_name and isinstance(self, (Single, Multi)):
            b = b[C.NAME_LENGTH:-1]           # sin nombre ni checksum
        return hashlib.sha1(b).hexdigest()[:16]

    def to_dict(self) -> dict:
        return to_dict(self)


# ================================================================== SINGLE

@dataclass
class Source:
    delay: int = 0                # 0..100
    wave: int = 0                 # 0..255 (panel 1..256)
    ks_curve: int = 0             # 0..7  (panel 1..8)
    coarse: int = 0               # -24..+24
    key_track: bool = True        # False -> fixed_key
    fixed_key: int = 60           # nota MIDI
    fine: int = 0                 # -50..+50
    prs_freq: bool = False        # presión -> afinación
    vib_autobend: bool = True     # vibrato / auto bend
    vel_curve: int = 0            # 0..7  (panel 1..8)

    @property
    def wave_name(self) -> str:
        return C.wave_name(self.wave)

    @classmethod
    def from_bytes(cls, d: bytes) -> "Source":
        return cls(
            delay=d[0] & 0x7F,
            wave=((d[1] & 0x01) << 7) | (d[2] & 0x7F),
            ks_curve=(d[1] >> 4) & 0x07,
            coarse=_bi(d[3] & 0x3F, 24),
            key_track=bool(d[3] & 0x40),
            fixed_key=d[4] & 0x7F,
            fine=_bi(d[5]),
            prs_freq=bool(d[6] & 0x01),
            vib_autobend=bool(d[6] & 0x02),
            vel_curve=(d[6] >> 2) & 0x07,
        )

    def to_bytes(self) -> bytes:
        return bytes([
            self.delay & 0x7F,
            ((self.wave >> 7) & 0x01) | ((self.ks_curve & 0x07) << 4),
            self.wave & 0x7F,
            _enc(self.coarse, 24) & 0x3F | (0x40 if self.key_track else 0),
            self.fixed_key & 0x7F,
            _enc(self.fine),
            int(self.prs_freq) | (int(self.vib_autobend) << 1) | ((self.vel_curve & 0x07) << 2),
        ])


@dataclass
class Amp:
    """DCA de una fuente: envolvente y modulaciones de nivel/tiempo."""
    level: int = 75
    attack: int = 0
    decay: int = 50
    sustain: int = 100
    release: int = 30
    level_vel: int = 0            # ±50
    level_prs: int = 0
    level_ks: int = 0
    time_vel_on: int = 0
    time_vel_off: int = 0
    time_ks: int = 0

    @classmethod
    def from_bytes(cls, d: bytes) -> "Amp":
        return cls(d[0] & 0x7F, d[1] & 0x7F, d[2] & 0x7F, d[3] & 0x7F, d[4] & 0x7F,
                   *(_bi(x) for x in d[5:11]))

    def to_bytes(self) -> bytes:
        return bytes([self.level, self.attack, self.decay, self.sustain, self.release]) + \
            bytes(_enc(v) for v in (self.level_vel, self.level_prs, self.level_ks,
                                    self.time_vel_on, self.time_vel_off, self.time_ks))


@dataclass
class Filter:
    cutoff: int = 100
    resonance: int = 0            # 0..7
    lfo: bool = False             # LFO modula el corte
    cutoff_vel: int = 0           # ±50
    cutoff_prs: int = 0
    cutoff_ks: int = 0
    env_depth: int = 0            # ±50
    env_vel_depth: int = 0        # ±50
    attack: int = 0
    decay: int = 50
    sustain: int = 0              # ±50 (Edisyn lo trata como bipolar)
    release: int = 30
    time_vel_on: int = 0          # ±50
    time_vel_off: int = 0
    time_ks: int = 0

    @classmethod
    def from_bytes(cls, d: bytes) -> "Filter":
        return cls(
            cutoff=d[0] & 0x7F, resonance=d[1] & 0x07, lfo=bool(d[1] & 0x08),
            cutoff_vel=_bi(d[2]), cutoff_prs=_bi(d[3]), cutoff_ks=_bi(d[4]),
            env_depth=_bi(d[5]), env_vel_depth=_bi(d[6]),
            attack=d[7] & 0x7F, decay=d[8] & 0x7F, sustain=_bi(d[9]), release=d[10] & 0x7F,
            time_vel_on=_bi(d[11]), time_vel_off=_bi(d[12]), time_ks=_bi(d[13]),
        )

    def to_bytes(self) -> bytes:
        return bytes([
            self.cutoff, (self.resonance & 0x07) | (0x08 if self.lfo else 0),
            _enc(self.cutoff_vel), _enc(self.cutoff_prs), _enc(self.cutoff_ks),
            _enc(self.env_depth), _enc(self.env_vel_depth),
            self.attack, self.decay, _enc(self.sustain), self.release,
            _enc(self.time_vel_on), _enc(self.time_vel_off), _enc(self.time_ks),
        ])


@dataclass
class Single(_Patch):
    DATA_SIZE = 131               # 130 parámetros + checksum
    _RESERVED = ("s11_reserved",)

    name: str = "Init      "
    volume: int = 100
    effect: int = 0               # 0..31 (panel 1..32)
    submix: int = 0               # 0..7 = A..H
    source_mode: int = 0          # Normal, Twin, Double
    poly_mode: int = 0
    am12: bool = False
    am34: bool = False
    source_mute_bits: int = 0b1100  # bits 0..3 de s14: 1 = fuente silenciada
    vib_shape: int = 0
    bend_range: int = 2           # 0..12
    wheel_assign: int = 0         # Vibrato, LFO, DCF
    vib_speed: int = 0
    wheel_depth: int = 0          # ±50
    autobend_time: int = 0
    autobend_depth: int = 0       # ±50
    autobend_ks_time: int = 0
    autobend_vel_depth: int = 0
    vib_prs: int = 0              # ±50
    vib_depth: int = 0            # ±50
    lfo_shape: int = 0
    lfo_speed: int = 0
    lfo_delay: int = 0
    lfo_depth: int = 0            # ±50
    lfo_prs: int = 0              # ±50
    prs_freq: int = 0             # ±50
    s11_reserved: int = field(default=0, repr=False)  # bits 5-6 de s11 (fábrica: 0x20)
    sources: list[Source] = field(default_factory=lambda: [Source() for _ in range(4)])
    amps: list[Amp] = field(default_factory=lambda: [Amp() for _ in range(4)])
    filters: list[Filter] = field(default_factory=lambda: [Filter() for _ in range(2)])

    # --- propiedades legibles
    @property
    def effect_number(self) -> int:
        """Número de efecto como en el panel (1..32)."""
        return self.effect + 1

    @property
    def source_count(self) -> int:
        """Fuentes que usa el modo: Normal=2, Twin y Double=4."""
        return 2 if self.source_mode == 0 else 4

    def source_active(self, i: int) -> bool:
        """True si la fuente i (0..3) está activa (no silenciada).
        Bit a 1 = fuente silenciada (el manual lo dice al revés). Comprobado
        sobre el banco de fábrica: en modo Normal las fuentes 3-4, que no se
        usan, aparecen con bit 1, y en Twin/Double todas aparecen con bit 0."""
        return not (self.source_mute_bits >> i) & 1

    @classmethod
    def from_bytes(cls, d: bytes) -> "Single":
        if len(d) < 130:
            raise ValueError(_("un {kind} ocupa {size} bytes, recibidos {got}", kind="Single", size=131, got=len(d)))
        p = cls(
            name=_name_from(d),
            volume=d[10] & 0x7F,
            effect=d[11] & 0x1F,
            submix=d[12] & 0x07,
            source_mode=d[13] & 0x03,
            poly_mode=(d[13] >> 2) & 0x03,
            am12=bool(d[13] & 0x10),
            am34=bool(d[13] & 0x20),
            source_mute_bits=d[14] & 0x0F,
            vib_shape=(d[14] >> 4) & 0x03,
            bend_range=d[15] & 0x0F,
            wheel_assign=(d[15] >> 4) & 0x03,
            vib_speed=d[16] & 0x7F,
            wheel_depth=_bi(d[17]),
            autobend_time=d[18] & 0x7F,
            autobend_depth=_bi(d[19]),
            autobend_ks_time=_bi(d[20]),
            autobend_vel_depth=_bi(d[21]),
            vib_prs=_bi(d[22]),
            vib_depth=_bi(d[23]),
            lfo_shape=d[24] & 0x03,
            lfo_speed=d[25] & 0x7F,
            lfo_delay=d[26] & 0x7F,
            lfo_depth=_bi(d[27]),
            lfo_prs=_bi(d[28]),
            prs_freq=_bi(d[29]),
            s11_reserved=d[11] & 0x60,
        )
        p.sources = [Source.from_bytes(c) for c in _deinterleave(d[30:58], 4)]
        p.amps = [Amp.from_bytes(c) for c in _deinterleave(d[58:102], 4)]
        p.filters = [Filter.from_bytes(c) for c in _deinterleave(d[102:130], 2)]
        return p

    def data_bytes(self) -> bytes:
        """Los 130 bytes de parámetros (sin checksum)."""
        b = bytearray(_name_to(self.name))
        b += bytes([
            self.volume, (self.effect & 0x1F) | (self.s11_reserved & 0x60), self.submix & 0x07,
            (self.source_mode & 3) | ((self.poly_mode & 3) << 2)
            | (0x10 if self.am12 else 0) | (0x20 if self.am34 else 0),
            (self.source_mute_bits & 0x0F) | ((self.vib_shape & 3) << 4),
            (self.bend_range & 0x0F) | ((self.wheel_assign & 3) << 4),
            self.vib_speed, _enc(self.wheel_depth),
            self.autobend_time, _enc(self.autobend_depth),
            _enc(self.autobend_ks_time), _enc(self.autobend_vel_depth),
            _enc(self.vib_prs), _enc(self.vib_depth),
            self.lfo_shape & 3, self.lfo_speed, self.lfo_delay,
            _enc(self.lfo_depth), _enc(self.lfo_prs), _enc(self.prs_freq),
        ])
        b += _interleave([s.to_bytes() for s in self.sources])
        b += _interleave([a.to_bytes() for a in self.amps])
        b += _interleave([f.to_bytes() for f in self.filters])
        assert len(b) == 130
        return bytes(b)

    def to_bytes(self) -> bytes:
        d = self.data_bytes()
        return d + bytes([checksum(d)])

    def summary(self) -> str:
        waves = ", ".join(self.sources[i].wave_name for i in range(self.source_count)
                          if self.source_active(i))
        return _("{name}  vol {volume}  efecto {effect}  {mode}  [{waves}]", name=self.name, volume=self.volume,
                 effect=self.effect_number,
                 mode=f"{C.SOURCE_MODES[self.source_mode]}/{C.POLY_MODES[self.poly_mode]}", waves=waves)


# ================================================================== MULTI

@dataclass
class Section:
    single: int = 0               # índice del Single 0..63 (A-1..D-16)
    low_key: int = 0
    high_key: int = 127
    channel: int = 0              # 0..15
    vel_switch: int = 2           # 0 Soft, 1 Loud, 2 All
    muted: bool = False
    submix: int = 0               # 0..7
    play_mode: int = 0            # Keyboard, MIDI, Mix
    level: int = 100
    transpose: int = 0            # ±24
    tune: int = 0                 # ±50
    # bits que el manual no documenta (0 en el banco de fábrica, 1 en algunos
    # bancos de terceros): bit 6 del byte 0 y bits 5-6 del byte 4. Se conservan.
    reserved: int = field(default=0, repr=False)

    @classmethod
    def from_bytes(cls, d: bytes) -> "Section":
        return cls(
            single=d[0] & 0x3F, low_key=d[1] & 0x7F, high_key=d[2] & 0x7F,
            channel=d[3] & 0x0F, vel_switch=(d[3] >> 4) & 0x03, muted=bool(d[3] & 0x40),
            submix=d[4] & 0x07, play_mode=(d[4] >> 3) & 0x03,
            level=d[5] & 0x7F, transpose=_bi(d[6], 24), tune=_bi(d[7]),
            reserved=((d[0] >> 6) & 1) | ((d[4] >> 4) & 0x06),   # bit 0 = byte 0 bit 6; bits 1-2 = byte 4 bits 5-6
        )

    def to_bytes(self) -> bytes:
        return bytes([
            (self.single & 0x3F) | ((self.reserved & 1) << 6), self.low_key, self.high_key,
            (self.channel & 0x0F) | ((self.vel_switch & 3) << 4) | (0x40 if self.muted else 0),
            (self.submix & 7) | ((self.play_mode & 3) << 3) | ((self.reserved & 0x06) << 4),
            self.level, _enc(self.transpose, 24), _enc(self.tune),
        ])


@dataclass
class Multi(_Patch):
    DATA_SIZE = 77                # 10 nombre + vol + efecto + 8x8 secciones + checksum

    name: str = "Init Multi"
    volume: int = 100
    effect: int = 0               # 0..31
    sections: list[Section] = field(default_factory=lambda: [Section() for _ in range(8)])

    @property
    def effect_number(self) -> int:
        return self.effect + 1

    @property
    def used_singles(self) -> list[int]:
        """Índices de Singles referenciados por secciones no silenciadas."""
        return sorted({s.single for s in self.sections if not s.muted})

    @classmethod
    def from_bytes(cls, d: bytes) -> "Multi":
        if len(d) < 76:
            raise ValueError(_("un {kind} ocupa {size} bytes, recibidos {got}", kind="Multi", size=77, got=len(d)))
        return cls(
            name=_name_from(d), volume=d[10] & 0x7F, effect=d[11] & 0x1F,
            sections=[Section.from_bytes(d[12 + 8 * i: 20 + 8 * i]) for i in range(8)],
        )

    def data_bytes(self) -> bytes:
        b = _name_to(self.name) + bytes([self.volume, self.effect & 0x1F])
        b += b"".join(s.to_bytes() for s in self.sections)
        return b

    def to_bytes(self) -> bytes:
        d = self.data_bytes()
        return d + bytes([checksum(d)])


# ================================================================== DRUM

@dataclass
class DrumSource:
    wave: int = 96                # 0..255
    decay: int = 50               # 0..100
    tune: int = 0                 # ±50
    level: int = 100

    @property
    def wave_name(self) -> str:
        return C.wave_name(self.wave)


@dataclass
class DrumNote:
    submix: int = 0
    s1: DrumSource = field(default_factory=DrumSource)
    s2: DrumSource = field(default_factory=lambda: DrumSource(level=0))

    @classmethod
    def from_bytes(cls, d: bytes) -> "DrumNote":
        a, b = d[0:10:2], d[1:10:2]

        def src(x: bytes) -> DrumSource:
            return DrumSource(wave=((x[0] & 0x01) << 7) | (x[1] & 0x7F),
                              decay=x[2] & 0x7F, tune=_bi(x[3]), level=x[4] & 0x7F)
        return cls(submix=(a[0] >> 4) & 0x07, s1=src(a), s2=src(b))

    def to_bytes(self) -> bytes:
        def src(s: DrumSource, extra: int = 0) -> bytes:
            return bytes([((s.wave >> 7) & 1) | extra, s.wave & 0x7F, s.decay, _enc(s.tune), s.level])
        d = _interleave([src(self.s1, (self.submix & 7) << 4), src(self.s2)])
        return d + bytes([checksum(d)])


@dataclass
class Drum(_Patch):
    DATA_SIZE = 11 + 11 * C.DRUM_NOTE_COUNT   # 682
    _RESERVED = ("reserved",)

    channel: int = 9              # 0..15 (canal 10)
    volume: int = 100
    vel_depth: int = 0            # ±50
    reserved: bytes = field(default=bytes(7), repr=False)   # 7 bytes de relleno
    notes: list[DrumNote] = field(default_factory=lambda: [DrumNote() for _ in range(C.DRUM_NOTE_COUNT)])

    @classmethod
    def from_bytes(cls, d: bytes) -> "Drum":
        if len(d) < cls.DATA_SIZE:
            raise ValueError(_("un {kind} ocupa {size} bytes, recibidos {got}", kind="Drum", size=cls.DATA_SIZE, got=len(d)))
        notes = [DrumNote.from_bytes(d[11 + 11 * i: 22 + 11 * i]) for i in range(C.DRUM_NOTE_COUNT)]
        return cls(channel=d[0] & 0x0F, volume=d[1] & 0x7F, vel_depth=_bi(d[2]),
                   reserved=bytes(d[3:10]), notes=notes)

    def to_bytes(self) -> bytes:
        common = bytes([self.channel & 0x0F, self.volume, _enc(self.vel_depth)]) + bytes(self.reserved[:7]).ljust(7, b'\0')
        out = common + bytes([checksum(common)])
        for n in self.notes:
            out += n.to_bytes()
        return out


# ================================================================== EFFECT

@dataclass
class SubmixSetting:
    pan: int = 0                  # ±7
    send1: int = 0                # 0..100 (solo K4)
    send2: int = 0


@dataclass
class Effect(_Patch):
    DATA_SIZE = 35
    _RESERVED = ("reserved",)

    type: int = 0                 # 0..15
    param1: int = 0               # ±7
    param2: int = 0               # ±7
    param3: int = 0               # 0..31
    reserved: bytes = field(default=bytes(6), repr=False)   # 6 bytes de relleno
    submixes: list[SubmixSetting] = field(default_factory=lambda: [SubmixSetting() for _ in range(8)])

    @property
    def type_name(self) -> str:
        return C.EFFECT_TYPES[self.type] if self.type < len(C.EFFECT_TYPES) else f"?{self.type}"

    @property
    def param_names(self) -> tuple[str, str, str]:
        return C.EFFECT_PARAM_NAMES[self.type] if self.type < 16 else ("P1", "P2", "P3")

    @property
    def name(self) -> str:
        """Los efectos no tienen nombre: se usa el del tipo."""
        return self.type_name

    @classmethod
    def from_bytes(cls, d: bytes) -> "Effect":
        subs = [SubmixSetting(pan=(d[10 + 3 * i] & 0x0F) - 7, send1=d[11 + 3 * i] & 0x7F,
                              send2=d[12 + 3 * i] & 0x7F) for i in range(8)]
        return cls(type=d[0] & 0x0F, param1=_bi(d[1] & 0x0F, 7), param2=_bi(d[2] & 0x0F, 7),
                   param3=d[3] & 0x1F, reserved=bytes(d[4:10]), submixes=subs)

    def to_bytes(self) -> bytes:
        d = bytes([self.type & 0x0F, _enc(self.param1, 7), _enc(self.param2, 7), self.param3 & 0x1F])
        d += bytes(self.reserved[:6]).ljust(6, b'\0')
        for s in self.submixes:
            d += bytes([_enc(s.pan, 7), s.send1, s.send2])
        return d + bytes([checksum(d)])

    def summary(self) -> str:
        n = self.param_names
        return f"{self.type_name}: {n[0]} {self.param1}, {n[1]} {self.param2}, {n[2]} {self.param3}"


# Tamaño de cada tipo en un volcado
SIZES = {"single": Single.DATA_SIZE, "multi": Multi.DATA_SIZE,
         "drum": Drum.DATA_SIZE, "effect": Effect.DATA_SIZE}
ALL_DUMP_SIZE = 64 * Single.DATA_SIZE + 64 * Multi.DATA_SIZE + Drum.DATA_SIZE + 32 * Effect.DATA_SIZE
