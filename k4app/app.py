"""Ventana principal de Kalima."""
from __future__ import annotations

import os
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from k4lib import Bank, K4Error, Location
from k4lib import constants as C
from k4lib import i18n
from k4lib.editing import History, copy_patch
from k4lib.i18n import N_, _, _n
from k4lib.sysex import Function, index_name, write_patch_file

from . import theme as T
from .details import DetailPanel
from . import settings
from .dialogs import KIND_LABELS, ConnectDialog, DownloadDialog, SendDialog
from .worker import Worker

APP_NAME = "Kalima"
DEMO_BANK = Path(__file__).parent / "data" / "A401.SYX"
FILETYPES_OPEN = [(N_("Volcados del K4"), "*.syx *.SYX *.mid *.MID *.midi"), ("SysEx", "*.syx *.SYX"),
                  (N_("MIDI estándar"), "*.mid *.MID *.midi"), (N_("Todos los archivos"), "*.*")]
FILETYPES_SAVE = [("SysEx", "*.syx"), (N_("MIDI estándar"), "*.mid")]


def _writable(path: Path) -> bool:
    """¿Se puede sobrescribir `path`? El banco de ejemplo nunca (va dentro de la
    aplicación; en el .exe, en una carpeta temporal que se borra al salir)."""
    try:
        if path.resolve() == DEMO_BANK.resolve():
            return False
    except OSError:
        return False
    if path.exists():
        return os.access(path, os.W_OK)
    return os.access(path.parent, os.W_OK)


def _filetypes(types):
    return [(_(label), pattern) for label, pattern in types]

# pestaña -> (columnas (id, título, ancho, estirable))
TABS = {
    "single": ("Singles", [("pos", N_("Pos."), 52, False), ("name", N_("Nombre"), 110, False),
                           ("mode", N_("Modo"), 108, False), ("fx", N_("Ef."), 38, False),
                           ("waves", N_("Ondas activas"), 210, True), ("used", "Multis", 52, False)]),
    "multi": ("Multis", [("pos", N_("Pos."), 52, False), ("name", N_("Nombre"), 110, False),
                         ("fx", N_("Ef."), 38, False), ("secs", N_("Secc."), 48, False),
                         ("singles", N_("Singles que usa"), 260, True)]),
    "effect": (N_("Efectos"), [("pos", N_("Nº"), 40, False), ("type", N_("Tipo"), 210, False),
                               ("params", N_("Parámetros"), 190, True), ("used", N_("Uso"), 90, False)]),
    "drum": ("Drum", [("pos", N_("Nota"), 56, False), ("s1", N_("Fuente 1"), 170, True),
                      ("s2", N_("Fuente 2"), 170, True), ("mix", "Submix", 56, False)]),
}


class K4App(tk.Tk):
    def __init__(self, path: str | None = None):
        super().__init__()
        self.withdraw()
        self.title(APP_NAME)
        self.geometry("1360x840")
        self.minsize(1040, 640)
        self.fonts = T.setup(self)
        self._set_icon()

        self.bank: Bank | None = None
        self.path: Path | None = None
        self.modified = False
        self.k4 = None                       # K4Midi o FakeK4 cuando hay conexión
        self._drum_same = {}                 # ¿Drum del K4 == Drum del archivo? (caché)
        self.channel = 1
        self.last_connection: dict = {}
        self.selected: tuple[str, int] | None = None
        self.worker = Worker(self)
        self.confirm = messagebox.askyesno   # se puede sustituir (tests)
        self.settings = settings.load()
        self.test_notes = tk.StringVar(value=self.settings.get("test_notes", "chord"))
        self.test_notes.trace_add("write", lambda *a: self._save_setting("test_notes", self.test_notes.get()))
        self.language = tk.StringVar(value=i18n.get_language())
        # edición de Singles
        self.live_edit = tk.BooleanVar(value=self.settings.get("live_edit", True))
        self.live_write = tk.BooleanVar(value=False)   # efecto / Drum: escribir en el K4 al editar
        self.editing: tuple[str, int | None] | None = None   # (tipo, posición) en edición
        self.edit_history: History | None = None
        self._live_after = None              # envío en directo pendiente (after id)
        self._live_slot = None               # (conexión, tarjeta, índice) ya seleccionado en el K4

        self._build_menu()
        self._build_toolbar()
        self._build_status()        # antes que el cuerpo: si no, el cuerpo expansible la tapa
        self._build_body()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._update_connection_ui()
        self._refresh()
        self.deiconify()
        if path:
            self.after(50, lambda: self.load_path(path))

    # ================================================================ construcción

    def _set_icon(self):
        data = Path(__file__).parent / "data"
        try:
            if sys.platform == "win32" and (data / "k4.ico").exists():
                self.iconbitmap(default=str(data / "k4.ico"))
            elif (data / "k4.png").exists():
                self._icon = tk.PhotoImage(file=str(data / "k4.png")).subsample(8)
                self.iconphoto(True, self._icon)
        except tk.TclError:
            pass

    def _build_menu(self):
        mb = tk.Menu(self)
        m = tk.Menu(mb, tearoff=False)
        m.add_command(label=_("Nuevo banco vacío"), command=self.new_bank)
        m.add_command(label=_("Abrir…"), accelerator="Ctrl+O", command=self.open_file)
        m.add_command(label=_("Abrir banco de fábrica de ejemplo (A401)"), command=lambda: self.load_path(DEMO_BANK))
        m.add_separator()
        m.add_command(label=_("Guardar"), accelerator="Ctrl+S", command=self.save)
        m.add_command(label=_("Guardar como…"), accelerator=_("Ctrl+Mayús+S"), command=self.save_as)
        m.add_command(label=_("Exportar patch seleccionado…"), command=self.export_selected)
        m.add_separator()
        m.add_command(label=_("Salir"), command=self.on_close)
        mb.add_cascade(label=_("Archivo"), menu=m)

        m = tk.Menu(mb, tearoff=False)
        m.add_command(label=_("Conectar…"), command=self.connect)
        self._k4_items = []                   # entradas que requieren conexión (por posición)
        m.add_command(label=_("Desconectar"), command=self.disconnect)
        self._k4_items.append(m.index("end"))
        m.add_separator()
        m.add_command(label=_("Descargar del K4…"), accelerator="F5", command=self.download)
        self._k4_items.append(m.index("end"))
        m.add_command(label=_("Enviar al K4…"), accelerator="F6", command=self.send)
        self._k4_items.append(m.index("end"))
        m.add_command(label=_("Escuchar seleccionado"), accelerator=_("Intro"), command=self.audition_selected)
        self._k4_items.append(m.index("end"))
        notes_menu = tk.Menu(m, tearoff=False)
        from k4lib.midi import TEST_NOTE_MODES
        for value, label in TEST_NOTE_MODES.items():
            notes_menu.add_radiobutton(label=_(label), value=value, variable=self.test_notes)
        m.add_cascade(label=_("Nota de prueba al escuchar"), menu=notes_menu)
        mb.add_cascade(label="K4", menu=m)
        self.k4_menu = m

        m = tk.Menu(mb, tearoff=False)
        for code, native in i18n.LANGUAGES.items():
            m.add_radiobutton(label=native, value=code, variable=self.language,
                              command=lambda c=code: self.change_language(c))
        title = _("Idioma")
        mb.add_cascade(label=title if i18n.get_language() == "en" else f"{title} / Language", menu=m)

        m = tk.Menu(mb, tearoff=False)
        m.add_command(label=_("Acerca de Kalima"), command=self.about)
        mb.add_cascade(label=_("Ayuda"), menu=m)
        self.configure(menu=mb)

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(10, 8, 10, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text=_("Abrir…"), style="Tool.TButton", command=self.open_file).pack(side="left")
        self.save_btn = ttk.Button(bar, text=_("Guardar"), style="Tool.TButton", command=self.save)
        self.save_btn.pack(side="left", padx=(6, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
        self.connect_btn = ttk.Button(bar, text=_("Conectar…"), style="Tool.TButton", command=self.toggle_connection)
        self.connect_btn.pack(side="left")
        self.download_btn = ttk.Button(bar, text="⬇  " + _("Descargar del K4"), style="Tool.TButton",
                                       command=self.download)
        self.download_btn.pack(side="left", padx=(6, 0))
        self.send_btn = ttk.Button(bar, text="⬆  " + _("Enviar al K4"), style="Tool.TButton", command=self.send)
        self.send_btn.pack(side="left", padx=(6, 0))

        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self._fill_lists())
        entry = ttk.Entry(bar, textvariable=self.search, width=24)
        entry.pack(side="right")
        ttk.Label(bar, text=_("Filtrar por nombre")).pack(side="right", padx=(0, 8))
        self.search_entry = entry

    def _build_body(self):
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=10)
        left = ttk.Frame(pw)
        self.nb = ttk.Notebook(left)
        self.nb.pack(fill="both", expand=True)
        self.trees: dict[str, ttk.Treeview] = {}
        self.tab_kinds: list[str] = []
        for kind, (title, cols) in TABS.items():
            frame = ttk.Frame(self.nb, style="Panel.TFrame")
            tv = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", selectmode="browse")
            for cid, text, width, stretch in cols:
                tv.heading(cid, text=_(text), anchor="w")
                tv.column(cid, width=width, minwidth=34, anchor="w", stretch=stretch)
            tv.tag_configure("odd", background=T.STRIPE)
            tv.tag_configure("empty", foreground="#a0a4aa")
            tv.tag_configure("group", foreground=T.FG)
            sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
            tv.configure(yscrollcommand=sb.set)
            tv.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            tv.bind("<<TreeviewSelect>>", lambda e, k=kind: self._on_select(k))
            tv.bind("<Double-1>", lambda e, k=kind: self._on_activate(k, e))
            tv.bind("<Return>", lambda e, k=kind: self.audition_selected())
            tv.bind("<Button-3>", lambda e, k=kind: self._context_menu(k, e))
            tv.bind("<Button-2>", lambda e, k=kind: self._context_menu(k, e))
            self.nb.add(frame, text=_(title))
            self.trees[kind] = tv
            self.tab_kinds.append(kind)
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._on_tab())
        pw.add(left, weight=2)

        right = ttk.Frame(pw, style="Panel.TFrame")
        tk.Frame(right, width=1, bg=T.BORDER).pack(side="left", fill="y")
        self.detail = DetailPanel(right, self)
        self.detail.pack(side="left", fill="both", expand=True)
        pw.add(right, weight=3)
        self._sash_done = False

        def place_sash(event=None):
            # colocar el divisor solo cuando la ventana ya tiene su tamaño real
            # (en equipos lentos, o bajo Wine, eso tarda en ocurrir)
            if self._sash_done:
                return
            width = pw.winfo_width()
            if width < 600:
                return
            pw.sashpos(0, min(560, int(width * 0.42)))
            self._sash_done = pw.sashpos(0) > 100

        pw.bind("<Configure>", place_sash, add="+")
        self.after(300, place_sash)

    def _build_status(self):
        bar = ttk.Frame(self, padding=(12, 5))
        bar.pack(fill="x", side="bottom")
        self.file_label = ttk.Label(bar, text="", style="Status.TLabel")
        self.file_label.pack(side="left")
        # el indicador MIDI se empaqueta antes que el mensaje para que nunca quede tapado
        self.midi_label = ttk.Label(bar, text="", style="Status.TLabel")
        self.midi_label.pack(side="right")
        self.msg_label = ttk.Label(bar, text="", style="Status.TLabel")
        self.msg_label.pack(side="left", padx=(18, 0))
        self.progress = ttk.Progressbar(bar, length=160, mode="indeterminate")
        self.progress_label = ttk.Label(bar, text="", style="Status.TLabel")

    def _bind_keys(self):
        self.bind_all("<Control-o>", lambda e: self.open_file())
        self.bind_all("<Control-s>", lambda e: self.save())
        self.bind_all("<Control-S>", lambda e: self.save_as())
        self.bind_all("<Control-f>", lambda e: self.search_entry.focus_set())
        self.bind_all("<F5>", lambda e: self.download())
        self.bind_all("<F6>", lambda e: self.send())
        self.bind_all("<Control-z>", lambda e: self._edit_key("undo"))
        self.bind_all("<Control-y>", lambda e: self._edit_key("redo"))
        self.bind_all("<Control-Z>", lambda e: self._edit_key("redo"))
        if sys.platform == "darwin":
            self.bind_all("<Command-o>", lambda e: self.open_file())
            self.bind_all("<Command-s>", lambda e: self.save())

    # ================================================================ estado y listas

    def status(self, text: str, warn: bool = False):
        self.msg_label.configure(text=text, foreground=T.WARN if warn else T.MUTED)

    def _set_modified(self, value: bool = True):
        self.modified = value
        self._update_title()

    def _update_title(self):
        name = self.path.name if self.path else (_("Descargado del K4") if self.bank else "")
        mark = " •" if self.modified else ""
        self.title(f"{name}{mark} — {APP_NAME}" if name else APP_NAME)
        if self.bank:
            where = _("tarjeta externa") if self.bank.external else _("memoria interna")
            full = _("banco completo") if self.bank.is_complete else _("banco parcial")
            self.file_label.configure(text=f"{name}{mark}   ·   {full}, {where}")
        else:
            self.file_label.configure(text=_("Ningún banco abierto"))

    def _refresh(self):
        self._fill_lists()
        self._update_title()
        if self.selected:
            self._show(*self.selected)
        elif self.bank is None:
            self.detail.show_welcome()

    def _fill_lists(self):
        text = self.search.get().strip().lower()
        b = self.bank
        for kind, tv in self.trees.items():
            keep = tv.selection()
            tv.delete(*tv.get_children())
            if b is None:
                continue
            rows = getattr(self, f"_rows_{kind}")(b)
            n = 0
            for iid, values, label in rows:
                if text and text not in label.lower():
                    continue
                tags = ["empty"] if values[1] == "—" else []
                if n % 2:
                    tags.append("odd")
                tv.insert("", "end", iid=iid, values=values, tags=tags)
                n += 1
            if keep and tv.exists(keep[0]):
                tv.selection_set(keep[0])
        if b:
            counts = {"single": sum(s is not None for s in b.singles), "multi": sum(m is not None for m in b.multis),
                      "effect": sum(e is not None for e in b.effects), "drum": 61 if b.drum else 0}
            for kind, idx in zip(self.tab_kinds, range(4)):
                self.nb.tab(idx, text=f"{_(TABS[kind][0])}  {counts[kind]}")

    def _rows_single(self, b: Bank):
        users = b.single_users()
        for i, s in enumerate(b.singles):
            pos = index_name(i)
            if s is None:
                yield str(i), (pos, "—", "", "", "", ""), ""
                continue
            waves = ", ".join(s.sources[k].wave_name for k in range(s.source_count) if s.source_active(k))
            used = len({m for m, _ in users.get(i, [])})
            yield str(i), (pos, s.name, f"{C.SOURCE_MODES[s.source_mode]} · {C.POLY_MODES[s.poly_mode]}",
                           s.effect_number, waves, used or ""), s.name

    def _rows_multi(self, b: Bank):
        for i, m in enumerate(b.multis):
            pos = index_name(i)
            if m is None:
                yield str(i), (pos, "—", "", "", ""), ""
                continue
            active = [sec for sec in m.sections if not sec.muted]
            names = []
            for sec in active:
                s = b.singles[sec.single]
                n = (s.name.strip() if s else "?")
                if n not in names:
                    names.append(n)
            yield str(i), (pos, m.name, m.effect_number, len(active), ", ".join(names)), m.name

    def _rows_effect(self, b: Bank):
        users = b.effect_users()
        for i, e in enumerate(b.effects):
            if e is None:
                yield str(i), (i + 1, "—", "", ""), ""
                continue
            n = e.param_names
            u = users.get(i)
            use = f"{len(u['singles'])} S · {len(u['multis'])} M" if u else _("sin uso")
            yield str(i), (i + 1, e.type_name, f"{n[0]} {e.param1:+d} · {n[1]} {e.param2:+d} · {n[2]} {e.param3}",
                           use), e.type_name

    def _rows_drum(self, b: Bank):
        if b.drum is None:
            return
        for i, n in enumerate(b.drum.notes):
            s2 = n.s2.wave_name if n.s2.level else ""
            yield str(i), (C.note_name(C.DRUM_FIRST_NOTE + i), n.s1.wave_name, s2, C.SUBMIXES[n.submix]), \
                f"{n.s1.wave_name} {s2}"

    # ================================================================ selección

    def current_kind(self) -> str:
        return self.tab_kinds[self.nb.index(self.nb.select())]

    def _on_tab(self):
        kind = self.current_kind()
        sel = self.trees[kind].selection()
        if sel:
            self._on_select(kind)
        elif self.bank is not None:
            first = self.trees[kind].get_children()
            if first:
                self.trees[kind].selection_set(first[0])

    def _on_select(self, kind: str):
        sel = self.trees[kind].selection()
        if not sel or self.bank is None:
            return
        self.selected = (kind, int(sel[0]))
        self._show(*self.selected)

    def _show(self, kind: str, index: int):
        if self.bank is None:
            return
        if self._editor_for(kind, index):
            return
        {"single": self.detail.show_single, "multi": self.detail.show_multi,
         "effect": self.detail.show_effect, "drum": self.detail.show_drum}[kind](index)

    def _on_activate(self, kind: str, event):
        if self.trees[kind].identify_region(event.x, event.y) != "cell":
            return
        self.audition_selected()

    def goto(self, kind: str, index: int):
        """Salta a un patch (desde enlaces del panel de detalle)."""
        tv = self.trees[kind]
        if not tv.exists(str(index)):
            self.search.set("")
        self.nb.select(self.tab_kinds.index(kind))
        tv.selection_set(str(index))
        tv.see(str(index))
        tv.focus(str(index))

    def _context_menu(self, kind: str, event):
        row = self.trees[kind].identify_row(event.y)
        if not row or self.bank is None:
            return
        self.trees[kind].selection_set(row)
        i = int(row)
        menu = tk.Menu(self, tearoff=False)
        state = "normal" if self.k4 else "disabled"
        menu.add_command(label=_("Escuchar en el K4"), state=state, command=lambda: self.audition(kind, i))
        menu.add_command(label=_("Editar"), command=lambda: self.start_editing(kind, i))
        if kind in ("single", "multi"):
            menu.add_command(label=_("Seleccionar en el K4"), state=state,
                             command=lambda: self.program_change(kind, i))
        menu.add_command(label=_("Escribir en el K4…"), state=state, command=lambda: self.send((kind, i)))
        menu.add_separator()
        menu.add_command(label=_("Exportar…"), command=lambda: self.export_patch(kind, i))
        menu.tk_popup(event.x_root, event.y_root)

    def _describe(self, kind: str, index: int) -> str:
        b = self.bank
        if kind == "single":
            return f"Single {index_name(index)} «{b.singles[index].name.strip()}»"
        if kind == "multi":
            return f"Multi {index_name(index)} «{b.multis[index].name.strip()}»"
        if kind == "effect":
            return _("Efecto {n} ({type})", n=index + 1, type=b.effects[index].type_name)
        return "Drum"

    def _patch(self, kind: str, index: int):
        b = self.bank
        return {"single": lambda: b.singles[index], "multi": lambda: b.multis[index],
                "effect": lambda: b.effects[index], "drum": lambda: b.drum}[kind]()

    # ================================================================ archivos

    def _ask_discard(self) -> bool:
        if not self.modified:
            return True
        r = messagebox.askyesnocancel(APP_NAME, _("El banco abierto tiene cambios sin guardar.\n¿Guardarlos antes?"),
                                      parent=self)
        if r is None:
            return False
        if r:
            return self.save()
        return True

    def new_bank(self):
        if not self._ask_discard():
            return
        self._set_bank(Bank.empty(), None, modified=True)
        self.status(_("Banco nuevo con patches por defecto"))

    def open_file(self):
        if not self._ask_discard():
            return
        path = filedialog.askopenfilename(parent=self, title=_("Abrir volcado del K4"),
                                          filetypes=_filetypes(FILETYPES_OPEN))
        if path:
            self.load_path(path, ask=False)

    def load_path(self, path, ask: bool = True):
        if ask and not self._ask_discard():
            return
        try:
            bank = Bank.from_file(path)
        except (K4Error, ValueError, IndexError, OSError) as e:
            messagebox.showerror(APP_NAME, _("No se puede abrir {name}:\n{error}", name=Path(path).name, error=e),
                                 parent=self)
            return
        self._set_bank(bank, Path(path), modified=False)
        issues = bank.validate()
        msg = _("Abierto {name}", name=Path(path).name)
        if not bank.is_complete:
            msg += " (" + _("banco parcial") + ")"
        if issues:
            msg += " · " + _n("{n} referencia a un patch que falta", "{n} referencias a patches que faltan",
                              len(issues))
        self.status(msg, warn=bool(issues))

    def _set_bank(self, bank: Bank, path: Path | None, modified: bool):
        self.bank, self.path = bank, path
        self.selected = None
        self.modified = modified
        self.search.set("")
        self._refresh()
        kind = self.current_kind()
        first = self.trees[kind].get_children()
        if first:
            self.trees[kind].selection_set(first[0])
            self.trees[kind].focus(first[0])

    def save(self) -> bool:
        if self.bank is None:
            return False
        if self.path is None or self.path.suffix.lower() not in (".syx", ".mid", ".midi"):
            return self.save_as()
        if not _writable(self.path):
            messagebox.showinfo(APP_NAME, _("No se puede guardar en «{name}»: el archivo es de solo lectura o "
                                            "está en una carpeta protegida. Elige dónde guardar una copia.",
                                            name=self.path.name), parent=self)
            return self.save_as()
        return self._write_bank(self.path)

    def save_as(self) -> bool:
        if self.bank is None:
            return False
        initial = self.path.stem if self.path else _("banco-k4")
        path = filedialog.asksaveasfilename(parent=self, title=_("Guardar banco"), initialfile=initial,
                                            defaultextension=".syx", filetypes=_filetypes(FILETYPES_SAVE))
        if not path:
            return False
        return self._write_bank(Path(path))

    def _write_bank(self, path: Path) -> bool:
        try:
            self.bank.save(path, channel=self.channel - 1)
        except PermissionError:
            if messagebox.askyesno(APP_NAME, _("No hay permiso para escribir «{name}» (archivo de solo lectura, "
                                               "abierto en otro programa o carpeta protegida).\n\n"
                                               "¿Guardar en otro sitio?", name=path.name), parent=self):
                return self.save_as()
            return False
        except (K4Error, OSError) as e:
            messagebox.showerror(APP_NAME, _("No se ha podido guardar:\n{error}", error=e), parent=self)
            return False
        self.path = path
        self._set_modified(False)
        kind = _("archivo MIDI estándar") if path.suffix.lower() in (".mid", ".midi") else "SysEx"
        funcs = {m.function for m in self.bank.to_file_messages()}
        how = (_("volcado completo") if self.bank.is_complete else
               _("volcados de bloque") if funcs == {Function.BLOCK_DATA_DUMP} else
               _("un volcado por patch") if Function.BLOCK_DATA_DUMP not in funcs else
               _("bloques y patches sueltos"))
        self.status(_("Guardado {name} ({kind}, {how})", name=path.name, kind=kind, how=how))
        return True

    def export_selected(self):
        if self.selected:
            self.export_patch(*self.selected)
        else:
            self.status(_("Selecciona primero un patch"), warn=True)

    def export_patch(self, kind: str, index: int):
        if self._patch(kind, index) is None:
            return
        name = {"single": lambda: self.bank.singles[index].name.strip(),
                "multi": lambda: self.bank.multis[index].name.strip(),
                "effect": lambda: _("efecto-{n}", n=index + 1), "drum": lambda: "drum"}[kind]()
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip() or kind
        path = filedialog.asksaveasfilename(parent=self, title=_("Exportar {what}", what=self._describe(kind, index)),
                                            initialfile=safe, defaultextension=".syx",
                                            filetypes=_filetypes(FILETYPES_SAVE))
        if not path:
            return
        try:
            write_patch_file(path, [self.bank.patch_message(kind, index, self.channel - 1)])
        except (K4Error, OSError) as e:
            messagebox.showerror(APP_NAME, _("No se ha podido exportar:\n{error}", error=e), parent=self)
            return
        self.status(_("Exportado {what} en {name}", what=self._describe(kind, index), name=Path(path).name))

    # ================================================================ conexión

    def toggle_connection(self):
        self.disconnect() if self.k4 else self.connect()

    def connect(self) -> bool:
        opts = ConnectDialog(self, channel=self.channel, last=self.last_connection).run()
        if not opts:
            return False
        return self.connect_with(opts)

    def connect_with(self, opts: dict) -> bool:
        self.disconnect(quiet=True)
        try:
            if opts["simulate"]:
                from k4lib.fake import FakeK4
                self.k4 = FakeK4(Bank.from_file(DEMO_BANK), channel=opts["channel"], speed=0.25)
            else:
                from k4lib.midi import K4Midi
                self.k4 = K4Midi(in_port=opts["in"], out_port=opts["out"], channel=opts["channel"])
        except Exception as e:  # noqa: BLE001
            self.k4 = None
            messagebox.showerror(APP_NAME, _("No se ha podido conectar:\n{error}", error=e), parent=self)
            return False
        self.channel = opts["channel"]
        self.last_connection = opts
        self._update_connection_ui()
        self.status(_("Conectado al simulador (memoria interna con el banco A401)") if opts["simulate"]
                    else _("Conectado: {port}", port=opts["out"]))
        if self.selected:
            self._show(*self.selected)
        return True

    def disconnect(self, quiet: bool = False):
        if self.k4 is None:
            return
        if self.worker.busy:
            self.status(_("Espera a que termine la operación en curso"), warn=True)
            return
        try:
            self.k4.close()
        finally:
            self.k4 = None
        self._update_connection_ui()
        if not quiet:
            self.status(_("Desconectado"))
            if self.selected:
                self._show(*self.selected)

    def _update_connection_ui(self):
        connected = self.k4 is not None
        busy = self.worker.busy
        self.connect_btn.configure(text=_("Desconectar") if connected else _("Conectar…"))
        for b in (self.download_btn, self.send_btn):
            b.state(["!disabled"] if connected and not busy else ["disabled"])
        if self.bank is None:
            self.send_btn.state(["disabled"])
        if connected:
            name = self.k4.out_name
            self.midi_label.configure(text="●  " + _("{port} · canal {channel}", port=name, channel=self.channel),
                                      foreground=T.OK)
        else:
            self.midi_label.configure(text="○  " + _("K4 sin conectar"), foreground=T.MUTED)
        for index in self._k4_items:
            self.k4_menu.entryconfigure(index, state="normal" if connected else "disabled")
        if self.detail.editor is not None:
            self.detail.editor.update_connection(connected)

    def _require_connection(self) -> bool:
        if self.k4 is not None:
            return True
        return self.connect()

    # ================================================================ tareas MIDI

    def _run(self, description: str, fn, on_done, determinate: bool = False):
        """Lanza fn(progress) en el hilo MIDI mostrando el progreso."""
        if self.worker.busy:
            self.status(_("Ya hay una operación MIDI en curso"), warn=True)
            return
        if self._live_after is not None:          # esta operación ya envía lo necesario
            self.after_cancel(self._live_after)
            self._live_after = None
        self._live_slot = None                    # puede cambiar el programa del K4
        self.status("")
        self.progress.configure(mode="determinate" if determinate else "indeterminate", value=0)
        self.progress_label.configure(text=description)
        self.progress.pack(side="right", padx=(0, 14), before=self.msg_label)
        self.progress_label.pack(side="right", padx=(0, 8), before=self.msg_label)
        if not determinate:
            self.progress.start(12)

        def progress(n, total):
            self.progress.configure(maximum=total, value=n)
            self.progress_label.configure(text=f"{description} {n}/{total}")

        def finish():
            self.progress.stop()
            self.progress.pack_forget()
            self.progress_label.pack_forget()
            self.after(10, self._update_connection_ui)

        def done(result):
            finish()
            on_done(result)

        def error(exc):
            finish()
            text = str(exc)
            self.status(text[0].upper() + text[1:] if text.lower().startswith("error")
                        else _("Error: {message}", message=text),
                        warn=True)
            messagebox.showerror(APP_NAME, str(exc), parent=self)

        self.worker.submit(fn, done, error, progress)
        self._update_connection_ui()

    # ---------------------------------------------------------------- descarga

    def download(self):
        if not self._require_connection():
            return
        opts = DownloadDialog(self, has_bank=self.bank is not None,
                              external=self.bank.external if self.bank else False).run()
        if opts:
            self.download_with(opts)

    def download_with(self, opts: dict):
        k4, ext = self.k4, opts["external"]
        what, kind, index = opts["what"], opts["kind"], opts["index"]

        def task(progress):
            if what == "all":
                return k4.get_bank(ext)
            if what in ("singles", "multis", "effects"):
                return k4.get_block({"singles": "single", "multis": "multi", "effects": "effect"}[what], ext)
            part = Bank()
            loc = Location(ext, index)
            if kind == "single":
                part.singles[index] = k4.get_single(loc)
            elif kind == "multi":
                part.multis[index] = k4.get_multi(loc)
            elif kind == "effect":
                part.effects[index] = k4.get_effect(index + 1, ext)
            else:
                part.drum = k4.get_drum(ext)
            return part

        def done(part: Bank):
            part.external = ext
            if opts["mode"] == "merge" and self.bank is not None:
                self.bank.merge(part)
                self._set_modified(True)
                self._refresh()
            else:
                self._set_bank(part, None, modified=True)
            what_txt = {"all": _("banco completo"), "singles": "64 Singles", "multis": "64 Multis",
                        "effects": _("32 efectos")}.get(what, _(KIND_LABELS[kind]))
            self.status(_("Descargado del K4: {what} ({where})", what=what_txt,
                          where=_("tarjeta") if ext else _("memoria interna")))
            if what == "one":
                self.goto(kind, index)

        self._run(_("Descargando…"), task, done)

    # ---------------------------------------------------------------- envío

    def send(self, selection: tuple[str, int] | None = None):
        if self.bank is None:
            self.status(_("No hay ningún banco abierto"), warn=True)
            return
        if not self._require_connection():
            return
        sel = selection or self.selected
        sel_info = None
        if sel and self._patch(*sel) is not None:
            sel_info = (sel[0], sel[1], self._describe(*sel))
        opts = SendDialog(self, selection=sel_info, bank_complete=self.bank.is_complete,
                          external=self.bank.external).run()
        if opts:
            self.send_with(opts, sel)

    def send_with(self, opts: dict, sel: tuple[str, int] | None):
        k4, ext, what = self.k4, opts["external"], opts["what"]
        where = _("la tarjeta del K4") if ext else _("la memoria interna del K4")
        if what == "buffer":
            single = self.bank.singles[sel[1]]
            self._run(_("Enviando…"), lambda p: k4.send_to_edit_buffer(single),
                      lambda r: self.status(_("En la memoria de edición: {name} (no se ha guardado)",
                                              name=single.name.strip())))
            return

        if what == "bank":
            n = len(self.bank.to_messages())
            question = _("Se van a escribir {n} patches en {where}, sustituyendo lo que haya en esas "
                         "posiciones.\n\nEsta acción no se puede deshacer. ¿Continuar?", n=n, where=where)
        else:
            kind, index = sel
            target = opts.get("target", index)
            dest = (_("el efecto {n}", n=target + 1) if kind == "effect" else _("el Drum") if kind == "drum"
                    else _("la posición {pos}", pos=index_name(target)))
            question = _("Se va a escribir {what} en {dest} de {where}, sustituyendo lo que haya.\n\n¿Continuar?",
                         what=self._describe(kind, index), dest=dest, where=where)
        if not self.confirm(APP_NAME, question, parent=self, icon="warning"):
            self.status(_("Envío cancelado"))
            return

        if what == "bank":
            bank = self.bank
            self._run(_("Escribiendo"), lambda p: k4.write_bank(bank, external=ext, progress=p),
                      lambda r: self.status(_("Banco escrito en {where}: {n} patches confirmados por el K4",
                                              where=where, n=len(r))),
                      determinate=True)
            return

        kind, index = sel
        target = opts.get("target", index)
        patch = self._patch(kind, index)

        self._drum_same.clear()          # el Drum del K4 puede cambiar

        def task(progress):
            loc = Location(ext, target if kind != "drum" else 0)
            if kind == "single":
                return k4.write_single(patch, loc)
            if kind == "multi":
                return k4.write_multi(patch, loc)
            if kind == "effect":
                return k4.write_effect(patch, target + 1, ext)
            return k4.write_drum(patch, ext)

        self._run(_("Escribiendo…"), task, lambda r: self.status(f"{self._describe(kind, index)}: {r}"))

    # ---------------------------------------------------------------- editar

    def _editing_live(self) -> tk.BooleanVar:
        """Casilla de envío en directo que corresponde al patch en edición."""
        return self.live_edit if self.editing and self.editing[0] in ("single", "multi") else self.live_write

    def start_editing(self, kind: str, index: int):
        """Abre el editor de parámetros de un patch (en el Drum, index es la nota)."""
        patch = self._patch(kind, index) if self.bank else None
        if patch is None:
            self.status(_("Posición vacía: no hay patch que editar"), warn=True)
            return
        if self.edit_history is None or self.edit_history.patch is not patch:
            self.edit_history = History(patch)
            if kind in ("effect", "drum"):
                self.live_write.set(False)        # escribir en el K4 se confirma cada vez
        self.editing = (kind, None if kind == "drum" else index)
        if self.selected != (kind, index):
            self.goto(kind, index)                # al seleccionarlo se abre el editor
        else:
            self._show(kind, index)
        self._schedule_live()

    def stop_editing(self):
        sel = self.selected
        self._end_editing()
        if sel is not None:
            self._show(*sel)

    def _end_editing(self):
        if self._live_after is not None:
            self.after_cancel(self._live_after)
            self._live_after = None
        self.editing = None
        self.edit_history = None
        self.live_write.set(False)

    def _editor_for(self, kind: str, index: int) -> bool:
        """Si se está editando este patch, muestra el editor y devuelve True."""
        if self.editing is None:
            return False
        h = self.edit_history
        ekind, eindex = self.editing
        same = kind == ekind and (kind == "drum" or index == eindex)
        if not same or h is None or h.patch is not self._patch(kind, index):
            self._end_editing()                  # otra selección, u otro banco cargado
            return False
        self.detail.show_editor(kind, index, h)
        return True

    def _edit_key(self, action: str):
        ed = self.detail.editor
        if ed is None:
            return None
        getattr(ed, action)()
        return "break"

    def patch_edited(self, kind: str, index: int, key: str):
        """El editor avisa de un cambio (index: posición; en el Drum, la nota)."""
        self._set_modified(True)
        self._update_row(kind, index)
        b = self.bank
        if kind == "single" and key in ("name", "undo", "redo", "revert"):
            for i in range(len(b.multis)):         # los Multis muestran los nombres de sus Singles
                self._update_row("multi", i)
        elif kind == "multi":
            for i in range(len(b.singles)):        # columna «Multis» (uso de cada Single)
                self._update_row("single", i)
        elif kind == "drum" and key in ("undo", "redo", "revert"):
            for i in range(C.DRUM_NOTE_COUNT):
                self._update_row("drum", i)
        if kind == "drum":
            self._drum_same.clear()
        self._schedule_live()

    def single_edited(self, index: int, key: str):
        self.patch_edited("single", index, key)

    def _update_row(self, kind: str, index: int):
        tv = self.trees[kind]
        if not tv.exists(str(index)):
            return
        for iid, values, _label in getattr(self, f"_rows_{kind}")(self.bank):
            if iid == str(index):
                tv.item(iid, values=values)
                return

    def live_toggled(self):
        if self.editing and self.editing[0] in ("effect", "drum"):
            if self.live_write.get():
                kind, index = self.editing
                what = _("el Drum") if kind == "drum" else _("el efecto {n}", n=index + 1)
                if not self.confirm(APP_NAME, _("Cada cambio se escribirá en {what} de la memoria del K4, "
                                                "sustituyendo lo que haya ahora. ¿Activar?", what=what),
                                    parent=self):
                    self.live_write.set(False)
                    return
        else:
            self._save_setting("live_edit", bool(self.live_edit.get()))
        self._schedule_live()

    def _schedule_live(self, delay: int | None = None):
        """Envía el patch en edición al K4, agrupando los cambios que llegan seguidos:
        Single y Multi a su memoria de edición; efecto y Drum, escritos en su memoria."""
        if self.editing is None or self.k4 is None or not self._editing_live().get():
            return
        if delay is None:
            delay = 120 if self.editing[0] in ("single", "multi") else 300
        if self._live_after is not None:
            self.after_cancel(self._live_after)
        self._live_after = self.after(delay, self._live_flush)

    def _live_flush(self):
        self._live_after = None
        if self.editing is None or self.k4 is None or not self._editing_live().get():
            return
        if self.worker.busy:
            self._schedule_live(100)
            return
        k4, ext = self.k4, self.bank.external
        kind, index = self.editing
        snapshot = copy_patch(self.edit_history.patch)    # el hilo MIDI no toca el objeto del banco
        slot = (id(k4), ext, kind, index)
        select = kind in ("single", "multi") and self._live_slot != slot

        def task(progress):
            if kind == "effect":
                return k4.write_effect(snapshot, index + 1, ext)
            if kind == "drum":
                return k4.write_drum(snapshot, ext)
            if select:                       # el K4 tiene que estar en ese modo y posición
                k4.program_change(Location(ext, index), multi=kind == "multi")
                time.sleep(0.15)
            k4.send_to_edit_buffer(snapshot)

        def done(_result):
            self._live_slot = slot if kind in ("single", "multi") else self._live_slot
            if select:
                self.status(_("K4 en {what} {pos}: los cambios se oyen al tocar (no se guardan en su memoria)",
                              what="Single" if kind == "single" else "Multi",
                              pos=("E-" if ext else "") + index_name(index)))
            elif kind in ("effect", "drum"):
                self.status(_("Escrito en el K4: {what}", what=self._describe(kind, index or 0)))

        def error(exc):
            self._live_slot = None
            if kind in ("effect", "drum"):
                self.live_write.set(False)       # no insistir si la memoria está protegida, etc.
            self.status(_("No se han podido enviar los cambios al K4: {error}", error=exc), warn=True)

        self.worker.submit(task, done, error)

    def _audition_effect(self, index: int):
        """Un efecto no suena solo: se escucha con un Single del banco que lo use
        (o, si no hay, con un Multi). Ese patch se carga en la memoria de edición,
        así que coincide con el del archivo; el efecto es el guardado en el K4."""
        users = self.bank.effect_users().get(index, {"singles": [], "multis": []})
        if users["singles"]:
            kind, pos = "single", users["singles"][0]
        elif users["multis"]:
            kind, pos = "multi", users["multis"][0]
        else:
            self.status(_("Ningún Single ni Multi del banco usa el efecto {n}: asígnaselo a uno para oírlo",
                          n=index + 1), warn=True)
            return
        patch = self._patch(kind, pos)
        k4, ext = self.k4, self.bank.external
        mode = self.test_notes.get() if self.test_notes.get() != "none" else "chord"
        written = self.editing == ("effect", index) and self.live_write.get()

        def done(notes):
            what = "Single" if kind == "single" else "Multi"
            msg = _("Suena el {what} {pos} «{name}», que usa el efecto {n}", what=what,
                    pos=("E-" if ext else "") + index_name(pos), name=patch.name.strip(), n=index + 1)
            if not notes:
                msg += " · " + _("ninguna sección responde a MIDI (modo Keyboard): tócalo desde el teclado del K4")
            elif not written:
                msg += " · " + _("con el efecto guardado en el K4; para oír tus cambios, escríbelo en el K4")
            self.status(msg, warn=not notes)

        self._run(_("Enviando…"), lambda p: k4.audition(patch, Location(ext, pos), test_notes=mode), done)

    # ---------------------------------------------------------------- escuchar

    def audition_selected(self):
        if self.selected:
            kind, i = self.selected
            self.audition(kind, i)

    def audition(self, kind: str, index: int):
        """Pone el K4 en el modo adecuado, carga el patch en su memoria de edición
        (sin guardarlo) y toca la nota de prueba elegida en el menú K4."""
        if self.k4 is None:
            self.status(_("Conecta el K4 para escuchar los patches"), warn=True)
            return
        patch = self._patch(kind, index)
        if patch is None or kind not in ("single", "multi", "drum", "effect"):
            return
        if kind == "effect":
            return self._audition_effect(index)
        if kind == "drum":
            return self._audition_drum(patch, index)
        k4, ext, mode = self.k4, self.bank.external, self.test_notes.get()
        name = patch.name.strip()

        def done(notes):
            what = "Single" if kind == "single" else "Multi"
            msg = _("{what} «{name}» cargado en la memoria de edición del K4 (sin guardar)", what=what, name=name)
            if notes:
                msg += " · " + _("tocando nota de prueba")
            elif mode == "none":
                msg += " · " + _("toca el teclado del K4 para oírlo")
            else:
                msg += " · " + _("ninguna sección responde a MIDI (modo Keyboard): tócalo desde el teclado del K4")
            if kind == "multi":
                msg += ". " + _("Las secciones usan los Singles guardados en el K4.")
            self.status(msg, warn=bool(mode != "none" and not notes))

        self._run(_("Enviando…"), lambda p: k4.audition(patch, Location(ext, index), test_notes=mode), done)

    def _audition_drum(self, drum, index: int):
        """Toca la nota del kit en el canal del Drum. No hay memoria de edición para el
        Drum, así que suena el guardado en el K4; la primera vez se comprueba si
        coincide con el del archivo."""
        k4, ext = self.k4, self.bank.external
        key = (id(k4), ext, drum.canonical_bytes())
        known = self._drum_same.get(key)
        note = C.note_name(C.DRUM_FIRST_NOTE + index)

        def done(same):
            if same is None:
                same = known
            self._drum_same[key] = same
            msg = _("Drum {note} en el canal {channel}", note=note, channel=drum.channel + 1)
            if same is True:
                msg += " · " + _("el Drum del K4 coincide con el del archivo")
            elif same is False:
                msg += " · " + _("suena el Drum guardado en el K4, que es distinto del del archivo: "
                                 "usa «Escribir Drum en el K4…» para oír este")
            else:
                msg += " · " + _("suena el Drum guardado en el K4 (no hay memoria de edición para el Drum)")
            self.status(msg, warn=same is False)

        self._run(_("Tocando…"), lambda p: k4.audition_drum(drum, index, ext, compare=known is None), done)

    def program_change(self, kind: str, index: int):
        if self.k4 is None:
            self.status(_("Conecta el K4 primero"), warn=True)
            return
        k4, ext = self.k4, self.bank.external
        self._run(_("Cambiando programa…"),
                  lambda p: k4.program_change(Location(ext, index), multi=kind == "multi"),
                  lambda r: self.status(_("K4 en {what} {pos} (lo guardado en el K4, que puede no coincidir "
                                          "con el archivo)", what="Multi" if kind == "multi" else "Single",
                                          pos=("E-" if ext else "") + index_name(index))))

    # ================================================================ varios

    def about(self):
        from k4lib import __version__
        messagebox.showinfo(APP_NAME, _("Kalima {version}\nGestor de bancos para el Kawai K4 / K4r\n\n"
                                        "Usa k4lib para leer y escribir SysEx.", version=__version__), parent=self)

    def change_language(self, code: str):
        """Guarda el idioma elegido; se aplica al reiniciar."""
        self._save_setting("language", code)
        if code != i18n.get_language():
            messagebox.showinfo(APP_NAME, i18n.translate_to(code, N_("El idioma cambiará la próxima vez que abras "
                                                                     "la aplicación.")), parent=self)

    def _save_setting(self, key: str, value):
        self.settings[key] = value
        settings.save(self.settings)

    def on_close(self):
        if self.worker.busy and not messagebox.askyesno(
                APP_NAME, _("Hay una operación MIDI en curso. ¿Salir de todos modos?"), parent=self):
            return
        if not self._ask_discard():
            return
        if self.k4:
            try:
                self.k4.close()
            except Exception:  # noqa: BLE001
                pass
        self.destroy()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if sys.platform == "win32":
        try:                                   # nitidez en pantallas con escalado
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            # icono propio en la barra de tareas (y no el de Python)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kalima.App")
        except Exception:  # noqa: BLE001
            pass
    i18n.set_language(settings.load().get("language"))     # None → idioma del sistema
    app = K4App(argv[0] if argv else None)
    app.mainloop()
