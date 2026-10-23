"""Motore di snapping per il canvas CAD.

Ordine di priorità:
  1. punti di snap espliciti degli item (endpoint, midpoint, centri, ...)
  2. intersezioni con la griglia (fallback, sempre attivo)

Gli item che vogliono esporre punti di snap devono implementare il protocollo
``SnapProvider``: basta un metodo ``snap_points() -> Iterable[QPointF]``.

Il motore è indipendente dalla UI: opera su coordinate scena e su una scala
``px_per_unit`` passata dal chiamante.
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from PySide6.QtCore import QPointF


@runtime_checkable
class SnapProvider(Protocol):
    """Protocollo per item che espongono punti di snap."""

    def snap_points(self) -> Iterable[QPointF]:
        """Restituisce i punti notevoli dell'item in coordinate scena."""
        ...  # pragma: no cover - puro protocollo


class SnapEngine:
    """Calcola il punto di snap più vicino a una posizione data.

    Attributes:
        grid_step: passo della griglia di snap (mm). Se ``<= 0`` lo snap a
            griglia è disabilitato e si considera solo lo snap a item.
        enabled: se ``False``, ``snap()`` ritorna la posizione originale.
        pixel_tolerance: tolleranza in pixel per lo snap a item.
    """

    def __init__(
        self,
        grid_step: float = 1.0,
        enabled: bool = True,
        pixel_tolerance: float = 10.0,
    ) -> None:
        self.grid_step = float(grid_step)
        self.enabled = bool(enabled)
        self.pixel_tolerance = float(pixel_tolerance)

    # ------------------------------------------------------------------ API
    def snap(self, scene_pos: QPointF, view) -> QPointF:
        """Restituisce la posizione agganciata.

        Args:
            scene_pos: posizione del cursore in coordinate scena (mm).
            view: ``CadGraphicsView`` da cui ricavare la scala corrente.

        Returns:
            Punto agganciato. Se lo snap è disabilitato ritorna ``scene_pos``
            (stesso oggetto). Altrimenti:
              - il punto di snap a item più vicino, se entro tolleranza;
              - altrimenti il punto sulla griglia;
              - altrimenti ``scene_pos``.
        """
        if not self.enabled:
            return scene_pos

        px_per_unit = abs(view.transform().m11())
        if px_per_unit <= 0.0:
            return scene_pos
        tol_scene = self.pixel_tolerance / px_per_unit
        tol_scene_sq = tol_scene * tol_scene

        best: QPointF | None = None
        best_d2 = tol_scene_sq

        scene = view.cad_scene
        for item in scene.items():
            if not isinstance(item, SnapProvider):
                continue
            for pt in item.snap_points():
                d2 = (pt.x() - scene_pos.x()) ** 2 + (pt.y() - scene_pos.y()) ** 2
                if d2 <= best_d2:
                    best_d2 = d2
                    best = QPointF(pt)

        if best is not None:
            return best

        if self.grid_step > 0.0:
            gx = round(scene_pos.x() / self.grid_step) * self.grid_step
            gy = round(scene_pos.y() / self.grid_step) * self.grid_step
            return QPointF(gx, gy)

        return scene_pos