"""Prueba de humo de la interfaz: recorre los flujos con el simulador y hace capturas.

En Linux:  xvfb-run -a -s "-screen 0 1360x900x24" python tools/gui_smoke.py capturas/
Idioma: K4_LANG=en|fr|es (por defecto, el del sistema).
(las capturas usan `import` de ImageMagick)."""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from k4app.app import DEMO_BANK, K4App  # noqa: E402
from k4lib import Bank  # noqa: E402

SHOTS = Path(sys.argv[1])
OUT = SHOTS / "out"
OUT.mkdir(parents=True, exist_ok=True)
log = []


def shot(app, name):
    app.update()
    time.sleep(0.3)
    app.update()
    subprocess.run(["import", "-window", "root", str(SHOTS / f"{name}.png")], check=True)
    log.append(f"shot {name}")


def wait_worker(app, timeout=30):
    t0 = time.time()
    while app.worker.busy and time.time() - t0 < timeout:
        app.update()
        time.sleep(0.02)
    for _ in range(5):
        app.update()
        time.sleep(0.02)
    assert not app.worker.busy, "worker sigue ocupado"


app = K4App()
app.geometry("1360x840+0+0")
app.update()
shot(app, "01_inicio")

app.load_path(DEMO_BANK, ask=False)
app.update()
assert app.bank and app.bank.singles[0].name == "Melo Vox 1"
shot(app, "02_singles_A1")

app.goto("single", 5)
shot(app, "03_single_twin")

app.goto("multi", 0)
shot(app, "04_multi")

app.goto("effect", 2)
shot(app, "05_efecto")

app.goto("drum", 0)
shot(app, "06_drum")

app.search.set("bass")
app.nb.select(0)
app.update()
n = len(app.trees["single"].get_children())
log.append(f"filtro 'bass': {n} singles")
shot(app, "07_filtro")
app.search.set("")

# --- diálogo de conexión (captura y cierre automático)
from k4app.dialogs import ConnectDialog, DownloadDialog, SendDialog  # noqa: E402


def capture_dialog(cls, name, **kw):
    def later():
        shot(app, name)
        for w in app.winfo_children():
            if isinstance(w, cls):
                w.cancel()
    app.after(400, later)
    return cls(app, **kw).run()


capture_dialog(ConnectDialog, "08_dialogo_conectar", channel=1)

# --- conectar al simulador
assert app.connect_with({"simulate": True, "in": "", "out": "", "channel": 1})
app.goto("single", 0)
shot(app, "09_conectado")

# escuchar
app.audition("single", 3)
wait_worker(app)
assert app.k4.edit_buffer.name == app.bank.singles[3].name
log.append("audición OK: " + app.k4.edit_buffer.name)
assert any(n[0] for n in app.k4.notes), "no se tocó ninguna nota de prueba"

app.goto("multi", 0)
app.audition("multi", 0)
wait_worker(app)
assert app.k4.edit_buffer_multi.name == app.bank.multis[0].name
assert app.k4.current_program == (False, 64)
log.append("audición de Multi OK: " + app.msg_label.cget("text"))
shot(app, "09b_multi_escuchando")

app.goto("drum", 2)
app.k4.notes.clear()
app.audition("drum", 2)
wait_worker(app)
assert [n[2] for n in app.k4.notes if n[0]] == [38], app.k4.notes
log.append("audición de Drum OK: " + app.msg_label.cget("text"))
shot(app, "09c_drum_escuchando")

# --- editor de Singles con envío en directo al simulador
def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def control(key, index=0):
    return next(c for c in app.detail.editor.controls if c.param.key == key and c.index == index)


app._set_modified(False)
app.live_edit.set(True)
app.goto("single", 5)
pump(0.3)
app.start_editing("single", 5)
pump(0.5)
wait_worker(app)
ed = app.detail.editor
assert ed is not None and app.editing == ("single", 5)
assert app.k4.current_program == (False, 5)                 # el K4 pasa a ese Single
single = app.bank.singles[5]
original = single.to_bytes()

c = control("dcf.cutoff", 0)
c.var.set("12")                                             # como si se escribiera en el Spinbox
c = control("src.wave", 1)
c.var.set(c.param.display(196)); c._commit()                # lista desplegable de ondas
c = control("src.coarse", 0)
for v in ("1", "2", "3"):                                   # flechas: se agrupan en un solo paso
    c.var.set(v)
pump(0.4)
wait_worker(app)
assert single.filters[0].cutoff == 12 and single.sources[1].wave == 196 and single.sources[0].coarse == 3
assert app.modified
assert app.k4.edit_buffer.to_bytes() == single.to_bytes(), "el K4 no ha recibido los cambios"
row = app.trees["single"].item("5", "values")
from k4lib.constants import wave_name  # noqa: E402
assert wave_name(196) in str(row[4]), row                    # la lista refleja la onda nueva
log.append("editor: cambios aplicados y enviados en directo OK")

ed.name_var.set("Editado!")
pump(0.3)
assert app.trees["single"].item("5", "values")[1].strip() == "Editado!"
shot(app, "09d_editor")

app._edit_key("undo")                                       # Ctrl+Z: deshace el nombre
assert single.name.strip() != "Editado!"
ed.undo(); ed.undo(); ed.undo()
assert single.filters[0].cutoff != 12 and single.to_bytes() == original, "deshacer no vuelve al original"
ed.redo()
assert single.filters[0].cutoff == 12
ed.revert()
assert single.to_bytes() == original
pump(0.4)
wait_worker(app)
assert app.k4.edit_buffer.to_bytes() == original
log.append("editor: deshacer / rehacer / volver al original OK")

app.goto("single", 6)                                       # otra selección cierra el editor
pump(0.3)
assert app.editing is None and app.detail.editor is None
app.start_editing("single", 6)
pump(0.3)
app.stop_editing()
pump(0.3)
assert app.detail.editor is None

# Multi: en directo por su memoria de edición
app.start_editing("multi", 2)
pump(0.5)
wait_worker(app)
assert app.k4.current_program == (False, 66)                # modo Multi, programa 64 + 2 (A-3)
multi = app.bank.multis[2]
control("sec.level", 0).var.set("33")
c = control("sec.single", 1)
c.var.set(c._options()[40]); c._commit()
control("sec.muted", 7).var.set(1); control("sec.muted", 7)._commit()
pump(0.4)
wait_worker(app)
assert multi.sections[0].level == 33 and multi.sections[1].single == 40 and multi.sections[7].muted
assert app.k4.edit_buffer_multi.to_bytes() == multi.to_bytes(), "el K4 no ha recibido el Multi"
assert app.detail.editor.zones.rows == [i for i, sec in enumerate(multi.sections) if not sec.muted]
shot(app, "09e_editor_multi")
app.detail.editor.revert()
pump(0.3)
log.append("editor de Multi OK")

# efecto: no se escribe en el K4 hasta activarlo (con confirmación)
app.confirm = lambda *a, **k: True
app.start_editing("effect", 4)
pump(0.3)
fx = app.bank.effects[4]
k4_fx_before = app.k4.banks[False].effects[4].to_bytes()
c = control("type", 0)
c.var.set(c.param.display(8)); c._commit()                 # Chorus
control("param1", 0).var.set("-3")
pump(0.5)
wait_worker(app)
assert fx.type == 8 and fx.param1 == -3
assert app.k4.banks[False].effects[4].to_bytes() == k4_fx_before, "no debía escribir sin permiso"
assert app.detail.editor.param_labels["param1"].cget("text") == fx.param_names[0]
app.live_write.set(True); app.live_toggled()
control("sub.send1", 2).var.set("77")
pump(0.6)
wait_worker(app)
assert app.k4.banks[False].effects[4].to_bytes() == fx.to_bytes(), "el efecto no se ha escrito en el K4"
users = app.bank.effect_users()[4]["singles"]
app.audition("effect", 4)                                   # suena con un Single que usa el efecto
wait_worker(app)
assert app.k4.current_program == (False, users[0]), app.k4.current_program
assert app.k4.edit_buffer.name == app.bank.singles[users[0]].name and app.k4.notes
log.append("escuchar efecto: " + app.msg_label.cget("text"))
shot(app, "09f_editor_efecto")
log.append("editor de efecto OK (escritura solo tras confirmar)")

# Drum: el editor sigue abierto al cambiar de nota
app.start_editing("drum", 3)
pump(0.3)
assert not app.live_write.get(), "otro patch: la escritura en directo vuelve a estar desactivada"
d = app.bank.drum
control("dsrc.level", 3 * 2 + 1).var.set("0")
pump(0.3)
assert d.notes[3].s2.level == 0
app.goto("drum", 5)
pump(0.3)
assert app.detail.editor is not None and app.detail.editor.index == 5
control("dsrc.tune", 5 * 2).var.set("12")
app.live_write.set(True); app.live_toggled()
pump(0.6)
wait_worker(app)
assert d.notes[5].s1.tune == 12 and app.k4.banks[False].drum.to_bytes() == d.to_bytes()
app.audition("drum", 5)
wait_worker(app)
shot(app, "09g_editor_drum")
app.stop_editing()
pump(0.3)
assert app.detail.editor is None and app.editing is None
log.append("editor de Drum OK")
app.live_edit.set(True)
app.goto("single", 0)

capture_dialog(DownloadDialog, "10_dialogo_descarga", has_bank=True)

# --- descargar un único patch (combinar) y luego el banco entero (sustituir)
app.k4.banks[False].singles[10].name = "DelSimulad"
app.download_with({"what": "one", "kind": "single", "index": 10, "external": False, "mode": "merge"})
wait_worker(app)
assert app.bank.singles[10].name == "DelSimulad", app.bank.singles[10].name
assert app.modified
log.append("descarga de un Single combinada OK")

app.download_with({"what": "all", "kind": "single", "index": 0, "external": False, "mode": "replace"})
wait_worker(app)
assert app.bank.is_complete and app.bank.singles[10].name == "DelSimulad"
log.append("descarga de banco completo OK")
shot(app, "11_descargado")

# --- envíos
sel = ("single", 2)
app.goto(*sel)
capture_dialog(SendDialog, "12_dialogo_envio", selection=("single", 2, app._describe(*sel)),
               bank_complete=True, external=False)

app.confirm = lambda *a, **k: True
app.bank.singles[2].name = "Modificado"
app.send_with({"what": "other", "external": False, "target": 63}, sel)
wait_worker(app)
assert app.k4.banks[False].singles[63].name == "Modificado"
log.append("escritura de Single en D-16 OK")

import k4app.app as A  # noqa: E402
errors = []
A.messagebox.showerror = lambda title, msg, **k: errors.append(msg)
app.send_with({"what": "other", "external": True, "target": 0}, sel)   # sin tarjeta
wait_worker(app)
from k4lib.i18n import _  # noqa: E402
assert errors and _("error: no hay tarjeta externa insertada") in errors[-1], errors
log.append("error sin tarjeta mostrado: " + errors[-1])

app.bank.move_single(0, 40)
start = time.time()
app.send_with({"what": "bank", "external": False}, None)
app.update()
time.sleep(0.4)
shot(app, "13_escribiendo_banco")
wait_worker(app, timeout=60)
assert app.k4.banks[False].singles[40].name == "Melo Vox 1"
log.append(f"banco escrito en {time.time() - start:.1f}s: " + app.msg_label.cget("text"))

# --- guardar .mid y .syx y releer
app._write_bank(OUT / "banco.mid")
app._write_bank(OUT / "banco.syx")
assert Bank.from_file(OUT / "banco.mid").to_all_dump().to_bytes() == Bank.from_file(OUT / "banco.syx").to_all_dump().to_bytes()
assert not app.modified
log.append("guardado .mid y .syx OK, idénticos al releer")
shot(app, "14_guardado")

# --- «Guardar» sobre un archivo de solo lectura: avisa y pasa a «Guardar como»
import os, stat  # noqa: E401,E402
ro = OUT / "solo-lectura.syx"
if ro.exists():
    os.chmod(ro, stat.S_IWRITE | stat.S_IREAD); ro.unlink()
app._write_bank(ro)
os.chmod(ro, stat.S_IREAD)
infos, asked = [], []
A.messagebox.showinfo = lambda title, msg, **k: infos.append(msg)
A.filedialog.asksaveasfilename = lambda **k: asked.append(k) or str(OUT / "copia.syx")
app.path = ro
app._set_modified(True)
if os.getuid() != 0:                     # root ignora el permiso de solo lectura
    assert app.save() and asked and infos, (asked, infos)
    assert app.path == OUT / "copia.syx" and (OUT / "copia.syx").exists()
    log.append("guardar en solo lectura -> guardar como OK: " + infos[-1])
asked.clear()
app.path = A.DEMO_BANK                   # el banco de ejemplo nunca se sobrescribe
app.save()
assert asked, "el banco de ejemplo debería abrir «Guardar como»"
log.append("guardar el banco de ejemplo -> guardar como OK")

app.disconnect()
shot(app, "15_desconectado")

# --- cambio de idioma: se guarda en los ajustes y se avisa en el idioma elegido
from k4app import settings  # noqa: E402
from k4lib import i18n  # noqa: E402
infos = []
A.messagebox.showinfo = lambda title, msg, **k: infos.append(msg)
target = "fr" if i18n.get_language() != "fr" else "en"
app.change_language(target)
assert settings.load()["language"] == target
assert infos and infos[-1] == i18n.translate_to(target, "El idioma cambiará la próxima vez que abras la aplicación.")
log.append(f"cambio de idioma a {target} guardado; aviso: {infos[-1]}")
app.destroy()
print("\n".join(log))
print("TODO OK")
