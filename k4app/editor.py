"""Editor de parámetros (Single, Multi, efecto y Drum) dentro del panel de detalle.

Los controles se generan a partir de las tablas de k4lib.editing. Cada cambio
pasa por History (deshacer/rehacer) y avisa a la aplicación, que marca el banco
como modificado, actualiza las listas y, si está activado, lo envía al K4:

- Single y Multi: a la memoria de edición (se oye sin guardar nada).
- Efecto y Drum: no tienen memoria de edición; solo se pueden oír escribiéndolos
  en la memoria del K4, así que ese envío está desactivado por defecto y pide
  confirmación.
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from k4lib import constants as C
from k4lib.editing import TABLES, History, Param, get_value, set_name, set_value
from k4lib.i18n import _
from k4lib.sysex import index_name

from . import theme as T
from .widgets import EnvelopeView, KeyboardZones, section

# ancho (en caracteres) de cada tipo de control
_WIDTH = {"wave": 13, "choice": 10, "note": 5, "effect": 19, "single": 15, "int": 4, "signed": 4}
_CHOICE_WIDTH = {"submix": 4, "source_mode": 8, "poly_mode": 8, "wheel_assign": 8, "lfo_shape": 10,
                 "vib_shape": 10, "sec.submix": 2, "sec.vel_switch": 4, "sec.play_mode": 6,
                 "sec.single": 11, "sec.low_key": 4, "sec.high_key": 4, "type": 30, "note.submix": 4}
_SPIN_WIDTH = {"sec.channel": 3, "sec.level": 3, "sec.transpose": 3, "sec.tune": 3}


class _Control:
    """Un control enlazado a un parámetro y a una de sus copias (fuente, sección...)."""

    def __init__(self, editor: "PatchEditor", parent, param: Param, index: int):
        self.editor, self.param, self.index = editor, param, index
        p = param
        if p.kind == "bool":
            self.var = tk.IntVar()
            self.widget = ttk.Checkbutton(parent, variable=self.var, style="Panel.TCheckbutton",
                                          command=self._commit)
        elif p.kind in ("choice", "wave", "note", "effect", "single"):
            self.var = tk.StringVar()
            width = _CHOICE_WIDTH.get(p.key, _WIDTH[p.kind])
            self.widget = ttk.Combobox(parent, textvariable=self.var, values=self._options(), width=width,
                                       state="readonly", height=20)
            self.widget.bind("<<ComboboxSelected>>", lambda e: self._commit())
        else:
            self.var = tk.StringVar()
            self.widget = ttk.Spinbox(parent, textvariable=self.var, from_=p.lo + p.offset, to=p.hi + p.offset,
                                      increment=1, width=_SPIN_WIDTH.get(p.key, _WIDTH[p.kind]),
                                      command=self._commit)
            self.var.trace_add("write", lambda *a: self._typed())
            self.widget.bind("<FocusOut>", lambda e: self.refresh())
            self.widget.bind("<Return>", lambda e: (self._commit(), self.refresh()))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.widget.bind(seq, editor.forward_wheel)        # la rueda desplaza el panel, no cambia el valor

    def _options(self) -> list[str]:
        bank = self.editor.app.bank
        if self.param.kind == "effect":
            fx = bank.effects
            return [f"{n + 1} · {fx[n].type_name if fx[n] else '?'}" for n in range(32)]
        if self.param.kind == "single":
            return [f"{index_name(n)} · {s.name.strip() if s else '—'}" for n, s in enumerate(bank.singles)]
        return self.param.options()

    def _text(self, value: int) -> str:
        p = self.param
        if p.kind in ("effect", "single"):
            return self._options()[value]
        if p.kind == "signed":
            return str(value)
        return p.display(value) if p.kind in ("choice", "wave", "note") else str(value + p.offset)

    def _parse(self) -> int:
        p = self.param
        if p.kind == "bool":
            return int(self.var.get())
        if p.kind in ("effect", "single"):
            return self._options().index(self.var.get())
        return p.parse(self.var.get())

    def _typed(self):
        """Mientras se escribe en un Spinbox: aplica el valor en cuanto es válido."""
        if not self.editor.loading:
            self._commit(quiet=True)

    def _commit(self, quiet: bool = False):
        if self.editor.loading:
            return
        try:
            value = self._parse()
        except ValueError as e:
            if not quiet:
                self.editor.app.status(str(e), warn=True)
            return
        self.editor.change(self.param, self.index, value)

    def refresh(self):
        value = get_value(self.editor.patch, self.param, self.index)
        loading, self.editor.loading = self.editor.loading, True
        try:
            if self.param.kind == "bool":
                self.var.set(value)
            else:
                if self.param.kind in ("effect", "single"):
                    self.widget.configure(values=self._options())
                self.var.set(self._text(value))
        finally:
            self.editor.loading = loading


class PatchEditor:
    """Construye el editor en `panel.inner`.

    kind: "single", "multi", "effect" o "drum"; index: posición del patch (en el
    Drum, la nota que se está viendo, 0..60)."""

    def __init__(self, panel, app, kind: str, index: int, history: History):
        self.panel, self.app, self.kind, self.index, self.history = panel, app, kind, index, history
        self.patch = history.patch
        self.params, self.layout = TABLES[kind]
        self.controls: list[_Control] = []
        self.loading = False
        self.column_labels: list[tuple[ttk.Label, str, int]] = []
        self.param_labels: dict[str, ttk.Label] = {}
        self.envelopes = self.zones = None
        self.name_var = None
        self._build()
        self.refresh()

    # el editor de Singles se llamaba así; se mantiene el nombre
    @property
    def single(self):
        return self.patch

    # ---------------------------------------------------------------- construcción

    def _title_text(self) -> str:
        p = self.patch
        if self.kind == "effect":
            return f"{p.type_name}"
        if self.kind == "drum":
            return f"Drum · {C.note_name(C.DRUM_FIRST_NOTE + self.index)}"
        return p.name.strip() or _("(sin nombre)")

    def _subtitle(self) -> str:
        if self.kind == "effect":
            return _("Efecto {n}", n=self.index + 1)
        if self.kind == "drum":
            return _("Nota MIDI {note} del kit de percusión", note=C.DRUM_FIRST_NOTE + self.index)
        return f"{'Single' if self.kind == 'single' else 'Multi'} {self.panel._loc(self.index)}"

    def _build(self):
        inner, app, kind = self.panel.inner, self.app, self.kind
        top = ttk.Frame(inner, style="Panel.TFrame")
        top.pack(fill="x")
        self.title = ttk.Label(top, text="", style="Title.TLabel")
        self.title.pack(side="left")
        ttk.Label(top, text=_("editando"), style="Badge.TLabel").pack(side="left", padx=(10, 0), pady=(6, 0))
        ttk.Label(inner, text=self._subtitle(), style="Muted.TLabel").pack(anchor="w")

        bar = ttk.Frame(inner, style="Panel.TFrame")
        bar.pack(fill="x", pady=(12, 0))
        ttk.Button(bar, text="✓  " + _("Terminar edición"), style="Accent.TButton",
                   command=app.stop_editing).pack(side="left", padx=(0, 8))
        self.play_btn = ttk.Button(bar, text="▶  " + _("Escuchar"), command=lambda: app.audition(kind, self.index))
        self.play_btn.pack(side="left", padx=(0, 8))
        write_text = _("Escribir Drum en el K4…") if kind == "drum" else _("Escribir en el K4…")
        self.write_btn = ttk.Button(bar, text=write_text,
                                    command=lambda: app.send((kind, 0 if kind == "drum" else self.index)))
        self.write_btn.pack(side="left")
        bar = ttk.Frame(inner, style="Panel.TFrame")
        bar.pack(fill="x", pady=(6, 0))
        self.undo_btn = ttk.Button(bar, text="↶  " + _("Deshacer"), command=self.undo)
        self.undo_btn.pack(side="left", padx=(0, 4))
        self.redo_btn = ttk.Button(bar, text="↷  " + _("Rehacer"), command=self.redo)
        self.redo_btn.pack(side="left", padx=(0, 8))
        self.revert_btn = ttk.Button(bar, text=_("Volver al original"), command=self.revert)
        self.revert_btn.pack(side="left", padx=(0, 8))

        live = ttk.Frame(inner, style="Panel.TFrame")
        live.pack(fill="x", pady=(8, 0))
        if kind in ("single", "multi"):
            text, var = _("Enviar los cambios al K4 mientras edito (sin guardarlos en su memoria)"), app.live_edit
        elif kind == "effect":
            text, var = _("Escribir cada cambio en el efecto {n} del K4 (sustituye el de su memoria)",
                          n=self.index + 1), app.live_write
        else:
            text, var = _("Escribir cada cambio en el Drum del K4 (sustituye el de su memoria)"), app.live_write
        self.live_check = ttk.Checkbutton(live, text=text, variable=var, style="Panel.TCheckbutton",
                                          command=app.live_toggled)
        self.live_check.pack(side="left")
        hint = {"multi": _("Las secciones suenan con los Singles guardados en el K4 en esas posiciones."),
                "effect": _("El efecto no tiene memoria de edición: para oír los cambios hay que escribirlo en el "
                            "K4. «Escuchar» toca un Single del banco que usa este efecto."),
                "drum": _("El Drum no tiene memoria de edición: para oír los cambios hay que escribirlo en el K4."),
                }.get(kind)
        if hint:
            ttk.Label(inner, text=hint, style="Muted.TLabel", wraplength=640, justify="left").pack(anchor="w",
                                                                                                pady=(4, 0))
        self.offline_label = ttk.Label(inner, text="", style="Muted.TLabel")
        self.offline_label.pack(anchor="w", pady=(4, 0))
        self.update_connection(app.k4 is not None)

        if kind in ("single", "multi"):
            g = section(inner, _("Nombre"))
            self.name_var = tk.StringVar()
            ttk.Entry(g, textvariable=self.name_var, width=14, font=self.app.fonts["mono"]).pack(anchor="w")
            self.name_var.trace_add("write", lambda *a: self._name_typed())
            ttk.Label(g, text=_("10 caracteres como máximo, solo ASCII."), style="Muted.TLabel").pack(anchor="w",
                                                                                                       pady=(2, 0))

        for title, keys, how in self.layout:
            params = [self.params[k] for k in keys]
            g = section(inner, _(title))
            if how == "pairs":
                self._grid_pairs(g, params)
            elif how == "columns":
                self._grid_columns(g, params)
            else:
                self._grid_rows(g, params)
            if kind == "single" and params[0].scope == "source":
                g = section(inner, _("Envolventes"))
                self.envelopes = EnvelopeView(g, self.patch)
                self.envelopes.pack(fill="x")
            if kind == "multi" and params[0].scope == "common":
                g = section(inner, _("Zonas de teclado"))
                self.zones = KeyboardZones(g, self.patch, self._single_names())
                self.zones.pack(fill="x")

    def _single_names(self) -> list[str]:
        return [s.name if s else "?" for s in self.app.bank.singles]

    def _indexes(self, scope: str) -> list[tuple[str, int]]:
        """(etiqueta, índice) de cada copia del ámbito que muestra este editor."""
        if scope in ("source", "amp"):
            return [(f"S{i + 1}", i) for i in range(4)]
        if scope == "filter":
            return [(f"F{i + 1}", i) for i in range(2)]
        if scope == "section":
            return [(str(i + 1), i) for i in range(8)]
        if scope == "submix":
            return [(C.SUBMIXES[i], i) for i in range(8)]
        if scope == "note":
            return [("", self.index)]
        if scope == "note_src":
            return [("S1", self.index * 2), ("S2", self.index * 2 + 1)]
        return [("", 0)]

    def _label(self, parent, p: Param, **grid):
        lab = ttk.Label(parent, text=_(p.label), style="Key.TLabel")
        lab.grid(**grid)
        self.param_labels[p.key] = lab
        return lab

    def _grid_pairs(self, parent, params: list[Param], columns: int = 2):
        f = ttk.Frame(parent, style="Panel.TFrame")
        f.pack(fill="x")
        if self.kind == "effect":
            columns = 1                                    # nombres de parámetros largos según el tipo
        for n, p in enumerate(params):
            r, c = divmod(n, columns)
            self._label(f, p, row=r, column=c * 2, sticky="w", padx=(0, 10), pady=2)
            ctl = _Control(self, f, p, self._indexes(p.scope)[0][1])
            ctl.widget.grid(row=r, column=c * 2 + 1, sticky="w", padx=(0, 30), pady=2)
            self.controls.append(ctl)

    def _color(self, prefix: str, i: int) -> str:
        return T.SERIES[i * 2 if prefix == "F" else i]

    def _grid_columns(self, parent, params: list[Param]):
        """Una fila por parámetro y una columna por copia (S1..S4, F1-F2)."""
        f = ttk.Frame(parent, style="Panel.TFrame")
        f.pack(fill="x")
        copies = self._indexes(params[0].scope)
        for col, (text, i) in enumerate(copies):
            lab = ttk.Label(f, text=text, style="Value.TLabel", font=self.app.fonts["bold"],
                            foreground=self._color(text[0], col))
            lab.grid(row=0, column=col + 1, sticky="w", padx=(0, 6), pady=(0, 4))
            self.column_labels.append((lab, text[0], col))
        for r, p in enumerate(params, start=1):
            self._label(f, p, row=r, column=0, sticky="w", padx=(0, 10), pady=1)
            for col, (_text, i) in enumerate(copies):
                ctl = _Control(self, f, p, i)
                ctl.widget.grid(row=r, column=col + 1, sticky="w", padx=(0, 6), pady=1)
                self.controls.append(ctl)

    def _grid_rows(self, parent, params: list[Param]):
        """Una fila por copia (sección, submix) y una columna por parámetro."""
        f = ttk.Frame(parent, style="Panel.TFrame")
        f.pack(fill="x")
        copies = self._indexes(params[0].scope)
        for c, p in enumerate(params, start=1):
            self._label(f, p, row=0, column=c, sticky="w", padx=(0, 3), pady=(0, 4))
        for r, (text, i) in enumerate(copies, start=1):
            color = T.SERIES[i % len(T.SERIES)] if params[0].scope == "section" else T.FG
            ttk.Label(f, text=text, style="Value.TLabel", font=self.app.fonts["bold"],
                      foreground=color).grid(row=r, column=0, sticky="w", padx=(0, 8), pady=1)
            for c, p in enumerate(params, start=1):
                ctl = _Control(self, f, p, i)
                ctl.widget.grid(row=r, column=c, sticky="w", padx=(0, 3), pady=1)
                self.controls.append(ctl)

    def forward_wheel(self, event):
        self.panel._wheel(event)
        return "break"

    # ---------------------------------------------------------------- cambios

    def change(self, param: Param, index: int, value: int):
        if get_value(self.patch, param, index) == value:
            return
        self.history.before_change(f"{param.key}/{index}", time.monotonic())
        set_value(self.patch, param, value, index)
        self._after_change(param.key, index)

    def _name_typed(self):
        if self.loading:
            return
        text = self.name_var.get()
        if len(text) > C.NAME_LENGTH:
            self.name_var.set(text[:C.NAME_LENGTH])      # vuelve a llamar a esta función
            return
        if text.ljust(C.NAME_LENGTH) == self.patch.name:
            return
        self.history.before_change("name", time.monotonic())
        set_name(self.patch, text)
        self._after_change("name", 0)

    def _after_change(self, key: str, index: int):
        self._update_extras()
        self._update_buttons()
        self.app.patch_edited(self.kind, self.index, key)

    def undo(self):
        if self.history.undo():
            self.refresh()
            self.app.patch_edited(self.kind, self.index, "undo")

    def redo(self):
        if self.history.redo():
            self.refresh()
            self.app.patch_edited(self.kind, self.index, "redo")

    def revert(self):
        if self.history.revert():
            self.refresh()
            self.app.patch_edited(self.kind, self.index, "revert")

    # ---------------------------------------------------------------- refresco

    def refresh(self):
        """Pone todos los controles con los valores del modelo."""
        self.loading = True
        try:
            if self.name_var is not None:
                self.name_var.set(self.patch.name.rstrip())
            for ctl in self.controls:
                ctl.refresh()
        finally:
            self.loading = False
        self._update_extras()
        self._update_buttons()

    def _update_extras(self):
        """Lo que depende de varios parámetros: título, columnas sin uso, envolventes,
        zonas de teclado y nombres de los parámetros del efecto."""
        self.title.configure(text=self._title_text())
        if self.kind == "single":
            s = self.patch
            for lab, prefix, i in self.column_labels:
                if prefix == "S":
                    used = i < s.source_count
                    text = f"S{i + 1}" + ("" if used else "  " + _("sin uso")) + \
                           ("" if not used or s.source_active(i) else "  " + _("silenciada"))
                else:
                    used = i == 0 or s.source_count == 4
                    text = f"F{i + 1}" + ("" if used else "  " + _("sin uso"))
                lab.configure(text=text, foreground=self._color(prefix, i) if used else T.MUTED)
            self.envelopes.redraw()
        elif self.kind == "multi":
            self.zones.names = self._single_names()
            self.zones.redraw()
        elif self.kind == "effect":
            for key, name in zip(("param1", "param2", "param3"), self.patch.param_names):
                self.param_labels[key].configure(text=name)

    def _update_buttons(self):
        h = self.history
        self.undo_btn.state(["!disabled"] if h.undo_stack else ["disabled"])
        self.redo_btn.state(["!disabled"] if h.redo_stack else ["disabled"])
        self.revert_btn.state(["!disabled"] if h.changed else ["disabled"])

    def update_connection(self, connected: bool):
        for w in (self.live_check, self.play_btn, self.write_btn):
            w.state(["!disabled"] if connected else ["disabled"])
        self.offline_label.configure(text="" if connected else
                                     _("Conecta el K4 para oír los cambios mientras editas."))

