"""Simulador de un K4 para probar sin el aparato.

Se comporta como K4Midi (misma interfaz), pero en lugar de puertos MIDI
responde desde un banco en memoria: atiende peticiones de volcado, acepta
escrituras con su confirmación (o error de checksum, protección o falta de
tarjeta) y guarda el buffer de edición y los Parameter Send recibidos.

    from k4lib.fake import FakeK4
    k4 = FakeK4(Bank.from_file("A401.SYX"))
    bank = k4.get_bank()
"""
from __future__ import annotations

from .i18n import _

import queue
import time

from .bank import Bank
from .midi import K4Midi
from .patches import Drum, Effect, Multi, Single
from .sysex import MIDI_BYTES_PER_SECOND, Function, K4Error, Location, Message, checksum


class FakeK4(K4Midi):
    def __init__(self, bank: Bank | None = None, *, external_bank: Bank | None = None,
                 channel: int = 1, speed: float = 0.0, write_protect: bool = False):
        """speed: fracción del tiempo real de transmisión MIDI que se simula
        (0 = instantáneo, 1 = tan lento como un K4 de verdad)."""
        self.in_name = self.out_name = _("Simulador K4")
        self.channel = channel - 1
        self.timeout = 3.0
        self.pause = 0.0
        self.speed = speed
        self.write_protect = write_protect
        self.banks = {False: bank or Bank.empty(), True: external_bank}
        self.edit_buffer: Single | None = None
        self.edit_buffer_multi: Multi | None = None
        self.notes: list[tuple[bool, int, int, int]] = []   # (on, canal, nota, velocidad)
        self.parameters: list[tuple[int, int, int]] = []
        self.current_program: tuple[bool, int] = (False, 0)
        self.received: list[Message] = []
        self._replies: queue.Queue[Message] = queue.Queue()
        self._pending_external = False

    # ---------------------------------------------------------- transporte
    def close(self):
        pass

    def _drain(self):
        while not self._replies.empty():
            self._replies.get_nowait()

    def _wire(self, nbytes: int):
        if self.speed:
            time.sleep(nbytes / MIDI_BYTES_PER_SECOND * self.speed)

    def send(self, msg: Message) -> None:
        self.received.append(msg)
        self._wire(len(msg.to_bytes()))
        if msg.channel == self.channel:          # el K4 ignora otros canales
            self._handle(msg)

    def receive(self, functions: set[int], timeout: float | None = None) -> Message:
        deadline = time.monotonic() + (timeout or self.timeout)
        while time.monotonic() < deadline:
            try:
                m = self._replies.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                break
            if m.function in functions:
                self._wire(len(m.to_bytes()))
                return m
        raise K4Error(_("el K4 no ha respondido (simulador)"))

    def _note(self, on: bool, channel: int, note: int, velocity: int) -> None:
        self.notes.append((on, channel, note, velocity))

    def play_notes(self, notes, duration: float = 1.0) -> None:
        super().play_notes(notes, duration * self.speed)   # sin esperar en tests

    def program_change(self, loc, external: bool = False, multi: bool = False) -> None:
        loc = loc if isinstance(loc, Location) else Location.parse(str(loc))
        self.current_program = (loc.external, loc.index + (64 if multi else 0))

    # ---------------------------------------------------------- lógica
    def _reply(self, function: int, body: bytes = b"") -> None:
        self._replies.put(Message(self.channel, function, body))

    def _handle(self, m: Message) -> None:
        fn = m.function
        if fn == Function.PARAMETER_SEND:
            self.parameters.append(tuple(m.body[:3]))
            return
        if fn == Function.EDIT_BUFFER_DUMP:
            if m.sub2 == 0x40:
                self.edit_buffer_multi = Multi.from_bytes(m.data)
            else:
                self.edit_buffer = Single.from_bytes(m.data)
            return
        if fn == Function.PROGRAM_CHANGE:
            self._pending_external = bool(m.body and m.body[0] & 0x02)
            return

        ext = bool(m.sub1 & 0x02) if m.sub1 is not None else False
        bank = self.banks[ext]
        if bank is None:                          # sin tarjeta insertada
            if fn == Function.ONE_DATA_DUMP:
                self._reply(Function.WRITE_ERROR_NO_CARD)
            return
        s1, s2 = (m.sub1 or 0) & 0x01, m.sub2 or 0

        if fn == Function.ONE_DUMP_REQUEST:
            kind = ("effect" if s2 < 32 else "drum") if s1 else ("single" if s2 < 64 else "multi")
            index = s2 - 64 if kind == "multi" else s2
            try:
                reply = bank.patch_message(kind, index, self.channel, ext)
            except K4Error:
                return
            self._replies.put(reply)
        elif fn == Function.BLOCK_DUMP_REQUEST:
            if s1:
                data = b"".join(e.to_bytes() for e in bank.effects)
            elif s2 == 0x40:
                data = b"".join(x.to_bytes() for x in bank.multis)
            else:
                data = b"".join(x.to_bytes() for x in bank.singles)
            self._reply(Function.BLOCK_DATA_DUMP, bytes([m.sub1, s2]) + data)
        elif fn == Function.ALL_DUMP_REQUEST:
            self._replies.put(bank.to_all_dump(self.channel, ext))
        elif fn == Function.ONE_DATA_DUMP:
            if self.write_protect and not ext:
                self._reply(Function.WRITE_ERROR_PROTECT)
                return
            if not self._checksums_ok(m):
                self._reply(Function.WRITE_ERROR)
                return
            bank._load_dump(m)
            self._reply(Function.WRITE_COMPLETE)

    @staticmethod
    def _checksums_ok(m: Message) -> bool:
        d = m.data
        if (m.sub1 & 0x01) and m.sub2 == 0x20:    # drum: checksum común + uno por nota
            size = Drum.DATA_SIZE
            if len(d) != size or d[10] != checksum(d[:10]):
                return False
            return all(d[11 + 11 * i + 10] == checksum(d[11 + 11 * i: 21 + 11 * i]) for i in range(61))
        size = (Effect.DATA_SIZE if m.sub1 & 0x01 else
                Single.DATA_SIZE if m.sub2 < 64 else Multi.DATA_SIZE)
        return len(d) == size and d[-1] == checksum(d[:-1])
