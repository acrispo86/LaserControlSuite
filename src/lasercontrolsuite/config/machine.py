"""Modello della macchina laser (area di lavoro, origine).

Puro Python: nessuna dipendenza da Qt. Il modello è serializzato da
``config.settings.Settings`` tramite QSettings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


DEFAULT_MACHINE_NAME: str = "Laser"
DEFAULT_WORK_AREA_MM: float = 400.0


class MachineOrigin(str, Enum):
    """Posizione dell'origine (0,0) rispetto all'area di lavoro."""

    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    CENTER = "center"

    @property
    def label_it(self) -> str:
        return {
            MachineOrigin.BOTTOM_LEFT: "Angolo basso-sinistra",
            MachineOrigin.BOTTOM_RIGHT: "Angolo basso-destra",
            MachineOrigin.CENTER: "Centro area",
        }[self]


@dataclass(frozen=True)
class Machine:
    """Descrizione di una macchina laser."""

    name: str
    width_mm: float
    height_mm: float
    origin: MachineOrigin = MachineOrigin.BOTTOM_LEFT

    def __post_init__(self) -> None:
        if self.width_mm <= 0 or self.height_mm <= 0:
            raise ValueError("Le dimensioni dell'area di lavoro devono essere > 0")

    def work_area_bounds(self) -> tuple[float, float, float, float]:
        """Rettangolo area di lavoro in coordinate macchina.

        Returns:
            ``(x_min, y_min, x_max, y_max)``.
        """
        if self.origin is MachineOrigin.BOTTOM_LEFT:
            return (0.0, 0.0, self.width_mm, self.height_mm)
        if self.origin is MachineOrigin.BOTTOM_RIGHT:
            return (-self.width_mm, 0.0, 0.0, self.height_mm)
        # CENTER
        half_w = self.width_mm / 2.0
        half_h = self.height_mm / 2.0
        return (-half_w, -half_h, half_w, half_h)

    def origin_point(self) -> tuple[float, float]:
        """Punto d'origine in coordinate macchina (sempre ``(0, 0)``)."""
        return (0.0, 0.0)

    def is_empty(self) -> bool:
        return self.width_mm <= 0 or self.height_mm <= 0