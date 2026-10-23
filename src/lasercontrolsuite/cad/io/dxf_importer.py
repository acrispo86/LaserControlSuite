"""Importatore DXF → entità del core.

Supporta i tipi più comuni usati nei file laser:
  - ``LINE`` → ``PolylineEntity`` (2 punti)
  - ``LWPOLYLINE`` / ``POLYLINE`` → ``PolylineEntity`` (chiusura preservata)
  - ``CIRCLE`` → ``CircleEntity``
  - ``ARC`` → ``PolylineEntity`` (approssimato a segmenti, ~1° per segmento)
  - ``ELLIPSE`` → ``PolylineEntity`` (approssimato con sampling)
  - ``SPLINE`` → ``PolylineEntity`` (approssimato con ``ezdxf`` flattening)
  - ``INSERT`` → espansione ricorsiva dei blocchi

Le unità vengono lette da ``$INSUNITS`` e convertite in millimetri.

Limiti noti MVP:
  - I bulges delle LWPOLYLINE non vengono convertiti in archi (retta).
  - I layer DXF non generano layer del core: tutte le entità vanno nel layer
    attivo al momento dell'importazione. Lo step successivo potrà raffinare
    questa scelta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

from lasercontrolsuite.cad.io.units import dxf_unit_scale_mm
from lasercontrolsuite.core.entities import (
    CircleEntity,
    Entity,
    PolylineEntity,
)
from lasercontrolsuite.core.matrix import Matrix2D


@dataclass
class DxfImportResult:
    """Risultato di un import DXF."""

    entities: list[Entity] = field(default_factory=list)
    layer_id: str = ""
    source_path: str = ""
    unit_scale: float = 1.0
    warnings: list[str] = field(default_factory=list)

    def bounds(self) -> tuple[float, float, float, float]:
        """Bounding box complessivo delle entità importate (mm, coordinate mondo)."""
        if not self.entities:
            return (0.0, 0.0, 0.0, 0.0)
        boxes = [e.world_bounding_box() for e in self.entities]
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        return (x0, y0, x1, y1)


def import_dxf(path: str | Path, layer_id: str) -> DxfImportResult:
    """Importa un file DXF e restituisce le entità convertite.

    Args:
        path: percorso del file DXF.
        layer_id: id del layer del core in cui inserire le entità.

    Returns:
        ``DxfImportResult`` con le entità pronte per essere aggiunte al
        documento. Le entità hanno ``layer_id`` impostato a ``layer_id``.

    Raises:
        FileNotFoundError: se il file non esiste.
        ezdxf.DXFStructureError: se il DXF è malformato.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File DXF non trovato: {path}")

    doc = ezdxf.readfile(str(p))
    insunits = int(doc.header.get("$INSUNITS", 4) or 4)
    unit_scale = dxf_unit_scale_mm(insunits)

    result = DxfImportResult(layer_id=layer_id, source_path=str(p), unit_scale=unit_scale)

    msp = doc.modelspace()
    for entity in msp:
        try:
            converted = _convert_entity(entity, unit_scale, layer_id, result.warnings)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"{entity.dxftype()}: {exc}")
            continue
        result.entities.extend(converted)

    return result


# =====================================================================
# Dispatch per tipo
# =====================================================================
def _convert_entity(
    e, scale: float, layer_id: str, warnings: list[str]
) -> list[Entity]:
    t = e.dxftype()
    handler = _HANDLERS.get(t)
    if handler is None:
        warnings.append(f"Tipo non supportato: {t}")
        return []
    return handler(e, scale, layer_id, warnings)


def _convert_line(e, scale: float, layer_id: str, warnings) -> list[Entity]:
    start = e.dxf.start
    end = e.dxf.end
    poly = PolylineEntity.line(
        layer_id=layer_id,
        x1=start.x * scale,
        y1=start.y * scale,
        x2=end.x * scale,
        y2=end.y * scale,
    )
    return [poly]


def _convert_lwpolyline(e, scale: float, layer_id: str, warnings) -> list[Entity]:
    pts = [(p[0] * scale, p[1] * scale) for p in e.get_points("xy")]
    if len(pts) < 2:
        return []
    closed = bool(e.closed)
    # Nota: i bulges non sono gestiti (verranno approssimati a segmenti).
    has_bulge = any(abs(p[4]) > 1e-12 for p in e.get_points("xyb") if len(p) > 4)
    if has_bulge:
        warnings.append("LWPOLYLINE con bulge: archi approssimati a segmenti rettilinei.")
    return [PolylineEntity(layer_id=layer_id, points=pts, closed=closed)]


def _convert_polyline(e, scale: float, layer_id: str, warnings) -> list[Entity]:
    pts: list[tuple[float, float]] = []
    for v in e.vertices:
        pts.append((v.dxf.location.x * scale, v.dxf.location.y * scale))
    if len(pts) < 2:
        return []
    closed = bool(e.is_closed)
    return [PolylineEntity(layer_id=layer_id, points=pts, closed=closed)]


def _convert_circle(e, scale: float, layer_id: str, warnings) -> list[Entity]:
    c = e.dxf.center
    return [
        CircleEntity(
            layer_id=layer_id,
            cx=c.x * scale,
            cy=c.y * scale,
            r=e.dxf.radius * scale,
        )
    ]


def _convert_arc(e, scale: float, layer_id: str, warnings) -> list[Entity]:
    """Approssima l'arco con segmenti (1° per segmento)."""
    import math

    c = e.dxf.center
    r = e.dxf.radius * scale
    a0 = math.radians(e.dxf.start_angle)
    a1 = math.radians(e.dxf.end_angle)
    # Normalizza sweep in [0, 2π)
    sweep = (a1 - a0) % (2.0 * math.pi)
    if sweep <= 1e-9:
        sweep = 2.0 * math.pi
    n = max(8, int(math.degrees(sweep)))  # ~1° per step

    pts: list[tuple[float, float]] = []
    for i in range(n + 1):
        t = i / n
        angle = a0 + sweep * t
        pts.append(
            (
                (c.x + r * math.cos(angle) / scale) * scale,
                (c.y + r * math.sin(angle) / scale) * scale,
            )
        )
    return [PolylineEntity(layer_id=layer_id, points=pts, closed=False)]


def _convert_ellipse(e, scale: float, layer_id: str, warnings) -> list[Entity]:
    c = e.dxf.center
    major = e.dxf.major_axis
    ratio = float(e.dxf.ratio)
    start = float(e.dxf.start_param)
    end = float(e.dxf.end_param)

    a = (major.x ** 2 + major.y ** 2) ** 0.5 * scale
    b = a * ratio
    # Rotazione del semiasse maggiore
    import math
    rot = math.atan2(major.y, major.x)

    sweep = (end - start) % (2.0 * math.pi)
    is_full = abs(sweep) < 1e-9 or abs(sweep - 2.0 * math.pi) < 1e-6
    if is_full:
        sweep = 2.0 * math.pi

    n = max(24, int(math.degrees(sweep)))
    pts: list[tuple[float, float]] = []
    cos_r, sin_r = math.cos(rot), math.sin(rot)
    for i in range(n + 1):
        t = start + sweep * i / n
        x = a * math.cos(t)
        y = b * math.sin(t)
        # Ruota e trasla
        xr = x * cos_r - y * sin_r + c.x * scale
        yr = x * sin_r + y * cos_r + c.y * scale
        pts.append((xr, yr))
    return [PolylineEntity(layer_id=layer_id, points=pts, closed=is_full)]


def _convert_spline(e, scale: float, layer_id: str, warnings) -> list[Entity]:
    """Approssima la spline con ``flattening``."""
    try:
        pts = [(p.x * scale, p.y * scale) for p in e.flattening(distance=0.05 * scale)]
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"SPLINE flattening fallito: {exc}")
        return []
    if len(pts) < 2:
        return []
    return [PolylineEntity(layer_id=layer_id, points=pts, closed=False)]


def _convert_insert(e, scale: float, layer_id: str, warnings) -> list[Entity]:
    """Espande i blocchi di una INSERT applicando la trasformazione."""
    import math

    # Transform della INSERT (in unità DXF, quindi scaliamo dopo)
    insert_point = e.dxf.insert
    sx = float(getattr(e.dxf, "xscale", 1.0) or 1.0)
    sy = float(getattr(e.dxf, "yscale", 1.0) or 1.0)
    rot = math.radians(float(getattr(e.dxf, "rotation", 0.0) or 0.0))

    # Composizione: scale → rotazione → traslazione
    m = (
        Matrix2D.translation(insert_point.x, insert_point.y)
        @ Matrix2D.rotation(rot)
        @ Matrix2D.scaling(sx, sy)
    )

    entities: list[Entity] = []
    try:
        virtual = list(e.virtual_entities())
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"INSERT: espansione fallita: {exc}")
        return []

    for sub in virtual:
        sub_entities = _convert_entity(sub, scale, layer_id, warnings)
        for se in sub_entities:
            # Applica la trasformazione (in coordinate DXF, poi la scala
            # verrà applicata dalle entità stesse tramite la transform).
            # Le entità escono già in mm, quindi la trasformazione va fatta
            # in mm: moltiplichiamo la traslazione per scale.
            mm_m = Matrix2D(
                m.a, m.b, m.c, m.d, m.e * scale, m.f * scale
            )
            se.transform = mm_m @ se.transform
            entities.append(se)
    return entities


_HANDLERS = {
    "LINE": _convert_line,
    "LWPOLYLINE": _convert_lwpolyline,
    "POLYLINE": _convert_polyline,
    "CIRCLE": _convert_circle,
    "ARC": _convert_arc,
    "ELLIPSE": _convert_ellipse,
    "SPLINE": _convert_spline,
    "INSERT": _convert_insert,
}