"""Conversione `TextEntity` → `PathEntity` usando QPainterPath (adapter Qt).

Il core resta puro Python: `entity_to_path()` in `core/path_edit.py`
restituisce ``None`` per i testi. La conversione vera vive qui, nell'adapter
Qt, e usa `QPainterPath.addText` per ottenere i glifi reali.

Un testo multi-carattere produce **N subpath** (uno per contorno chiuso).
I fori (es. la "O", la "A") diventano subpath separati — stessa limitazione
di LightBurn quando esporti in formati che non supportano compound path.
Le informazioni "foro vs contorno" vanno perse: è una limitazione nota di
`PathEntity` a singolo subpath, documentata in KNOWN_ISSUES.
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QPainterPath, QTransform

from lasercontrolsuite.cad.qt_utils import mm_per_px_at_qt_dpi
from lasercontrolsuite.core.entities import TextEntity
from lasercontrolsuite.core.path import PathEntity, PathNode


# Identico a entity_item.TEXT_MM_PER_PT — tenere allineati.
# (Duplicato per non creare dipendenza text_to_path → entity_item.)
TEXT_MM_PER_PT = 25.4 / 72.0

# Tolleranza (mm) per considerare due punti coincidenti (chiusura subpath).
_CLOSE_TOL = 1e-4


def text_entity_to_paths(entity: TextEntity) -> list[PathEntity] | None:
    """Converte un ``TextEntity`` in una lista di ``PathEntity`` (una per subpath).

    Args:
        entity: il testo da convertire. Deve avere ``text`` non vuoto.

    Returns:
        Lista di ``PathEntity`` con la stessa ``transform`` e ``layer_id``
        dell'originale, oppure ``None`` se il testo è vuoto o non produce
        geometria (es. caratteri non renderizzabili).
    """
    if not entity.text:
        return None

    font = QFont(entity.font_family)
    pt_size = entity.font_size_mm / TEXT_MM_PER_PT
    font.setPointSizeF(max(1.0, pt_size))

    raw_path = QPainterPath()
    raw_path.addText(0.0, 0.0, font, entity.text)

    if raw_path.isEmpty():
        return None

    # Conversione px → mm + flip Y (identico a EntityItem._build_text_path)
    s = mm_per_px_at_qt_dpi()
    conv = QTransform()
    conv.scale(s, -s)
    local_path = conv.map(raw_path)

    if local_path.isEmpty():
        return None

    subpaths = _qpainterpath_to_subpaths(local_path)

    result: list[PathEntity] = []
    for nodes, closed in subpaths:
        if len(nodes) < 2:
            continue
        result.append(
            PathEntity(
                layer_id=entity.layer_id,
                nodes=nodes,
                closed=closed,
                transform=entity.transform,
            )
        )

    return result or None


def _qpainterpath_to_subpaths(
    path: QPainterPath,
) -> list[tuple[list[PathNode], bool]]:
    """Estrae i subpath come ``(nodes, closed)``.

    Preserva le curve come cubic bezier (``handle_out`` / ``handle_in``).
    Se un subpath chiude tornando al primo punto, l'ultimo nodo duplicato
    viene rimosso e ``closed=True``. Se la chiusura era una curva, i handle
    vengono trasferiti correttamente:
      - ``handle_out`` del penultimo nodo resta (già settato durante la curva)
      - ``handle_in`` del primo nodo viene dal ``ctrl2`` della curva di chiusura
    """
    subpaths: list[tuple[list[PathNode], bool]] = []
    current_nodes: list[PathNode] = []

    def _flush() -> None:
        nonlocal current_nodes
        if len(current_nodes) < 2:
            current_nodes = []
            return
        first = current_nodes[0]
        last = current_nodes[-1]
        closed = (
            abs(first.point[0] - last.point[0]) < _CLOSE_TOL
            and abs(first.point[1] - last.point[1]) < _CLOSE_TOL
        )
        if closed:
            if last.handle_in is not None:
                first.handle_in = last.handle_in
            current_nodes.pop()
            if len(current_nodes) < 2:
                current_nodes = []
                return
        subpaths.append((current_nodes, closed))
        current_nodes = []

    n = path.elementCount()
    i = 0
    while i < n:
        el = path.elementAt(i)
        t = el.type
        if t == QPainterPath.ElementType.MoveToElement:
            _flush()
            current_nodes = [PathNode(point=(el.x, el.y))]
            i += 1
        elif t == QPainterPath.ElementType.LineToElement:
            if current_nodes:
                current_nodes.append(PathNode(point=(el.x, el.y)))
            i += 1
        elif t == QPainterPath.ElementType.CurveToElement:
            # Struttura: CurveToElement (ctrl1), CurveToDataElement (ctrl2),
            # CurveToDataElement (endpoint).
            if i + 2 < n and current_nodes:
                ctrl1 = (el.x, el.y)
                data1 = path.elementAt(i + 1)
                data2 = path.elementAt(i + 2)
                ctrl2 = (data1.x, data1.y)
                endpt = (data2.x, data2.y)
                prev = current_nodes[-1]
                prev.handle_out = (
                    ctrl1[0] - prev.point[0],
                    ctrl1[1] - prev.point[1],
                )
                current_nodes.append(
                    PathNode(
                        point=endpt,
                        handle_in=(ctrl2[0] - endpt[0], ctrl2[1] - endpt[1]),
                    )
                )
                i += 3
            else:
                i += 1
        else:
            i += 1

    _flush()
    return subpaths