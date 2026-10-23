"""Ordinamento dei percorsi per ridurre i movimenti a vuoto.

Step 9c — Invariante multi-layer
--------------------------------
L'ordinamento **non mischia mai** percorsi appartenenti a layer diversi:
i layer vengono lavorati in sequenza (raggruppati), e dentro ogni layer
si applica il nearest-neighbor greedy. Questo perché il G-code cambia
potenza/velocità fra un layer e l'altro: mescolarli genererebbe continue
accensioni/spegnimenti con parametri diversi.

L'ordine dei gruppi è quello di prima apparizione nei ``paths`` passati.
Chi vuole controllare l'ordine dei layer deve ordinarli **prima** di
chiamare ``order_paths`` (vedi ``cam.gcode``).
"""

from __future__ import annotations

import math

from lasercontrolsuite.cam.flatten import FlatPath


def order_paths(
    paths: list[FlatPath],
    start: tuple[float, float] = (0.0, 0.0),
    allow_reverse: bool = True,
) -> list[FlatPath]:
    """Riordina i percorsi preservando i gruppi per layer."""
    if not paths:
        return []

    # Raggruppa per layer preservando l'ordine di prima apparizione.
    groups: dict[str, list[FlatPath]] = {}
    order: list[str] = []
    for p in paths:
        lid = p.layer_id
        if lid not in groups:
            groups[lid] = []
            order.append(lid)
        groups[lid].append(p)

    result: list[FlatPath] = []
    current = start
    for lid in order:
        group = groups[lid]
        ordered = _nearest_neighbor(group, current, allow_reverse)
        if ordered:
            last = ordered[-1]
            current = last.points[0] if last.closed else last.points[-1]
        result.extend(ordered)
    return result


def _nearest_neighbor(
    paths: list[FlatPath],
    start: tuple[float, float],
    allow_reverse: bool,
) -> list[FlatPath]:
    remaining = list(paths)
    ordered: list[FlatPath] = []
    current = start

    while remaining:
        best_i = 0
        best_d = float("inf")
        best_reverse = False

        for i, p in enumerate(remaining):
            head = p.points[0]
            d_head = math.hypot(head[0] - current[0], head[1] - current[1])
            if d_head < best_d:
                best_i, best_d, best_reverse = i, d_head, False
            if allow_reverse and not p.closed:
                tail = p.points[-1]
                d_tail = math.hypot(tail[0] - current[0], tail[1] - current[1])
                if d_tail < best_d:
                    best_i, best_d, best_reverse = i, d_tail, True

        path = remaining.pop(best_i)
        if best_reverse:
            path = FlatPath(
                points=list(reversed(path.points)),
                closed=path.closed,
                entity_id=path.entity_id,
                layer_id=path.layer_id,
            )
        ordered.append(path)
        current = path.points[0] if path.closed else path.points[-1]

    return ordered