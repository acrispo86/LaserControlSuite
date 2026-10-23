"""Layer di disegno con parametri CAM (stile LightBurn).

Ogni layer porta con sé:
  - attributi visivi (colore, visibile, bloccato)
  - parametri di taglio (potenza, velocità, passate, air assist)
  - una ``priority`` che determina l'ordine di lavorazione tra i layer
    (numero più basso = lavorato prima). A parità di priority, vince
    l'ordine di inserimento nel documento.

Il core resta puro Python: nessuna dipendenza Qt, unità in mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lasercontrolsuite.core.ids import new_id


#: Palette di colori proposti quando si crea un nuovo layer dal pannello CAM.
#: Riprende i colori di default di LightBurn (giallo, rosso, verde, blu, ...).
SUGGESTED_COLORS: tuple[str, ...] = (
    "#FFD400",  # giallo
    "#FF3030",  # rosso
    "#00C853",  # verde
    "#2979FF",  # blu
    "#AA00FF",  # viola
    "#FF6D00",  # arancio
    "#00BCD4",  # ciano
    "#EC407A",  # rosa
)


@dataclass
class Layer:
    """Layer di disegno con parametri CAM."""

    id: str = field(default_factory=new_id)
    name: str = "Layer"
    color: str = "#FFD400"        # #RRGGBB
    visible: bool = True
    locked: bool = False
    priority: int = 0             # ordine di lavorazione (crescente)

    # Parametri CAM
    power_percent: int = 50       # 0-100 %
    speed_mm_min: float = 600.0   # velocità di taglio (F in G-code)
    passes: int = 1               # numero di ripetizioni
    air_assist: bool = False      # M8/M9

    @classmethod
    def new(
        cls,
        name: str,
        color: str = "#FFD400",
        priority: int = 0,
    ) -> "Layer":
        return cls(name=name, color=color, priority=priority)

    def normalized(self) -> "Layer":
        """Restituisce una copia con valori normalizzati (clamp)."""
        return Layer(
            id=self.id,
            name=self.name,
            color=self.color,
            visible=bool(self.visible),
            locked=bool(self.locked),
            priority=int(self.priority),
            power_percent=max(0, min(100, int(self.power_percent))),
            speed_mm_min=max(1.0, float(self.speed_mm_min)),
            passes=max(1, int(self.passes)),
            air_assist=bool(self.air_assist),
        )