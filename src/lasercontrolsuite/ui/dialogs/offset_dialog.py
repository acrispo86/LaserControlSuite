"""Dialog per offset/contorno (inset/outset)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QVBoxLayout,
)


class OffsetDialog(QDialog):
    """Chiede i parametri per un offset (inset/outset)."""

    def __init__(
        self, parent=None, default_distance: float = 0.5
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Offset / Contorno")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._distance = QDoubleSpinBox(self)
        self._distance.setRange(0.001, 1000.0)
        self._distance.setDecimals(3)
        self._distance.setValue(default_distance)
        self._distance.setSuffix(" mm")
        self._distance.setSingleStep(0.1)

        self._mode = QComboBox(self)
        self._mode.addItem("Esterno (outset)", "outset")
        self._mode.addItem("Interno (inset)", "inset")

        self._join = QComboBox(self)
        self._join.addItem("Arrotondato", "round")
        self._join.addItem("Mitre", "mitre")
        self._join.addItem("Smussato", "bevel")

        form.addRow("Distanza:", self._distance)
        form.addRow("Lato:", self._mode)
        form.addRow("Giunzioni:", self._join)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[float, str, str]:
        """Restituisce ``(distance_mm, mode_str, join_style_str)``."""
        return (
            self._distance.value(),
            self._mode.currentData(),
            self._join.currentData(),
        )