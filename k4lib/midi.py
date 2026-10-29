"""Comunicación MIDI con el K4 usando mido (+ python-rtmidi).

    from k4lib.midi import K4Midi
    with K4Midi("UM-ONE", channel=1) as k4:      # nombre (o parte) del puerto
        bank = k4.get_bank()                     # banco interno completo
        s = k4.get_single("A-1")
        k4.send_to_edit_buffer(s)                # escuchar sin guardar
        k4.write_single(s, "D-16")               # guardar (espera confirmación)

Requisitos en el K4: recepción de SysEx activada en SYSTEM y el mismo
canal MIDI que el indicado aquí.
"""
from __future__ import annotations

from .i18n import N_, _

import time

from .bank import Bank
from .constants import DRUM_FIRST_NOTE
from .patches import Drum, Effect, Multi, Single
from .sysex import (DRUM, EFFECT, MULTI, SINGLE, WRITE_RESULTS, Function, K4Error, Location, Message,
                    all_dump_request, block_dump_request, edit_buffer_dump, one_data_dump,
                    one_dump_request, parameter_send, program_bank_select)

try:
    import mido
except ImportError:  # pragma: no cover
    mido = None


def list_ports() -> tuple[list[str], list[str]]:
    """(entradas, salidas) MIDI disponibles."""
    _need_mido()
    return mido.get_input_names(), mido.get_output_names()


def _need_mido():
    if mido is None:
        raise K4Error(_("falta mido: pip install mido python-rtmidi"))


def _find_port(names: list[str], wanted: str | None, kind: str) -> str:
    if not names:
        raise K4Error(_("no hay puertos MIDI de {kind}", kind=_(kind)))
    if wanted is None:
        return names[0]
    for n in names:
        if wanted.lower() in n.lower():
            return n
    raise K4Error(_("no encuentro el puerto de {kind} «{wanted}». Disponibles: {names}", kind=_(kind), wanted=wanted, names=", ".join(names)))


class SysexInput:
    """Entrada MIDI que reensambla los SysEx que llegan partidos en trozos.

    En Windows (WinMM) los SysEx de más de ~1 KB se entregan en varios trozos,
    y mido descarta en silencio cualquier trozo que no sea un mensaje completo:
    un volcado de banco del K4 (15 KB) se perdería entero. Por eso la entrada se
    lee directamente de python-rtmidi y los bytes se juntan aquí, de F0 a F7.

    `rt` permite inyectar un objeto con la interfaz de rtmidi.MidiIn (tests)."""

    def __init__(self, name: str | None = None, rt=None):
        if rt is None:
            try:
                import rtmidi
            except ImportError:
                raise K4Error(_("falta python-rtmidi: pip install python-rtmidi")) from None
            try:
                rt = rtmidi.MidiIn(queue_size_limit=4096)
            except TypeError:
                rt = rtmidi.MidiIn()
            ports = rt.get_ports()
            if name in ports:
                index = ports.index(name)
            else:
                matches = [i for i, p in enumerate(ports) if name and name.lower() in p.lower()]
                if not matches:
                    raise K4Error(_("no encuentro el puerto de {kind} «{wanted}». Disponibles: {names}", kind=_("entrada"), wanted=name, names=", ".join(ports)))
                index = matches[0]
            rt.open_port(index)
        rt.ignore_types(sysex=False, timing=True, active_sense=True)
        self.rt = rt
        self._buf: bytearray | None = None
        self.reset_stats()

    def reset_stats(self):
        self.bytes_received = 0       # bytes recibidos (de cualquier tipo)
        self.chunks = 0               # trozos entregados por el controlador
        self.sysex_received = 0       # SysEx completos reensamblados

    def poll(self) -> list[bytes]:
        """Devuelve los SysEx completos (F0..F7) llegados desde la última llamada."""
        done = []
        while True:
            item = self.rt.get_message()
            if not item:
                break
            data = item[0]
            self.chunks += 1
            self.bytes_received += len(data)
            for b in data:
                if b == 0xF0:
                    self._buf = bytearray([b])
                elif self._buf is None:
                    continue                  # bytes fuera de un SysEx
                elif b >= 0xF8:
                    continue                  # tiempo real intercalado (clock, active sensing…)
                elif b == 0xF7:
                    self._buf.append(b)
                    done.append(bytes(self._buf))
                    self._buf = None
                elif b & 0x80:
                    self._buf = None          # otro byte de estado: SysEx interrumpido
                else:
                    self._buf.append(b)
        self.sysex_received += len(done)
        return done

    def drain(self):
        self.poll()
        self._buf = None
        self.reset_stats()

    def close(self):
        try:
            self.rt.close_port()
        except Exception:  # noqa: BLE001
            pass


TEST_NOTE_MODES = {"none": N_("Ninguna"), "note": N_("Una nota (Do 4)"), "chord": N_("Acorde (Do mayor)")}
_VELOCITY_FOR_SWITCH = {0: 50, 1: 115, 2: 100}       # Soft, Loud, All


def test_note_plan(patch: Single | Multi, mode: str, channel: int) -> list[tuple[int, int, int]]:
    """Notas de prueba (canal 0..15, nota, velocidad) para escuchar un patch.

    Single: en el canal del K4; si el Single es monofónico (Solo) solo una nota.
    Multi: en el canal de cada sección activa que responde a MIDI (modo MIDI o Mix),
    dentro de su zona de teclado y con una velocidad acorde a su conmutación por
    velocidad (Soft/Loud). Las secciones en modo Keyboard no responden a MIDI."""
    if mode == "none":
        return []
    shape = (0, 4, 7) if mode == "chord" else (0,)
    if isinstance(patch, Single):
        intervals = (0,) if patch.poly_mode >= 2 else shape
        return [(channel, 60 + i, 100) for i in intervals]
    out, seen = [], set()
    for sec in patch.sections:
        if sec.muted or sec.play_mode == 0:
            continue
        lo, hi = sorted((sec.low_key, sec.high_key))
        base = min(max(60, lo), hi)
        for i in shape:
            n = base + i
            if lo <= n <= hi and (sec.channel, n) not in seen:
                seen.add((sec.channel, n))
                out.append((sec.channel, n, _VELOCITY_FOR_SWITCH.get(sec.vel_switch, 100)))
    return out


def _loc(loc: Location | str | int, external: bool = False) -> Location:
    if isinstance(loc, Location):
        return loc
    if isinstance(loc, int):
        return Location(external, loc)
    return Location.parse(loc)


class K4Midi:
    """Conexión con un K4. channel es 1..16, como en el panel."""

    def __init__(self, port: str | None = None, *, in_port: str | None = None,
                 out_port: str | None = None, channel: int = 1, timeout: float = 3.0,
                 pause: float = 0.12):
        _need_mido()
        ins, outs = mido.get_input_names(), mido.get_output_names()
        self.in_name = _find_port(ins, in_port or port, N_("entrada"))
        self.out_name = _find_port(outs, out_port or port, N_("salida"))
        self.channel = channel - 1
        self.timeout = timeout
        self.pause = pause              # pausa entre mensajes; el K4 es lento
        self.out = mido.open_output(self.out_name)
        try:
            self.inp = SysexInput(self.in_name)
        except Exception:
            self.out.close()
            raise

    @classmethod
    def with_ports(cls, inp: SysexInput, out, *, channel: int = 1, timeout: float = 3.0,
                   pause: float = 0.0, in_name: str = "entrada", out_name: str = "salida") -> "K4Midi":
        """Crea la conexión con puertos ya abiertos (o simulados, para tests)."""
        self = cls.__new__(cls)
        self.in_name, self.out_name = in_name, out_name
        self.channel, self.timeout, self.pause = channel - 1, timeout, pause
        self.inp, self.out = inp, out
        return self

    # -------------------------------------------------------------- básico

    def close(self):
        self.inp.close()
        self.out.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def send(self, msg: Message) -> None:
        self.out.send(mido.Message("sysex", data=msg.to_mido_data()))
        time.sleep(self.pause)

    def _drain(self):
        self.inp.drain()

    def receive(self, functions: set[int], timeout: float | None = None) -> Message:
        """Espera un SysEx del K4 cuya función esté en `functions`.

        `timeout` es el tiempo máximo *sin recibir nada*: mientras sigan llegando
        datos (un banco completo tarda ~5 s) la espera se prolonga."""
        idle = timeout or self.timeout
        start = last_activity = time.monotonic()
        seen_bytes = self.inp.bytes_received
        others: list[str] = []
        while True:
            for raw in self.inp.poll():
                try:
                    m = Message.parse(raw)
                except K4Error:
                    others.append(_("SysEx ajeno de {n} bytes", n=len(raw)))
                    continue
                if m.function in functions:
                    return m
                others.append(m.describe())
            now = time.monotonic()
            if self.inp.bytes_received != seen_bytes:
                seen_bytes = self.inp.bytes_received
                last_activity = now
            if now - last_activity > idle or now - start > max(60.0, idle * 4):
                break
            time.sleep(0.005)
        raise K4Error(self._no_reply_message(others))

    def _no_reply_message(self, others: list[str]) -> str:
        inp = self.inp
        if inp.bytes_received == 0:
            return _("no ha llegado ningún dato MIDI por la entrada «{port}». Comprueba que es el puerto "
                     "correcto y que el MIDI OUT del K4 va a la entrada del interfaz.", port=self.in_name)
        if inp.sysex_received == 0:
            return _("han llegado {bytes} bytes ({chunks} trozos) por «{port}», pero ningún mensaje SysEx "
                     "completo. El interfaz MIDI podría estar perdiendo datos de los SysEx largos.",
                     bytes=inp.bytes_received, chunks=inp.chunks, port=self.in_name)
        if others:
            return _("han llegado mensajes del K4, pero no la respuesta esperada: {messages}. Revisa el canal MIDI.",
                     messages="; ".join(others[:3]))
        return _("el K4 no ha respondido (revisa canal, SysEx activado y cableado)")

    def request(self, msg: Message, functions: set[int], timeout: float | None = None) -> Message:
        self._drain()
        self.send(msg)
        return self.receive(functions, timeout)

    # -------------------------------------------------------------- lectura

    def get_single(self, loc: Location | str | int, external: bool = False) -> Single:
        r = self.request(one_dump_request(self.channel, SINGLE, _loc(loc, external)),
                         {Function.ONE_DATA_DUMP})
        return Single.from_bytes(r.data)

    def get_multi(self, loc: Location | str | int, external: bool = False) -> Multi:
        r = self.request(one_dump_request(self.channel, MULTI, _loc(loc, external)),
                         {Function.ONE_DATA_DUMP})
        return Multi.from_bytes(r.data)

    def get_effect(self, number: int, external: bool = False) -> Effect:
        """number: 1..32 como en el panel."""
        r = self.request(one_dump_request(self.channel, EFFECT, Location(external, number - 1)),
                         {Function.ONE_DATA_DUMP})
        return Effect.from_bytes(r.data)

    def get_drum(self, external: bool = False) -> Drum:
        r = self.request(one_dump_request(self.channel, DRUM, external=external),
                         {Function.ONE_DATA_DUMP})
        return Drum.from_bytes(r.data)

    def get_block(self, kind: str, external: bool = False) -> Bank:
        """Bloque de 64 Singles, 64 Multis o 32 efectos, como Bank parcial."""
        r = self.request(block_dump_request(self.channel, kind, external),
                         {Function.BLOCK_DATA_DUMP}, timeout=self.timeout * 2)
        return Bank.from_messages([r])

    def get_bank(self, external: bool = False) -> Bank:
        """Banco completo (unos 15 KB; tarda unos segundos a 31250 baudios)."""
        r = self.request(all_dump_request(self.channel, external),
                         {Function.ALL_DATA_DUMP}, timeout=self.timeout * 2)
        return Bank.from_messages([r])

    # -------------------------------------------------------------- escritura

    def send_to_edit_buffer(self, patch: Single | Multi) -> None:
        """Carga un Single o un Multi en la memoria de edición, sin guardarlo.
        Solo se oye si el K4 está en el modo correspondiente (ver audition)."""
        kind = MULTI if isinstance(patch, Multi) else SINGLE
        self.send(edit_buffer_dump(self.channel, patch.to_bytes(), kind))

    def audition(self, patch: Single | Multi, loc: Location | str | int, external: bool = False,
                 test_notes: str = "chord") -> list[tuple[int, int, int]]:
        """Escucha un patch del archivo en el K4 sin escribirlo en memoria:

        1. Program Change a su posición, para poner el K4 en modo Single o Multi
           (la memoria de edición solo suena en el modo activo).
        2. Volcado del patch a la memoria de edición.
        3. Notas de prueba (test_notes: "none", "note" o "chord").

        Un Multi suena con los Singles *guardados en el K4* en las posiciones que
        indican sus secciones. Devuelve las notas tocadas (canal, nota, velocidad)."""
        is_multi = isinstance(patch, Multi)
        self.program_change(loc, external, multi=is_multi)
        self.send_to_edit_buffer(patch)
        time.sleep(0.1)
        notes = test_note_plan(patch, test_notes, self.channel)
        if notes:
            self.play_notes(notes)
        return notes

    def audition_drum(self, drum: Drum, note: int, external: bool = False, compare: bool = True,
                      duration: float = 0.6) -> bool | None:
        """Toca una nota del kit (índice 0..60, notas MIDI 36..96) en el canal del Drum.

        El Drum no tiene memoria de edición: suena el Drum *guardado en el K4*. Con
        `compare` se pide antes al K4 su Drum y se devuelve si coincide con `drum`
        (True/False), o None si el K4 no ha respondido a la petición."""
        same = None
        if compare:
            try:
                same = self.get_drum(external).canonical_bytes() == drum.canonical_bytes()
            except K4Error:
                same = None
        self.play_notes([(drum.channel, DRUM_FIRST_NOTE + note, 100)], duration)
        return same

    def play_notes(self, notes: list[tuple[int, int, int]], duration: float = 1.0) -> None:
        """Toca a la vez las notas (canal 0..15, nota, velocidad) y las suelta tras `duration`."""
        for ch, note, vel in notes:
            self._note(True, ch, note, vel)
        time.sleep(duration)
        for ch, note, _ in notes:
            self._note(False, ch, note, 0)

    def _note(self, on: bool, channel: int, note: int, velocity: int) -> None:
        self.out.send(mido.Message("note_on" if on else "note_off", channel=channel,
                                   note=note, velocity=velocity))

    def _write(self, kind: str, loc: Location | None, data: bytes, external: bool = False) -> str:
        reply = self.request(one_data_dump(self.channel, kind, loc, data, external),
                             set(WRITE_RESULTS))
        text = _(WRITE_RESULTS[Function(reply.function)])
        if reply.function != Function.WRITE_COMPLETE:
            raise K4Error(text)
        return text

    def write_single(self, single: Single, loc: Location | str | int, external: bool = False) -> str:
        return self._write(SINGLE, _loc(loc, external), single.to_bytes())

    def write_multi(self, multi: Multi, loc: Location | str | int, external: bool = False) -> str:
        return self._write(MULTI, _loc(loc, external), multi.to_bytes())

    def write_effect(self, effect: Effect, number: int, external: bool = False) -> str:
        return self._write(EFFECT, Location(external, number - 1), effect.to_bytes())

    def write_drum(self, drum: Drum, external: bool = False) -> str:
        return self._write(DRUM, None, drum.to_bytes(), external)

    def write_bank(self, bank: Bank, external: bool = False, progress=None) -> list[str]:
        """Escribe el banco patch a patch, comprobando la confirmación de cada uno.
        Más lento que un volcado completo, pero detecta cualquier fallo."""
        msgs = bank.to_messages(self.channel, external)
        results = []
        for n, m in enumerate(msgs, 1):
            reply = self.request(m, set(WRITE_RESULTS))
            if reply.function != Function.WRITE_COMPLETE:
                raise K4Error(_("patch {n}/{total} ({message}): {error}", n=n, total=len(msgs),
                                message=m.describe(), error=_(WRITE_RESULTS[Function(reply.function)])))
            results.append(m.describe())
            if progress:
                progress(n, len(msgs))
        return results

    # -------------------------------------------------------------- control

    def program_change(self, loc: Location | str | int, external: bool = False,
                       multi: bool = False) -> None:
        """Selecciona un Single o, con multi=True, un Multi (programas 64..127)."""
        loc = _loc(loc, external)
        self.send(program_bank_select(self.channel, loc.external))
        program = loc.index + (64 if multi else 0)
        self.out.send(mido.Message("program_change", channel=self.channel, program=program))
        time.sleep(0.2)                 # el K4 necesita >100 ms tras cambiar de patch

    def set_parameter(self, name_or_number: str | int, value: int, section: int = 0) -> None:
        """Parameter Send en tiempo real sobre el Single en edición.

        Con un nombre de k4lib.params.PARAMETERS el valor va en unidades del
        panel (p. ej. 'filter_env_depth', -20); con un número va crudo."""
        from .params import encode
        number, raw = encode(name_or_number, value)
        self.send(parameter_send(self.channel, number, raw, section))
