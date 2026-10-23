"""Bootstrap dell'applicazione Qt."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from lasercontrolsuite import __version__
from lasercontrolsuite.resources.theme_manager import ThemeManager
from lasercontrolsuite.ui.main_window import MainWindow


def get_or_create_qapplication(argv: list[str] | None = None) -> QApplication:
    """Restituisce l'istanza esistente di ``QApplication`` o ne crea una nuova."""
    existing = QApplication.instance()
    if existing is not None:
        if isinstance(existing, QApplication):
            return existing
        raise RuntimeError(
            "Esiste già un QCoreApplication non-GUI: impossibile creare "
            "una QApplication sopra di esso."
        )
    if argv is None:
        argv = sys.argv
    return QApplication(argv)


def configure_application(app: QApplication) -> None:
    """Imposta metadati, carica la preferenza tema, applica QSS + palette."""
    app.setApplicationName("LaserControlSuite")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("LaserControlSuite")
    app.setOrganizationDomain("lasercontrolsuite.local")

    manager = ThemeManager.instance()
    manager.load_preference()
    manager.apply_to_app(app)


def main(argv: list[str] | None = None) -> int:
    app = get_or_create_qapplication(argv)
    configure_application(app)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())