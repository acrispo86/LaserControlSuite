"""Smoke test: l'applicazione si importa, la finestra si crea, i test girano.

Strategia:
- Un'unica ``QApplication`` per sessione, gestita dal fixture ``qapp``.
- I test che invocano ``main()`` non devono chiudere l'applicazione
  condivisa: verifichiamo il comportamento tramite ``QTimer`` e
  intercettando la chiusura della finestra.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Istanza condivisa di QApplication per tutti i test della sessione."""
    from lasercontrolsuite.app import get_or_create_qapplication

    return get_or_create_qapplication([])


def test_version_exposed() -> None:
    """Il pacchetto espone la versione."""
    import lasercontrolsuite

    assert lasercontrolsuite.__version__ == "0.1.0"


def test_get_or_create_qapplication_returns_singleton(qapp: QApplication) -> None:
    """Il helper restituisce sempre la stessa istanza, senza ricrearla."""
    from lasercontrolsuite.app import get_or_create_qapplication

    same = get_or_create_qapplication([])
    assert same is qapp


def test_main_window_creates(qapp: QApplication) -> None:
    """La MainWindow si istanzia e ha titolo/menù corretti."""
    from lasercontrolsuite.ui.main_window import MainWindow

    window = MainWindow()
    try:
        assert window.windowTitle().startswith("LaserControlSuite")
        assert window.centralWidget() is not None
        assert window.statusBar() is not None
        menu_titles = [a.text() for a in window.menuBar().actions()]
        assert "&File" in menu_titles
        assert "&?" in menu_titles
    finally:
        window.close()


def test_main_runs_and_quits(qapp: QApplication) -> None:
    """``main()`` ritorna 0 quando l'event loop termina.

    Nota: ``main()`` riusa la QApplication condivisa del fixture; il timer
    chiude l'event loop dopo 50 ms. Non chiamiamo ``qapp.quit()`` prima perché
    l'event loop non è ancora partito.
    """
    from PySide6.QtCore import QTimer

    from lasercontrolsuite.app import main

    QTimer.singleShot(50, qapp.quit)
    exit_code = main([])
    assert exit_code == 0