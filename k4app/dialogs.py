"""Diálogos: conexión MIDI, descarga desde el K4 y envío al K4."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from k4lib.sysex import Location
from k4lib.i18n import N_, _

from . import theme as T

KIND_LABELS = {"single": "Single", "multi": "Multi", "effect": N_("Efecto"), "drum": "Drum"}


class Dialog(tk.Toplevel):
    """Diálogo modal; `result` queda a None si se cancela."""

    title_text = ""
    ok_text = N_("Aceptar")

    def __init__(self, master, **kw):
        super().__init__(master)
        self.withdraw()
        self.title(_(self.title_text))
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.transient(master)
        self.result = None
        self.body = ttk.Frame(self, padding=(20, 16, 20, 8))
        self.body.pack(fill="both", expand=True)
        self.build(self.body, **kw)
        self.error = ttk.Label(self, text="", foreground=T.WARN, padding=(20, 0))
        self.error.pack(fill="x")
        bar = ttk.Frame(self, padding=(20, 8, 20, 16))
        bar.pack(fill="x")
        ttk.Button(bar, text=_("Cancelar"), command=self.cancel).pack(side="right")
        self.ok_button = ttk.Button(bar, text=_(self.ok_text), style="Accent.TButton", command=self.ok)
        self.ok_button.pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + max(40, (master.winfo_height() - self.winfo_reqheight()) // 3)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.grab_set()
        self.focus_set()

    def build(self, body, **kw):  # pragma: no cover - abstracto
        raise NotImplementedError

    def validate(self):
        """Devuelve el resultado o lanza ValueError con un mensaje para el usuario."""
        raise NotImplementedError

    def ok(self):
        try:
            self.result = self.validate()
        except ValueError as e:
            self.error.configure(text=str(e))
            return
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

    def run(self):
        self.wait_window()
        # Liberar aquí (hilo principal) las variables Tk del diálogo: si el
        # recolector las encontrara desde el hilo MIDI, Tk protestaría.
        import gc
        gc.collect()
        return self.result


def _radio_group(parent, var, options, **pack):
    for value, text in options:
        ttk.Radiobutton(parent, text=text, value=value, variable=var).pack(anchor="w", pady=1, **pack)


# ------------------------------------------------------------------ conexión

class ConnectDialog(Dialog):
    title_text = N_("Conectar con el K4")
    ok_text = N_("Conectar")

    def build(self, body, channel: int = 1, last: dict | None = None):
        last = last or {}
        self.ins, self.outs, problem = [], [], None
        try:
            from k4lib.midi import list_ports
            self.ins, self.outs = list_ports()
        except Exception as e:  # noqa: BLE001
            problem = str(e)
            if "rtmidi" in problem.lower() or "backend" in problem.lower() or "module" in problem.lower():
                problem = _("No se pueden abrir puertos MIDI: instala python-rtmidi (pip install python-rtmidi).")

        self.simulate = tk.BooleanVar(value=last.get("simulate", bool(problem) or not self.outs))
        self.in_var = tk.StringVar(value=last.get("in") if last.get("in") in self.ins else
                                   (self.ins[0] if self.ins else ""))
        self.out_var = tk.StringVar(value=last.get("out") if last.get("out") in self.outs else
                                    (self.outs[0] if self.outs else ""))
        self.channel = tk.IntVar(value=channel)

        grid = ttk.Frame(body)
        grid.pack(fill="x")
        ttk.Label(grid, text=_("Entrada MIDI (desde el K4)")).grid(row=0, column=0, sticky="w", pady=4)
        self.in_box = ttk.Combobox(grid, textvariable=self.in_var, values=self.ins, width=38, state="readonly")
        self.in_box.grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(grid, text=_("Salida MIDI (hacia el K4)")).grid(row=1, column=0, sticky="w", pady=4)
        self.out_box = ttk.Combobox(grid, textvariable=self.out_var, values=self.outs, width=38, state="readonly")
        self.out_box.grid(row=1, column=1, sticky="w", padx=(12, 0))
        ttk.Label(grid, text=_("Canal MIDI del K4")).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(grid, from_=1, to=16, textvariable=self.channel, width=5).grid(
            row=2, column=1, sticky="w", padx=(12, 0))

        ttk.Separator(body).pack(fill="x", pady=12)
        ttk.Checkbutton(body, text=_("Usar el simulador (probar sin el K4 conectado)"),
                        variable=self.simulate, command=self._toggle).pack(anchor="w")
        note = _("En el K4: SYSTEM → recepción de SysEx activada y el mismo canal que aquí.")
        ttk.Label(body, text=note, foreground=T.MUTED, wraplength=460).pack(anchor="w", pady=(10, 0))
        if problem:
            ttk.Label(body, text=problem, foreground=T.WARN, wraplength=460).pack(anchor="w", pady=(8, 0))
        elif not self.outs:
            ttk.Label(body, text=_("No se ha encontrado ningún puerto MIDI."), foreground=T.WARN).pack(
                anchor="w", pady=(8, 0))
        self._toggle()

    def _toggle(self):
        state = "disabled" if self.simulate.get() else "readonly"
        self.in_box.configure(state=state)
        self.out_box.configure(state=state)

    def validate(self):
        try:
            ch = int(self.channel.get())
        except (tk.TclError, ValueError):
            raise ValueError(_("El canal debe ser un número de 1 a 16")) from None
        if not 1 <= ch <= 16:
            raise ValueError(_("El canal debe estar entre 1 y 16"))
        if not self.simulate.get() and (not self.in_var.get() or not self.out_var.get()):
            raise ValueError(_("Elige un puerto de entrada y uno de salida"))
        return {"simulate": self.simulate.get(), "in": self.in_var.get(),
                "out": self.out_var.get(), "channel": ch}


# ------------------------------------------------------------------ descarga

class DownloadDialog(Dialog):
    title_text = N_("Descargar del K4")
    ok_text = N_("Descargar")

    def build(self, body, has_bank: bool = False, external: bool = False):
        self.what = tk.StringVar(value="all")
        self.memory = tk.StringVar(value="ext" if external else "int")
        self.mode = tk.StringVar(value="merge" if has_bank else "replace")
        self.kind = tk.StringVar(value="Single")
        self.pos = tk.StringVar(value="A-1")

        lf = ttk.LabelFrame(body, text=_("Qué descargar"), padding=(12, 6))
        lf.pack(fill="x")
        _radio_group(lf, self.what, [("all", _("Banco completo (Singles, Multis, Drum y efectos)")),
                                     ("singles", _("Solo los 64 Singles")), ("multis", _("Solo los 64 Multis")),
                                     ("effects", _("Solo los 32 efectos")), ("one", _("Un solo patch:"))])
        row = ttk.Frame(lf)
        row.pack(anchor="w", padx=(22, 0), pady=(2, 4))
        ttk.Combobox(row, textvariable=self.kind, values=[_(v) for v in KIND_LABELS.values()], width=8,
                     state="readonly").pack(side="left")
        ttk.Label(row, text="  " + _("posición / número")).pack(side="left")
        e = ttk.Entry(row, textvariable=self.pos, width=8)
        e.pack(side="left", padx=(6, 0))
        e.bind("<FocusIn>", lambda ev: self.what.set("one"))

        lf = ttk.LabelFrame(body, text=_("Memoria"), padding=(12, 6))
        lf.pack(fill="x", pady=(10, 0))
        _radio_group(lf, self.memory, [("int", _("Interna")), ("ext", _("Tarjeta externa"))], side="left",
                     padx=(0, 16))

        lf = ttk.LabelFrame(body, text=_("En el programa"), padding=(12, 6))
        lf.pack(fill="x", pady=(10, 0))
        _radio_group(lf, self.mode, [("replace", _("Sustituir el banco abierto")),
                                     ("merge", _("Combinar con el banco abierto (mismas posiciones)"))])
        if not has_bank:
            for w in lf.winfo_children():
                w.state(["disabled"])

    def validate(self):
        kind = {_(v): k for k, v in KIND_LABELS.items()}[self.kind.get()]
        external = self.memory.get() == "ext"
        index = 0
        if self.what.get() == "one" and kind != "drum":
            text = self.pos.get().strip()
            if kind == "effect":
                if not text.isdigit() or not 1 <= int(text) <= 32:
                    raise ValueError(_("Los efectos se indican con un número de 1 a 32"))
                index = int(text) - 1
            else:
                loc = Location.parse(text)          # ValueError con mensaje propio
                index = loc.index
        return {"what": self.what.get(), "kind": kind, "index": index,
                "external": external, "mode": self.mode.get()}


# ------------------------------------------------------------------ envío

class SendDialog(Dialog):
    title_text = N_("Enviar al K4")
    ok_text = N_("Continuar…")

    def build(self, body, selection: tuple[str, int, str] | None = None,
              bank_complete: bool = True, external: bool = False):
        """selection: (kind, index, descripción) del patch seleccionado, si lo hay."""
        self.selection = selection
        self.what = tk.StringVar(value="same" if selection else "bank")
        self.memory = tk.StringVar(value="ext" if external else "int")
        self.target = tk.StringVar(value="")

        lf = ttk.LabelFrame(body, text=_("Qué enviar"), padding=(12, 6))
        lf.pack(fill="x")
        options = []
        if selection:
            kind, index, desc = selection
            options.append(("same", _("{what} → a su misma posición", what=desc)))
            if kind != "drum":
                options.append(("other", _("{what} → a otra posición:", what=desc)))
            if kind == "single":
                options.append(("buffer", _("{what} → a la memoria de edición (para oírlo; no se guarda)", what=desc)))
        options.append(("bank", _("Banco completo, patch a patch con verificación")
                        + ("" if bank_complete else " " + _("(solo los patches presentes)"))))
        for value, text in options:
            ttk.Radiobutton(lf, text=text, value=value, variable=self.what).pack(anchor="w", pady=1)
            if value == "other":
                row = ttk.Frame(lf)
                row.pack(anchor="w", padx=(22, 0), pady=(0, 4))
                e = ttk.Entry(row, textvariable=self.target, width=8)
                e.pack(side="left")
                e.bind("<FocusIn>", lambda ev: self.what.set("other"))
                hint = _("número 1–32") if selection[0] == "effect" else _("p. ej. D-16")
                ttk.Label(row, text=f"  ({hint})", foreground=T.MUTED).pack(side="left")

        lf = ttk.LabelFrame(body, text=_("Memoria de destino"), padding=(12, 6))
        lf.pack(fill="x", pady=(10, 0))
        _radio_group(lf, self.memory, [("int", _("Interna")), ("ext", _("Tarjeta externa"))], side="left",
                     padx=(0, 16))
        ttk.Label(body, text=_("Escribir en el K4 sustituye lo que haya en esas posiciones y no se puede deshacer. "
                               "Si quieres conservarlo, descarga antes el banco y guárdalo."),
                  foreground=T.MUTED, wraplength=470).pack(anchor="w", pady=(12, 0))

    def validate(self):
        what = self.what.get()
        res = {"what": what, "external": self.memory.get() == "ext"}
        if what == "other":
            kind = self.selection[0]
            text = self.target.get().strip()
            if not text:
                raise ValueError(_("Indica la posición de destino"))
            if kind == "effect":
                if not text.isdigit() or not 1 <= int(text) <= 32:
                    raise ValueError(_("Los efectos se indican con un número de 1 a 32"))
                res["target"] = int(text) - 1
            else:
                res["target"] = Location.parse(text).index
        return res
