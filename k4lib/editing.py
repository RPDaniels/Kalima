"""Tablas de parámetros editables de los patches (Single, Multi, efecto y Drum).

Cada parámetro describe dónde vive en el modelo (ámbito + atributo), su rango
en unidades del modelo, cómo se muestra (desplazamiento del panel, signo,
lista de opciones) y su nombre en Parameter Send, si lo tiene.

La interfaz genera los controles a partir de estas tablas y las pruebas
comprueban que cubren todos los campos con rangos que caben en los bits del
formato. Uso:

    p = SINGLE_PARAMS["dcf.cutoff"]
    get_value(single, p, 1)            # corte del filtro 2
    set_value(single, p, 60, 1)        # valida el rango
    p.display(60)                      # '60'

El índice elige la copia del parámetro dentro del patch: fuente o filtro de un
Single, sección de un Multi, submix de un efecto, nota del Drum (0..60) o fuente
de una nota del Drum (nota * 2 + fuente).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import constants as C
from .i18n import N_, _
from .patches import ARROW_LEFT, Drum, Effect, Multi, Single
from .sysex import index_name

# Copias de cada ámbito dentro de su patch
SCOPE_COUNT = {"common": 1, "source": 4, "amp": 4, "filter": 2, "section": 8, "submix": 8,
               "note": C.DRUM_NOTE_COUNT, "note_src": 2 * C.DRUM_NOTE_COUNT}


@dataclass(frozen=True)
class Param:
    key: str                         # identificador único, p. ej. "dca.attack"
    scope: str                       # una clave de SCOPE_COUNT
    attr: str                        # atributo en el objeto del ámbito
    label: str                       # texto marcado con N_ o término del K4 (sin traducir)
    lo: int                          # rango en unidades del modelo
    hi: int
    kind: str = "int"                # int, signed, choice, bool, wave, note, effect, single
    choices: tuple[str, ...] = ()
    offset: int = 0                  # valor del panel = valor del modelo + offset
    send: str | None = None          # nombre en k4lib.params.PARAMETERS

    @property
    def count(self) -> int:
        """Cuántas copias hay en su patch (4 fuentes, 8 secciones, 61 notas...)."""
        return SCOPE_COUNT[self.scope]

    def display(self, value: int) -> str:
        """Texto para el usuario (en unidades del panel)."""
        if self.kind == "bool":
            return _("sí") if value else _("no")
        if self.kind == "choice":
            return self.choices[value]
        if self.kind == "wave":
            return f"{value + 1} · {C.wave_name(value)}"
        if self.kind == "note":
            return C.note_name(value)
        if self.kind == "single":
            return index_name(value)
        if self.kind == "signed":
            return f"{value:+d}" if value else "0"
        return str(value + self.offset)

    def options(self) -> list[str]:
        """Todos los valores posibles como texto (para listas desplegables)."""
        return [self.display(v) for v in range(self.lo, self.hi + 1)]

    def parse(self, text: str) -> int:
        """Convierte texto del usuario (unidades del panel) en valor del modelo.
        Acepta también el texto de display() para listas y ondas."""
        text = text.strip()
        if self.kind in ("choice", "wave", "note", "bool", "single"):
            opts = self.options()
            if text in opts:
                return self.lo + opts.index(text)
            if self.kind == "wave":
                text = text.split("·")[0].strip()
            elif self.kind in ("note", "single"):
                low = [o.lower() for o in opts]
                if text.lower() in low:
                    return self.lo + low.index(text.lower())
        try:
            value = int(text.replace("+", "")) - (self.offset if self.kind != "wave" else 1)
        except ValueError:
            raise ValueError(_("«{text}» no es un valor válido", text=text)) from None
        if not self.lo <= value <= self.hi:
            raise ValueError(_("{name}: {value} fuera de {lo}..{hi}", name=_(self.label), value=text,
                               lo=self.display(self.lo), hi=self.display(self.hi)))
        return value


def _p(key, scope, attr, label, lo, hi, kind="int", choices=(), offset=0, send=None):
    return Param(key, scope, attr, label, lo, hi, kind, tuple(choices), offset, send)


_BI = dict(lo=-50, hi=50, kind="signed")

SINGLE_PARAM_LIST: list[Param] = [
    # ---------------------------------------------------------------- comunes
    _p("volume", "common", "volume", N_("Volumen"), 0, 100, send="volume"),
    _p("effect", "common", "effect", N_("Efecto"), 0, 31, "effect", offset=1, send="effect"),
    _p("submix", "common", "submix", "Submix", 0, 7, "choice", C.SUBMIXES, send="submix"),
    _p("source_mode", "common", "source_mode", N_("Modo de fuentes"), 0, 2, "choice", C.SOURCE_MODES,
       send="source_mode"),
    _p("poly_mode", "common", "poly_mode", N_("Polifonía"), 0, 3, "choice", C.POLY_MODES, send="poly_mode"),
    _p("am12", "common", "am12", "AM 1→2", 0, 1, "bool", send="am12"),
    _p("am34", "common", "am34", "AM 3→4", 0, 1, "bool", send="am34"),
    _p("bend_range", "common", "bend_range", "Pitch bend", 0, 12, send="bend_range"),
    _p("wheel_assign", "common", "wheel_assign", N_("Rueda: destino"), 0, 2, "choice", C.WHEEL_ASSIGNS,
       send="wheel_assign"),
    _p("wheel_depth", "common", "wheel_depth", N_("Rueda: profundidad"), **_BI, send="wheel_depth"),
    _p("prs_freq", "common", "prs_freq", N_("Presión → afinación"), **_BI, send="prs_freq"),
    # modulación
    _p("lfo_shape", "common", "lfo_shape", N_("LFO: forma"), 0, 3, "choice", C.LFO_SHAPES, send="lfo_shape"),
    _p("lfo_speed", "common", "lfo_speed", N_("LFO: velocidad"), 0, 100, send="lfo_speed"),
    _p("lfo_delay", "common", "lfo_delay", N_("LFO: retardo"), 0, 100, send="lfo_delay"),
    _p("lfo_depth", "common", "lfo_depth", N_("LFO: profundidad"), **_BI, send="lfo_depth"),
    _p("lfo_prs", "common", "lfo_prs", N_("Presión → LFO"), **_BI, send="lfo_prs"),
    _p("vib_shape", "common", "vib_shape", N_("Vibrato: forma"), 0, 3, "choice", C.LFO_SHAPES,
       send="vib_shape"),
    _p("vib_speed", "common", "vib_speed", N_("Vibrato: velocidad"), 0, 100, send="vib_speed"),
    _p("vib_depth", "common", "vib_depth", N_("Vibrato: profundidad"), **_BI, send="vib_depth"),
    _p("vib_prs", "common", "vib_prs", N_("Presión → vibrato"), **_BI, send="vib_prs"),
    _p("autobend_time", "common", "autobend_time", N_("Auto bend: tiempo"), 0, 100, send="autobend_time"),
    _p("autobend_depth", "common", "autobend_depth", N_("Auto bend: profundidad"), **_BI,
       send="autobend_depth"),
    _p("autobend_ks_time", "common", "autobend_ks_time", N_("Auto bend: KS → tiempo"), **_BI,
       send="autobend_ks_time"),
    _p("autobend_vel_depth", "common", "autobend_vel_depth", N_("Auto bend: vel → prof."), **_BI,
       send="autobend_vel_depth"),
    # ---------------------------------------------------------------- fuentes (×4)
    _p("src.active", "source", "active", N_("Activa"), 0, 1, "bool"),
    _p("src.wave", "source", "wave", N_("Onda"), 0, 255, "wave", send="src_wave"),
    _p("src.coarse", "source", "coarse", "Coarse", -24, 24, "signed", send="src_coarse"),
    _p("src.fine", "source", "fine", "Fine", **_BI, send="src_fine"),
    _p("src.key_track", "source", "key_track", N_("Sigue el teclado"), 0, 1, "bool", send="src_key_track"),
    _p("src.fixed_key", "source", "fixed_key", N_("Nota fija"), 0, 127, "note", send="src_fixed_key"),
    _p("src.delay", "source", "delay", N_("Retardo"), 0, 100, send="src_delay"),
    _p("src.vel_curve", "source", "vel_curve", N_("Curva vel."), 0, 7, "choice", C.VELOCITY_CURVES,
       send="src_vel_curve"),
    _p("src.ks_curve", "source", "ks_curve", N_("Curva KS"), 0, 7, "choice", C.KS_CURVES, send="src_ks_curve"),
    _p("src.prs_freq", "source", "prs_freq", N_("Presión → afinación"), 0, 1, "bool", send="src_prs_freq"),
    _p("src.vib_autobend", "source", "vib_autobend", "Vibrato / auto bend", 0, 1, "bool",
       send="src_vib_autobend"),
    # ---------------------------------------------------------------- DCA (×4)
    _p("dca.level", "amp", "level", N_("Nivel"), 0, 100, send="amp_level"),
    _p("dca.attack", "amp", "attack", "Attack", 0, 100, send="amp_attack"),
    _p("dca.decay", "amp", "decay", "Decay", 0, 100, send="amp_decay"),
    _p("dca.sustain", "amp", "sustain", "Sustain", 0, 100, send="amp_sustain"),
    _p("dca.release", "amp", "release", "Release", 0, 100, send="amp_release"),
    _p("dca.level_vel", "amp", "level_vel", N_("Nivel · velocidad"), **_BI, send="amp_level_vel"),
    _p("dca.level_prs", "amp", "level_prs", N_("Nivel · presión"), **_BI, send="amp_level_prs"),
    _p("dca.level_ks", "amp", "level_ks", N_("Nivel · KS"), **_BI, send="amp_level_ks"),
    _p("dca.time_vel_on", "amp", "time_vel_on", N_("Tiempo · vel. on"), **_BI, send="amp_time_vel_on"),
    _p("dca.time_vel_off", "amp", "time_vel_off", N_("Tiempo · vel. off"), **_BI, send="amp_time_vel_off"),
    _p("dca.time_ks", "amp", "time_ks", N_("Tiempo · KS"), **_BI, send="amp_time_ks"),
    # ---------------------------------------------------------------- DCF (×2)
    _p("dcf.cutoff", "filter", "cutoff", N_("Corte"), 0, 100, send="filter_cutoff"),
    _p("dcf.resonance", "filter", "resonance", N_("Resonancia"), 0, 7, send="filter_resonance"),
    _p("dcf.lfo", "filter", "lfo", "LFO", 0, 1, "bool", send="filter_lfo"),
    _p("dcf.cutoff_vel", "filter", "cutoff_vel", N_("Corte · velocidad"), **_BI, send="filter_cutoff_vel"),
    _p("dcf.cutoff_prs", "filter", "cutoff_prs", N_("Corte · presión"), **_BI, send="filter_cutoff_prs"),
    _p("dcf.cutoff_ks", "filter", "cutoff_ks", N_("Corte · KS"), **_BI, send="filter_cutoff_ks"),
    _p("dcf.env_depth", "filter", "env_depth", N_("Envolvente: profundidad"), **_BI, send="filter_env_depth"),
    _p("dcf.env_vel_depth", "filter", "env_vel_depth", N_("Envolvente · velocidad"), **_BI,
       send="filter_env_vel_depth"),
    _p("dcf.attack", "filter", "attack", "Attack", 0, 100, send="filter_attack"),
    _p("dcf.decay", "filter", "decay", "Decay", 0, 100, send="filter_decay"),
    _p("dcf.sustain", "filter", "sustain", "Sustain", **_BI, send="filter_sustain"),
    _p("dcf.release", "filter", "release", "Release", 0, 100, send="filter_release"),
    _p("dcf.time_vel_on", "filter", "time_vel_on", N_("Tiempo · vel. on"), **_BI, send="filter_time_vel_on"),
    _p("dcf.time_vel_off", "filter", "time_vel_off", N_("Tiempo · vel. off"), **_BI,
       send="filter_time_vel_off"),
    _p("dcf.time_ks", "filter", "time_ks", N_("Tiempo · KS"), **_BI, send="filter_time_ks"),
]

SINGLE_PARAMS: dict[str, Param] = {p.key: p for p in SINGLE_PARAM_LIST}

# Agrupación para la interfaz: (título, claves, disposición). Disposiciones:
#   "pairs"   pares nombre / control en dos columnas
#   "columns" una fila por parámetro y una columna por copia (S1..S4, F1-F2)
#   "rows"    una fila por copia (sección, submix) y una columna por parámetro
SINGLE_LAYOUT: list[tuple[str, list[str], str]] = [
    (N_("General"), ["volume", "effect", "submix", "source_mode", "poly_mode", "bend_range",
                     "wheel_assign", "wheel_depth", "prs_freq", "am12", "am34"], "pairs"),
    (N_("Modulación"), ["lfo_shape", "lfo_speed", "lfo_delay", "lfo_depth", "lfo_prs",
                        "vib_shape", "vib_speed", "vib_depth", "vib_prs",
                        "autobend_time", "autobend_depth", "autobend_ks_time", "autobend_vel_depth"], "pairs"),
    (N_("Fuentes"), [p.key for p in SINGLE_PARAM_LIST if p.scope == "source"], "columns"),
    (N_("Amplificadores (DCA)"), [p.key for p in SINGLE_PARAM_LIST if p.scope == "amp"], "columns"),
    (N_("Filtros (DCF)"), [p.key for p in SINGLE_PARAM_LIST if p.scope == "filter"], "columns"),
]

# ================================================================== MULTI

MULTI_PARAM_LIST: list[Param] = [
    _p("volume", "common", "volume", N_("Volumen"), 0, 100),
    _p("effect", "common", "effect", N_("Efecto"), 0, 31, "effect", offset=1),
    _p("sec.single", "section", "single", "Single", 0, 63, "single"),
    _p("sec.low_key", "section", "low_key", N_("Desde"), 0, 127, "note"),
    _p("sec.high_key", "section", "high_key", N_("Hasta"), 0, 127, "note"),
    _p("sec.channel", "section", "channel", N_("Canal"), 0, 15, offset=1),
    _p("sec.vel_switch", "section", "vel_switch", N_("Veloc."), 0, 2, "choice", C.VELOCITY_SWITCHES),
    _p("sec.play_mode", "section", "play_mode", N_("Modo"), 0, 2, "choice", C.MULTI_PLAY_MODES),
    _p("sec.level", "section", "level", N_("Nivel"), 0, 100),
    _p("sec.transpose", "section", "transpose", N_("Transp."), -24, 24, "signed"),
    _p("sec.tune", "section", "tune", N_("Afin."), -50, 50, "signed"),
    _p("sec.submix", "section", "submix", "Submix", 0, 7, "choice", C.SUBMIXES),
    _p("sec.muted", "section", "muted", "Mute", 0, 1, "bool"),          # término del panel del K4
]
MULTI_PARAMS: dict[str, Param] = {p.key: p for p in MULTI_PARAM_LIST}
MULTI_LAYOUT: list[tuple[str, list[str], str]] = [
    (N_("General"), ["volume", "effect"], "pairs"),
    (N_("Secciones"), [p.key for p in MULTI_PARAM_LIST if p.scope == "section"], "rows"),
]

# ================================================================== EFECTO

EFFECT_PARAM_LIST: list[Param] = [
    _p("type", "common", "type", N_("Tipo"), 0, 15, "choice", C.EFFECT_TYPES),
    # los nombres reales dependen del tipo (Effect.param_names)
    _p("param1", "common", "param1", N_("Parámetro 1"), -7, 7, "signed"),
    _p("param2", "common", "param2", N_("Parámetro 2"), -7, 7, "signed"),
    _p("param3", "common", "param3", N_("Parámetro 3"), 0, 31),
    _p("sub.pan", "submix", "pan", N_("Panorama"), -7, 7, "signed"),
    _p("sub.send1", "submix", "send1", N_("Envío 1"), 0, 100),
    _p("sub.send2", "submix", "send2", N_("Envío 2"), 0, 100),
]
EFFECT_PARAMS: dict[str, Param] = {p.key: p for p in EFFECT_PARAM_LIST}
EFFECT_LAYOUT: list[tuple[str, list[str], str]] = [
    (N_("Parámetros"), ["type", "param1", "param2", "param3"], "pairs"),
    ("Submixes", ["sub.pan", "sub.send1", "sub.send2"], "rows"),
]

# ================================================================== DRUM

DRUM_PARAM_LIST: list[Param] = [
    _p("channel", "common", "channel", N_("Canal"), 0, 15, offset=1),
    _p("volume", "common", "volume", N_("Volumen"), 0, 100),
    _p("vel_depth", "common", "vel_depth", N_("Velocidad → nivel"), -50, 50, "signed"),
    _p("note.submix", "note", "submix", "Submix", 0, 7, "choice", C.SUBMIXES),
    _p("dsrc.wave", "note_src", "wave", N_("Onda"), 0, 255, "wave"),
    _p("dsrc.decay", "note_src", "decay", "Decay", 1, 100),
    _p("dsrc.tune", "note_src", "tune", N_("Afinación"), -50, 50, "signed"),
    _p("dsrc.level", "note_src", "level", N_("Nivel"), 0, 100),
]
DRUM_PARAMS: dict[str, Param] = {p.key: p for p in DRUM_PARAM_LIST}
DRUM_LAYOUT: list[tuple[str, list[str], str]] = [
    (N_("Kit (común)"), ["channel", "volume", "vel_depth"], "pairs"),
    (N_("Esta nota"), ["note.submix"], "pairs"),
    (N_("Fuentes de esta nota"), ["dsrc.wave", "dsrc.decay", "dsrc.tune", "dsrc.level"], "columns"),
]

# tipo de patch -> (parámetros, disposición)
TABLES = {
    "single": (SINGLE_PARAMS, SINGLE_LAYOUT),
    "multi": (MULTI_PARAMS, MULTI_LAYOUT),
    "effect": (EFFECT_PARAMS, EFFECT_LAYOUT),
    "drum": (DRUM_PARAMS, DRUM_LAYOUT),
}


_LISTS = {"source": "sources", "amp": "amps", "filter": "filters", "section": "sections",
          "submix": "submixes", "note": "notes"}


def _target(patch, scope: str, index: int):
    if scope == "common":
        return patch
    if scope == "note_src":
        note = patch.notes[index // 2]
        return note.s2 if index % 2 else note.s1
    return getattr(patch, _LISTS[scope])[index]


def get_value(patch, param: Param, index: int = 0) -> int:
    """Valor (unidades del modelo) del parámetro; index = fuente, filtro, sección..."""
    if param.key == "src.active":
        return int(patch.source_active(index))
    return int(getattr(_target(patch, param.scope, index), param.attr))


def set_value(patch, param: Param, value: int, index: int = 0) -> None:
    """Cambia el parámetro, comprobando el rango."""
    value = int(value)
    if not param.lo <= value <= param.hi:
        raise ValueError(_("{name}: {value} fuera de {lo}..{hi}", name=_(param.label), value=value,
                           lo=param.lo, hi=param.hi))
    if param.key == "src.active":
        bit = 1 << index
        patch.source_mute_bits = (patch.source_mute_bits & ~bit) | (0 if value else bit)
        return
    obj = _target(patch, param.scope, index)
    current = getattr(obj, param.attr)
    setattr(obj, param.attr, bool(value) if isinstance(current, bool) else value)


def set_name(patch: Single | Multi, name: str) -> str:
    """Pone el nombre (10 caracteres ASCII imprimibles; el resto se sustituye por
    espacios) y lo devuelve tal como queda."""
    clean = "".join(c if 32 <= ord(c) < 127 or c == ARROW_LEFT else " " for c in name)[:C.NAME_LENGTH]
    patch.name = clean.ljust(C.NAME_LENGTH)
    return patch.name


def copy_patch(patch):
    """Copia independiente (por bytes, así conserva también los bits reservados)."""
    return type(patch).from_bytes(patch.to_bytes())


copy_single = copy_patch


def restore(patch, data: bytes) -> None:
    """Restaura en el mismo objeto el estado guardado con patch.to_bytes()."""
    other = type(patch).from_bytes(data)
    for k, v in vars(other).items():
        setattr(patch, k, v)


class History:
    """Deshacer / rehacer por instantáneas (bytes de cualquier patch).

    Los cambios seguidos del mismo parámetro (por ejemplo, mantener pulsada la
    flecha de un control) se agrupan en un solo paso si llegan dentro de
    `merge_seconds`."""

    def __init__(self, patch, merge_seconds: float = 1.0, limit: int = 200):
        self.patch = self.single = patch      # .single: nombre anterior, se mantiene
        self.original = patch.to_bytes()
        self.merge_seconds = merge_seconds
        self.limit = limit
        self.undo_stack: list[bytes] = []
        self.redo_stack: list[bytes] = []
        self._last: tuple[str, float] | None = None

    def before_change(self, key: str, now: float) -> None:
        """Llamar antes de modificar el patch; key identifica el parámetro."""
        if self._last and self._last[0] == key and now - self._last[1] < self.merge_seconds and self.undo_stack:
            self._last = (key, now)
            return
        self.undo_stack.append(self.single.to_bytes())
        del self.undo_stack[:-self.limit]
        self.redo_stack.clear()
        self._last = (key, now)

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append(self.single.to_bytes())
        restore(self.single, self.undo_stack.pop())
        self._last = None
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append(self.single.to_bytes())
        restore(self.single, self.redo_stack.pop())
        self._last = None
        return True

    def revert(self) -> bool:
        """Vuelve al estado del principio de la edición (se puede deshacer)."""
        if self.single.to_bytes() == self.original:
            return False
        self.undo_stack.append(self.single.to_bytes())
        self.redo_stack.clear()
        restore(self.single, self.original)
        self._last = None
        return True

    @property
    def changed(self) -> bool:
        return self.single.to_bytes() != self.original
