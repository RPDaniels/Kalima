"""Panel derecho: detalle del patch seleccionado."""
from __future__ import annotations

from tkinter import ttk

from k4lib import constants as C
from k4lib.i18n import _, _n
from k4lib.sysex import index_name

from . import theme as T
from .widgets import EnvelopeView, KeyboardZones, ScrollFrame, kv_grid, section, table


def _onoff(b: bool) -> str:
    return _("sí") if b else _("no")


def _signed(v: int) -> str:
    return f"{v:+d}" if v else "0"


class DetailPanel(ScrollFrame):
    """Muestra el detalle de un patch. `app` aporta las acciones (escuchar,
    escribir en el K4, exportar, saltar a otro patch...)."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.editor = None
        self.show_welcome()

    def clear(self):
        self.editor = None
        super().clear()

    # ---------------------------------------------------------------- cabecera

    def _header(self, title: str, subtitle: str, badges: list[str] = ()):
        top = ttk.Frame(self.inner, style="Panel.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text=title, style="Title.TLabel").pack(side="left")
        for b in badges:
            ttk.Label(top, text=b, style="Badge.TLabel").pack(side="left", padx=(10, 0), pady=(6, 0))
        ttk.Label(self.inner, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

    def _actions(self, buttons: list[tuple[str, callable, bool]]):
        """buttons: (texto, función, requiere conexión)."""
        bar = ttk.Frame(self.inner, style="Panel.TFrame")
        bar.pack(fill="x", pady=(12, 0))
        connected = self.app.k4 is not None
        for i, (text, fn, needs_midi) in enumerate(buttons):
            b = ttk.Button(bar, text=text, command=fn, style="Accent.TButton" if i == 0 else "TButton")
            if needs_midi and not connected:
                b.state(["disabled"])
            b.pack(side="left", padx=(0, 8))
        if any(needs for *_rest, needs in buttons) and not connected:
            ttk.Label(self.inner, text=_("Conecta el K4 (menú K4 → Conectar) para escuchar o escribir en él."),
                      style="Muted.TLabel").pack(anchor="w", pady=(6, 0))

    def _loc(self, index: int) -> str:
        ext = self.app.bank.external if self.app.bank else False
        return ("E-" if ext else "") + index_name(index)

    # ---------------------------------------------------------------- bienvenida

    def show_welcome(self):
        self.clear()
        ttk.Label(self.inner, text="Kalima", style="Title.TLabel").pack(anchor="w", pady=(30, 4))
        ttk.Label(self.inner, text=_("Gestor de bancos para el Kawai K4 / K4r"), style="Muted.TLabel").pack(anchor="w")
        bar = ttk.Frame(self.inner, style="Panel.TFrame")
        bar.pack(anchor="w", pady=(22, 0))
        ttk.Button(bar, text=_("Abrir archivo…"), style="Accent.TButton",
                   command=self.app.open_file).pack(side="left", padx=(0, 8))
        ttk.Button(bar, text=_("Conectar al K4…"), command=self.app.connect).pack(side="left", padx=(0, 8))
        ttk.Button(bar, text=_("Descargar del K4…"), command=self.app.download).pack(side="left")
        tips = [
            _("Abre volcados .syx o archivos MIDI (.mid) con SysEx del K4."),
            _("Selecciona un patch para ver su detalle; doble clic sobre un Single o un Multi lo hace "
              "sonar en el K4 sin guardarlo (la nota de prueba se elige en el menú K4)."),
            _("Sin el aparato a mano, «Conectar» ofrece un simulador para probarlo todo."),
            _("El idioma se cambia en el menú Idioma."),
        ]
        tip_box = ttk.Frame(self.inner, style="Panel.TFrame")
        tip_box.pack(anchor="w", pady=(26, 0))
        for t in tips:
            ttk.Label(tip_box, text="•  " + t, style="Key.TLabel", wraplength=520,
                      justify="left").pack(anchor="w", pady=3)

    def show_empty(self, what: str):
        self.clear()
        ttk.Label(self.inner, text=what, style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.inner, text=_("Posición vacía: este patch no estaba en el archivo cargado."),
                  style="Muted.TLabel").pack(anchor="w", pady=4)

    # ---------------------------------------------------------------- single

    def show_single(self, i: int):
        bank, app = self.app.bank, self.app
        s = bank.singles[i]
        self.clear()
        if s is None:
            return self.show_empty(f"Single {self._loc(i)}")
        users = bank.single_users().get(i, [])
        badges = [C.SOURCE_MODES[s.source_mode], C.POLY_MODES[s.poly_mode]]
        self._header(s.name.strip() or _("(sin nombre)"), f"Single {self._loc(i)}", badges)
        self._actions([
            ("▶  " + _("Escuchar en el K4"), lambda: app.audition("single", i), True),
            ("✎  " + _("Editar"), lambda: app.start_editing("single", i), False),
            (_("Seleccionar en el K4"), lambda: app.program_change("single", i), True),
            (_("Escribir en el K4…"), lambda: app.send(("single", i)), True),
            (_("Exportar…"), lambda: app.export_patch("single", i), False),
        ])

        fx = bank.effects[s.effect]
        g = section(self.inner, _("General"))
        kv_grid(g, [
            (_("Volumen"), str(s.volume)),
            (_("Efecto"), f"{s.effect_number} · {fx.type_name if fx else '?'}"),
            ("Submix", C.SUBMIXES[s.submix]),
            ("Pitch bend", _n("{n} semitono", "{n} semitonos", s.bend_range)),
            (_("Rueda"), f"{C.WHEEL_ASSIGNS[s.wheel_assign]} {_signed(s.wheel_depth)}"),
            (_("Presión → afinación"), _signed(s.prs_freq)),
            ("AM 1→2", _onoff(s.am12)),
            ("AM 3→4", _onoff(s.am34)),
            (_("Fuentes en uso"), str(s.source_count)),
        ])

        g = section(self.inner, _("Fuentes"))
        rows, muted = [], set()
        for k in range(4):
            src = s.sources[k]
            active = k < s.source_count and s.source_active(k)
            if not active:
                muted.add(k)
            state = _("activa") if active else (_("silenciada") if k < s.source_count else _("sin uso"))
            pitch = _("teclado") if src.key_track else _("fija {note}", note=C.note_name(src.fixed_key))
            rows.append((f"S{k + 1}", state, f"{src.wave + 1} · {src.wave_name}", _signed(src.coarse),
                         _signed(src.fine), pitch, src.delay,
                         C.VELOCITY_CURVES[src.vel_curve], C.KS_CURVES[src.ks_curve]))
        table(g, [("s", "", 30), ("st", _("Estado"), 70), ("wave", _("Onda"), 138), ("co", "Coarse", 60),
                  ("fi", "Fine", 42), ("kt", _("Afinación"), 84), ("dl", _("Retardo"), 68),
                  ("vc", _("Curva vel."), 112), ("kc", _("Curva KS"), 84)], rows, muted_rows=muted)

        g = section(self.inner, _("Envolventes"))
        EnvelopeView(g, s).pack(fill="x")

        g = section(self.inner, _("Amplificadores (DCA)"))
        rows = []
        for k in range(4):
            a = s.amps[k]
            rows.append((f"S{k + 1}", a.level, a.attack, a.decay, a.sustain, a.release,
                         _signed(a.level_vel), _signed(a.level_prs), _signed(a.level_ks),
                         _signed(a.time_vel_on), _signed(a.time_vel_off), _signed(a.time_ks)))
        table(g, [("s", "", 34), ("lv", _("Nivel"), 58), ("a", "A", 38), ("d", "D", 40), ("su", "S", 40),
                  ("r", "R", 40), ("mv", _("Niv·vel"), 62), ("mp", _("Niv·pres"), 72), ("mk", _("Niv·KS"), 58),
                  ("tv", _("T·vel on"), 66), ("to", _("T·vel off"), 70), ("tk", _("T·KS"), 60)],
              rows, muted_rows=muted)

        g = section(self.inner, _("Filtros (DCF)"))
        rows = []
        for k, f in enumerate(s.filters):
            rows.append((f"F{k + 1}", f.cutoff, f.resonance, _onoff(f.lfo), _signed(f.cutoff_vel),
                         _signed(f.cutoff_prs), _signed(f.cutoff_ks), _signed(f.env_depth),
                         _signed(f.env_vel_depth), f"{f.attack}/{f.decay}/{_signed(f.sustain)}/{f.release}",
                         f"{_signed(f.time_vel_on)} / {_signed(f.time_vel_off)} / {_signed(f.time_ks)}"))
        table(g, [("f", "", 34), ("c", _("Corte"), 50), ("r", "Reso", 44), ("l", "LFO", 40),
                  ("cv", _("Corte·vel"), 66), ("cp", _("Corte·pres"), 72), ("ck", _("Corte·KS"), 64),
                  ("ed", "Env", 40), ("ev", _("Env·vel"), 56), ("adsr", "A/D/S/R", 96),
                  ("t", _("T·vel on/off/KS"), 120)], rows,
              muted_rows={1} if s.source_count == 2 else set())

        g = section(self.inner, _("Modulación"))
        kv_grid(g, [
            ("LFO", C.LFO_SHAPES[s.lfo_shape]), (_("Velocidad"), str(s.lfo_speed)),
            (_("Retardo"), str(s.lfo_delay)), (_("Profundidad"), _signed(s.lfo_depth)),
            (_("Presión → LFO"), _signed(s.lfo_prs)), ("", ""),
            ("Vibrato", C.LFO_SHAPES[s.vib_shape]), (_("Velocidad"), str(s.vib_speed)),
            (_("Profundidad"), _signed(s.vib_depth)), (_("Presión → vibrato"), _signed(s.vib_prs)), ("", ""), ("", ""),
            ("Auto bend", _("tiempo {value}", value=s.autobend_time)), (_("Profundidad"), _signed(s.autobend_depth)),
            (_("KS → tiempo"), _signed(s.autobend_ks_time)), (_("Vel → prof."), _signed(s.autobend_vel_depth)),
        ], columns=3)

        g = section(self.inner, _("Efecto"))
        if fx:
            n = fx.param_names
            ttk.Label(g, text=f"{s.effect_number} · {fx.type_name}", style="Value.TLabel").pack(anchor="w")
            ttk.Label(g, text=f"{n[0]} {fx.param1:+d}   ·   {n[1]} {fx.param2:+d}   ·   {n[2]} {fx.param3}",
                      style="Key.TLabel").pack(anchor="w", pady=(2, 0))
            ttk.Button(g, text=_("Ver efecto →"), style="Link.TButton",
                       command=lambda: app.goto("effect", s.effect)).pack(anchor="w", pady=(4, 0))
        else:
            ttk.Label(g, text=_("El efecto no está en el banco cargado"), style="Warn.TLabel").pack(anchor="w")

        g = section(self.inner, _n("Usado por {n} sección de Multis", "Usado por {n} secciones de Multis", len(users)))
        if not users:
            ttk.Label(g, text=_("Ningún Multi usa este Single: puedes moverlo o sustituirlo sin afectar a nada."),
                      style="Key.TLabel").pack(anchor="w")
        for mi, si in users:
            m = bank.multis[mi]
            ttk.Button(g, text=f"{index_name(mi)}  {m.name.strip()}  ·  " + _("sección {n}", n=si + 1),
                       style="Link.TButton", command=lambda mi=mi: app.goto("multi", mi)).pack(anchor="w")

    def show_editor(self, kind: str, index: int, history):
        """Editor de parámetros; en el Drum, index es la nota que se ve."""
        from .editor import PatchEditor
        self.clear()
        self.editor = PatchEditor(self, self.app, kind, index, history)
        return self.editor

    # ---------------------------------------------------------------- multi

    def show_multi(self, i: int):
        bank, app = self.app.bank, self.app
        m = bank.multis[i]
        self.clear()
        if m is None:
            return self.show_empty(f"Multi {self._loc(i)}")
        active = [k for k, sec in enumerate(m.sections) if not sec.muted]
        self._header(m.name.strip() or _("(sin nombre)"), f"Multi {self._loc(i)}",
                     [_n("{n} sección activa", "{n} secciones activas", len(active))])
        self._actions([
            ("▶  " + _("Escuchar en el K4"), lambda: app.audition("multi", i), True),
            ("✎  " + _("Editar"), lambda: app.start_editing("multi", i), False),
            (_("Seleccionar en el K4"), lambda: app.program_change("multi", i), True),
            (_("Escribir en el K4…"), lambda: app.send(("multi", i)), True),
            (_("Exportar…"), lambda: app.export_patch("multi", i), False),
        ])
        ttk.Label(self.inner, text=_("Al escucharlo, las secciones suenan con los Singles guardados en el K4 "
                                     "en esas posiciones, que pueden no coincidir con los de este archivo."),
                  style="Muted.TLabel", wraplength=640, justify="left").pack(anchor="w", pady=(6, 0))
        fx = bank.effects[m.effect]
        g = section(self.inner, _("General"))
        kv_grid(g, [(_("Volumen"), str(m.volume)),
                    (_("Efecto"), f"{m.effect_number} · {fx.type_name if fx else '?'}")], columns=2)

        names = [s.name if s else "?" for s in bank.singles]
        g = section(self.inner, _("Zonas de teclado"))
        KeyboardZones(g, m, names).pack(fill="x")

        g = section(self.inner, _("Secciones"))
        rows = []
        for k, sec in enumerate(m.sections):
            rows.append((k + 1, f"{index_name(sec.single)}  {names[sec.single].strip()}",
                         sec.channel + 1, f"{C.note_name(sec.low_key)} – {C.note_name(sec.high_key)}",
                         C.VELOCITY_SWITCHES[sec.vel_switch], C.MULTI_PLAY_MODES[sec.play_mode],
                         sec.level, _signed(sec.transpose), _signed(sec.tune), C.SUBMIXES[sec.submix],
                         _("silenciada") if sec.muted else _("activa")))
        table(g, [("n", "#", 28), ("s", "Single", 128), ("ch", _("Canal"), 66), ("z", _("Zona"), 80),
                  ("v", _("Veloc."), 52), ("mo", _("Modo"), 60), ("l", _("Nivel"), 56), ("t", _("Transp."), 60),
                  ("tu", _("Afin."), 52), ("sm", "Submix", 64), ("st", _("Estado"), 70)],
              rows, muted_rows={k for k, sec in enumerate(m.sections) if sec.muted},
              on_activate=lambda k: app.goto("single", m.sections[k].single))
        ttk.Label(g, text=_("Doble clic en una sección para ver su Single."), style="Muted.TLabel").pack(
            anchor="w", pady=(4, 0))

    # ---------------------------------------------------------------- efecto

    def show_effect(self, i: int):
        bank, app = self.app.bank, self.app
        e = bank.effects[i]
        self.clear()
        if e is None:
            return self.show_empty(_("Efecto {n}", n=i + 1))
        subtitle = _("Efecto {n}", n=i + 1) + (" (" + _("tarjeta") + ")" if bank.external else "")
        self._header(e.type_name, subtitle)
        self._actions([
            ("▶  " + _("Escuchar en el K4"), lambda: app.audition("effect", i), True),
            ("✎  " + _("Editar"), lambda: app.start_editing("effect", i), False),
            (_("Escribir en el K4…"), lambda: app.send(("effect", i)), True),
            (_("Exportar…"), lambda: app.export_patch("effect", i), False),
        ])
        n = e.param_names
        g = section(self.inner, _("Parámetros"))
        kv_grid(g, [(n[0], f"{e.param1:+d}"), (n[1], f"{e.param2:+d}"), (n[2], str(e.param3))])

        g = section(self.inner, "Submixes")
        rows = [(C.SUBMIXES[k], f"{sm.pan:+d}" if sm.pan else _("centro"), sm.send1, sm.send2)
                for k, sm in enumerate(e.submixes)]
        table(g, [("s", "Submix", 60), ("p", _("Panorama"), 80), ("e1", _("Envío 1"), 70),
                  ("e2", _("Envío 2"), 70)], rows)
        ttk.Label(g, text=_("En el K4r los envíos no se usan y el panorama selecciona la salida."),
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

        users = bank.effect_users().get(i, {"singles": [], "multis": []})
        ns, nm = len(users["singles"]), len(users["multis"])
        g = section(self.inner, _("Usado por {singles} y {multis}",
                                  singles=_n("{n} Single", "{n} Singles", ns), multis=_n("{n} Multi", "{n} Multis", nm)))
        if not users["singles"] and not users["multis"]:
            ttk.Label(g, text=_("Ningún patch usa este efecto."), style="Key.TLabel").pack(anchor="w")
        items = [("single", k, bank.singles[k].name) for k in users["singles"]] + \
                [("multi", k, bank.multis[k].name) for k in users["multis"]]
        if items:
            rows = [(("Single" if kind == "single" else "Multi"), index_name(k), name)
                    for kind, k, name in items]
            table(g, [("t", _("Tipo"), 60), ("p", _("Pos."), 50), ("n", _("Nombre"), 160)], rows,
                  height=min(8, len(rows)),
                  on_activate=lambda r: app.goto(items[r][0], items[r][1]))

    # ---------------------------------------------------------------- drum

    def show_drum(self, note: int):
        bank, app = self.app.bank, self.app
        d = bank.drum
        self.clear()
        if d is None:
            return self.show_empty("Drum")
        n = d.notes[note]
        midi = C.DRUM_FIRST_NOTE + note
        self._header(f"Drum · {C.note_name(midi)}", _("Nota MIDI {note} del kit de percusión", note=midi))
        self._actions([
            ("▶  " + _("Escuchar en el K4"), lambda: app.audition("drum", note), True),
            ("✎  " + _("Editar"), lambda: app.start_editing("drum", note), False),
            (_("Escribir Drum en el K4…"), lambda: app.send(("drum", 0)), True),
            (_("Exportar Drum…"), lambda: app.export_patch("drum", 0), False),
        ])
        g = section(self.inner, _("Kit (común)"))
        kv_grid(g, [(_("Canal"), str(d.channel + 1)), (_("Volumen"), str(d.volume)),
                    (_("Velocidad → nivel"), _signed(d.vel_depth))])
        g = section(self.inner, _("Esta nota"))
        kv_grid(g, [("Submix", C.SUBMIXES[n.submix])], columns=1)
        rows = [(f"S{k + 1}", f"{src.wave + 1} · {src.wave_name}", src.decay, _signed(src.tune), src.level)
                for k, src in enumerate((n.s1, n.s2))]
        table(g, [("s", "", 34), ("w", _("Onda"), 210), ("d", "Decay", 56), ("t", _("Afinación"), 76),
                  ("l", _("Nivel"), 50)], rows, muted_rows={k for k, src in enumerate((n.s1, n.s2)) if not src.level})
