"""Configurazione persistente dell'applicazione (QSettings).

Contiene il modello ``Machine`` (dataclass puro) e il wrapper ``Settings``
che legge/scrive le preferenze con ``QSettings``.
"""

from __future__ import annotations

from lasercontrolsuite.config.machine import (
    DEFAULT_MACHINE_NAME,
    DEFAULT_WORK_AREA_MM,
    Machine,
    MachineOrigin,
)
from lasercontrolsuite.config.settings import Settings

__all__ = [
    "Machine",
    "MachineOrigin",
    "Settings",
    "DEFAULT_MACHINE_NAME",
    "DEFAULT_WORK_AREA_MM",
]