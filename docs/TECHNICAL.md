# Kalima — Technical documentation

Developer reference for **Kalima** (the desktop application, package `k4app`;
formerly *K4 Librarian*) and **k4lib** (the library): code architecture, use as a Python
library, and a detailed description of the patch system and the MIDI System Exclusive
protocol of the **Kawai K4 / K4r** synthesizer (1989).

> Document version: 0.5.3 · Python ≥ 3.10 (3.12 recommended on Windows)

---

## Contents

1. [Overview](#1-overview)
2. [Repository layout](#2-repository-layout)
3. [Development setup](#3-development-setup)
4. [Using the library from Python](#4-using-the-library-from-python)
5. [Command line](#5-command-line)
6. [Desktop application architecture](#6-desktop-application-architecture)
7. [Internationalization](#7-internationalization)
8. [The K4 patch system](#8-the-k4-patch-system)
9. [System Exclusive protocol](#9-system-exclusive-protocol)
10. [Byte-by-byte data format](#10-byte-by-byte-data-format)
11. [Manual errata and observed behavior](#11-manual-errata-and-observed-behavior)
12. [.syx and .mid files](#12-syx-and-mid-files)
13. [Tests](#13-tests)
14. [Windows packaging](#14-windows-packaging)
15. [Open items and roadmap](#15-open-items-and-roadmap)
16. [References and credits](#16-references-and-credits)

---

## 1. Overview

The project has three independent layers:

```
┌──────────────────────────────────────────────────────────────┐
│ k4app        Tkinter application (window, dialogs, MIDI thread)│
├──────────────────────────────────────────────────────────────┤
│ k4lib.cli    Command line  (python -m k4lib …)                 │
├──────────────────────────────────────────────────────────────┤
│ k4lib        Library                                           │
│   ├─ patches   Single / Multi / Drum / Effect models           │
│   ├─ bank      Full bank, dependencies, reordering             │
│   ├─ sysex     Messages, checksum, slots, files                │
│   ├─ params    Parameter Send table                            │
│   ├─ midi      K4Midi: talking to the instrument               │
│   ├─ fake      FakeK4: simulator with the same interface       │
│   └─ i18n      Translations (es / en / fr)                     │
└──────────────────────────────────────────────────────────────┘
```

- **`k4lib` has no dependencies** for working with `.syx` files. `mido` is only needed
  for `.mid` files and MIDI output; `python-rtmidi` provides the MIDI ports.
- **Byte-exact round trip**: reading a dump and serializing it again produces exactly
  the same bytes, including the undocumented bits the K4 sends (see §11).
- **The GUI talks to the K4 only through `K4Midi`**, and `FakeK4` implements the same
  interface, so everything can be developed and tested without the instrument.

---

## 2. Repository layout

```
k4lib-project/
├── k4lib/                  Library
│   ├── __init__.py         Public API (Bank, Single, Multi, Location…)
│   ├── constants.py        Waves, effect types, curves, note names
│   ├── sysex.py            SysEx messages, checksum, Location, .syx/.mid I/O
│   ├── patches.py          Single, Source, Amp, Filter, Multi, Section, Drum, Effect
│   ├── bank.py             Bank and load_collection
│   ├── params.py           Parameter numbers for Parameter Send
│   ├── editing.py          Editable parameter tables (all patch types), undo/redo
│   ├── midi.py             K4Midi, SysexInput, test_note_plan
│   ├── fake.py             FakeK4 (simulator)
│   ├── i18n.py             _(), N_(), _n(), language detection
│   ├── locales/            en.py, fr.py (Spanish is the source language)
│   ├── cli.py              Command line
│   └── __main__.py         python -m k4lib
├── k4app/                  Desktop application
│   ├── app.py              Main window and actions
│   ├── details.py          Detail panels for each patch type
│   ├── dialogs.py          Connect, download, send
│   ├── editor.py           Patch editor (controls generated from k4lib.editing)
│   ├── widgets.py          Envelopes, keyboard zones, tables, scrolling
│   ├── worker.py           MIDI worker thread
│   ├── settings.py         User settings (JSON)
│   ├── theme.py            ttk style
│   ├── data/               A401.SYX (sample factory bank), icons
│   └── __main__.py         python -m k4app
├── tests/
│   ├── A401.SYX            Factory bank used by the tests
│   ├── conftest.py         Runs the tests in Spanish (source language)
│   ├── test_k4lib.py       Library, simulator and MIDI tests
│   ├── test_editing.py     Editable parameter table and history
│   └── test_i18n.py        Translation catalog checks
├── tools/gui_smoke.py      GUI smoke test (Xvfb + simulator)
├── packaging/              PyInstaller: .spec, version info, construir_exe.bat
├── docs/                   This documentation
└── pyproject.toml
```

Source comments and docstrings are written in Spanish.

---

## 3. Development setup

```bash
git clone https://github.com/<user>/<repository>.git
cd <repository>
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[midi,dev]"
pytest
```

| Extra | Installs | Needed for |
|---|---|---|
| (none) | — | Reading, editing and saving `.syx` |
| `midi` | `mido`, `python-rtmidi` | `.mid` files and talking to the K4 |
| `dev` | `pytest` | Tests |

**Windows:** `python-rtmidi` 1.5.8 only ships Windows wheels for **CPython 3.12**. With
other versions pip tries to compile it and usually fails without a configured C++
compiler. With the Python launcher: `py -3.12 -m pip install -e ".[midi,dev]"`.

**Linux:** Tkinter may require `sudo apt install python3-tk`; `python-rtmidi` needs the
ALSA headers (`libasound2-dev`) when no wheel is available.

Installed entry points:

| Command | Same as |
|---|---|
| `k4 …` | `python -m k4lib …` |
| `kalima [file]` | `python -m k4app [file]` |

---

## 4. Using the library from Python

### 4.1 Reading and inspecting a bank

```python
from k4lib import Bank, Location

bank = Bank.from_file("tests/A401.SYX")      # .syx or .mid; full, blocks or single dumps
print(bank.is_complete, "card" if bank.external else "internal")

for i, s in enumerate(bank.singles):
    print(Location(False, i), s.name, s.effect_number)

s = bank.singles[0]                           # Single A-1
print(s.summary())                            # name, volume, effect, mode, active waves
print(s.sources[0].wave, s.sources[0].wave_name)   # 18 'Triangle'  (front panel: 19)
print(s.amps[0].attack, s.filters[0].cutoff)
print(s.source_active(2))                     # does S3 sound?
print(bank.effects[s.effect].summary())

m = bank.multis[0]
for sec in m.sections:
    if not sec.muted:
        print(bank.singles[sec.single].name, sec.channel + 1, sec.low_key, sec.high_key)

print(bank.drum.notes[0].s1.wave_name)        # note C1 (MIDI 36)
```

All models are `dataclasses`. `patch.to_dict()` returns a nested dictionary (handy for
JSON) and `patch.fingerprint()` a hash used to detect duplicates.

### 4.2 Editing and saving

```python
s = bank.singles[5]
s.name = "My Sound"                   # padded or cut to 10 characters
s.sources[1].wave = 200               # 0..255 (front panel 1..256)
s.filters[0].env_depth = -20          # bipolar values are already centered on 0
s.wheel_depth = 12

bank.save("my-bank.syx")              # one full dump, or block dumps if incomplete
bank.save("my-bank.mid")              # standard MIDI file with spaced SysEx events
```

### 4.3 Dependencies and reordering

```python
bank.single_users()        # {single: [(multi, section), …]}  unmuted sections
bank.effect_users()        # {effect: {"singles": […], "multis": […]}}
bank.unused_singles()      # Singles not used by any Multi
bank.unused_effects()

bank.swap_singles(0, 63)   # swap and rewrite the Multi sections
bank.move_single(0, 40)    # move, shifting the ones in between (like dragging)
bank.swap_effects(0, 31)   # swap and rewrite Singles and Multis

# copy a Single from another bank, bringing its effect along
other = Bank.from_file("other.syx")
src = other.singles[3]
bank.import_single(src, dst=10, effect=other.effects[src.effect])

bank.validate()            # references to patches that are not loaded
bank.find("bass")          # [("single", 58, "Round Bass"), …]
bank.duplicates()          # groups of Singles identical except for the name
```

Editing through the parameter table (`k4lib.editing`), which validates ranges and
knows how each value is shown on the front panel:

```python
import time
from k4lib.editing import SINGLE_PARAMS, History, get_value, set_value, set_name

s = bank.singles[5]
h = History(s)                                  # undo/redo by snapshots
h.before_change("dcf.cutoff/0", time.monotonic())
set_value(s, SINGLE_PARAMS["dcf.cutoff"], 60, 0)  # filter 1 (index 1 = filter 2)
set_value(s, SINGLE_PARAMS["src.wave"], 196, 1)   # S2; ValueError if out of range
SINGLE_PARAMS["src.wave"].display(196)          # '197 · …' as on the front panel
SINGLE_PARAMS["src.coarse"].parse("+12")        # 12 (accepts panel units and names)
set_name(s, "New Pad")                          # 10 printable ASCII characters
h.undo(); h.redo(); h.revert()
```

Collections of files:

```python
from k4lib import load_collection
for b in load_collection("C:/Music/K4"):       # recursive; ignores non-K4 files
    for kind, i, name in b.find("pad"):
        print(b.source, kind, i, name)
```

### 4.4 Talking to the K4

```python
from k4lib.midi import K4Midi, list_ports

print(list_ports())                            # (inputs, outputs)

with K4Midi("UM-ONE", channel=1) as k4:        # port name, or part of it
    bank = k4.get_bank()                       # full internal bank (~5 s)
    ext = k4.get_bank(external=True)           # memory card
    s = k4.get_single("A-1")
    m = k4.get_multi("B-3")
    e = k4.get_effect(5)                       # 1..32
    d = k4.get_drum()
    part = k4.get_block("single")              # partial Bank with the 64 Singles

    k4.audition(s, "A-1")                      # hear it without saving: Single mode + load + chord
    k4.audition(m, "B-3", test_notes="note")   # a Multi, one note per MIDI section
    k4.send_to_edit_buffer(s)                  # only load it into the edit buffer
    k4.audition_drum(d, 2)                     # play drum key D (MIDI 38) on the drum channel
    k4.set_parameter("filter_cutoff", 60, section=0)   # real time
    k4.program_change("A-3")                   # select a Single
    k4.program_change("A-1", multi=True)       # select a Multi

    k4.write_single(s, "D-16")                 # write and wait for the 0x40 confirmation
    k4.write_bank(bank, progress=lambda n, t: print(n, t))
```

`K4Midi(port=None, *, in_port=None, out_port=None, channel=1, timeout=3.0, pause=0.12)`:

- `port` matches the same substring in inputs and outputs; `in_port` / `out_port`
  choose them separately.
- `pause` is the wait after each sent message (the K4 is slow at processing SysEx).
- Errors (no reply, write-protected memory, no card, checksum) raise `k4lib.K4Error`
  with a translated message. When no reply arrives, the message tells apart “no data
  arrived” (port or cable), “bytes arrived but no complete SysEx” (an interface losing
  data) and “something else arrived” (channel).
- Output uses `mido`; **input reads directly from `python-rtmidi`** through
  `k4lib.midi.SysexInput`, which reassembles chunked SysEx messages (see §9.8).
- The timeout counts from the last byte received, so a long dump does not time out
  while it is still arriving.
- `K4Midi.with_ports(inp, out, …)` builds a connection from already-open (or fake)
  ports, which is how the chunking tests work.

Slots are accepted as a `Location`, as text (`"A-1"`, `"d16"`, `"E-B-3"` = card,
`"64"`) or as an integer index 0..63.

### 4.5 Simulator

```python
from k4lib import Bank
from k4lib.fake import FakeK4

k4 = FakeK4(Bank.from_file("tests/A401.SYX"),     # internal memory
            external_bank=None,                   # None = no card
            channel=1, speed=0.0,                 # speed=1 simulates real MIDI speed
            write_protect=False)
bank = k4.get_bank()                              # same interface as K4Midi
k4.write_single(bank.singles[0], "D-16")
k4.edit_buffer, k4.edit_buffer_multi, k4.notes, k4.parameters, k4.received   # state for tests
```

### 4.6 Low-level messages

```python
from k4lib.sysex import (Message, Location, one_dump_request, block_dump_request,
                         all_dump_request, one_data_dump, edit_buffer_dump,
                         parameter_send, program_bank_select, checksum, read_syx, write_syx)

one_dump_request(0, "single", Location.parse("A-1")).to_bytes().hex(" ")
# 'f0 40 00 00 00 04 00 00 f7'

msg = Message.parse(bytes.fromhex("F0 40 00 22 00 04 00 00 F7"))
msg.channel, msg.function, msg.sub1, msg.sub2, msg.data

for m in read_syx("file.syx"):
    print(m.describe())
```

---

## 5. Command line

```bash
python -m k4lib list  bank.syx [--multis] [--effects] [--drum] [--all]
python -m k4lib show  bank.syx A-1 [--json]      # details of a Single
python -m k4lib show  bank.syx M:A-1             # details of a Multi
python -m k4lib refs  bank.syx                   # dependencies and unused effects
python -m k4lib find  folder text                # search by name in every .syx
python -m k4lib dups  folder                     # identical Singles across files
python -m k4lib ports
python -m k4lib get   out.syx  --port UM-ONE [--channel 1] [--ext]
python -m k4lib put   bank.syx --port UM-ONE [--channel 1] [--ext]
python -m k4lib --lang en|es|fr …                # output language
```

---

## 6. Desktop application architecture

| Module | Responsibility |
|---|---|
| `app.K4App` | Window, menus, toolbar, lists (one `ttk.Treeview` per tab), open bank state, file and MIDI actions |
| `details.DetailPanel` | Rebuilt on every selection: `show_single`, `show_multi`, `show_effect`, `show_drum`, `show_editor` |
| `editor.PatchEditor` | Editor for any patch type: one control per parameter and copy (source, filter, section, submix, Drum source), generated from `k4lib.editing.TABLES` |
| `widgets` | `ScrollFrame`, `table()`, `kv_grid()`, `section()`, `EnvelopeView` (Canvas), `KeyboardZones` (Canvas) |
| `dialogs` | Modal `Dialog` base with validation; `ConnectDialog`, `DownloadDialog`, `SendDialog` return an options `dict` |
| `worker.Worker` | Single MIDI thread |
| `settings` | Language and test note, stored as JSON per user |
| `theme` | Palette, fonts and ttk styles (`clam`) |

**Threading model.** Tkinter is not thread-safe, and talking to the K4 is slow (a full
bank takes ~5 s). `Worker` keeps a dedicated thread that runs tasks **one at a time**
(the K4 cannot handle interleaved conversations). Each task is a function
`fn(progress)`; the thread posts events to a queue and the Tk thread collects them with
`root.after()` every 40 ms to call `on_done`, `on_error` or `on_progress`. No widget is
touched from the MIDI thread.

**Dialog / action split.** Each action has two methods: one that opens the dialog
(`connect`, `download`, `send`) and one that runs with an options `dict`
(`connect_with`, `download_with`, `send_with`). Automated tests
(`tools/gui_smoke.py`) go through the flows without interaction. The confirmation
before writing to the K4 goes through `app.confirm`, which tests can replace.

**List identifiers.** The `iid` of each `Treeview` row is the patch index (`"0"`…`"63"`);
`app.selected` stores `(kind, index)`. Menu entries that need a connection are
enabled/disabled by position, not by label, because labels are translated.

**Patch editor.** “Edit” (button, context menu) sets `app.editing = (kind, index)`
and opens `PatchEditor` in the detail panel; selecting another patch or loading
another bank closes it. The Drum is edited as a whole, so moving between its keys keeps
the editor open on the new key (`editing = ("drum", None)`). Every parameter is a
`k4lib.editing.Param` (scope, attribute, range, display offset, kind, Parameter Send
name), so the controls are generated, not written by hand: `Spinbox` for numbers,
read-only `Combobox` for lists, waves, notes, effects (with the bank's effect types)
and Singles (with the bank's names), `Checkbutton` for switches. Each table has a
layout (`TABLES[kind][1]`) of sections with one of three arrangements: `pairs`
(common parameters), `columns` (parameter × S1–S4, F1–F2 or the Drum key's S1–S2;
unused Single sources are marked in the column header) and `rows` (one row per Multi
section or effect submix). The editor redraws what depends on several values: the
envelopes of a Single, the keyboard zones of a Multi and the parameter names of an
effect, which change with its type. Each change goes through `History.before_change`; repeated changes of
the same control within one second (holding a spin arrow) are merged into one undo
step. Undo/redo restore the snapshot **into the same object**, so the bank and the
editor keep their references. Ctrl+Z, Ctrl+Y and Ctrl+Shift+Z work while the editor is
open. The mouse wheel over a control scrolls the panel instead of changing the value.

**Live editing.** With the K4 connected and “Send changes to the K4 while editing”
checked (saved in the settings), `app.patch_edited` schedules `_live_flush` 120 ms
after the last change, so a burst of changes produces one message. The flush sends a
copy of the patch (the MIDI thread never touches the bank's object). For a Single or a
Multi: the first time, a Program Change to its slot to put the K4 in that mode and
slot, then function `23` (edit buffer). Nothing is written to the K4's memory.

Effects and the Drum have no edit buffer, so the only way to hear a change is to
**write** them (`write_effect`, `write_drum`), replacing what the K4 has in that slot.
Their checkbox (“Write every change to …”, `app.live_write`) is off whenever editing
starts, asks for confirmation when turned on and is not saved in the settings; the
delay is 300 ms, and any write error (protected memory, no card) turns it off.

**Playing an effect.** An effect makes no sound by itself, so “Play” on an effect
(button, Enter, double-click, context menu) picks the first Single of the bank that
uses it (or, if none, the first Multi) and auditions it as usual: Program Change to its
slot, the file's patch to the edit buffer and the test notes. The patch then matches
the file, but the effect it uses is the one stored in the K4, so the status bar
reminds you to write the effect when editing without “Write every change”. Any other MIDI operation resets
the selected slot, so the next live send selects it again. Parameter Send would be
lighter (3 bytes instead of 140), but resending the whole patch is robust and does not
depend on unconfirmed details such as the filter 2 section number.

**Settings.** `k4app/settings.py` stores a JSON file in `%APPDATA%\Kalima`
(Windows), `~/Library/Application Support/Kalima` (macOS) or
`~/.config/kalima` (Linux). While that file does not exist, the one in the old
`K4Librarian` / `k4librarian` folder is read, so settings survive the rename. The
`K4_SETTINGS` variable points to another file (used by the tests).

---

## 7. Internationalization

The application and the library are available in **Spanish, English and French**.

- **Source language: Spanish.** The Spanish text written in the code is the key.
  `k4lib/locales/en.py` and `fr.py` map each key to its translation.
- **Marking texts** (`k4lib/i18n.py`):
  - `_("Saved {name}", name=…)` translates and fills `{…}` placeholders.
  - `N_("…")` only marks a text defined at module level (evaluated at import time,
    before the language is known); it is translated when displayed with `_(text)`.
  - `_n(singular, plural, n)` handles plurals. The catalog value is a
    `(singular, plural)` tuple. French uses the singular for 0 and 1.
- **Language selection.** `set_language(code)` is called once at startup; `None` means
  “detect”: the `K4_LANG` variable, the Windows UI language, the locale, then
  `LANG`/`LC_*`. Unsupported languages fall back to English. The application reads the
  language from its settings and applies menu changes **on restart**;
  `translate_to(code, text)` shows the restart notice in the newly chosen language.
- **Terms kept untranslated**: the K4's own names, as shown on the instrument
  (Single, Multi, Drum, wave names, Normal/Twin/Double, Poly/Solo, Soft/Loud/All,
  effect types, parameter abbreviations such as Coarse/Fine/ADSR).
- **Catalog check.** `tests/test_i18n.py` extracts every `_()`, `N_()` and `_n()` literal
  from the source and fails if a text has no English or French translation, if a
  translation is unused, if placeholders differ or if a plural is not a pair.

Adding a language: create `k4lib/locales/<code>.py` with `MESSAGES = {…}`, add it to
`LANGUAGES` in `i18n.py` and to `CATALOGS` in the test, and adjust the plural rule in
`_n()` if needed.

---

## 8. The K4 patch system

### 8.1 Memory

The K4 has an **internal memory** and an optional **memory card** (RAM/ROM), both with
the same organization:

| Type | Count | Numbering | Contents |
|---|---|---|---|
| Single | 64 | A-1 … D-16 (4 groups × 16) | A complete sound |
| Multi | 64 | A-1 … D-16 | Combination of up to 8 Singles |
| Effect | 32 | 1 … 32 | Effect processor program |
| Drum | 1 | — | 61-note drum kit |

Over MIDI, Singles respond to Program Change 0–63 and Multis to 64–127; internal memory
or card is selected with a SysEx message first (§9.4).

### 8.2 Dependencies by slot number

Patches **do not contain** what they use: they reference it by slot.

```
Multi ──(8 sections)──► Single A-1…D-16
Multi ────────────────► Effect 1…32
Single ───────────────► Effect 1…32
Drum: no references (uses waves directly)
```

In practice, reordering Singles or effects, or mixing patches from different banks,
changes the sound of the Multis and Singles pointing at those slots.
`Bank.swap_singles`, `move_single`, `swap_effects` and `import_single` rewrite the
references to avoid that.

### 8.3 Single

A Single combines up to **4 sources** (S1–S4). Each source plays one of the **256 ROM
waveforms** (*Digital Multi Spectrum* synthesis: single-cycle waves, PCM-type waves and
attack/percussion samples) and has its own amplitude envelope (DCA).

| Block | Parameters |
|---|---|
| Common | Name (10 chars), volume, effect (1–32), submix/output (A–H) |
| Source mode | **Normal**: 2 sources (S1, S2) · **Twin** and **Double**: 4 sources |
| Polyphony | Poly 1, Poly 2, Solo 1, Solo 2 |
| AM | Amplitude modulation S1→S2 and S3→S4 |
| Source (×4) | Wave, delay, coarse (±24 semitones) and fine (±50) tuning, key tracking or fixed note, key scaling curve (1–8), velocity curve (1–8), pressure→pitch and vibrato/auto bend switches, mute |
| DCA (×4) | Level, ADSR envelope, level modulation by velocity / pressure / key scaling, time modulation by note-on velocity / note-off velocity / key scaling |
| DCF (×2) | Resonant low-pass filter: cutoff, resonance (0–7), LFO on/off, cutoff modulation by velocity / pressure / KS, its own ADSR envelope with depth and velocity depth, time modulation. DCF1 processes the S1–S2 pair and DCF2 the S3–S4 pair |
| LFO | Shape (triangle, sawtooth, square, random), speed, delay, depth, pressure→depth |
| Vibrato | Shape, speed, depth, pressure→depth |
| Auto bend | Time, depth, KS→time, velocity→depth |
| Controllers | Pitch bend range (0–12), wheel assignment (vibrato, LFO, DCF) and depth, pressure→pitch |

On the front panel waves are numbered **1–256**; in SysEx and in `k4lib`, **0–255**. The
same applies to effects (1–32 / 0–31) and curves (1–8 / 0–7).

### 8.4 Multi

A Multi has a name, volume, effect and **8 sections**. Each section defines:

| Parameter | Values |
|---|---|
| Single | 0–63 (A-1…D-16) |
| Zone | Low and high note (0–127) |
| Receive channel | 1–16 |
| Velocity switch | Soft, Loud, All |
| Mode | Keyboard (keyboard only), MIDI (MIDI only), Mix (both) |
| Mute | yes/no |
| Level | 0–100 |
| Transpose | ±24 semitones |
| Tune | ±50 |
| Submix | A–H |

With sections on different channels in MIDI mode, the K4 works as a multitimbral module
with up to 8 parts.

### 8.5 Drum

A single kit of **61 notes**, C1 to C6 (MIDI notes 36–96). Each note has a submix (A–H)
and **two sources**, each with wave, decay (1–100), tune (±50) and level (0–100). The
common part sets the kit's MIDI channel, volume and velocity sensitivity.

### 8.6 Effect

16 effect types (index 0–15) with three parameters whose meaning depends on the type:

| # | Type | P1 (±7) | P2 (±7) | P3 (0–31) |
|---|---|---|---|---|
| 1–4 | Reverb 1–4 | Pre.delay | Rev.Time | Tone |
| 5 | Gate Reverb | Pre.delay | Gate Time | Tone |
| 6 | Reverse Gate | Pre.delay | Gate Time | Tone |
| 7 | Normal Delay | Feedback | Tone | Delay |
| 8 | Stereo Panpot Delay | Feedback | L/R Delay | Delay |
| 9 | Chorus | Width | Feedback | Rate |
| 10 | Overdrive + Flanger | Drive | Fl.Type | 1-2 Bal |
| 11 | Overdrive + Normal Delay | Drive | Delay Time | 1-2 Bal |
| 12 | Overdrive + Reverb | Drive | Rev.Type | 1-2 Bal |
| 13 | Normal Delay + Normal Delay | Delay1 | Delay2 | 1-2 Bal |
| 14 | Normal Delay + Stereo Panpot Delay | Delay1 | Delay2 | 1-2 Bal |
| 15 | Chorus + Normal Delay | Chorus | Delay | 1-2 Bal |
| 16 | Chorus + Stereo Panpot Delay | Chorus | Delay | 1-2 Bal |

Each effect program also defines, for the **8 submixes (A–H)**, a pan (±7) and two send
levels. Singles and Drum notes are assigned to a submix. On the **K4r** (rack version,
with individual outputs) the sends are not used and the pan value selects the output.

---

## 9. System Exclusive protocol

### 9.1 Header

```
F0 40 0n ff 00 04 [body…] F7
│  │  │  │  │  │
│  │  │  │  │  └─ machine ID: 04 = K4/K4r
│  │  │  │  └──── group: 00 = synthesizers
│  │  │  └─────── function (§9.2)
│  │  └────────── MIDI channel − 1 (00 = channel 1). The K4 ignores other channels
│  └───────────── manufacturer: 40 = Kawai
└──────────────── start of SysEx
```

In dumps and requests the body starts with two *substatus* bytes, **s1** and **s2**,
which identify the patch (§9.3). In `k4lib`: `Message(channel, function, body)`, with
`sub1`, `sub2` and `data` (= `body[2:]`).

### 9.2 Functions

| Code | Name | Direction | Body |
|---|---|---|---|
| `00` | One patch dump request | → K4 | s1 s2 |
| `01` | Block patch dump request | → K4 | s1 s2 |
| `02` | All patch dump request | → K4 | s1 s2 |
| `10` | Parameter send | → K4 | pp ss vv (§9.6) |
| `20` | One patch data dump | ↔ | s1 s2 data |
| `21` | Block patch data dump | ↔ | s1 s2 data |
| `22` | All patch data dump | ↔ | s1 s2 data |
| `23` | Edit buffer dump | → K4 | `00 00` + Single, or `00 40` + Multi |
| `30` | Program change (memory) | → K4 | 00 = internal, 02 = card |
| `40` | Write complete | ← K4 | — |
| `41` | Write error | ← K4 | — |
| `42` | Write error: protected | ← K4 | — |
| `43` | Write error: no card | ← K4 | — |

### 9.3 Addressing (s1, s2)

Bit 1 of s1 (value `02`) means **memory card**; bit 0 (value `01`) separates effects and
the Drum from Singles and Multis.

| Patch | s1 internal / card | s2 |
|---|---|---|
| Single A-1…D-16 | `00` / `02` | `00`–`3F` (0–63) |
| Multi A-1…D-16 | `00` / `02` | `40`–`7F` (64–127) |
| Effect 1–32 | `01` / `03` | `00`–`1F` (0–31) |
| Drum | `01` / `03` | `20` |
| Block of Singles | `00` / `02` | `00` |
| Block of Multis | `00` / `02` | `40` |
| Block of effects | `01` / `03` | `00` |
| Full bank | `00` / `02` | `00` |

### 9.4 Message flows

**Reading.** Send a request (`00`, `01` or `02`) and the K4 answers with the matching dump
(`20`, `21` or `22`) carrying the same s1/s2. If the patch does not exist (e.g. no card),
the K4 does not answer: a timeout is required.

```
→ F0 40 00 00 00 04 00 05 F7                      request: internal Single A-6
← F0 40 00 20 00 04 00 05 [131 bytes] F7          dump
```

**Writing.** Send the dump with the target slot and the K4 answers `40` (success) or an
error `41`–`43`:

```
→ F0 40 00 20 00 04 00 3F [131 bytes] F7          write to D-16
← F0 40 00 40 00 04 F7                            write complete
```

`K4Midi.write_bank` writes patch by patch (161 messages) and requires the `40` reply for
each one: slower than a full dump, but it detects any failure.

**Edit buffer.** `F0 40 0n 23 00 04 00 00 [131 bytes] F7` loads a Single into the edit
buffer, and `F0 40 0n 23 00 04 00 40 [77 bytes] F7` a Multi; nothing is saved. **They
only sound if the K4 is in the matching mode**: a Single loaded while the K4 is on a
Multi is not heard. There is **no** reverse operation: the edit buffer cannot be read.

**Selecting a program.** `F0 40 0n 30 00 04 00|02 F7` selects internal memory or card,
then a standard Program Change selects the patch. The K4 needs about 100–200 ms after
each change.

**Playing a patch from the file** (`K4Midi.audition`, “Play on K4” button):

1. `F0 40 0n 30 00 04 00|02 F7` + Program Change to the patch's slot (0–63 Single, 64–127
   Multi). This puts the K4 in the right mode; then wait ~200 ms.
2. Edit buffer dump, which replaces what the Program Change just loaded.
3. Test notes (`test_note_plan`): C4 or a C major chord on the K4's channel. A Single in
   Solo mode gets a single note. For a Multi, notes go to the channel of each active
   section in MIDI or Mix mode, inside its zone, with a velocity matching its velocity
   switch (Soft 50, Loud 115, All 100). Sections in Keyboard mode do not respond to MIDI.

A Multi played this way uses the Singles **stored in the K4** at the slots its sections
point to, not the ones in the file.

**Playing a Drum key** (`K4Midi.audition_drum`): the Drum has no edit buffer, so the only
way to hear it without writing is to play the key (MIDI note 36 + index) on the Drum's
receive channel; what sounds is the Drum **stored in the K4**. With `compare=True` the
K4's Drum is requested first and the method returns whether it matches the file's
(`None` if the K4 did not answer). The application checks only once per Drum and
connection, and says when the K4's Drum differs ("Write Drum to K4…" to hear the file's).

### 9.5 Checksum

```
checksum = (0xA5 + sum of the data bytes) & 0x7F
```

It is placed at the end of every Single, Multi and Effect; in the Drum, at the end of the
common part and of each note (the Drum has no overall checksum). A wrong checksum in a
write produces reply `41`.

### 9.6 Parameter Send (function `10`)

Changes a parameter of the Single being edited, in real time:

```
F0 40 0n 10 00 04 pp ss vv F7
   pp  parameter number (table below)
   ss  = (section << 1) | bit 7 of the value
   vv  = low 7 bits of the value
```

The **section** is the source (0–3 = S1–S4) for source and DCA parameters, and the filter
for DCF parameters (`k4lib` uses 0 = F1, 2 = F2, following Edisyn). The value's high bit
is only needed for the wave (0–255). Values are sent **raw** (e.g. a depth of −20 is sent
as 30).

| pp | Parameter | Raw range | pp | Parameter | Raw range |
|---|---|---|---|---|---|
| 0–9 | Name (ASCII) | 32–127 | 37 | S coarse | 0–48 |
| 10 | Volume | 0–100 | 38 | S key track | 0–1 |
| 11 | Effect | 0–31 | 39 | S fixed key | 0–127 |
| 12 | Submix | 0–7 | 40 | S fine | 0–100 |
| 13 | Source mode | 0–2 | 41 | S pressure→pitch | 0–1 |
| 14 | Polyphony | 0–3 | 42 | S vibrato/auto bend | 0–1 |
| 15 | AM 1→2 | 0–1 | 43 | S velocity curve | 0–7 |
| 16 | AM 3→4 | 0–1 | 44 | DCA level | 0–100 |
| 17 | Vibrato shape | 0–3 | 45–48 | DCA A, D, S, R | 0–100 |
| 18 | Pitch bend range | 0–12 | 49–51 | DCA level by vel/prs/KS | 0–100 |
| 19 | Wheel assignment | 0–2 | 52–54 | DCA time by vel on/off/KS | 0–100 |
| 20 | Vibrato speed | 0–100 | 55 | DCF cutoff | 0–100 |
| 21 | Wheel depth | 0–100 | 56 | DCF resonance | 0–7 |
| 22–25 | Auto bend time, depth, KS, vel | 0–100 | 57 | DCF LFO | 0–1 |
| 26 | Vibrato pressure | 0–100 | 58–60 | DCF cutoff by vel/prs/KS | 0–100 |
| 27 | Vibrato depth | 0–100 | 61 | DCF envelope depth | 0–100 |
| 28 | LFO shape | 0–3 | 62 | DCF env. by velocity | 0–100 |
| 29 | LFO speed | 0–100 | 63–66 | DCF A, D, S, R | 0–100 |
| 30 | LFO delay | 0–100 | 67–69 | DCF time by vel on/off/KS | 0–100 |
| 31 | LFO depth | 0–100 | | | |
| 32 | LFO pressure | 0–100 | | | |
| 33 | Pressure→pitch | 0–100 | | | |
| 34 | S delay | 0–100 | | | |
| 35 | S KS curve | 0–7 | | | |
| 36 | S wave | 0–255 | | | |

`k4lib.params.PARAMETERS` holds the same table with names, offsets and front-panel
ranges; `K4Midi.set_parameter("filter_env_depth", -20)` does the conversion.

Examples (channel 1):

```
filter 1 cutoff = 50          F0 40 00 10 00 04 37 00 32 F7
S2 wave = 201 (index 200)     F0 40 00 10 00 04 24 03 48 F7   (ss = 1<<1 | 1)
```

### 9.7 Timing

MIDI runs at 31,250 baud, about **3,125 bytes/s**:

| Message | Bytes | Transmission time |
|---|---|---|
| One Single | 140 | ~45 ms |
| Block of 64 Singles | 8,393 | ~2.7 s |
| Full bank | 15,123 | ~4.8 s |

`K4Midi` waits `pause` (0.12 s) after each send, and its timeouts count from the last
byte received.

### 9.8 Long SysEx on Windows

The Windows MIDI driver (WinMM, used by RtMidi) receives SysEx in 1 KB buffers and
delivers longer messages **in several chunks**. `mido` 1.3 converts each chunk with
`Message.from_bytes` and **silently drops** the ones that are not a complete message,
so a bank dump (15 KB) never arrives even though the K4 reports *data dump completed*.
Short messages (a Single, 140 bytes) do arrive.

`SysexInput` reads from `rtmidi.MidiIn` without going through `mido` and rebuilds each
SysEx byte by byte: it starts at `F0`, ignores interleaved real-time messages
(`F8`–`FF`), discards the message if another status byte appears, and completes it at
`F7`. `python-rtmidi` 1.5.8 does not allow enlarging those buffers, so reassembly is the
only solution.

---

## 10. Byte-by-byte data format

Notation: values marked **±N** are stored with an offset of N (0 in SysEx = −N). Bits not
listed are unused (see §11.2).

### 10.1 Single (131 bytes)

| Byte | Bits | Contents | Range |
|---|---|---|---|
| 0–9 | | ASCII name | |
| 10 | 0–6 | Volume | 0–100 |
| 11 | 0–4 | Effect | 0–31 |
| | 5–6 | *Reserved* (0x20 in every factory patch) | |
| 12 | 0–2 | Submix / output | 0–7 (A–H) |
| 13 | 0–1 | Source mode | 0 Normal, 1 Twin, 2 Double |
| | 2–3 | Polyphony | 0 Poly1, 1 Poly2, 2 Solo1, 3 Solo2 |
| | 4 | AM S1→S2 | |
| | 5 | AM S3→S4 | |
| 14 | 0–3 | Mute S1…S4 (**1 = muted**, see §11.1) | |
| | 4–5 | Vibrato shape | 0–3 |
| 15 | 0–3 | Pitch bend range | 0–12 |
| | 4–5 | Wheel assignment | 0 Vibrato, 1 LFO, 2 DCF |
| 16 | | Vibrato speed | 0–100 |
| 17 | | Wheel depth | ±50 |
| 18 | | Auto bend: time | 0–100 |
| 19 | | Auto bend: depth | ±50 |
| 20 | | Auto bend: KS → time | ±50 |
| 21 | | Auto bend: velocity → depth | ±50 |
| 22 | | Vibrato: pressure → depth | ±50 |
| 23 | | Vibrato: depth | ±50 |
| 24 | 0–1 | LFO: shape | 0–3 |
| 25 | | LFO: speed | 0–100 |
| 26 | | LFO: delay | 0–100 |
| 27 | | LFO: depth | ±50 |
| 28 | | LFO: pressure → depth | ±50 |
| 29 | | Pressure → pitch | ±50 |
| 30–57 | | **Sources** (7 parameters × 4, interleaved) | |
| 58–101 | | **DCA** (11 parameters × 4, interleaved) | |
| 102–129 | | **DCF** (14 parameters × 2, interleaved) | |
| 130 | | Checksum | |

**Interleaving.** The source, DCA and DCF blocks are not stored source by source but
**parameter by parameter**: parameter *k* of source *i* is at `start + k × N + i`, with
N = 4 (sources and DCA) or 2 (DCF). For example, the delays of S1–S4 are bytes 30, 31,
32 and 33.

Source parameters (k = 0…6, base 30):

| k | Bits | Contents | Range |
|---|---|---|---|
| 0 | | Delay | 0–100 |
| 1 | 0 | Bit 7 of the wave | |
| | 4–6 | Key scaling curve | 0–7 |
| 2 | 0–6 | Low 7 bits of the wave | wave = (b1 & 1) << 7 \| b2 → 0–255 |
| 3 | 0–5 | Coarse tuning | ±24 |
| | 6 | Key tracking (0 = fixed note) | |
| 4 | | Fixed note | 0–127 |
| 5 | | Fine tuning | ±50 |
| 6 | 0 | Pressure → pitch | |
| | 1 | Vibrato / auto bend | |
| | 2–4 | Velocity curve | 0–7 |

DCA (k = 0…10, base 58): level, attack, decay, sustain, release (0–100); level by
velocity, pressure and KS (±50); time by note-on velocity, note-off velocity and KS (±50).

DCF (k = 0…13, base 102): cutoff (0–100); resonance (bits 0–2, 0–7) + LFO (bit 3);
cutoff by velocity, pressure and KS (±50); envelope depth (±50); depth by velocity
(±50); attack, decay (0–100); sustain (±50); release (0–100); time by velocity on/off
and KS (±50).

### 10.2 Multi (77 bytes)

| Byte | Contents |
|---|---|
| 0–9 | ASCII name |
| 10 | Volume (0–100) |
| 11 | Effect (0–31) |
| 12–75 | 8 sections × 8 bytes (consecutive, **not** interleaved) |
| 76 | Checksum |

Section (8 bytes):

| Offset | Bits | Contents | Range |
|---|---|---|---|
| 0 | | Single | 0–63 |
| 1 | | Low note | 0–127 |
| 2 | | High note | 0–127 |
| 3 | 0–3 | Receive channel | 0–15 |
| | 4–5 | Velocity switch | 0 Soft, 1 Loud, 2 All |
| | 6 | Muted | |
| 4 | 0–2 | Submix | 0–7 |
| | 3–4 | Mode | 0 Keyboard, 1 MIDI, 2 Mix |
| 5 | | Level | 0–100 |
| 6 | | Transpose | ±24 |
| 7 | | Tune | ±50 |

### 10.3 Drum (682 bytes)

| Byte | Contents |
|---|---|
| 0 | MIDI channel (0–15) |
| 1 | Volume (0–100) |
| 2 | Velocity → level (±50) |
| 3–9 | *Reserved* (not zero in the factory bank) |
| 10 | Checksum of bytes 0–9 |
| 11–681 | 61 notes × 11 bytes |

Note (11 bytes): two 5-byte sources interleaved (`S1b0 S2b0 S1b1 S2b1 …`) and a checksum
of those 10 bytes.

| Source byte | Bits | Contents |
|---|---|---|
| b0 | 0 | Bit 7 of the wave |
| | 4–6 | Submix (S1 only) |
| b1 | 0–6 | Low 7 bits of the wave |
| b2 | | Decay (1–100) |
| b3 | | Tune (±50) |
| b4 | | Level (0–100) |

### 10.4 Effect (35 bytes)

| Byte | Contents |
|---|---|
| 0 | Type (0–15) |
| 1 | Parameter 1 (±7) |
| 2 | Parameter 2 (±7) |
| 3 | Parameter 3 (0–31) |
| 4–9 | *Reserved* (not zero in the factory bank) |
| 10–33 | 8 submixes × 3 bytes: pan (±7), send 1 (0–100), send 2 (0–100) |
| 34 | Checksum |

### 10.5 Full bank (15,123 bytes)

| Offset in the message | Contents | Bytes |
|---|---|---|
| 0–7 | `F0 40 0n 22 00 04 s1 00` | 8 |
| 8 | 64 Singles | 64 × 131 = 8,384 |
| 8,392 | 64 Multis | 64 × 77 = 4,928 |
| 13,320 | Drum | 682 |
| 14,002 | 32 effects | 32 × 35 = 1,120 |
| 15,122 | `F7` | 1 |

Data: 15,114 bytes. Block dumps use the same order and sizes for their type (64 Singles,
64 Multis or 32 effects).

---

## 11. Manual errata and observed behavior

### 11.1 Inverted source mute bit

The manual says a 0 in byte 14 mutes the source. **It is the other way round: 1 = muted.**
Verified with the A401 factory bank: in Normal mode, sources 3 and 4 (which are unused)
have the bit set in 46 of the 54 patches (85%), and in Twin/Double all of them are 0.
Edisyn reaches the same conclusion. In `k4lib`, `Single.source_mute_bits` keeps the raw
bits and `Single.source_active(i)` interprets them.

### 11.2 Reserved bits and bytes

The K4 sends values in bits the manual does not document:

- Bit 5 of byte 11 of the Singles is `0x20` in all 64 factory patches.
- Bytes 4–9 of the effects and 3–9 of the Drum, described as padding, are not zero.
- In Multi sections, bit 6 of byte 0 and bits 5–6 of byte 4 are 0 in the factory bank
  but set in some third-party banks (bit 5 of byte 4 in every section of one of them).
- Name character `0x7F`, used by some factory banks, is shown on HD44780-type displays
  like the K4's as a left arrow; `k4lib` represents it as “←” and writes it back as `0x7F`.

`k4lib` keeps them (`Single.s11_reserved`, `Effect.reserved`, `Drum.reserved`,
`Section.reserved`) so that
reading and rewriting a bank does not alter it: every complete bank in a collection of
about 50 real banks comes back byte for byte. `fingerprint()` and `canonical_bytes()`
ignore them when comparing patches. On reading, all other fields are masked to their
documented bits.

### 11.3 Velocity switch order

The order is **0 = Soft, 1 = Loud, 2 = All** (as in Edisyn). In the factory bank 452 of
the 512 sections have value 2, which only makes sense if 2 = All. Other sources list the
values as All/Soft/Loud, which is wrong.

### 11.4 Other

- **Edit buffer**: the manual omits or gets s1/s2 wrong for function `23`; `00 00` (Single)
  and `00 40` (Multi) are used, as in Edisyn.
- **Reading the edit buffer**: the K4 does not support it.
- **DCF sustain**: treated as bipolar (±50), as in Edisyn.
- **Filter 2 section in Parameter Send**: `k4lib` uses 2, following Edisyn.
  *To be confirmed with the instrument*; it could be 1.
- **Program Change in Multi mode**: the `RCV PRG` system setting changes how the K4
  interprets Program Change (`SECT` routes them to the Multi sections). If the K4 does
  not change program when playing a patch, check that setting. *To be confirmed.*
- **Timing**: the pause between messages (0.12 s) and the reply timeouts *still need to
  be tuned with the instrument*.
- **MIDI notes** are named with 60 = C4, so 0 = C-1 and 127 = G9.

---

## 12. .syx and .mid files

- **`.syx`**: a raw sequence of SysEx messages (`F0 … F7`). `read_syx` splits them,
  ignores those that are not from the K4 and accepts full, block and single dumps mixed
  in the same file. Some old files omit the final `F7` of each message (for example,
  three block dumps where only the last one is closed): `split_sysex` treats a new `F0`,
  or the end of the file, as the end of the previous message, and the checksum still
  validates the data.
- **Checking and repairing dumps** (`bank.check_dump`, run by `Bank.from_messages`):
  every dump is compared with its expected size and every patch's checksum is
  verified; the problems end up in `Bank.warnings` and the application shows them when
  opening the file.
  - *Text-mode transfers.* Many 1990s files went through FTP, modems or BBSs in text
    mode, which inserted a `0D` before every `0A` (an MS-DOS line break): the dump is
    longer than it should be and everything after the first insertion is shifted. If
    removing `0D` before `0A` restores the exact size and leaves fewer bad checksums
    than before (normally none), the repaired dump is used and `Bank.repaired` is set.
    The file itself is never modified; “Save as” writes a corrected copy.
  - *Zeroed patches.* Some programs save what they do not have (Multis, effects, the
    Drum) as zeros. A patch that is all zeros is left empty (`None`), not reported as
    damaged.
  - *Damaged patches* (bad checksum) are loaded anyway and listed in the warning.
  - A file with only dump *requests* (`F0 40 0n 00/01/02 …`) is refused with a message
    saying so.
- **`.mid`**: a standard MIDI file (SMF type 0) with the SysEx messages as events. It is
  detected by the `MThd` header, not by the extension. When writing
  (`write_midi_file`), each event is separated from the next by the previous message's
  transmission time plus 0.2 s, so a sequencer playing the file back does not overload
  the K4.
- `Bank.save(path)` chooses the format from the extension. A complete bank is saved as a
  single full dump. An incomplete one (`Bank.to_file_messages`) uses a block dump for each
  complete group (64 Singles, 64 Multis, 32 effects) and single dumps for the rest,
  plus the Drum if present.
- In the application, **Save** never overwrites the bundled demo bank, nor a read-only
  file or one in a protected folder: it explains why and opens **Save as**.

---

## 13. Tests

```bash
pytest                      # 220 tests (many parametrized)
```

They cover reading the factory bank, checksum validity, mute semantics, the
**byte-exact round trip**, editing and rewriting patches, message construction,
Parameter Send, slots, reordering with references, importing with an effect,
fingerprints, `.mid` files, the CLI, the simulator (reads, writes, card, protection and
checksum errors, bank write, edit buffer, audition of Singles, Multis and Drum keys), test-note planning, the velocity
switch order, reception of SysEx chunked the way Windows delivers it (with interleaved
noise) and its error messages, files whose dumps lack the final `F7`
(`tests/ZAIDA3.SYX`), block saving of partial banks, repair of text-mode transfers,
damaged and zeroed patches, the editable parameter tables of the four patch types (every model field covered, minimum and maximum of
each parameter surviving the SysEx round trip without touching other fields, ranges
matching the Parameter Send table, display and parsing, undo/redo grouping), and the
translation catalogs (§7).
`tests/conftest.py` runs every test in Spanish, the source language.

GUI smoke test (Linux with Xvfb):

```bash
K4_LANG=en xvfb-run -a -s "-screen 0 1360x900x24" python tools/gui_smoke.py screenshots/
```

It opens the bank, goes through the tabs, filters, connects to the simulator, plays a
Single, a Multi and a Drum key, edits a Single and a Multi (checking that the
simulator's edit buffer receives each change, and undo/redo/revert), an effect (not
written until enabled, then written) and the Drum (switching keys while editing), downloads a patch and the bank, writes a patch and the whole bank,
triggers the no-card error, saves as `.syx` and `.mid` and compares both, and changes the
language, taking a screenshot at each step.

---

## 14. Windows packaging

`packaging/Kalima.spec` builds a single `Kalima.exe` (no console) with
PyInstaller, containing Python, Tkinter, `mido`, `python-rtmidi`, the translations, the
sample bank and the icon. Details:

- `hiddenimports=["mido.backends.rtmidi", …]`: `mido` loads its backend dynamically and
  PyInstaller does not detect it on its own. The translation catalogs
  (`k4lib.locales.en`, `k4lib.locales.fr`) are loaded with `importlib`, so they are
  listed there as well.
- `datas`: `k4app/data` is copied to `k4app/data` inside the executable;
  `Path(__file__).parent / "data"` works the same packaged or not.
- `version_info.txt`: metadata shown in the file's *Properties*.

On Windows with Python 3.12: double-click `packaging\construir_exe.bat` (output in
`dist\Kalima.exe`).

The executable is **not signed**: SmartScreen shows a warning the first time.
Distributing it without that warning requires a code-signing certificate.

---

## 15. Open items and roadmap

- Verify with the instrument: timing, filter 2 section, external dumps, `RCV PRG`.
- Reordering in the GUI (dragging Singles/effects using `move_single` / `swap_effects`).
- Parameter Send instead of resending the whole Single; draggable envelope points;
  comparison with the original.
- Collection library: persistent index (SQLite) with search, tags and duplicates across
  files.
- Parameter-by-parameter patch comparison.
- Continuous integration: tests on GitHub Actions and automatic `.exe` builds on a
  Windows runner.

---

## 16. References and credits

- **Edisyn** (Sean Luke, Apache 2.0 license), `KawaiK4.java` and `KawaiK4Multi.java`:
  Parameter Send table, wave name list, edit buffer addressing, velocity switch order
  and manual errata.
- **ksynth** (Conifer Productions, Rust crate): structure of Multi, Drum, Effect and the
  bank, and the A401 factory bank used in the tests.
- Kawai: *K4/K4r MIDI Implementation* (owner's manual).
- **A401.SYX** is a Kawai factory bank, freely distributed by Kawai USA.

Before publishing the repository, check the licenses of the projects above and add a
`LICENSE` file with the license you choose for this one.
