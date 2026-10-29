"""Tablas de nombres y constantes del Kawai K4/K4r."""

NAME_LENGTH = 10
SINGLE_COUNT = 64
MULTI_COUNT = 64
EFFECT_COUNT = 32
DRUM_NOTE_COUNT = 61          # C1..C6 (notas MIDI 36..96)
DRUM_FIRST_NOTE = 36
SUBMIX_COUNT = 8

GROUPS = "ABCD"

# 256 formas de onda (índice 0..255; el panel las numera 1..256).
# Lista tomada del editor Edisyn (Sean Luke).
WAVES = [
    "Sin 1st", "Sin 2nd", "Sin 3rd", "Sin 4th", "Sin 5th", "Sin 6th", "Sin 7th", "Sin 8th", "Sin 9th",
    "Saw 1", "Saw 2", "Saw 3", "Saw 4", "Saw 5", "Saw 6", "Saw 7", "Saw 8",
    "Pulse", "Triangle", "Square", "Rectangular 1", "Rectangular 2", "Rectangular 3", "Rectangular 4",
    "Rectangular 5", "Rectangular 6",
    "Pure Horn L", "Punch Brass 1", "Oboe 1", "Oboe 2", "Classic Grand",
    "Electric Piano 1", "Electric Piano 2", "Electric Piano 3", "Electric Organ 1", "Electric Organ 2",
    "Positif", "Electric Organ 3", "Electric Organ 4", "Electric Organ 5", "Electric Organ 6",
    "Electric Organ 7", "Electric Organ 8", "Electric Organ 9", "Classic Guitar", "Steel Strings",
    "Harp", "Wood Bass", "Synth Bass 3", "Digibass", "Finger Bass", "Marimba", "Synth Voice",
    "Glass Harp 1", "Cello", "Xylophone", "Electric Piano 4", "Synclavier M", "Electric Piano 5",
    "Electric Organ 10", "Electric Organ 11", "Electric Organ 12", "Big Pipe", "Glass Harp 2", "Random",
    "Electric Piano 6", "Synth Bass 4", "Synth Bass 1", "Synth Bass 2", "Quena", "Oboe 3", "Pure Horn H",
    "Fat Brass", "Punch Brass 2", "Electric Piano 7", "Electric Piano 8", "Synclavier 2",
    "Harpsichord M", "Harpsichord L", "Harpsichord H", "Electric Organ 13", "Koto", "Sitar L", "Sitar H",
    "Pick Bass", "Synth Bass 5", "Synth Bass 6", "Vibraphone Attack", "Vibraphone 1", "Horn Vibe",
    "Steel Drum 1", "Steel Drum 2", "Vibraphone 2", "Marimba Attack", "Harmonica", "Synth", "Kick",
    "Gated Kick", "Snare Tite", "Snare Deep", "Snare Hi", "Rim Snare", "Rim Shot", "Tom", "Tom VR",
    "Electric Tom", "High Hat Closed", "High Hat Open", "High Hat Open VR", "High Hat Foot", "Crash",
    "Crash VR", "Crash VR 2", "Ride Edge", "Ride Edge VR", "Ride Cup", "Ride Cup VR", "Claps", "Cowbell",
    "Conga", "Conga Slap", "Tambourine", "Tambourine VR", "Claves", "Timbale", "Shaker", "Shaker VR",
    "Timpani", "Timpani VR", "Sleighbell", "Bell", "Metal Hit", "Click", "Pole", "Glocken", "Marimba",
    "Piano Attack", "Water Drop", "Char", "Piano Normal", "Piano VR", "Cello Normal", "Cello VR 1",
    "Cello VR 2", "Cello 1-Shot", "Strings Normal", "Strings VR", "Slap Bass L Normal", "Slap Bass L VR",
    "Slap Bass L 1-Shot", "Slap Bass H Normal", "Slap Bass H VR", "Slap Bass H 1-Shot",
    "Pick Bass Normal", "Pick Bass VR", "Pick Bass 1-Shot", "Wood Bass Attack", "Wood Bass Normal",
    "Wood Bass VR", "Fretless Normal", "Fretless VR", "Synth Bass Normal", "Synth Bass VR",
    "Electric Guitar Mute Normal", "Electric Guitar Mute VR", "Electric Guitar Mute 1-Shot",
    "Dist Mute Normal", "Dist Mute VR", "Dist Mute 1-Shot", "Dist Lead Normal", "Dist Lead VR",
    "Electric Guitar Normal", "Gut Guitar Normal", "Gut Guitar VR", "Gut Guitar 1-Shot", "Flute Normal",
    "Flute 1-Shot", "Bottle Blow Normal", "Bottle Blow VR", "Sax Normal", "Sax VR 1", "Sax VR 2",
    "Sax 1-Shot", "Trumpet Normal", "Trumpet VR 1", "Trumpet VR 2", "Trumpet 1-Shot", "Trombone Normal",
    "Trombone VR", "Trombone 1-Shot", "Voice", "Noise", "Piano 1", "Piano 2", "Piano 3", "Piano 4",
    "Piano 5", "Cello 1", "Cello 2", "Cello 3", "Cello 4", "Cello 5", "Cello 6", "Strings 1", "Strings 2",
    "Slap Bass L", "Slap Bass L 1-Shot", "Slap Bass H", "Slap Bass H 1-Shot", "Pick Bass 1",
    "Pick Bass 2 1-Shot", "Pick Bass 3 1-Shot", "Electric Guitar Mute", "Electric Guitar Mute 1-Shot",
    "Dist Lead 1", "Dist Lead 2", "Dist Lead 3", "Gut Guitar 1", "Gut Guitar 2", "Gut Guitar 3 1-Shot",
    "Gut Guitar 4 1-Shot", "Flute 1", "Flute 2", "Sax 1", "Sax 2", "Sax 3", "Sax 4 1-Shot",
    "Sax 5 1-Shot", "Sax 6 1-Shot", "Trumpet", "Trumpet 1-Shot", "Voice 1", "Voice 2",
    "Reverse 1", "Reverse 2", "Reverse 3", "Reverse 4", "Reverse 5", "Reverse 6", "Reverse 7",
    "Reverse 8", "Reverse 9", "Reverse 10", "Reverse 11",
    "Loop 1", "Loop 2", "Loop 3", "Loop 4", "Loop 5", "Loop 6", "Loop 7", "Loop 8", "Loop 9",
    "Loop 10", "Loop 11", "Loop 12",
]

SOURCE_MODES = ["Normal", "Twin", "Double"]
POLY_MODES = ["Poly 1", "Poly 2", "Solo 1", "Solo 2"]
LFO_SHAPES = ["Triangle", "Sawtooth", "Square", "Random"]
WHEEL_ASSIGNS = ["Vibrato", "LFO", "DCF"]
KS_CURVES = ["Linear", "Exponential", "Logarithmic", "Ramped", "Split", "Triangle", "Late", "Early"]
VELOCITY_CURVES = ["Linear", "Logarithmic", "Exponential", "Exponential Strong",
                   "Linear Then Off", "Off Then Linear", "Slow Middle", "Fast Middle"]
SUBMIXES = "ABCDEFGH"

MULTI_PLAY_MODES = ["Keyboard", "MIDI", "Mix"]
VELOCITY_SWITCHES = ["Soft", "Loud", "All"]   # orden confirmado con el banco de fábrica y Edisyn

# Tipos de efecto (índice 0..15 en SysEx; el panel los numera 1..16)
EFFECT_TYPES = [
    "Reverb 1", "Reverb 2", "Reverb 3", "Reverb 4", "Gate Reverb", "Reverse Gate",
    "Normal Delay", "Stereo Panpot Delay", "Chorus", "Overdrive + Flanger",
    "Overdrive + Normal Delay", "Overdrive + Reverb", "Normal Delay + Normal Delay",
    "Normal Delay + Stereo Panpot Delay", "Chorus + Normal Delay", "Chorus + Stereo Panpot Delay",
]
EFFECT_PARAM_NAMES = [
    ("Pre.delay", "Rev.Time", "Tone"), ("Pre.delay", "Rev.Time", "Tone"),
    ("Pre.delay", "Rev.Time", "Tone"), ("Pre.delay", "Rev.Time", "Tone"),
    ("Pre.delay", "Gate Time", "Tone"), ("Pre.delay", "Gate Time", "Tone"),
    ("Feedback", "Tone", "Delay"), ("Feedback", "L/R Delay", "Delay"),
    ("Width", "Feedback", "Rate"), ("Drive", "Fl.Type", "1-2 Bal"),
    ("Drive", "Delay Time", "1-2 Bal"), ("Drive", "Rev.Type", "1-2 Bal"),
    ("Delay1", "Delay2", "1-2 Bal"), ("Delay1", "Delay2", "1-2 Bal"),
    ("Chorus", "Delay", "1-2 Bal"), ("Chorus", "Delay", "1-2 Bal"),
]

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(n: int) -> str:
    """Nombre de nota MIDI con la convención del K4 (60 = C4)."""
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


def wave_name(index: int) -> str:
    return WAVES[index] if 0 <= index < len(WAVES) else f"?{index}"
