"""Operazioni geometriche pure (nessuna dipendenza Qt).

Forniscono trasformazioni *calcolate* che i command (Qt) applicheranno al
documento. Restare pure le rende testabili senza QApplication.
"""

from __future__ import annotations

import copy
import math
from enum import Enum

from lasercontrolsuite.core.entities import Entity
from lasercontrolsuite.core.ids import new_id
from lasercontrolsuite.core.matrix import Matrix2D


class AlignMode(str, Enum):
    LEFT = "left"
    CENTER_H = "center_h"
    RIGHT = "right"
    BOTTOM = "bottom"
    CENTER_V = "center_v"
    TOP = "top"


class DistributeMode(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


def _bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def compute_align(
    entities: list[Entity], mode: AlignMode
) -> dict[str, Matrix2D]:
    """Calcola le trasformazioni per allineare un gruppo di entità.

    Le entità si allineano al bounding box **comune** (unione dei singoli bbox).

    Returns:
        Mappa ``{entity_id: nuova_transform}``. Vuota se nulla da fare.
    """
    if not entities:
        return {}

    boxes = {e.id: e.world_bounding_box() for e in entities}
    all_x0 = min(b[0] for b in boxes.values())
    all_y0 = min(b[1] for b in boxes.values())
    all_x1 = max(b[2] for b in boxes.values())
    all_y1 = max(b[3] for b in boxes.values())

    result: dict[str, Matrix2D] = {}
    for e in entities:
        x0, y0, x1, y1 = boxes[e.id]
        dx = dy = 0.0

        if mode == AlignMode.LEFT:
            dx = all_x0 - x0
        elif mode == AlignMode.RIGHT:
            dx = all_x1 - x1
        elif mode == AlignMode.CENTER_H:
            dx = ((all_x0 + all_x1) / 2.0) - ((x0 + x1) / 2.0)
        elif mode == AlignMode.BOTTOM:
            dy = all_y0 - y0
        elif mode == AlignMode.TOP:
            dy = all_y1 - y1
        elif mode == AlignMode.CENTER_V:
            dy = ((all_y0 + all_y1) / 2.0) - ((y0 + y1) / 2.0)

        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            continue
        result[e.id] = Matrix2D.translation(dx, dy) @ e.transform
    return result


def compute_distribute(
    entities: list[Entity], mode: DistributeMode
) -> dict[str, Matrix2D]:
    """Distribuisce uniformemente i **centri** tra il primo e l'ultimo.

    Il primo e l'ultimo (per posizione) restano fermi, gli altri vengono
    spostati per avere centri equidistanti.
    """
    if len(entities) < 3:
        return {}

    items: list[tuple[Entity, float]] = []
    for e in entities:
        cx, cy = _bbox_center(e.world_bounding_box())
        items.append((e, cx if mode == DistributeMode.HORIZONTAL else cy))

    items.sort(key=lambda pair: pair[1])
    first = items[0][1]
    last = items[-1][1]
    n = len(items)
    step = (last - first) / (n - 1)

    result: dict[str, Matrix2D] = {}
    for i, (e, value) in enumerate(items):
        target = first + i * step
        d = target - value
        if abs(d) < 1e-12:
            continue
        if mode == DistributeMode.HORIZONTAL:
            result[e.id] = Matrix2D.translation(d, 0.0) @ e.transform
        else:
            result[e.id] = Matrix2D.translation(0.0, d) @ e.transform
    return result


def nudge_transforms(
    entities: list[Entity], dx: float, dy: float
) -> dict[str, Matrix2D]:
    """Restituisce le nuove transform per uno spostamento di ``(dx, dy)``."""
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return {}
    delta = Matrix2D.translation(dx, dy)
    return {e.id: delta @ e.transform for e in entities}


def clone_entity(entity: Entity) -> Entity:
    """Copia profonda di una entità con nuovo id."""
    new = copy.deepcopy(entity)
    new.id = new_id()
    return new


def compute_polar_array(
    entities: list[Entity],
    center: tuple[float, float],
    count: int,
    total_angle_deg: float = 360.0,
    start_angle_deg: float = 0.0,
    include_original: bool = True,
    rotate_copies: bool = True,
) -> list[Entity]:
    """Restituisce una lista di cloni delle entità per un array circolare.

    Args:
        entities: entità sorgente.
        center: coordinate del centro di rotazione ``(cx, cy)``.
        count: numero totale di elementi (incluso l'originale se
            ``include_original=True``).
        total_angle_deg: angolo totale coperto (default 360°). Se 360,
            l'ultima copia non si sovrappone alla prima.
        start_angle_deg: angolo iniziale dell'originale (default 0°).
        include_original: se True, l'elemento a ``start_angle_deg`` è
            considerato l'originale e non viene clonato.
        rotate_copies: se True, le copie vengono ruotate; se False, vengono
            traslate mantenendo l'orientamento (array circolare "move only").

    Returns:
        Lista di entità clonate con la nuova trasformazione applicata.
    """
    count = max(1, int(count))
    if count == 1 or not entities:
        return []

    cx, cy = float(center[0]), float(center[1])
    if abs(total_angle_deg - 360.0) < 1e-9:
        step = 360.0 / count
    else:
        step = total_angle_deg / max(1, count - 1) if count > 1 else 0.0

    result: list[Entity] = []
    start_index = 1 if include_original else 0

    for i in range(start_index, count):
        angle = start_angle_deg + i * step
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        for e in entities:
            clone = clone_entity(e)
            if rotate_copies:
                rot = Matrix2D.rotation_deg(angle)
                # Rotazione attorno al centro: T(cx, cy) @ R(angle) @ T(-cx, -cy)
                M_rot = (
                    Matrix2D.translation(cx, cy)
                    @ rot
                    @ Matrix2D.translation(-cx, -cy)
                )
                clone.transform = M_rot @ e.transform
            else:
                # Trasla il centro dell'entità lungo l'arco senza ruotarla.
                bb = e.world_bounding_box()
                ex = (bb[0] + bb[2]) / 2.0
                ey = (bb[1] + bb[3]) / 2.0
                # Nuova posizione del centro ruotata attorno a (cx, cy)
                dx = ex - cx
                dy = ey - cy
                nx = cx + dx * cos_a - dy * sin_a
                ny = cy + dx * sin_a + dy * cos_a
                M_trans = Matrix2D.translation(nx - ex, ny - ey)
                clone.transform = M_trans @ e.transform
            result.append(clone)

    return result


def rotation_of(matrix: Matrix2D) -> float:
    """Estrae l'angolo di rotazione (radianti) dalla matrice.

    Valido per matrici senza riflessione. La scala, se presente, viene
    "assorbita" dal calcolo (atan2 non dipende da essa).
    """
    return math.atan2(matrix.b, matrix.a)