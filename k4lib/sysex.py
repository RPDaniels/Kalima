"""Mensajes System Exclusive del Kawai K4/K4r.

Formato general:  F0 40 0n ff 00 04 [cuerpo...] F7
    40  fabricante Kawai
    0n  canal MIDI - 1
    ff  función
    00  grupo (sintetizadores)
    04  ID de máquina K4/K4r
En los volcados y peticiones el cuerpo empieza por dos bytes de
"substatus" (s1, s2) que indican qué patch es.
"""
from __future__ import annotations

from .i18n import N_, _

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable

from .constants import GROUPS

SYSEX_START = 0xF0
SYSEX_END = 0xF7
MANUFACTURER = 0x40
GROUP = 0x00
MACHINE_ID = 0x04


class Function(IntEnum):
    ONE_DUMP_REQUEST = 0x00
    BLOCK_DUMP_REQUEST = 0x01
    ALL_DUMP_REQUEST = 0x02
    PARAMETER_SEND = 0x10
    ONE_DATA_DUMP = 0x20
    BLOCK_DATA_DUMP = 0x21
    ALL_DATA_DUMP = 0x22
    EDIT_BUFFER_DUMP = 0x23
    PROGRAM_CHANGE = 0x30
    WRITE_COMPLETE = 0x40
    WRITE_ERROR = 0x41
    WRITE_ERROR_PROTECT = 0x42
    WRITE_ERROR_NO_CARD = 0x43


class K4Error(Exception):
    pass


def checksum(data: Iterable[int]) -> int:
    """Checksum Kawai K1/K4: (0xA5 + suma de los bytes) & 0x7F."""
    return (0xA5 + sum(data)) & 0x7F


# ---------------------------------------------------------------- posiciones

@dataclass(frozen=True, order=True)
class Location:
    """Posición de memoria: interna/externa (tarjeta) + índice 0..63 (A-1..D-16)."""
    external: bool
    index: int

    def __post_init__(self):
        if not 0 <= self.index < 64:
            raise ValueError(_("índice fuera de rango: {index}", index=self.index))

    @property
    def name(self) -> str:
        g, n = divmod(self.index, 16)
        return f"{'E-' if self.external else ''}{GROUPS[g]}-{n + 1}"

    def __str__(self) -> str:
        return self.name

    @classmethod
    def parse(cls, text: str) -> "Location":
        """Acepta 'A-1', 'd16', 'E-A-1', 'ext:B-3' o un número 1..64."""
        t = text.strip().upper().replace(" ", "")
        external = False
        for prefix in ("EXT:", "EXT-", "E-", "E:"):
            if t.startswith(prefix):
                external, t = True, t[len(prefix):]
                break
        if t.isdigit():
            return cls(external, int(t) - 1)
        t = t.replace("-", "")
        if len(t) >= 2 and t[0] in GROUPS and t[1:].isdigit():
            n = int(t[1:])
            if 1 <= n <= 16:
                return cls(external, GROUPS.index(t[0]) * 16 + n - 1)
        raise ValueError(_("posición no válida: «{text}» (usa por ejemplo A-1, D-16 o E-B-3)", text=text))


def index_name(index: int) -> str:
    g, n = divmod(index, 16)
    return f"{GROUPS[g]}-{n + 1}"


# ---------------------------------------------------------------- mensajes

@dataclass
class Message:
    """Un mensaje SysEx del K4 ya separado en cabecera y cuerpo."""
    channel: int            # 0..15
    function: int
    body: bytes = b""

    @property
    def sub1(self) -> int | None:
        return self.body[0] if len(self.body) > 0 else None

    @property
    def sub2(self) -> int | None:
        return self.body[1] if len(self.body) > 1 else None

    @property
    def data(self) -> bytes:
        """Datos del volcado (sin s1/s2)."""
        return self.body[2:]

    @property
    def external(self) -> bool:
        return bool(self.sub1 is not None and self.sub1 & 0x02)

    def to_bytes(self) -> bytes:
        return bytes([SYSEX_START, MANUFACTURER, self.channel & 0x0F, self.function,
                      GROUP, MACHINE_ID]) + bytes(self.body) + bytes([SYSEX_END])

    def to_mido_data(self) -> list[int]:
        """Contenido para mido.Message('sysex', data=...) (sin F0/F7)."""
        return list(self.to_bytes()[1:-1])

    @classmethod
    def parse(cls, raw: bytes | Iterable[int]) -> "Message":
        b = bytes(raw)
        if b and b[0] == SYSEX_START:
            b = b[1:]
        if b and b[-1] == SYSEX_END:
            b = b[:-1]
        if len(b) < 5 or b[0] != MANUFACTURER:
            raise K4Error(_("no es un mensaje SysEx de Kawai"))
        if b[3] != GROUP or b[4] != MACHINE_ID:
            raise K4Error(_("no es un mensaje del K4 (grupo {group:02X}, máquina {machine:02X})", group=b[3], machine=b[4]))
        return cls(channel=b[1] & 0x0F, function=b[2], body=b[5:])

    def describe(self) -> str:
        try:
            fn = Function(self.function).name
        except ValueError:
            fn = f"0x{self.function:02X}"
        return f"ch{self.channel + 1} {fn} s1={self.sub1} s2={self.sub2} {len(self.data)} bytes"


def split_sysex(blob: bytes) -> list[bytes]:
    """Separa un archivo .syx (o un flujo) en mensajes F0..F7 individuales.

    Tolera mensajes sin el F7 final, que dejan algunos programas antiguos (p. ej.
    ZAIDA3.SYX, de 1998, guarda tres volcados de bloque y solo cierra el último):
    como los datos SysEx nunca contienen F0, un F0 nuevo (o el final del archivo)
    cierra el mensaje anterior, al que se le añade el F7 que falta."""
    out, start = [], None
    for i, b in enumerate(blob):
        if b == SYSEX_START:
            if start is not None and i - start > 1:
                out.append(bytes(blob[start:i]) + bytes([SYSEX_END]))
            start = i
        elif b == SYSEX_END and start is not None:
            out.append(bytes(blob[start:i + 1]))
            start = None
    if start is not None and len(blob) - start > 1:
        out.append(bytes(blob[start:]) + bytes([SYSEX_END]))
    return out


def read_syx(path) -> list[Message]:
    """Lee un archivo y devuelve los mensajes del K4 que contiene (ignora el resto).
    Acepta SysEx en bruto (.syx) y archivos MIDI estándar (.mid) con eventos SysEx."""
    with open(path, "rb") as f:
        blob = f.read()
    if blob[:4] == b"MThd":
        return read_midi_file(path)
    msgs = []
    for raw in split_sysex(blob):
        try:
            msgs.append(Message.parse(raw))
        except K4Error:
            pass
    return msgs


def write_syx(path, messages: Iterable[Message | bytes]) -> None:
    with open(path, "wb") as f:
        for m in messages:
            f.write(m.to_bytes() if isinstance(m, Message) else bytes(m))


def read_midi_file(path) -> list[Message]:
    """Extrae los SysEx del K4 de un archivo MIDI estándar (necesita mido)."""
    try:
        import mido
    except ImportError:
        raise K4Error(_("para leer archivos .mid hace falta mido: pip install mido")) from None
    msgs = []
    for track in mido.MidiFile(path).tracks:
        for ev in track:
            if ev.type == "sysex":
                try:
                    msgs.append(Message.parse([SYSEX_START, *ev.data, SYSEX_END]))
                except K4Error:
                    pass
    return msgs


MIDI_BYTES_PER_SECOND = 3125        # 31250 baudios / 10 bits por byte


def write_midi_file(path, messages: Iterable[Message | bytes], margin: float = 0.2) -> None:
    """Guarda los SysEx en un archivo MIDI estándar (tipo 0).

    Entre mensaje y mensaje deja el tiempo que tarda en transmitirse el
    anterior más un margen, para que un secuenciador que reproduzca el
    archivo no sature al K4 (un banco completo tarda unos 5 s)."""
    try:
        import mido
    except ImportError:
        raise K4Error(_("para guardar archivos .mid hace falta mido: pip install mido")) from None
    tpb, tempo = 480, 500_000                       # 120 bpm: 480 ticks = 0,5 s
    ticks_per_second = tpb * 1_000_000 / tempo
    mf = mido.MidiFile(type=0, ticks_per_beat=tpb)
    track = mido.MidiTrack()
    mf.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Kawai K4 SysEx", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    delay = 0
    for m in messages:
        raw = m.to_bytes() if isinstance(m, Message) else bytes(m)
        track.append(mido.Message("sysex", data=list(raw[1:-1]), time=delay))
        delay = round((len(raw) / MIDI_BYTES_PER_SECOND + margin) * ticks_per_second)
    track.append(mido.MetaMessage("end_of_track", time=delay))
    mf.save(path)


def write_patch_file(path, messages: Iterable[Message | bytes]) -> None:
    """Guarda en .syx o .mid según la extensión del archivo."""
    if str(path).lower().endswith((".mid", ".midi", ".smf")):
        write_midi_file(path, messages)
    else:
        write_syx(path, messages)


# ---------------------------------------------------------------- constructores
# Tipos de patch para direccionar volcados y peticiones.
SINGLE, MULTI, DRUM, EFFECT = "single", "multi", "drum", "effect"


def address(kind: str, loc: Location | None = None, external: bool = False) -> tuple[int, int]:
    """Devuelve (s1, s2) para un patch concreto."""
    if loc is not None:
        external = loc.external
    ext = 0x02 if external else 0x00
    if kind == SINGLE:
        return ext, loc.index
    if kind == MULTI:
        return ext, 0x40 + loc.index
    if kind == EFFECT:
        if not 0 <= loc.index < 32:
            raise ValueError(_("los efectos van de 1 a 32"))
        return 0x01 | ext, loc.index
    if kind == DRUM:
        return 0x01 | ext, 0x20
    raise ValueError(kind)


def one_dump_request(channel: int, kind: str, loc: Location | None = None,
                     external: bool = False) -> Message:
    s1, s2 = address(kind, loc, external)
    return Message(channel, Function.ONE_DUMP_REQUEST, bytes([s1, s2]))


def block_dump_request(channel: int, kind: str, external: bool = False) -> Message:
    """Pide los 64 Singles, los 64 Multis o los 32 efectos de golpe."""
    ext = 0x02 if external else 0x00
    s1, s2 = {SINGLE: (ext, 0x00), MULTI: (ext, 0x40), EFFECT: (0x01 | ext, 0x00)}[kind]
    return Message(channel, Function.BLOCK_DUMP_REQUEST, bytes([s1, s2]))


def all_dump_request(channel: int, external: bool = False) -> Message:
    """Pide el banco completo (Singles, Multis, Drum y efectos)."""
    return Message(channel, Function.ALL_DUMP_REQUEST, bytes([0x02 if external else 0x00, 0x00]))


def one_data_dump(channel: int, kind: str, loc: Location | None, patch_bytes: bytes,
                  external: bool = False) -> Message:
    s1, s2 = address(kind, loc, external)
    return Message(channel, Function.ONE_DATA_DUMP, bytes([s1, s2]) + bytes(patch_bytes))


def edit_buffer_dump(channel: int, patch_bytes: bytes, kind: str = SINGLE) -> Message:
    """Envía un Single (s2 = 00) o un Multi (s2 = 40) a la memoria de edición: se oye
    sin escribir en memoria, siempre que el K4 esté en el modo correspondiente.
    El manual omite o equivoca s1/s2; estos valores son los que usa Edisyn."""
    if kind not in (SINGLE, MULTI):
        raise ValueError(_("solo Singles y Multis tienen memoria de edición"))
    s2 = 0x40 if kind == MULTI else 0x00
    return Message(channel, Function.EDIT_BUFFER_DUMP, bytes([0x00, s2]) + bytes(patch_bytes))


def parameter_send(channel: int, parameter: int, value: int, section: int = 0) -> Message:
    """Cambia un parámetro del Single en edición.

    section: fuente 0..3 (S1..S4) para parámetros de fuente/DCA;
             para filtros Edisyn usa 0 = F1 y 2 = F2.
    value:   valor crudo 0..255 (el bit 7 viaja en el byte de sección).
    """
    if not 0 <= value <= 255:
        raise ValueError(_("valor fuera de 0..255"))
    ss = ((section & 0x03) << 1) | ((value >> 7) & 0x01)
    return Message(channel, Function.PARAMETER_SEND, bytes([parameter & 0x7F, ss, value & 0x7F]))


def program_bank_select(channel: int, external: bool) -> Message:
    """Selecciona memoria interna o externa antes de un Program Change normal."""
    return Message(channel, Function.PROGRAM_CHANGE, bytes([0x02 if external else 0x00]))


WRITE_RESULTS = {
    Function.WRITE_COMPLETE: N_("escritura completada"),
    Function.WRITE_ERROR: N_("error de escritura (¿fallo de transmisión o checksum?)"),
    Function.WRITE_ERROR_PROTECT: N_("error: memoria protegida contra escritura"),
    Function.WRITE_ERROR_NO_CARD: N_("error: no hay tarjeta externa insertada"),
}
