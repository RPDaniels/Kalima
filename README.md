# Kalima / k4lib

![Kalima](https://github.com/RPDaniels/Kalima/blob/main/Kalima.png?raw=true)

**Kalima** is a bank manager for the **Kawai K4 / K4r** synthesizer (1989) written in Python. It is
made of a library (`k4lib`) that reads, writes and manages MIDI System Exclusive dumps,
and a desktop application built on top of it (Tkinter, Python package `k4app`).
Earlier versions were called *K4 Librarian*.

The application is available in **English, Spanish and French** (Language menu;
the change applies on restart).

The full developer reference (architecture, API, SysEx protocol and byte-by-byte
format of the K4 patches) is in [`docs/TECHNICAL.md`](docs/TECHNICAL.md).

## Installation

```bash
pip install -e ".[midi,dev]"     # mido + python-rtmidi to talk to the K4
pytest                            # 214 tests using the A401 factory bank
```

Without the `midi` extra, everything that works with `.syx` files still works
(`.mid` files need `mido`). Tkinter ships with Python on Windows and macOS; on Linux
you may need the `python3-tk` package.

On Windows, `python-rtmidi` 1.5.8 only provides prebuilt wheels for **Python 3.12**;
with other versions pip tries to compile it and usually fails.

## Windows executable

`Kalima.exe` is a single file that bundles Python, the application and
`python-rtmidi`: download it and run it, nothing to install. It is not signed, so the
first time Windows shows “Windows protected your PC”: **More info → Run anyway**.
Dropping a `.syx` file onto the `.exe` opens it directly.

To rebuild it after changing the code, install Python 3.12 and double-click
`packaging\construir_exe.bat`; the result is `dist\Kalima.exe`. The PyInstaller
configuration is in `packaging/Kalima.spec`.

## Desktop application

```bash
python -m k4app [bank.syx]     # or, once installed: kalima
```

- **Open** `.syx` dumps or standard MIDI files (`.mid`) containing K4 SysEx
  (full banks, blocks or single patches, even mixed; also old files whose dumps lack
  the closing `F7`).
- **Browse** the bank in tabs (Singles, Multis, Effects, Drum) with a name filter.
- **Details** of the selected patch:
  - Single: sources, drawn envelopes, DCA, DCF, modulation and effect, and which Multis use it.
  - Multi: keyboard zones and sections.
  - Effect: parameters, submixes and which patches use it.
  - Drum: data for each note.

  Links jump from one patch to another.
- **Connect** to the K4 (ports and channel) or to the **simulator** to try everything
  without the instrument.
- **Download** from the K4: full bank, block of Singles, Multis or effects, or a single
  patch; replacing the open bank or merging into it.
- **Send** to the K4: a patch to its own slot or another one, a Single to the edit
  buffer (to hear it without saving) or the whole bank patch by patch with
  verification. It asks for confirmation before writing.
- **Play**: double-click, Enter or the “Play on K4” button on a Single or a Multi puts
  the K4 in the right mode, loads the patch into its edit buffer (without saving it)
  and plays a test note or chord (chosen in the K4 menu). On a Drum key it plays that
  key on the Drum channel; the Drum has no edit buffer, so you hear the one stored in
  the K4, and the app tells you if it differs from the file's. On an effect it plays a
  Single from the bank that uses it (or a Multi if no Single does).
- **Edit** Singles, Multis, effects and the Drum: “Edit” opens every parameter, with
  undo/redo and “Revert to original”. With the K4 connected, each change to a Single
  or a Multi is sent to its edit buffer, so you hear it as you play without
  overwriting anything in its memory; “Write to K4…” stores it. Effects and the Drum
  have no edit buffer: to hear them while editing you can enable writing each change
  to the K4 (it asks for confirmation, since it replaces what the K4 has).
- **Save** the bank as `.syx` or `.mid` (a partial bank is saved as block dumps), and
  **export** a single patch. Read-only files and the demo bank go to “Save as”. In `.mid` files
  each dump is spaced by its transmission time, so a sequencer can play the file back
  without overloading the K4.

MIDI operations run in a separate thread, so the window never freezes and the status
bar shows progress.
Shortcuts: Ctrl+O, Ctrl+S, Ctrl+Shift+S, Ctrl+F (filter), F5 (download), F6 (send).

User settings (language, test note) are stored in `%APPDATA%\Kalima\settings.json`
on Windows, `~/Library/Application Support/Kalima/` on macOS and
`~/.config/kalima/` on Linux. If that file does not exist yet, the settings of the
old *K4 Librarian* folder are read instead.

`tools/gui_smoke.py` runs through all these flows with the simulator and takes
screenshots (`K4_LANG=en|es|fr` selects the language).

## Quick start (Python)

```python
from k4lib import Bank, Location

bank = Bank.from_file("A401.SYX")
for i, s in enumerate(bank.singles):
    print(Location(False, i), s.name)

s = bank.singles[0]
print(s.summary())                        # name, volume, effect, mode, waves
print(bank.effects[s.effect].summary())   # the effect it uses

bank.move_single(0, 40)                   # reorder and fix the Multis that use it
bank.save("A401-reordered.syx")
```

With the K4 connected:

```python
from k4lib.midi import K4Midi

with K4Midi("UM-ONE", channel=1) as k4:   # port name, or part of it
    bank = k4.get_bank()                  # full internal bank
    k4.audition(bank.singles[5], "A-6")   # hear it without saving
    k4.set_parameter("filter_cutoff", 60, section=0)
    k4.write_single(bank.singles[5], "D-16")  # write and wait for the confirmation
```

Library messages follow the system language; force one with
`k4lib.i18n.set_language("en")` or the `K4_LANG` environment variable.

## Command line

```bash
python -m k4lib list  A401.SYX --all       # Singles, Multis, effects and Drum
python -m k4lib show  A401.SYX A-1         # details of a Single (--json)
python -m k4lib show  A401.SYX M:A-1       # details of a Multi
python -m k4lib refs  A401.SYX             # Multi→Single and effect dependencies
python -m k4lib find  ~/K4 "bass"          # search every .syx in a folder
python -m k4lib dups  ~/K4                 # identical Singles across files
python -m k4lib ports
python -m k4lib get   my-bank.syx --port UM-ONE [--ext]
python -m k4lib put   my-bank.syx --port UM-ONE [--ext]
python -m k4lib --lang fr refs A401.SYX    # output language
```

## Structure

| Module | Contents |
|---|---|
| `sysex.py` | Message format, checksum, slots (`A-1`…`D-16`, `E-` for the card), request and dump builders, `.syx` / `.mid` reading and writing |
| `patches.py` | `Single`, `Multi`, `Drum`, `Effect` with `from_bytes` / `to_bytes`, fingerprint for duplicates |
| `bank.py` | `Bank`: loads full, block or single dumps; dependencies; `swap_singles`, `move_single`, `swap_effects`, `import_single`; search; validation |
| `params.py` | Parameter numbers for *Parameter Send*, with front-panel ranges |
| `editing.py` | Editable parameter tables for the four patch types (ranges, display, Parameter Send names), `History` for undo/redo |
| `midi.py` | `K4Midi`: requests, verified writes, edit buffer, audition, program change; `SysexInput` reassembles chunked SysEx |
| `fake.py` | `FakeK4`: simulator with the same interface as `K4Midi` |
| `i18n.py`, `locales/` | Translations (Spanish source text, English and French catalogs) |
| `constants.py` | Waves, effect types, curves, modes |

Application (`k4app/`): `app.py` (main window), `details.py` (detail panels),
`dialogs.py` (connect, download, send), `editor.py` (patch editor), `widgets.py` (envelopes, keyboard zones,
tables), `worker.py` (MIDI thread), `settings.py` (user settings), `theme.py` (style).

Source comments and docstrings are in Spanish.

## Format (summary)

`F0 40 0n ff 00 04 s1 s2 data… F7`

| Patch | Size | s1 | s2 |
|---|---|---|---|
| Single | 131 | 00 int / 02 card | 0–63 |
| Multi | 77 | 00 / 02 | 64–127 |
| Drum | 682 | 01 / 03 | 0x20 |
| Effect | 35 | 01 / 03 | 0–31 |
| Full bank | 15114 | 00 / 02 | 00 |

Checksum: `(0xA5 + sum of data bytes) & 0x7F`. The Drum has one checksum for its
common part and one for each of its 61 notes.

## Design decisions and findings

- **Byte-exact dumps.** Bits the K4 does not document are preserved: bit 5 of the
  Singles' effect byte (0x20 in every factory patch) and the padding bytes of effects
  and the Drum (not zero in the factory bank). The duplicate fingerprint ignores them.
- **Source mute: 1 = muted**, the opposite of what the manual says. Verified with the
  factory bank: in Normal mode sources 3–4 have the bit set.
- **Velocity switch order: Soft, Loud, All** (0, 1, 2). Some sources list All/Soft/Loud,
  which is wrong: 452 of the 512 factory sections have value 2.
- **References by slot number.** Multis→Singles and Singles/Multis→effect. The bank
  reordering operations rewrite them so nothing changes its sound.
- **Long SysEx on Windows.** WinMM delivers messages over ~1 KB in chunks and `mido`
  silently drops them; input therefore reads from `python-rtmidi` directly and
  reassembles each message.
- **Edit buffer.** It only sounds if the K4 is in the matching mode, so playing a patch
  first sends a Program Change to its slot. The edit buffer cannot be read back.
- **Bank writes.** `write_bank` goes patch by patch and requires the 0x40 reply for each
  one; slower than a full dump, but it detects any failure.

## To be verified with the instrument

- Timing: pause between messages (`pause=0.12 s`) and reply timeouts.
- Filter 2 section number in Parameter Send (2 according to Edisyn; could be 1).
- Effect of the `RCV PRG` system setting on Program Change in Multi mode.

## References

- Edisyn, `KawaiK4.java` and `KawaiK4Multi.java` (Sean Luke, Apache 2.0): Parameter
  Send table, wave names, edit buffer addressing and manual errata.
- `ksynth` (Conifer Productions): structure of Multi, Drum, Effect and the bank, and
  the A401 factory bank used in the tests.
