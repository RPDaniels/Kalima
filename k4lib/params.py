"""Números de parámetro para el mensaje Parameter Send (función 0x10).

Tabla tomada del editor Edisyn, que la ha probado con el aparato.
Los parámetros de fuente/DCA se envían con section = 0..3 (S1..S4);
los de filtro con section 0 (F1) o 2 (F2), siguiendo a Edisyn.

Cada entrada: nombre -> (número, desplazamiento, mínimo, máximo) en
unidades del panel. El valor que viaja es valor + desplazamiento.
"""
from __future__ import annotations

from .i18n import _

PARAMETERS: dict[str, tuple[int, int, int, int]] = {
    # comunes
    "volume": (10, 0, 0, 100),
    "effect": (11, -1, 1, 32),              # panel 1..32 -> 0..31
    "submix": (12, 0, 0, 7),
    "source_mode": (13, 0, 0, 2),
    "poly_mode": (14, 0, 0, 3),
    "am12": (15, 0, 0, 1),
    "am34": (16, 0, 0, 1),
    "vib_shape": (17, 0, 0, 3),
    "bend_range": (18, 0, 0, 12),
    "wheel_assign": (19, 0, 0, 2),
    "vib_speed": (20, 0, 0, 100),
    "wheel_depth": (21, 50, -50, 50),
    "autobend_time": (22, 0, 0, 100),
    "autobend_depth": (23, 50, -50, 50),
    "autobend_ks_time": (24, 50, -50, 50),
    "autobend_vel_depth": (25, 50, -50, 50),
    "vib_prs": (26, 50, -50, 50),
    "vib_depth": (27, 50, -50, 50),
    "lfo_shape": (28, 0, 0, 3),
    "lfo_speed": (29, 0, 0, 100),
    "lfo_delay": (30, 0, 0, 100),
    "lfo_depth": (31, 50, -50, 50),
    "lfo_prs": (32, 50, -50, 50),
    "prs_freq": (33, 50, -50, 50),
    # por fuente (section 0..3)
    "src_delay": (34, 0, 0, 100),
    "src_ks_curve": (35, -1, 1, 8),
    "src_wave": (36, -1, 1, 256),            # panel 1..256 -> 0..255 (usa el bit 7)
    "src_coarse": (37, 24, -24, 24),
    "src_key_track": (38, 0, 0, 1),
    "src_fixed_key": (39, 0, 0, 127),
    "src_fine": (40, 50, -50, 50),
    "src_prs_freq": (41, 0, 0, 1),
    "src_vib_autobend": (42, 0, 0, 1),
    "src_vel_curve": (43, -1, 1, 8),
    # DCA (section 0..3)
    "amp_level": (44, 0, 0, 100),
    "amp_attack": (45, 0, 0, 100),
    "amp_decay": (46, 0, 0, 100),
    "amp_sustain": (47, 0, 0, 100),
    "amp_release": (48, 0, 0, 100),
    "amp_level_vel": (49, 50, -50, 50),
    "amp_level_prs": (50, 50, -50, 50),
    "amp_level_ks": (51, 50, -50, 50),
    "amp_time_vel_on": (52, 50, -50, 50),
    "amp_time_vel_off": (53, 50, -50, 50),
    "amp_time_ks": (54, 50, -50, 50),
    # DCF (section 0 = F1, 2 = F2)
    "filter_cutoff": (55, 0, 0, 100),
    "filter_resonance": (56, 0, 0, 7),
    "filter_lfo": (57, 0, 0, 1),
    "filter_cutoff_vel": (58, 50, -50, 50),
    "filter_cutoff_prs": (59, 50, -50, 50),
    "filter_cutoff_ks": (60, 50, -50, 50),
    "filter_env_depth": (61, 50, -50, 50),
    "filter_env_vel_depth": (62, 50, -50, 50),
    "filter_attack": (63, 0, 0, 100),
    "filter_decay": (64, 0, 0, 100),
    "filter_sustain": (65, 50, -50, 50),
    "filter_release": (66, 0, 0, 100),
    "filter_time_vel_on": (67, 50, -50, 50),
    "filter_time_vel_off": (68, 50, -50, 50),
    "filter_time_ks": (69, 50, -50, 50),
}
# Los caracteres del nombre son los parámetros 0..9 (valor = código ASCII).

FILTER_SECTION = {1: 0, 2: 2}


def encode(name_or_number: str | int, value: int) -> tuple[int, int]:
    """Devuelve (número de parámetro, valor crudo) listo para enviar."""
    if isinstance(name_or_number, int):
        return name_or_number, value
    try:
        number, offset, lo, hi = PARAMETERS[name_or_number]
    except KeyError:
        raise KeyError(_("parámetro desconocido: {name}", name=name_or_number)) from None
    if not lo <= value <= hi:
        raise ValueError(_("{name}: {value} fuera de {lo}..{hi}", name=name_or_number, value=value, lo=lo, hi=hi))
    return number, value + offset
