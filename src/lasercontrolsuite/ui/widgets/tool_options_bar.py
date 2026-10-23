"""Barra opzioni tool (sotto la toolbar principale).

Mostra i parametri specifici del tool attivo:
  - Poligono: numero di lati
  - Stella: numero di punte, rapporto interno
  - Testo: dimensione font (mm)

I tool leggono i valori da questa barra attraverso i rispettivi setter
(es. ``PolygonTool.sides``).

Nota sulla verifica di visibilità:
  ``QWidget.isVisible()`` dipende dalla visibilità dell'intera gerarchia
  (top-level incluso) e non è adatto ai test headless. Usiamo ``isHidden()``
  che risponde alla domanda "questo widget è stato esplicitamente nascosto?".
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QWidget,
)


class ToolOptionsBar(QWidget):
    """Barra di opzioni del tool corrente."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #333337; border-bottom: 1px solid #3F3F46;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # --- Poligono
        self._poly_label = QLabel("Lati poligono:")
        self._poly_sides = QSpinBox(self)
        self._poly_sides.setRange(3, 128)
        self._poly_sides.setValue(6)

        # --- Stella
        self._star_label = QLabel("Punte stella:")
        self._star_points = QSpinBox(self)
        self._star_points.setRange(3, 64)
        self._star_points.setValue(5)

        self._star_ratio_label = QLabel("Rapporto interno:")
        self._star_ratio = QDoubleSpinBox(self)
        self._star_ratio.setRange(0.05, 0.95)
        self._star_ratio.setSingleStep(0.05)
        self._star_ratio.setDecimals(2)
        self._star_ratio.setValue(0.40)

        # --- Testo
        self._text_label = QLabel("Font (mm):")
        self._text_size = QDoubleSpinBox(self)
        self._text_size.setRange(0.5, 500.0)
        self._text_size.setValue(10.0)
        self._text_size.setDecimals(2)

        for w in (
            self._poly_label, self._poly_sides,
            self._star_label, self._star_points,
            self._star_ratio_label, self._star_ratio,
            self._text_label, self._text_size,
        ):
            layout.addWidget(w)
        layout.addStretch(1)

        self._all_widgets = [
            self._poly_label, self._poly_sides,
            self._star_label, self._star_points,
            self._star_ratio_label, self._star_ratio,
            self._text_label, self._text_size,
        ]

        # Widget "logici" per la verifica di visibilità dall'esterno.
        self._option_widgets: dict[str, list[QWidget]] = {
            "polygon_sides": [self._poly_label, self._poly_sides],
            "star_points": [self._star_label, self._star_points],
            "star_inner_ratio": [self._star_ratio_label, self._star_ratio],
            "text_size": [self._text_label, self._text_size],
        }

        self.show_for_tool("select")

    # ------------------------------------------------------------------ API
    @property
    def polygon_sides(self) -> int:
        return self._poly_sides.value()

    @property
    def star_points(self) -> int:
        return self._star_points.value()

    @property
    def star_inner_ratio(self) -> float:
        return self._star_ratio.value()

    @property
    def text_size_mm(self) -> float:
        return self._text_size.value()

    def show_for_tool(self, name: str) -> None:
        """Mostra solo i widget rilevanti per il tool indicato."""
        for w in self._all_widgets:
            w.setVisible(False)

        if name == "polygon":
            self._set_option_visible("polygon_sides", True)
        elif name == "star":
            self._set_option_visible("star_points", True)
            self._set_option_visible("star_inner_ratio", True)
        elif name == "text":
            self._set_option_visible("text_size", True)

    def is_option_visible(self, name: str) -> bool:
        """Verifica se l'opzione indicata è attualmente visibile.

        Usa ``isHidden()`` per essere indipendente dalla gerarchia: ritorna
        ``True`` se i widget dell'opzione **non** sono stati esplicitamente
        nascosti.

        Args:
            name: uno tra ``"polygon_sides"``, ``"star_points"``,
                ``"star_inner_ratio"``, ``"text_size"``.

        Raises:
            KeyError: se il nome dell'opzione non è riconosciuto.
        """
        widgets = self._option_widgets[name]
        return all(not w.isHidden() for w in widgets)

    # -------------------------------------------------------------- internals
    def _set_option_visible(self, name: str, visible: bool) -> None:
        for w in self._option_widgets[name]:
            w.setVisible(visible)