"""Lettura/scrittura delle preferenze persistenti tramite QSettings.

Schema delle chiavi QSettings:

    active_machine            (string)  nome della macchina attiva
    machines/                 (array)   elenco delle macchine conosciute
        machines/size         (int)
        machines/<i>/name     (string)
        machines/<i>/width_mm (double)
        machines/<i>/height_mm(double)
        machines/<i>/origin   (string)  valore di ``MachineOrigin``

Il wrapper è volutamente sottile: nessuna logica oltre a serializzazione
e default. Le decisioni di business (quale macchina è attiva, come
inizializzarla) sono qui, in un unico punto.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from lasercontrolsuite.config.machine import (
    DEFAULT_MACHINE_NAME,
    DEFAULT_WORK_AREA_MM,
    Machine,
    MachineOrigin,
)


ORG_NAME: str = "LaserControlSuite"
APP_NAME: str = "LaserControlSuite"


class Settings:
    """Accesso alle preferenze persistenti dell'app."""

    def __init__(self, qsettings: QSettings | None = None) -> None:
        # Iniettabile per i test (QSettings con INI in tmp_path).
        self._qs = qsettings if qsettings is not None else QSettings(ORG_NAME, APP_NAME)

    # ------------------------------------------------------------------ API
    def get_active_machine(self) -> Machine:
        """Macchina attiva. Se non esiste, crea e salva un default."""
        self._qs.sync()
        machines = self._read_machines()
        if not machines:
            default = Machine(
                name=DEFAULT_MACHINE_NAME,
                width_mm=DEFAULT_WORK_AREA_MM,
                height_mm=DEFAULT_WORK_AREA_MM,
                origin=MachineOrigin.BOTTOM_LEFT,
            )
            self._write_machine(default)
            self._qs.setValue("active_machine", default.name)
            self._qs.sync()
            return default

        active_name = self._qs.value("active_machine", "", type=str) or ""
        for m in machines:
            if m.name == active_name:
                return m
        # Nome attivo non corrisponde a nessuna macchina: usa la prima.
        fallback = machines[0]
        self._qs.setValue("active_machine", fallback.name)
        self._qs.sync()
        return fallback

    def set_active_machine(self, machine: Machine) -> None:
        """Imposta la macchina attiva, salvandola se nuova."""
        self._write_machine(machine)
        self._qs.setValue("active_machine", machine.name)
        self._qs.sync()

    def list_machines(self) -> list[Machine]:
        self._qs.sync()
        return self._read_machines()

    def clear(self) -> None:
        """Cancella tutte le preferenze (per i test)."""
        self._qs.clear()
        self._qs.sync()

    # ------------------------------------------------------------- internals
    def _read_machines(self) -> list[Machine]:
        out: list[Machine] = []
        size = self._qs.beginReadArray("machines")
        try:
            for i in range(size):
                self._qs.setArrayIndex(i)
                name = self._qs.value("name", "", type=str) or ""
                if not name:
                    continue
                width = self._qs.value("width_mm", DEFAULT_WORK_AREA_MM, type=float)
                height = self._qs.value("height_mm", DEFAULT_WORK_AREA_MM, type=float)
                origin_str = self._qs.value("origin", MachineOrigin.BOTTOM_LEFT.value, type=str)
                try:
                    origin = MachineOrigin(origin_str)
                except ValueError:
                    origin = MachineOrigin.BOTTOM_LEFT
                try:
                    out.append(Machine(name=name, width_mm=float(width),
                                       height_mm=float(height), origin=origin))
                except ValueError:
                    continue
        finally:
            self._qs.endArray()
        return out

    def _write_machine(self, machine: Machine) -> None:
        machines = self._read_machines()
        replaced = False
        for i, existing in enumerate(machines):
            if existing.name == machine.name:
                machines[i] = machine
                replaced = True
                break
        if not replaced:
            machines.append(machine)

        self._qs.beginWriteArray("machines", len(machines))
        try:
            for i, m in enumerate(machines):
                self._qs.setArrayIndex(i)
                self._qs.setValue("name", m.name)
                self._qs.setValue("width_mm", float(m.width_mm))
                self._qs.setValue("height_mm", float(m.height_mm))
                self._qs.setValue("origin", m.origin.value)
        finally:
            self._qs.endArray()
        self._qs.sync()