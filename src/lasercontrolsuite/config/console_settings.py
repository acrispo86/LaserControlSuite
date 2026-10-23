"""Preferenze persistenti della Console GRBL.

Wrapper sottile su ``QSettings`` con namespace ``console/``. Un solo punto
di verità per: filtri di categoria, timestamp, autoscroll, macro.

Non contiene logica di rendering: espone solo getter/setter tipizzati che
il ``ConsolePanel`` legge e scrive. Le default sono qui, non nel pannello.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from lasercontrolsuite.config.settings import APP_NAME, ORG_NAME


#: Categorie di log riconosciute dalla console. L'ordine è quello di
#: visualizzazione delle checkbox e dei contatori.
CATEGORIES: tuple[str, ...] = ("ok", "error", "alarm", "status", "msg", "tx")

#: Macro suggerite la prima volta che l'utente apre la console.
DEFAULT_MACROS: tuple[str, ...] = (
    "$$",
    "$H",
    "$X",
    "?",
    "$I",
    "G10 L2 P1 X0 Y0",
    "G92 X0 Y0",
)


class ConsoleSettings:
    """Wrapper tipizzato su ``QSettings`` per la Console GRBL."""

    def __init__(self, qsettings: QSettings | None = None) -> None:
        self._qs = (
            qsettings
            if qsettings is not None
            else QSettings(ORG_NAME, APP_NAME)
        )

    # ------------------------------------------------------------------ filtri
    def get_show_category(self, category: str) -> bool:
        """True se la categoria va mostrata nel log (default: True)."""
        default = True
        return bool(self._qs.value(f"console/show/{category}", default, type=bool))

    def set_show_category(self, category: str, value: bool) -> None:
        self._qs.setValue(f"console/show/{category}", bool(value))
        self._qs.sync()

    def get_all_show(self) -> dict[str, bool]:
        return {c: self.get_show_category(c) for c in CATEGORIES}

    # ------------------------------------------------------------- timestamp
    def get_timestamp(self) -> bool:
        return bool(self._qs.value("console/timestamp", False, type=bool))

    def set_timestamp(self, value: bool) -> None:
        self._qs.setValue("console/timestamp", bool(value))
        self._qs.sync()

    # ------------------------------------------------------------ autoscroll
    def get_autoscroll(self) -> bool:
        return bool(self._qs.value("console/autoscroll", True, type=bool))

    def set_autoscroll(self, value: bool) -> None:
        self._qs.setValue("console/autoscroll", bool(value))
        self._qs.sync()

    # ----------------------------------------------------------------- macro
    def get_macros(self) -> list[str]:
        """Ritorna la lista macro. Alla prima apertura popola con le default."""
        size = self._qs.beginReadArray("console/macros")
        try:
            if size == 0:
                macros = list(DEFAULT_MACROS)
                self.set_macros(macros)
                return macros
            out: list[str] = []
            for i in range(size):
                self._qs.setArrayIndex(i)
                cmd = self._qs.value("cmd", "", type=str) or ""
                if cmd:
                    out.append(cmd)
            return out
        finally:
            self._qs.endArray()

    def set_macros(self, macros: list[str]) -> None:
        self._qs.beginWriteArray("console/macros", len(macros))
        try:
            for i, cmd in enumerate(macros):
                self._qs.setArrayIndex(i)
                self._qs.setValue("cmd", cmd)
        finally:
            self._qs.endArray()
        self._qs.sync()

    def add_macro(self, command: str) -> list[str]:
        macros = self.get_macros()
        if command and command not in macros:
            macros.append(command)
            self.set_macros(macros)
        return macros

    def remove_macro(self, command: str) -> list[str]:
        macros = [m for m in self.get_macros() if m != command]
        self.set_macros(macros)
        return macros

    def clear(self) -> None:
        """Cancella le preferenze console (per i test)."""
        self._qs.beginGroup("console")
        try:
            self._qs.remove("")
        finally:
            self._qs.endGroup()
        self._qs.sync()