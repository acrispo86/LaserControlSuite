"""Dialog impostazioni macchina: nome, dimensioni area, origine."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from lasercontrolsuite.config import Machine, MachineOrigin


class MachineSettingsDialog(QDialog):
    """Editor delle proprietà della macchina attiva."""

    def __init__(self, machine: Machine, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Impostazioni macchina laser")
        self.resize(380, 260)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Definisci l'area di lavoro del tuo laser. Questi valori vengono "
            "usati per l'anteprima del G-code e per visualizzare il piano "
            "di lavoro.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name_edit = QLineEdit(machine.name, self)
        form.addRow("Nome macchina:", self._name_edit)

        self._width_spin = QDoubleSpinBox(self)
        self._width_spin.setRange(1.0, 20000.0)
        self._width_spin.setDecimals(1)
        self._width_spin.setSuffix(" mm")
        self._width_spin.setValue(machine.width_mm)
        form.addRow("Larghezza area (X):", self._width_spin)

        self._height_spin = QDoubleSpinBox(self)
        self._height_spin.setRange(1.0, 20000.0)
        self._height_spin.setDecimals(1)
        self._height_spin.setSuffix(" mm")
        self._height_spin.setValue(machine.height_mm)
        form.addRow("Altezza area (Y):", self._height_spin)

        self._origin_combo = QComboBox(self)
        for origin in MachineOrigin:
            self._origin_combo.addItem(origin.label_it, origin.value)
        self._origin_combo.setCurrentIndex(
            max(0, self._origin_combo.findData(machine.origin.value))
        )
        form.addRow("Posizione origine:", self._origin_combo)

        layout.addLayout(form)
        layout.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ API
    def machine(self) -> Machine:
        """Restituisce la ``Machine`` corrispondente ai valori correnti."""
        origin_value = self._origin_combo.currentData()
        try:
            origin = MachineOrigin(origin_value)
        except (ValueError, TypeError):
            origin = MachineOrigin.BOTTOM_LEFT
        name = self._name_edit.text().strip() or "Laser"
        return Machine(
            name=name,
            width_mm=float(self._width_spin.value()),
            height_mm=float(self._height_spin.value()),
            origin=origin,
        )