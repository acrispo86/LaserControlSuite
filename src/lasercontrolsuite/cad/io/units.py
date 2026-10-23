"""Conversioni di unità per gli importatori.

Tutte le entità del core sono in **millimetri**. Gli importatori convertono
qui le unità native dei formati (pollici DXF, unità SVG) in mm.
"""

from __future__ import annotations

#: Valori del campo DXF $INSUNITS → fattore di conversione a mm.
#: Riferimento: tabella "Insertion units" della specifica DXF.
DXF_INSUNITS_TO_MM: dict[int, float] = {
    0: 1.0,           # Unitless → assunto mm
    1: 25.4,          # Inches
    2: 304.8,         # Feet
    3: 1609344.0,     # Miles
    4: 1.0,           # Millimeters
    5: 10.0,          # Centimeters
    6: 1000.0,        # Meters
    7: 1_000_000.0,   # Kilometers
    8: 2.54e-5,       # Microinches
    9: 0.0254,        # Mils
    10: 914.4,        # Yards
    11: 1e-7,         # Angstroms
    12: 1e-6,         # Nanometers
    13: 1e-3,         # Micrometers
    14: 100.0,        # Decimeters
    15: 10_000.0,     # Decameters
    16: 100_000.0,    # Hectometers
    17: 1e12,         # Gigameters
    18: 1.495978707e14,  # Astronomical units
    19: 9.4607304725808e18,  # Light years
    20: 3.0856775814914e19,  # Parsecs
    21: 304.8006096012192,   # US Survey Feet
    22: 25.4000508001016,    # US Survey Inch
    23: 914.4018288036576,   # US Survey Yard
    24: 1609347.2186944376,  # US Survey Mile
}


def dxf_unit_scale_mm(insunits_code: int) -> float:
    """Restituisce il fattore di scala da unità DXF a mm."""
    return DXF_INSUNITS_TO_MM.get(insunits_code, 1.0)


#: DPI di default del formato SVG (CSS px = 1/96 inch).
SVG_DEFAULT_DPI: float = 96.0

#: Millimetri per pollice.
MM_PER_INCH: float = 25.4


def svg_user_unit_to_mm() -> float:
    """Fattore di conversione da unità utente SVG (CSS px) a mm."""
    return MM_PER_INCH / SVG_DEFAULT_DPI


def parse_svg_length(value: str | None, default_mm: float = 0.0) -> float:
    """Interpreta un attributo di lunghezza SVG (``"100mm"``, ``"2in"``, ``"96"``).

    Unità supportate: ``mm``, ``cm``, ``m``, ``in``, ``ft``, ``pt``, ``pc``,
    ``px`` (equivalente a unità utente). Se nessuna unità è specificata, si
    assume unità utente (CSS px).
    """
    if value is None:
        return default_mm
    s = value.strip().lower()
    if not s:
        return default_mm

    units = (
        ("mm", 1.0),
        ("cm", 10.0),
        ("in", 25.4),
        ("ft", 304.8),
        ("m", 1000.0),
        ("pt", 25.4 / 72.0),
        ("pc", 25.4 / 6.0),
        ("px", 25.4 / 96.0),
    )
    for suffix, factor in units:
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)]) * factor
            except ValueError:
                return default_mm

    # Nessun suffisso: unità utente → mm
    try:
        return float(s) * svg_user_unit_to_mm()
    except ValueError:
        return default_mm