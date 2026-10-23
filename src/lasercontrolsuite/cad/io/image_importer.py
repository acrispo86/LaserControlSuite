"""Adapter che converte il risultato di ``_tracer`` in entità del core.

Il tracer lavora in pixel con Y-down (OpenCV); il core lavora in mm con Y-up.
Questo modulo fa la conversione:
  - px → mm: ``25.4 / dpi``
  - flip Y: ``y_mm = (height_px - y_px) * 25.4 / dpi``

Il modulo ``_tracer`` (fornito dall'utente) richiede opencv e scikit-image:
viene importato **lazy** dentro ``trace_image_file`` per non rompere
l'import del pacchetto quando gli extra non sono installati.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lasercontrolsuite.core.entities import Entity, PolylineEntity


@dataclass
class ImageTraceOptions:
    """Parametri per il tracing di un'immagine."""

    mode: str = "outline"          # 'outline' | 'centerline' | 'both'
    threshold: int | None = None   # None = Otsu automatico
    invert: bool = False
    blur: int = 0
    max_side: int | None = None
    epsilon: float = 1.0
    min_area: float = 4.0
    min_length: int = 3
    prune: int = 6
    dpi: float = 96.0              # risoluzione dell'immagine (px per pollice)


@dataclass
class ImageTraceResult:
    """Risultato del tracing."""

    entities: list[Entity] = field(default_factory=list)
    layer_id: str = ""
    source_path: str = ""
    width_mm: float = 0.0
    height_mm: float = 0.0
    n_outlines: int = 0
    n_centerlines: int = 0

    def bounds(self) -> tuple[float, float, float, float]:
        if not self.entities:
            return (0.0, 0.0, 0.0, 0.0)
        boxes = [e.world_bounding_box() for e in self.entities]
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        return (x0, y0, x1, y1)


def trace_image_file(
    path: str | Path,
    layer_id: str,
    options: ImageTraceOptions | None = None,
) -> ImageTraceResult:
    """Traccia un'immagine raster e converte il risultato in entità del core.

    Args:
        path: percorso dell'immagine (PNG/JPG/BMP/...).
        layer_id: id del layer in cui inserire le entità.
        options: parametri di tracing. Se ``None`` usa i default.

    Returns:
        ``ImageTraceResult`` con entità in mm, coordinate Y-up.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Immagine non trovata: {path}")

    if options is None:
        options = ImageTraceOptions()

    # Import lazy: fallisce con messaggio chiaro se mancano le dipendenze
    try:
        from lasercontrolsuite.cad.io import _tracer
    except ImportError as exc:
        raise ImportError(
            "Il tracing immagini richiede le dipendenze opzionali. "
            "Installa con: pip install lasercontrolsuite[trace]"
        ) from exc

    trace = _tracer.trace_image(
        str(p),
        mode=options.mode,
        threshold=options.threshold,
        invert=options.invert,
        blur=options.blur,
        max_side=options.max_side,
        epsilon=options.epsilon,
        min_area=options.min_area,
        min_length=options.min_length,
        prune=options.prune,
    )

    return _convert_trace_result(trace, layer_id, str(p), options.dpi)


def _convert_trace_result(
    trace, layer_id: str, source_path: str, dpi: float
) -> ImageTraceResult:
    """Converte ``TraceResult`` in entità del core."""
    import numpy as np  # già dipendenza obbligatoria

    w_px, h_px = trace.size
    mm_per_px = 25.4 / dpi if dpi > 0 else 25.4 / 96.0

    result = ImageTraceResult(
        layer_id=layer_id,
        source_path=source_path,
        width_mm=w_px * mm_per_px,
        height_mm=h_px * mm_per_px,
        n_outlines=len(trace.outlines),
        n_centerlines=len(trace.centerlines),
    )

    def _convert(polylines, close_default: bool) -> list[Entity]:
        out: list[Entity] = []
        for pl in polylines:
            pts_px = pl.points  # np.ndarray (N, 2) — (x, y)
            if pts_px is None or len(pts_px) < 2:
                continue
            # Conversione: x_mm = x_px * mm_per_px
            #               y_mm = (h_px - y_px) * mm_per_px
            xs = pts_px[:, 0].astype(float)
            ys = pts_px[:, 1].astype(float)
            pts_mm = [
                (float(xs[i]) * mm_per_px,
                 float(h_px - ys[i]) * mm_per_px)
                for i in range(len(xs))
            ]
            closed = bool(pl.closed) if hasattr(pl, "closed") else close_default
            out.append(PolylineEntity(layer_id=layer_id, points=pts_mm, closed=closed))
        return out

    result.entities.extend(_convert(trace.outlines, close_default=True))
    result.entities.extend(_convert(trace.centerlines, close_default=False))

    return result