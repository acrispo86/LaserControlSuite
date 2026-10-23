"""Dialog per gli array (lineare e circolare)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class ArrayDialog(QDialog):
    """Chiede i parametri per un array lineare o circolare."""

    def __init__(
        self,
        parent=None,
        default_center: tuple[float, float] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Array")
        self.setModal(True)

        layout = QVBoxLayout(self)
        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_linear_tab(), "Lineare")
        self._tabs.addTab(self._build_polar_tab(default_center), "Circolare")
        layout.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_linear_tab(self) -> QWidget:
        w = QWidget(self)
        form = QFormLayout(w)
        self._rows = QSpinBox(w)
        self._rows.setRange(1, 200)
        self._rows.setValue(1)
        self._cols = QSpinBox(w)
        self._cols.setRange(1, 200)
        self._cols.setValue(2)

        self._dx = QDoubleSpinBox(w)
        self._dx.setRange(-10000.0, 10000.0)
        self._dx.setDecimals(3)
        self._dx.setValue(20.0)
        self._dx.setSuffix(" mm")

        self._dy = QDoubleSpinBox(w)
        self._dy.setRange(-10000.0, 10000.0)
        self._dy.setDecimals(3)
        self._dy.setValue(0.0)
        self._dy.setSuffix(" mm")

        form.addRow("Righe:", self._rows)
        form.addRow("Colonne:", self._cols)
        form.addRow("Δ X:", self._dx)
        form.addRow("Δ Y:", self._dy)
        return w

    def _build_polar_tab(self, default_center: tuple[float, float] | None) -> QWidget:
        w = QWidget(self)
        form = QFormLayout(w)

        cx, cy = default_center if default_center is not None else (0.0, 0.0)

        self._cx = QDoubleSpinBox(w)
        self._cx.setRange(-1e6, 1e6)
        self._cx.setDecimals(3)
        self._cx.setValue(cx)
        self._cx.setSuffix(" mm")

        self._cy = QDoubleSpinBox(w)
        self._cy.setRange(-1e6, 1e6)
        self._cy.setDecimals(3)
        self._cy.setValue(cy)
        self._cy.setSuffix(" mm")

        self._count = QSpinBox(w)
        self._count.setRange(2, 200)
        self._count.setValue(4)

        self._total_angle = QDoubleSpinBox(w)
        self._total_angle.setRange(0.1, 360.0)
        self._total_angle.setDecimals(1)
        self._total_angle.setValue(360.0)
        self._total_angle.setSuffix(" °")

        self._start_angle = QDoubleSpinBox(w)
        self._start_angle.setRange(-360.0, 360.0)
        self._start_angle.setDecimals(1)
        self._start_angle.setValue(0.0)
        self._start_angle.setSuffix(" °")

        self._rotate_copies = QCheckBox("Ruota le copie", w)
        self._rotate_copies.setChecked(True)

        form.addRow("Centro X:", self._cx)
        form.addRow("Centro Y:", self._cy)
        form.addRow("Numero elementi:", self._count)
        form.addRow("Angolo totale:", self._total_angle)
        form.addRow("Angolo iniziale:", self._start_angle)
        form.addRow("", self._rotate_copies)
        return w

    # ------------------------------------------------------------------ API
    def mode(self) -> str:
        """Restituisce ``"linear"`` o ``"polar"`` in base alla tab attiva."""
        return "linear" if self._tabs.currentIndex() == 0 else "polar"

    def linear_values(self) -> tuple[int, int, float, float]:
        return (
            self._rows.value(),
            self._cols.value(),
            self._dx.value(),
            self._dy.value(),
        )

    def polar_values(self) -> tuple[tuple[float, float], int, float, float, bool]:
        return (
            (self._cx.value(), self._cy.value()),
            self._count.value(),
            self._total_angle.value(),
            self._start_angle.value(),
            self._rotate_copies.isChecked(),
        )