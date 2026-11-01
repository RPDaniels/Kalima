"""Banco completo del K4: 64 Singles, 64 Multis, 1 Drum y 32 efectos.

Además de leer y escribir volcados, el banco conoce las dependencias
internas del K4, que van por número de posición:
    Multi  -> Singles (cada sección apunta a un Single A-1..D-16)
    Multi  -> Efecto
    Single -> Efecto
Las operaciones de reordenación (swap_singles, move_single, swap_effects)
reescriben esas referencias para que los Multis sigan sonando igual.
"""
from __future__ import annotations

from .i18n import _, _n

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import constants as C
from .patches import ALL_DUMP_SIZE, Drum, Effect, Multi, Single
from .sysex import Function, K4Error, Message, checksum, index_name, read_syx, write_patch_file


# ------------------------------------------------------------------ comprobación de volcados

def _layout(m: Message) -> list[tuple[str, int]] | None:
    """Patches que contiene un volcado, en orden: (nombre, tamaño). None si no es un volcado."""
    s1, s2 = (m.sub1 or 0) & 0x01, m.sub2 or 0
    singles = [(f"Single {index_name(i)}", Single.DATA_SIZE) for i in range(64)]
    multis = [(f"Multi {index_name(i)}", Multi.DATA_SIZE) for i in range(64)]
    effects = [(_("efecto {n}", n=i + 1), Effect.DATA_SIZE) for i in range(32)]
    if m.function == Function.ALL_DATA_DUMP:
        return singles + multis + [("Drum", Drum.DATA_SIZE)] + effects
    if m.function == Function.BLOCK_DATA_DUMP:
        return effects if s1 else (multis if s2 == 0x40 else singles)
    if m.function == Function.ONE_DATA_DUMP:
        if s1:
            return [("Drum", Drum.DATA_SIZE)] if s2 == 0x20 else [effects[s2 % 32]]
        return [singles[s2]] if s2 < 64 else [multis[(s2 - 64) % 64]]
    return None


def _bad_checksums(m: Message, data: bytes) -> list[str]:
    """Nombres de los patches cuya suma de control no cuadra (datos dañados)."""
    bad, off = [], 0
    for name, size in _layout(m) or []:
        chunk = data[off:off + size]
        off += size
        if len(chunk) < size:
            bad.append(name)
        elif not any(chunk):
            continue                       # a cero: posición vacía, no dañada (ver _empty)
        elif name == "Drum":
            # el Drum lleva una suma para la parte común y otra por cada nota
            parts = [chunk[i:i + 11] for i in range(0, size, 11)]
            if any(checksum(p[:10]) != p[10] for p in parts):
                bad.append(name)
        elif checksum(chunk[:-1]) != chunk[-1]:
            bad.append(name)
    return bad


def _empty(m: Message, data: bytes) -> list[str]:
    """Patches que vienen a cero: algunos programas guardan así lo que no tienen."""
    out, off = [], 0
    for name, size in _layout(m) or []:
        chunk = data[off:off + size]
        off += size
        if len(chunk) == size and not any(chunk):
            out.append(name)
    return out


def check_dump(m: Message) -> tuple[Message, list[str]]:
    """Comprueba un volcado y, si se puede, lo repara. Devuelve el mensaje (el
    original o el reparado) y los avisos para el usuario.

    Reparación: los archivos pasados por un programa de transferencia en modo
    texto (FTP, módems, BBS de los 90) tienen un byte 0D delante de cada 0A
    (salto de línea de MS-DOS). Si quitándolos el volcado recupera su tamaño y
    quedan menos patches con la suma de control mal que antes (normalmente
    ninguno), se acepta la reparación. Los patches que vienen a cero se dejan
    vacíos."""
    layout = _layout(m)
    if layout is None:
        return m, []
    size = sum(n for _name, n in layout)
    data, notes = m.data, []
    if len(data) != size and b"\r\n" in data:
        fixed = data.replace(b"\r\n", b"\n")
        if len(fixed) == size and len(_bad_checksums(m, fixed)) < len(_bad_checksums(m, data)):
            notes.append(_n("reparado: el archivo tenía {n} byte 0D de más, típico de una transferencia en modo "
                            "texto", "reparado: el archivo tenía {n} bytes 0D de más, típico de una transferencia "
                            "en modo texto", len(data) - size))
            m = Message(m.channel, m.function, bytes(m.body[:2]) + fixed)
            data = fixed
    if len(data) > size:
        notes.append(_n("el volcado tiene {n} byte de más", "el volcado tiene {n} bytes de más", len(data) - size))
    elif len(data) < size:
        notes.append(_n("al volcado le falta {n} byte", "al volcado le faltan {n} bytes", size - len(data)))
    empty = _empty(m, data)
    if empty and len(empty) < len(layout):
        notes.append(_n("{n} patch viene a cero en el archivo y queda vacío ({names})",
                        "{n} patches vienen a cero en el archivo y quedan vacíos ({names})", len(empty),
                        names=", ".join(empty[:4]) + (", …" if len(empty) > 4 else "")))
    bad = _bad_checksums(m, data)
    if bad:
        names = ", ".join(bad[:4]) + (", …" if len(bad) > 4 else "")
        notes.append(_n("{n} patch con la suma de control incorrecta ({names}): sus datos están dañados",
                        "{n} patches con la suma de control incorrecta ({names}): sus datos están dañados",
                        len(bad), names=names))
    return m, notes


def _slot(pos: str) -> int:
    """'B-3' -> 18."""
    group, num = pos.split("-")
    return C.GROUPS.index(group) * 16 + int(num) - 1


@dataclass
class Bank:
    singles: list[Single | None] = field(default_factory=lambda: [None] * C.SINGLE_COUNT)
    multis: list[Multi | None] = field(default_factory=lambda: [None] * C.MULTI_COUNT)
    drum: Drum | None = None
    effects: list[Effect | None] = field(default_factory=lambda: [None] * C.EFFECT_COUNT)
    external: bool = False          # de dónde vino (memoria interna o tarjeta)
    source: str = ""                # archivo de origen, si lo hay
    warnings: list[str] = field(default_factory=list, repr=False, compare=False)   # avisos al cargar
    repaired: bool = field(default=False, repr=False, compare=False)    # check_dump corrigió algún volcado

    # ------------------------------------------------------------ construcción

    @classmethod
    def empty(cls) -> "Bank":
        """Banco con patches por defecto en todas las posiciones."""
        return cls([Single() for _ in range(64)], [Multi() for _ in range(64)],
                   Drum(), [Effect() for _ in range(32)])

    @classmethod
    def from_file(cls, path) -> "Bank":
        bank = cls.from_messages(read_syx(path))
        bank.source = str(path)
        return bank

    @classmethod
    def from_messages(cls, messages: list[Message]) -> "Bank":
        """Construye un banco a partir de volcados completos, de bloque o
        individuales (también mezclados). Las posiciones que no aparezcan
        quedan a None."""
        bank = cls()
        found = False
        for m in messages:
            if m.function in (Function.ALL_DATA_DUMP, Function.BLOCK_DATA_DUMP, Function.ONE_DATA_DUMP):
                checked, notes = check_dump(m)
                bank.repaired |= checked is not m
                bank.warnings += notes
                m = checked
                bank.external = m.external
                bank._load_dump(m)
                found = True
            elif m.function == Function.EDIT_BUFFER_DUMP:
                # un Single suelto, sin posición: lo colocamos en el primer hueco
                slot = next((i for i, s in enumerate(bank.singles) if s is None), None)
                if slot is not None:
                    bank.singles[slot] = Single.from_bytes(m.data)
                    found = True
        if not found:
            if any(m.function in (Function.ONE_DUMP_REQUEST, Function.BLOCK_DUMP_REQUEST, Function.ALL_DUMP_REQUEST)
                   for m in messages):
                raise K4Error(_("el archivo solo contiene peticiones de volcado al K4, no datos de sonidos"))
            raise K4Error(_("el archivo no contiene volcados de datos del K4"))
        return bank

    def _load_dump(self, m: Message) -> None:
        d = m.data
        self._place(m, d)
        # lo que viene a cero en el archivo no es un patch: posición vacía
        off = 0
        for name, size in _layout(m) or []:
            chunk = d[off:off + size]
            off += size
            if len(chunk) == size and not any(chunk):
                self._clear(name)

    def _clear(self, name: str) -> None:
        if name == "Drum":
            self.drum = None
            return
        kind, _sep, pos = name.partition(" ")
        if kind == "Single":
            self.singles[_slot(pos)] = None
        elif kind == "Multi":
            self.multis[_slot(pos)] = None
        else:                                   # "efecto N" (traducido): el número va al final
            self.effects[int(name.split()[-1]) - 1] = None

    def _place(self, m: Message, d: bytes) -> None:
        s1, s2 = m.sub1 & 0x01, m.sub2
        if m.function == Function.ALL_DATA_DUMP:
            if len(d) < ALL_DUMP_SIZE:
                raise K4Error(_("volcado completo truncado: {got} de {size} bytes", got=len(d), size=ALL_DUMP_SIZE))
            off = 0
            for i in range(64):
                self.singles[i] = Single.from_bytes(d[off:off + 131]); off += 131
            for i in range(64):
                self.multis[i] = Multi.from_bytes(d[off:off + 77]); off += 77
            self.drum = Drum.from_bytes(d[off:off + Drum.DATA_SIZE]); off += Drum.DATA_SIZE
            for i in range(32):
                self.effects[i] = Effect.from_bytes(d[off:off + 35]); off += 35
        elif m.function == Function.BLOCK_DATA_DUMP:
            if s1 == 0 and s2 == 0x00:
                for i in range(64):
                    self.singles[i] = Single.from_bytes(d[i * 131:(i + 1) * 131])
            elif s1 == 0 and s2 == 0x40:
                for i in range(64):
                    self.multis[i] = Multi.from_bytes(d[i * 77:(i + 1) * 77])
            elif s1 == 1:
                for i in range(32):
                    self.effects[i] = Effect.from_bytes(d[i * 35:(i + 1) * 35])
        else:  # ONE_DATA_DUMP
            if s1 == 0 and s2 < 64:
                self.singles[s2] = Single.from_bytes(d)
            elif s1 == 0:
                self.multis[s2 - 64] = Multi.from_bytes(d)
            elif s2 == 0x20:
                self.drum = Drum.from_bytes(d)
            else:
                self.effects[s2] = Effect.from_bytes(d)

    # ------------------------------------------------------------ exportación

    @property
    def is_complete(self) -> bool:
        return (self.drum is not None and None not in self.singles
                and None not in self.multis and None not in self.effects)

    def to_all_dump(self, channel: int = 0, external: bool | None = None) -> Message:
        """Un único mensaje con el banco completo (15123 bytes)."""
        if not self.is_complete:
            raise K4Error(_("el banco está incompleto; usa to_messages()"))
        ext = self.external if external is None else external
        body = bytes([0x02 if ext else 0x00, 0x00])
        body += b"".join(s.to_bytes() for s in self.singles)
        body += b"".join(m.to_bytes() for m in self.multis)
        body += self.drum.to_bytes()
        body += b"".join(e.to_bytes() for e in self.effects)
        return Message(channel, Function.ALL_DATA_DUMP, body)

    def to_messages(self, channel: int = 0, external: bool | None = None) -> list[Message]:
        """Un volcado individual por cada patch presente (sirve para bancos
        incompletos y para escribir patch a patch comprobando la respuesta)."""
        ext = 0x02 if (self.external if external is None else external) else 0x00
        out = []
        for i, s in enumerate(self.singles):
            if s:
                out.append(Message(channel, Function.ONE_DATA_DUMP, bytes([ext, i]) + s.to_bytes()))
        for i, m in enumerate(self.multis):
            if m:
                out.append(Message(channel, Function.ONE_DATA_DUMP, bytes([ext, 64 + i]) + m.to_bytes()))
        if self.drum:
            out.append(Message(channel, Function.ONE_DATA_DUMP, bytes([ext | 1, 0x20]) + self.drum.to_bytes()))
        for i, e in enumerate(self.effects):
            if e:
                out.append(Message(channel, Function.ONE_DATA_DUMP, bytes([ext | 1, i]) + e.to_bytes()))
        return out

    def patch_message(self, kind: str, index: int = 0, channel: int = 0,
                      external: bool | None = None) -> Message:
        """Volcado de un único patch en su posición (kind: single, multi, drum, effect)."""
        ext = 0x02 if (self.external if external is None else external) else 0x00
        if kind == "single":
            s1, s2, p = ext, index, self.singles[index]
        elif kind == "multi":
            s1, s2, p = ext, 64 + index, self.multis[index]
        elif kind == "drum":
            s1, s2, p = ext | 1, 0x20, self.drum
        elif kind == "effect":
            s1, s2, p = ext | 1, index, self.effects[index]
        else:
            raise ValueError(kind)
        if p is None:
            raise K4Error(_("esa posición está vacía"))
        return Message(channel, Function.ONE_DATA_DUMP, bytes([s1, s2]) + p.to_bytes())

    def merge(self, other: "Bank") -> None:
        """Copia en este banco los patches presentes en `other` (mismas posiciones)."""
        for i, s in enumerate(other.singles):
            if s is not None:
                self.singles[i] = s
        for i, m in enumerate(other.multis):
            if m is not None:
                self.multis[i] = m
        for i, e in enumerate(other.effects):
            if e is not None:
                self.effects[i] = e
        if other.drum is not None:
            self.drum = other.drum

    def to_file_messages(self, channel: int = 0, external: bool | None = None) -> list[Message]:
        """Mensajes para guardar en archivo: un volcado completo si el banco está
        completo; si no, un volcado de bloque por cada grupo completo (64 Singles,
        64 Multis, 32 efectos) y volcados sueltos para el resto."""
        if self.is_complete:
            return [self.to_all_dump(channel, external)]
        ext = 0x02 if (self.external if external is None else external) else 0x00
        out = []
        groups = ((self.singles, ext, 0x00), (self.multis, ext, 0x40), (self.effects, ext | 1, 0x00))
        for patches, s1, s2 in groups:
            if patches and None not in patches:
                body = bytes([s1, s2]) + b"".join(p.to_bytes() for p in patches)
                out.append(Message(channel, Function.BLOCK_DATA_DUMP, body))
            else:
                base = 0x40 if s2 == 0x40 else 0
                out += [Message(channel, Function.ONE_DATA_DUMP, bytes([s1, base + i]) + p.to_bytes())
                        for i, p in enumerate(patches) if p is not None]
        if self.drum:
            out.append(Message(channel, Function.ONE_DATA_DUMP, bytes([ext | 1, 0x20]) + self.drum.to_bytes()))
        return out

    def save(self, path, channel: int = 0) -> None:
        """Guarda el banco en .syx o, si la extensión es .mid, en un archivo MIDI estándar."""
        write_patch_file(path, self.to_file_messages(channel))

    # ------------------------------------------------------------ dependencias

    def single_users(self) -> dict[int, list[tuple[int, int]]]:
        """Single -> [(multi, sección)] que lo usan (secciones no silenciadas)."""
        users = defaultdict(list)
        for mi, m in enumerate(self.multis):
            if m:
                for si, sec in enumerate(m.sections):
                    if not sec.muted:
                        users[sec.single].append((mi, si))
        return dict(users)

    def effect_users(self) -> dict[int, dict[str, list[int]]]:
        """Efecto -> {'singles': [...], 'multis': [...]} que lo usan."""
        users: dict[int, dict[str, list[int]]] = defaultdict(lambda: {"singles": [], "multis": []})
        for i, s in enumerate(self.singles):
            if s:
                users[s.effect]["singles"].append(i)
        for i, m in enumerate(self.multis):
            if m:
                users[m.effect]["multis"].append(i)
        return dict(users)

    def unused_singles(self) -> list[int]:
        used = self.single_users()
        return [i for i in range(64) if i not in used]

    def unused_effects(self) -> list[int]:
        used = self.effect_users()
        return [i for i in range(32) if i not in used]

    # ------------------------------------------------------------ reordenación

    def swap_singles(self, a: int, b: int, fix_refs: bool = True) -> None:
        """Intercambia dos Singles y actualiza las secciones de los Multis."""
        self.singles[a], self.singles[b] = self.singles[b], self.singles[a]
        if fix_refs:
            self._remap_singles({a: b, b: a})

    def move_single(self, src: int, dst: int, fix_refs: bool = True) -> None:
        """Mueve un Single desplazando los intermedios (como arrastrar en una lista)."""
        order = list(range(64))
        order.insert(dst, order.pop(src))          # order[nueva] = vieja
        self.singles = [self.singles[i] for i in order]
        if fix_refs:
            self._remap_singles({old: new for new, old in enumerate(order)})

    def _remap_singles(self, mapping: dict[int, int]) -> None:
        for m in self.multis:
            if m:
                for sec in m.sections:
                    sec.single = mapping.get(sec.single, sec.single)

    def swap_effects(self, a: int, b: int, fix_refs: bool = True) -> None:
        """Intercambia dos efectos y actualiza los Singles y Multis que los usan."""
        self.effects[a], self.effects[b] = self.effects[b], self.effects[a]
        if fix_refs:
            swap = {a: b, b: a}
            for p in (*self.singles, *self.multis):
                if p:
                    p.effect = swap.get(p.effect, p.effect)

    def import_single(self, single: Single, dst: int, effect: Effect | None = None,
                      effect_dst: int | None = None) -> None:
        """Copia un Single a la posición dst. Si se da su efecto, lo copia
        también (a effect_dst o al primer efecto sin uso) y enlaza el Single."""
        self.singles[dst] = single
        if effect is not None:
            if effect_dst is None:
                same = next((i for i, e in enumerate(self.effects)
                             if e and e.fingerprint() == effect.fingerprint()), None)
                if same is not None:
                    single.effect = same
                    return
                free = self.unused_effects()
                if not free:
                    raise K4Error(_("no hay ningún efecto libre en el banco de destino"))
                effect_dst = free[0]
            self.effects[effect_dst] = effect
            single.effect = effect_dst

    # ------------------------------------------------------------ consultas

    def find(self, text: str) -> list[tuple[str, int, str]]:
        """Busca por nombre en Singles y Multis: [(tipo, índice, nombre)]."""
        t = text.lower()
        out = [("single", i, s.name) for i, s in enumerate(self.singles) if s and t in s.name.lower()]
        out += [("multi", i, m.name) for i, m in enumerate(self.multis) if m and t in m.name.lower()]
        return out

    def duplicates(self) -> list[list[int]]:
        """Grupos de Singles idénticos salvo el nombre."""
        groups = defaultdict(list)
        for i, s in enumerate(self.singles):
            if s:
                groups[s.fingerprint()].append(i)
        return [g for g in groups.values() if len(g) > 1]

    def validate(self) -> list[str]:
        """Problemas detectables: referencias a efectos o Singles inexistentes."""
        issues = []
        for i, s in enumerate(self.singles):
            if s and self.effects[s.effect] is None:
                issues.append(_("Single {pos} usa el efecto {effect}, que no está cargado", pos=index_name(i), effect=s.effect + 1))
        for i, m in enumerate(self.multis):
            if not m:
                continue
            for si, sec in enumerate(m.sections):
                if not sec.muted and self.singles[sec.single] is None:
                    issues.append(_("Multi {pos} sección {section} usa el Single {single}, que no está cargado",
                                    pos=index_name(i), section=si + 1, single=index_name(sec.single)))
        return issues


def load_collection(folder) -> list[Bank]:
    """Carga todos los .syx de una carpeta (recursivo). Ignora los que no son del K4."""
    banks = []
    files = (p for p in Path(folder).rglob("*") if p.suffix.lower() == ".syx")
    for p in sorted(files):
        try:
            banks.append(Bank.from_file(p))
        except (K4Error, ValueError, IndexError):
            continue
    return banks
