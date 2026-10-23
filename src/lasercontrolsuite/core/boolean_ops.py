"""Operazioni booleane su path (unione, sottrazione, intersezione).

Usa `shapely` per la geometria. Le entità selezionate vengono convertite in
poligoni (via `entity_to_path`), l'operazione viene applicata e il risultato
viene riconvertito in `PathEntity`.

Note:
  - I path aperti vengono chiusi automaticamente e generano un warning.
  - I path non convertibili (es. testo) generano un warning e vengono ignorati.
  - Il risultato con fori viene restituito come una lista di `PathEntity`:
    uno per l'anello esterno, uno per ogni foro.
"""

from __future__ import annotations

from enum import Enum

from shapely.geometry import Polygon
from shapely.ops import unary_union

from lasercontrolsuite.core.entities import Entity
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.path import PathEntity, PathNode
from lasercontrolsuite.core.path_edit import entity_to_path


class BooleanMode(str, Enum):
    UNION = "union"
    DIFFERENCE = "difference"
    INTERSECTION = "intersection"


def boolean_operation(
    entities: list[Entity], mode: BooleanMode
) -> tuple[list[PathEntity], list[str]]:
    """Esegue l'operazione booleana su un set di entità.

    Args:
        entities: entità da operare. Ordine significativo per `DIFFERENCE`:
            il primo è il target, gli altri vengono sottratti.
        mode: tipo di operazione.

    Returns:
        Una tupla `(risultato, warnings)`.
    """
    if len(entities) < 2:
        return [], ["Servono almeno due entità per l'operazione booleana."]

    warnings: list[str] = []
    polys: list[Polygon] = []

    for e in entities:
        poly = _entity_to_polygon(e, warnings)
        if poly is not None:
            polys.append(poly)

    if len(polys) < 2:
        return [], warnings + ["Meno di due entità convertibili in poligoni validi."]

    try:
        if mode == BooleanMode.UNION:
            result = unary_union(polys)
        elif mode == BooleanMode.INTERSECTION:
            result = polys[0]
            for p in polys[1:]:
                result = result.intersection(p)
                if result.is_empty:
                    break
        elif mode == BooleanMode.DIFFERENCE:
            result = polys[0]
            for p in polys[1:]:
                result = result.difference(p)
                if result.is_empty:
                    break
        else:
            return [], warnings + [f"Modalità sconosciuta: {mode}"]
    except Exception as exc:  # noqa: BLE001
        return [], warnings + [f"Errore geometrico: {exc}"]

    if result.is_empty:
        return [], warnings + ["Il risultato dell'operazione è vuoto."]

    # Estrai tutti i poligoni
    out_polys: list[Polygon] = []
    if isinstance(result, Polygon):
        out_polys.append(result)
    elif hasattr(result, "geoms"):
        for g in result.geoms:
            if isinstance(g, Polygon):
                out_polys.append(g)

    if not out_polys:
        return [], warnings + ["Il risultato non contiene poligoni."]

    paths: list[PathEntity] = []
    layer_id = entities[0].layer_id

    for poly in out_polys:
        # Anello esterno
        paths.append(_polygon_ring_to_path(poly.exterior, layer_id))
        # Fori
        for interior in poly.interiors:
            paths.append(_polygon_ring_to_path(interior, layer_id))

    return paths, warnings


def _entity_to_polygon(entity: Entity, warnings: list[str]) -> Polygon | None:
    """Converte un'entità in `Polygon` shapely, con gestione dei warning."""
    path = entity_to_path(entity)
    if path is None:
        warnings.append(f"Entità non convertibile in path: {entity.type_name}")
        return None

    pts = path.world_points()
    if len(pts) < 3:
        warnings.append(f"Path con meno di 3 punti, scartato: {entity.id[:8]}")
        return None

    if not path.closed:
        warnings.append(f"Path aperto chiuso automaticamente: {entity.id[:8]}")
        pts.append(pts[0])

    # Rimuovi duplicati consecutivi
    clean_pts = []
    for p in pts:
        if not clean_pts or clean_pts[-1] != p:
            clean_pts.append(p)

    # shapely si aspetta che l'ultimo punto non coincida col primo
    if len(clean_pts) > 1 and clean_pts[0] == clean_pts[-1]:
        clean_pts.pop()

    if len(clean_pts) < 3:
        warnings.append(f"Path degenere, scartato: {entity.id[:8]}")
        return None

    poly = Polygon(clean_pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
        if not poly.is_valid or poly.is_empty:
            warnings.append(f"Poligono non valido, scartato: {entity.id[:8]}")
            return None

    if poly.area < 1e-6:
        warnings.append(f"Poligono con area nulla, scartato: {entity.id[:8]}")
        return None

    return poly


def _polygon_ring_to_path(ring, layer_id: str) -> PathEntity:
    """Crea un `PathEntity` chiuso a partire da un anello shapely."""
    coords = list(ring.coords)
    # shapely chiude l'anello: rimuoviamo l'ultimo punto se coincide col primo
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords.pop()

    nodes = [PathNode((x, y)) for x, y in coords]
    return PathEntity(
        layer_id=layer_id,
        nodes=nodes,
        closed=True,
        transform=Matrix2D.identity(),
    )