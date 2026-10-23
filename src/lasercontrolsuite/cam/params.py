"""Parametri di taglio/incisione per la generazione G-code.

Step 9c — Modello multi-layer
-----------------------------
I parametri CAM sono divisi in due livelli:

- **GlobalParams** — proprietà della macchina o del lavoro nel suo insieme:
  S max, modalità laser, feed di rapido, ritorno a home, header.
  Non dipendono dal layer.
- **Parametri per layer** — vivono in ``core.layer.Layer``:
  potenza, velocità, passate, air assist. Ogni layer è una "cut".
- **CutParams** — aggregato dei due, usato dal motore di generazione per
  emettere il G-code di un singolo layer. Si costruisce con la factory
  ``CutParams.from_layer(layer, global_params)``.

Il vecchio uso "parametri globali per tutto" resta supportato passando un
``CutParams`` esplicito a ``generate_gcode``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LaserMode(str, Enum):
    """Modalità di controllo del laser.

    - ``M3``: potenza costante (on/off). Utile per tagli netti.
    - ``M4``: potenza dinamica in funzione della velocità. Riduce le
      bruciature nei rallentamenti e negli angoli. Richiede ``$32=1``.
    """

    M3 = "M3"
    M4 = "M4"


# =====================================================================
# GlobalParams — proprietà della macchina / del lavoro
# =====================================================================
@dataclass
class GlobalParams:
    """Parametri globali (indipendenti dal layer)."""

    travel_feed_mm_min: float = 0.0
    s_max: int = 1000
    laser_mode: LaserMode = LaserMode.M4
    travel_home: bool = True
    header_comment: str = ""

    def normalized(self) -> "GlobalParams":
        return GlobalParams(
            travel_feed_mm_min=max(0.0, float(self.travel_feed_mm_min)),
            s_max=max(1, int(self.s_max)),
            laser_mode=self.laser_mode
            if isinstance(self.laser_mode, LaserMode)
            else LaserMode(self.laser_mode),
            travel_home=bool(self.travel_home),
            header_comment=str(self.header_comment),
        )


# =====================================================================
# CutParams — aggregato per un singolo layer (o globali legacy)
# =====================================================================
@dataclass
class CutParams:
    """Parametri di taglio per un singolo layer (o per tutto il lavoro)."""

    feed_mm_min: float = 1000.0
    travel_feed_mm_min: float = 0.0
    power_percent: float = 50.0
    s_max: int = 1000
    passes: int = 1
    laser_mode: LaserMode = LaserMode.M4
    air_assist: bool = False
    travel_home: bool = True
    header_comment: str = ""

    # Metadati del layer di provenienza (vuoti se CutParams è "globale legacy")
    layer_id: str = ""
    layer_name: str = ""

    # ------------------------------------------------------------------ factory
    @classmethod
    def from_layer(cls, layer, global_params: GlobalParams) -> "CutParams":
        """Combina un layer con i parametri globali."""
        g = global_params.normalized()
        ln = layer.normalized()
        return cls(
            feed_mm_min=ln.speed_mm_min,
            travel_feed_mm_min=g.travel_feed_mm_min,
            power_percent=float(ln.power_percent),
            s_max=g.s_max,
            passes=ln.passes,
            laser_mode=g.laser_mode,
            air_assist=ln.air_assist,
            travel_home=g.travel_home,
            header_comment=g.header_comment,
            layer_id=ln.id,
            layer_name=ln.name,
        )

    # ------------------------------------------------------------------ API
    def s_value(self) -> int:
        """Valore S corrispondente alla potenza percentuale."""
        p = max(0.0, min(100.0, float(self.power_percent)))
        return int(round(p / 100.0 * max(1, int(self.s_max))))

    def normalized(self) -> "CutParams":
        """Restituisce una copia con valori normalizzati (clamp, >= 1 pass)."""
        return CutParams(
            feed_mm_min=max(1.0, float(self.feed_mm_min)),
            travel_feed_mm_min=max(0.0, float(self.travel_feed_mm_min)),
            power_percent=max(0.0, min(100.0, float(self.power_percent))),
            s_max=max(1, int(self.s_max)),
            passes=max(1, int(self.passes)),
            laser_mode=self.laser_mode
            if isinstance(self.laser_mode, LaserMode)
            else LaserMode(self.laser_mode),
            air_assist=bool(self.air_assist),
            travel_home=bool(self.travel_home),
            header_comment=str(self.header_comment),
            layer_id=str(self.layer_id),
            layer_name=str(self.layer_name),
        )