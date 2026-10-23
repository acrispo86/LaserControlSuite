"""Gestore del tema corrente (dark/light) con persistenza e signal.

Design
------
- Singleton (``ThemeManager.instance()``) perché il tema è globale.
- Signal ``themeChanged(str)`` emesso **dopo** che ``_current_name`` è
  stato aggiornato.
- Persistenza via ``QSettings`` (chiave ``ui/theme``).
- ``apply_to_app(app)`` è il metodo che i chiamanti usano per:
    1. applicare il QSS globale,
    2. applicare una ``QPalette`` coerente (placeholder, selection,
       ButtonText, ...),
    3. forzare il **repolish** di tutti i widget esistenti.

  Il punto 3 è essenziale: ``setStyleSheet`` su QApplication non ricostruisce
  in modo affidabile lo stile calcolato di **ogni** widget già creato
  (in particolare QToolButton dentro QToolBar). Il repolish esplicito
  garantisce che il nuovo QSS/palette vengano effettivamente applicati.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from lasercontrolsuite.resources.theme import DARK, LIGHT, Theme


ORG_NAME = "LaserControlSuite"
APP_NAME = "LaserControlSuite"
SETTINGS_KEY = "ui/theme"

VALID_THEMES: tuple[str, ...] = ("dark", "light")
DEFAULT_THEME = "dark"


class ThemeManager(QObject):
    """Singleton che gestisce il tema corrente."""

    #: Emesso **dopo** il cambio, con il nome del tema (``"dark"``/``"light"``).
    themeChanged = Signal(str)

    _instance: "ThemeManager | None" = None

    # ------------------------------------------------------------------ singleton
    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @classmethod
    def reset_for_tests(cls, qsettings: QSettings | None = None) -> "ThemeManager":
        """Ricrea il singleton. Solo per i test."""
        cls._instance = ThemeManager(qsettings=qsettings)
        return cls._instance

    def __init__(self, qsettings: QSettings | None = None) -> None:
        super().__init__()
        self._qs = (
            qsettings if qsettings is not None
            else QSettings(ORG_NAME, APP_NAME)
        )
        self._current_name: str = DEFAULT_THEME

    # ------------------------------------------------------------------ API
    def current_name(self) -> str:
        return self._current_name

    def theme(self) -> Theme:
        return LIGHT if self._current_name == "light" else DARK

    def qss(self) -> str:
        return self.theme().qss()

    def set_theme(self, name: str, *, persist: bool = True) -> None:
        """Cambia tema ed emette ``themeChanged`` (se diverso dal corrente)."""
        if name not in VALID_THEMES:
            raise ValueError(
                f"Tema sconosciuto: {name!r}. Validi: {VALID_THEMES}."
            )
        if name == self._current_name:
            return
        self._current_name = name
        if persist:
            self._save_preference()
        self.themeChanged.emit(name)

    def load_preference(self) -> str:
        """Legge il tema salvato e lo applica. Ritorna il nome applicato."""
        raw = self._qs.value(SETTINGS_KEY, DEFAULT_THEME, type=str) or DEFAULT_THEME
        name = raw if raw in VALID_THEMES else DEFAULT_THEME
        self._current_name = name
        return name

    # ------------------------------------------------------------------ app
    def apply_to_app(self, app: QApplication) -> None:
        """Applica QSS + palette + repolish all'applicazione.

        Chiamato al boot (``configure_application``) e ad ogni cambio tema.
        """
        app.setStyleSheet(self.qss())
        app.setPalette(self._build_palette())

        # Forza il repolish di tutti i widget esistenti: senza questo,
        # QToolButton in QToolBar e altri widget non ricostruiscono lo
        # stile calcolato e continuano a usare la palette precedente.
        for w in app.allWidgets():
            try:
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()
            except (RuntimeError, AttributeError):
                # Widget distrutto o non ancora pronto: ignora.
                pass

    def _build_palette(self) -> QPalette:
        """Palette coerente col tema corrente."""
        t = self.theme()
        p = QPalette()
        # Ruoli attivi
        p.setColor(QPalette.ColorRole.Window, QColor(t.bg_window))
        p.setColor(QPalette.ColorRole.WindowText, QColor(t.fg_primary))
        p.setColor(QPalette.ColorRole.Base, QColor(t.bg_input))
        p.setColor(QPalette.ColorRole.AlternateBase, QColor(t.bg_panel))
        p.setColor(QPalette.ColorRole.Text, QColor(t.fg_primary))
        p.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.fg_secondary))
        p.setColor(QPalette.ColorRole.Button, QColor(t.bg_panel))
        p.setColor(QPalette.ColorRole.ButtonText, QColor(t.fg_primary))
        p.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.bg_panel))
        p.setColor(QPalette.ColorRole.ToolTipText, QColor(t.fg_primary))
        p.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        p.setColor(QPalette.ColorRole.Link, QColor(t.accent))
        p.setColor(QPalette.ColorRole.BrightText, QColor("#FF0000"))
        # Ruoli disabilitati
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,
                   QColor(t.fg_disabled))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText,
                   QColor(t.fg_disabled))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText,
                   QColor(t.fg_disabled))
        return p

    # ------------------------------------------------------------------ internals
    def _save_preference(self) -> None:
        self._qs.setValue(SETTINGS_KEY, self._current_name)
        self._qs.sync()