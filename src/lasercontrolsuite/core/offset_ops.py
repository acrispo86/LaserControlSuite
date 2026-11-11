"""Operazioni di offset/contorno (inset/outset) su path.

Usa `shapely.buffer()` per calcolare l'offset geometrico. Ogni entità viene
offsettata **indipendentemente** (non è un'unione): è il comportamento atteso
per compensare il kerf del fascio o per creare contorni interni/esterni.

Semantica:
  - ``distance_mm`` è sempre >= 0; ``mode`` determina il segno:
      * ``OffsetMode.OUTSET`` → buffer positivo (contorno esterno)
      * ``OffsetMode.INSET``  → buffer negativo (contorno interno)
  - Un inset più grande della geometria produce risultato vuoto + warning.
  - Path aperti vengono chiusi automaticamente + warning (ereditato da
    ``entity_to_polygon``).
  - Entità non convertibili (es. testo) generano warning e vengono ignorate.
  - Il risultato con fori è una lista di ``PathEntity``: una per anello
    esterno, una per ogni foro (regola P25).

Riusa gli helper pubblici di ``core.boolean_ops`` per non duplicare la
logica di conversione entità ↔ shapely.

Nota shapely 2.x: il parametro ``quad_segs`` (segmenti per quarto di cerchio
sugli angoli ``ROUND``) sostituisce il vecchio ``resolution`` deprecato.
"""

from __future__ import annotations

from enum import Enum

from shapely.geometry import Polygon

from lasercontrolsuite.core.boolean_ops import (
    entity_to_polygon,
    polygons_to_paths,
)
from lasercontrolsuite.core.entities import Entity
from lasercontrolsuite.core.path import PathEntity


class OffsetMode(str, Enum):
    INSET = "inset"
    OUTSET = "outset"


class OffsetJoinStyle(str, Enum):
    ROUND = "round"
    MITRE = "mitre"
    BEVEL = "bevel"


# shapely.join_style: 1 = round, 2 = mitre, 3 = bevel
_JOIN_STYLE_MAP = {
    OffsetJoinStyle.ROUND: 1,
    OffsetJoinStyle.MITRE: 2,
    OffsetJoinStyle.BEVEL: 3,
}


def compute_offset(
    entities: list[Entity],
    distance_mm: float,
    mode: OffsetMode = OffsetMode.OUTSET,
    join_style: OffsetJoinStyle = OffsetJoinStyle.ROUND,
    mitre_limit: float = 5.0,
    quad_segs: int = 16,
) -> tuple[list[PathEntity], list[str]]:
    """Calcola l'offset (contorno) di un set di entità.

    Args:
        entities: entità da offsettare, indipendentemente l'una dall'altra.
        distance_mm: distanza dell'offset in mm (deve essere >= 0).
        mode: ``OUTSET`` (esterno) o ``INSET`` (interno).
        join_style: stile degli angoli generati agli spigoli.
        mitre_limit: limite per ``MITRE`` (rapporto rispetto al raggio).
        quad_segs: numero di segmenti per quarto di cerchio su ``ROUND``.

    Returns:
        Tupla ``(paths, warnings)``. ``paths`` è vuota se nessuna entità è
        stata offsettata con successo.
    """
    warnings: list[str] = []
    if not entities:
        return [], ["Nessuna entità fornita per l'offset."]

    if distance_mm < 0:
        warnings.append("La distanza di offset deve essere >= 0.")
        return [], warnings
    if distance_mm == 0:
        warnings.append("La distanza di offset è zero: nessuna modifica.")
        return [], warnings

    signed = distance_mm if mode == OffsetMode.OUTSET else -distance_mm
    join = _JOIN_STYLE_MAP[join_style]

    result_polys: list[Polygon] = []
    layer_id = entities[0].layer_id

    for e in entities:
        poly = entity_to_polygon(e, warnings)
        if poly is None:
            continue

        try:
            buffered = poly.buffer(
                signed,
                quad_segs=quad_segs,
                join_style=join,
                mitre_limit=mitre_limit,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Errore offset su entità {e.id[:8]}: {exc}")
            continue

        if buffered.is_empty:
            warnings.append(
                f"Offset vuoto per entità {e.id[:8]} "
                f"(distanza {signed:+.3f} mm)"
            )
            continue

        if isinstance(buffered, Polygon):
            result_polys.append(buffered)
        elif hasattr(buffered, "geoms"):
            for g in buffered.geoms:
                if isinstance(g, Polygon):
                    result_polys.append(g)

    if not result_polys:
        return [], warnings

    paths = polygons_to_paths(result_polys, layer_id)
    if not paths:
        warnings.append("Il risultato dell'offset non contiene path validi.")
    return paths, warnings