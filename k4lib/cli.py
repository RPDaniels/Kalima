"""Línea de órdenes:  python -m k4lib <orden> ...  [--lang es|en|fr]

    list   banco.syx [--multis] [--effects] [--drum]
    show   banco.syx A-1            (detalle de un Single; M:A-1 para un Multi)
    refs   banco.syx                (qué Multis usan cada Single, qué usa cada efecto)
    find   carpeta texto            (busca por nombre en todos los .syx)
    dups   carpeta                  (Singles repetidos entre archivos)
    ports                           (puertos MIDI)
    get    archivo.syx --port X [--ext]   (descarga el banco completo del K4)
    put    archivo.syx --port X [--ext]   (lo escribe patch a patch, con verificación)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

from . import constants as C
from .bank import Bank, load_collection
from .i18n import LANGUAGES, _, _n, get_language, set_language
from .patches import to_dict
from .sysex import Location, index_name


def _cols(items: list[str], ncols: int = 4) -> str:
    rows = (len(items) + ncols - 1) // ncols
    lines = []
    for r in range(rows):
        lines.append("   ".join(items[c * rows + r].ljust(18) for c in range(ncols)
                                if c * rows + r < len(items)))
    return "\n".join(lines)


def cmd_list(a):
    b = Bank.from_file(a.file)
    where = _("externo") if b.external else _("interno")
    print(f"{a.file}  ({where})\n\nSINGLES")
    print(_cols([f"{index_name(i):5} {s.name if s else '—'}" for i, s in enumerate(b.singles)]))
    if a.multis or a.all:
        print("\nMULTIS")
        print(_cols([f"{index_name(i):5} {m.name if m else '—'}" for i, m in enumerate(b.multis)]))
    if a.effects or a.all:
        print("\n" + _("EFECTOS"))
        for i, e in enumerate(b.effects):
            print(f"  {i + 1:2}  {e.summary() if e else '—'}")
    if (a.drum or a.all) and b.drum:
        d = b.drum
        print("\n" + _("DRUM  canal {channel}  volumen {volume}", channel=d.channel + 1, volume=d.volume))
        for i, n in enumerate(d.notes):
            print(f"  {C.note_name(C.DRUM_FIRST_NOTE + i):4} {n.s1.wave_name:24} {n.s2.wave_name if n.s2.level else ''}")


def cmd_show(a):
    b = Bank.from_file(a.file)
    ref = a.patch.upper()
    if ref.startswith("M:"):
        m = b.multis[Location.parse(ref[2:]).index]
        print(_("MULTI {name}  vol {volume}  efecto {effect}", name=m.name, volume=m.volume, effect=m.effect_number))
        for i, s in enumerate(m.sections):
            if s.muted:
                print(f"  {i + 1}: ({_('silenciada')})")
                continue
            single = b.singles[s.single].name if b.singles[s.single] else "?"
            print(f"  {i + 1}: {index_name(s.single):5} {single:10} ch{s.channel + 1:<2} "
                  f"{C.note_name(s.low_key)}-{C.note_name(s.high_key)} {C.MULTI_PLAY_MODES[s.play_mode]} "
                  + _("nivel {level} transp {transpose}", level=s.level, transpose=f"{s.transpose:+}"))
        return
    s = b.singles[Location.parse(ref).index]
    if a.json:
        print(json.dumps(to_dict(s), indent=2, ensure_ascii=False))
        return
    print(s.summary())
    fx = b.effects[s.effect]
    print("  " + _("efecto {effect}: {summary}", effect=s.effect_number, summary=fx.summary() if fx else "?"))
    for i in range(4):
        src, amp = s.sources[i], s.amps[i]
        state = _("activa") if s.source_active(i) else _("silenciada")
        print(f"  S{i + 1} ({state}): {src.wave_name:22} coarse {src.coarse:+} fine {src.fine:+}  "
              f"ADSR {amp.attack}/{amp.decay}/{amp.sustain}/{amp.release} " + _("nivel {level}", level=amp.level))
    for i, f in enumerate(s.filters):
        print(f"  F{i + 1}: cutoff {f.cutoff} reso {f.resonance} env {f.env_depth:+} "
              f"ADSR {f.attack}/{f.decay}/{f.sustain:+}/{f.release}")


def cmd_refs(a):
    b = Bank.from_file(a.file)
    users = b.single_users()
    print(_("SINGLES USADOS POR MULTIS"))
    for i in range(64):
        if i in users:
            ms = ", ".join(f"{index_name(m)}({b.multis[m].name.strip()})" for m in sorted({u[0] for u in users[i]}))
            print(f"  {index_name(i):5} {b.singles[i].name}  <- {ms}")
    print("\n" + _("Singles que ningún Multi usa: {list}", list=", ".join(index_name(i) for i in b.unused_singles())))
    print("\n" + _("EFECTOS"))
    eu = b.effect_users()
    for e in range(32):
        u = eu.get(e)
        if u:
            n = ", ".join([_n("{n} Single", "{n} Singles", len(u["singles"])),
                           _n("{n} Multi", "{n} Multis", len(u["multis"]))])
        else:
            n = _("sin uso")
        print(f"  {e + 1:2} {b.effects[e].type_name if b.effects[e] else '?':34} {n}")
    for issue in b.validate():
        print(_("AVISO:"), issue)


def cmd_find(a):
    for bank in load_collection(a.folder):
        for kind, i, name in bank.find(a.text):
            print(f"{bank.source}  {kind:6} {index_name(i):5} {name}")


def cmd_dups(a):
    seen = defaultdict(list)
    for bank in load_collection(a.folder):
        for i, s in enumerate(bank.singles):
            if s:
                seen[s.fingerprint()].append(f"{bank.source}:{index_name(i)} '{s.name}'")
    groups = [v for v in seen.values() if len(v) > 1]
    for g in groups:
        print("==", "\n   ".join(g))
    print("\n" + _n("{n} grupo de Singles idénticos (ignorando el nombre)",
                    "{n} grupos de Singles idénticos (ignorando el nombre)", len(groups)))


def cmd_ports(a):
    from .midi import list_ports
    ins, outs = list_ports()
    print(_("Entradas:"), *ins, sep="\n  ")
    print(_("Salidas:"), *outs, sep="\n  ")


def cmd_get(a):
    from .midi import K4Midi
    with K4Midi(a.port, channel=a.channel) as k4:
        bank = k4.get_bank(external=a.ext)
    bank.save(a.file, channel=a.channel - 1)
    print(_("Banco guardado en {path}", path=a.file))


def cmd_put(a):
    from .midi import K4Midi
    bank = Bank.from_file(a.file)
    with K4Midi(a.port, channel=a.channel) as k4:
        k4.write_bank(bank, external=a.ext,
                      progress=lambda n, t: print(f"\r{n}/{t}", end="", flush=True))
    print("\n" + _("Banco escrito y confirmado por el K4."))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    # el idioma se elige antes de construir los textos de ayuda
    lang = None
    if "--lang" in argv:
        i = argv.index("--lang")
        lang = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    previous = get_language()
    set_language(lang)
    try:
        _run(argv)
    finally:
        set_language(previous)


def _run(argv):
    p = argparse.ArgumentParser(prog="k4lib", description=_("Gestión de bancos del Kawai K4"),
                                epilog=_("Idioma: --lang {langs}", langs="|".join(LANGUAGES)))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help=_("lista Singles, Multis, efectos y Drum")); s.add_argument("file")
    for flag in ("multis", "effects", "drum", "all"):
        s.add_argument(f"--{flag}", action="store_true")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("show", help=_("detalle de un Single (M:A-1 para un Multi)"))
    s.add_argument("file"); s.add_argument("patch")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_show)

    s = sub.add_parser("refs", help=_("dependencias entre patches")); s.add_argument("file")
    s.set_defaults(fn=cmd_refs)
    s = sub.add_parser("find", help=_("busca por nombre en una carpeta"))
    s.add_argument("folder"); s.add_argument("text"); s.set_defaults(fn=cmd_find)
    s = sub.add_parser("dups", help=_("Singles repetidos en una carpeta")); s.add_argument("folder")
    s.set_defaults(fn=cmd_dups)
    s = sub.add_parser("ports", help=_("puertos MIDI")); s.set_defaults(fn=cmd_ports)

    for name, fn, help_text in (("get", cmd_get, _("descarga el banco completo del K4")),
                                ("put", cmd_put, _("escribe el banco en el K4, patch a patch"))):
        s = sub.add_parser(name, help=help_text); s.add_argument("file")
        s.add_argument("--port", help=_("nombre (o parte) del puerto MIDI"))
        s.add_argument("--channel", type=int, default=1)
        s.add_argument("--ext", action="store_true", help=_("tarjeta externa"))
        s.set_defaults(fn=fn)

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except Exception as e:  # mensajes limpios en la terminal
        print(_("Error: {message}", message=e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
