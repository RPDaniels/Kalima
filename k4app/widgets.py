"""Widgets propios: panel desplazable, tablas, envolventes y zonas de teclado."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from k4lib import constants as C
from k4lib.i18n import _

from . import theme as T


class ScrollFrame(ttk.Frame):
    """Marco con barra de desplazamiento vertical. Los hijos van en .inner."""

    def __init__(self, master, **kw):
        super().__init__(master, style="Panel.TFrame", **kw)
        self.canvas = tk.Canvas(self, bg=T.PANEL, highlightthickness=0, bd=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="Panel.TFrame", padding=(18, 14, 18, 18))
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._wheel, add="+")

    def _wheel(self, event):
        w = self.winfo_containing(event.x_root, event.y_root)
        while w is not None and w is not self:
            w = w.master
        if w is None or isinstance(self.winfo_containing(event.x_root, event.y_root), ttk.Treeview):
            return
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta * 2, "units")

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)


def section(parent, text: str, row: int | None = None) -> ttk.Frame:
    """Cabecera de sección con una línea, devuelve el marco para su contenido."""
    head = ttk.Frame(parent, style="Panel.TFrame")
    head.pack(fill="x", pady=(16, 6))
    ttk.Label(head, text=text.upper(), style="Section.TLabel").pack(side="left")
    tk.Frame(head, height=1, bg=T.BORDER).pack(side="left", fill="x", expand=True, padx=(10, 0), pady=(2, 0))
    body = ttk.Frame(parent, style="Panel.TFrame")
    body.pack(fill="x")
    return body


def kv_grid(parent, pairs: list[tuple[str, str]], columns: int = 3) -> ttk.Frame:
    """Rejilla de pares clave / valor."""
    f = ttk.Frame(parent, style="Panel.TFrame")
    f.pack(fill="x")
    for i, (k, v) in enumerate(pairs):
        r, c = divmod(i, columns)
        ttk.Label(f, text=k, style="Key.TLabel").grid(row=r, column=c * 2, sticky="w", padx=(0, 8), pady=2)
        ttk.Label(f, text=v, style="Value.TLabel").grid(row=r, column=c * 2 + 1, sticky="w", padx=(0, 26), pady=2)
    return f


def table(parent, columns: list[tuple[str, str, int]], rows: list[tuple], *,
          muted_rows: set[int] = frozenset(), height: int | None = None,
          on_activate=None) -> ttk.Treeview:
    """Tabla de solo lectura. columns: (id, título, ancho)."""
    tv = ttk.Treeview(parent, columns=[c[0] for c in columns], show="headings",
                      height=height or max(1, len(rows)), style="Detail.Treeview", selectmode="browse")
    for cid, title, width in columns:
        tv.heading(cid, text=title, anchor="w")
        tv.column(cid, width=width, minwidth=30, anchor="w", stretch=cid == columns[-1][0])
    tv.tag_configure("muted", foreground="#a0a4aa")
    tv.tag_configure("odd", background=T.STRIPE)
    for i, r in enumerate(rows):
        tags = ["muted"] if i in muted_rows else []
        if i % 2:
            tags.append("odd")
        tv.insert("", "end", iid=str(i), values=r, tags=tags)
    tv.pack(fill="x")
    if on_activate:
        tv.bind("<Double-1>", lambda e: tv.focus() and on_activate(int(tv.focus())))
        tv.bind("<Return>", lambda e: tv.focus() and on_activate(int(tv.focus())))
    return tv


# ------------------------------------------------------------------ envolventes

class EnvelopeView(tk.Canvas):
    """Dibuja las envolventes DCA de las fuentes activas y las de los filtros."""

    HOLD = 60   # duración (en las mismas unidades 0..100) del tramo de sostenido

    def __init__(self, master, single, **kw):
        super().__init__(master, height=170, bg=T.PANEL, highlightthickness=0, **kw)
        self.single = single
        self.bind("<Configure>", lambda e: self.redraw())

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50:
            return
        gap = 24
        pw = (w - gap) / 2
        self._panel(0, 0, pw, h, _("Amplitud (DCA)"), self._dca_curves())
        self._panel(pw + gap, 0, pw, h, _("Filtro (DCF)"), self._dcf_curves(), bipolar=True)

    def _dca_curves(self):
        s = self.single
        out = []
        for i in range(4):
            if i >= s.source_count or not s.source_active(i):
                continue
            a, src = s.amps[i], s.sources[i]
            peak = a.level / 100
            sus = peak * a.sustain / 100
            t = src.delay
            pts = [(0, 0), (t, 0)]
            t += a.attack; pts.append((t, peak))
            t += a.decay; pts.append((t, sus))
            t += self.HOLD; pts.append((t, sus))
            t += a.release; pts.append((t, 0))
            out.append((f"S{i + 1}", T.SERIES[i], pts))
        return out

    def _dcf_curves(self):
        s = self.single
        out = []
        for i, f in enumerate(s.filters):
            if s.source_count == 2 and i == 1:
                continue       # en modo Normal solo hay un filtro en uso
            sus = 0.5 + f.sustain / 100
            t = 0
            pts = [(0, 0.5)]
            t += f.attack; pts.append((t, 1.0))
            t += f.decay; pts.append((t, sus))
            t += self.HOLD; pts.append((t, sus))
            t += f.release; pts.append((t, 0.5))
            out.append((f"F{i + 1} ({f.env_depth:+})", T.SERIES[i * 2], pts))
        return out

    def _panel(self, x0, y0, w, h, title, curves, bipolar=False):
        top, bottom, left = y0 + 22, y0 + h - 8, x0 + 4
        right = x0 + w - 4
        tid = self.create_text(x0, y0 + 2, text=title, anchor="nw", fill=T.MUTED, font=("TkDefaultFont", 9))
        lx = self.bbox(tid)[2] + 12           # la leyenda va en la línea del título
        self.create_rectangle(left, top, right, bottom, outline=T.BORDER, fill="#fbfbf9")
        if bipolar:
            ym = (top + bottom) / 2
            self.create_line(left, ym, right, ym, fill=T.BORDER, dash=(3, 3))
        tmax = max([p[-1][0] for _, _, p in curves] + [1])
        for n, (label, color, pts) in enumerate(curves):
            coords = []
            for t, v in pts:
                coords += [left + 4 + (right - left - 8) * t / tmax,
                           bottom - 3 - (bottom - top - 12) * v - 2 * n]
            self.create_line(*coords, fill=color, width=2, smooth=False)
            tid = self.create_text(lx, y0 + 2, text=label, anchor="nw", fill=color,
                                   font=("TkDefaultFont", 9, "bold"))
            lx = self.bbox(tid)[2] + 10
        if not curves:
            self.create_text((left + right) / 2, (top + bottom) / 2, text=_("sin fuentes activas"),
                             fill=T.MUTED)


# ------------------------------------------------------------------ zonas de teclado

class KeyboardZones(tk.Canvas):
    """Teclado 0..127 con una barra por sección del Multi (zona y canal)."""

    def __init__(self, master, multi, single_names: list[str], **kw):
        self.multi = multi
        self.names = single_names
        self.rows = [i for i, s in enumerate(multi.sections) if not s.muted]
        height = 44 + 20 * max(1, len(self.rows)) + 12
        super().__init__(master, height=height, bg=T.PANEL, highlightthickness=0, **kw)
        self.bind("<Configure>", lambda e: self.redraw())

    def redraw(self):
        self.delete("all")
        self.rows = [i for i, s in enumerate(self.multi.sections) if not s.muted]   # puede haber cambiado
        w = self.winfo_width()
        if w < 100:
            return
        left, right = 4, w - 4
        span = right - left

        def x(note):
            return left + span * note / 128

        y = 4
        for row, i in enumerate(self.rows):
            sec = self.multi.sections[i]
            color = T.SERIES[i % len(T.SERIES)]
            x0, x1 = x(sec.low_key), x(sec.high_key + 1)
            self.create_rectangle(x0, y, x1, y + 16, fill=color, outline="")
            label = f"{i + 1} · ch{sec.channel + 1} · {self.names[sec.single].strip()}"
            if sec.transpose:
                label += f" · {sec.transpose:+}"
            tid = self.create_text(x0 + 5, y + 8, text=label, anchor="w", fill="white",
                                   font=("TkDefaultFont", 9, "bold"))
            if self.bbox(tid)[2] > x1 - 2:          # no cabe: etiqueta fuera de la barra
                self.itemconfigure(tid, fill=color)
                self.coords(tid, min(x1 + 5, right - 150), y + 8)
            y += 20
        if not self.rows:
            self.create_text(w / 2, y + 8, text=_("todas las secciones están silenciadas"), fill=T.MUTED)
            y += 20
        # teclado
        ky, kh = y + 6, 30
        self.create_rectangle(left, ky, right, ky + kh, fill="white", outline="#c9c6bd")
        for n in range(127):
            # separación entre teclas blancas: en E-F y B-C va en el límite de nota;
            # en el resto, en el centro de la tecla negra intermedia
            if n % 12 in (4, 11):
                xs = x(n + 1)
            elif n % 12 in (0, 2, 5, 7, 9):
                xs = x(n + 1.5)
            else:
                continue
            self.create_line(xs, ky, xs, ky + kh, fill="#d6d3ca")
        for n in range(128):
            if n % 12 in (1, 3, 6, 8, 10):
                self.create_rectangle(x(n) + 1, ky, x(n + 1) - 1, ky + kh * 0.6, fill="#2b2d31", outline="")
        for n in range(0, 128, 12):
            self.create_text(x(n) + 2, ky + kh + 2, text=C.note_name(n), anchor="nw", fill=T.MUTED,
                             font=("TkDefaultFont", 8))
        self.configure(height=ky + kh + 16)
