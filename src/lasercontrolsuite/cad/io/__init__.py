"""Importatori di formati esterni (DXF, SVG) e tracing di immagini.

Nota sui lazy import:
  - ``dxf_importer`` e ``svg_importer`` dipendono da ``ezdxf``/``svgpathtools``,
    che sono dipendenze obbligatorie.
  - ``image_importer`` dipende da ``opencv`` e ``scikit-image``, che sono
    dipendenze **opzionali** del gruppo ``[trace]``. Viene importato solo su
    richiesta, per non rompere l'import del pacchetto quando l'utente non ha
    installato gli extra.
"""

from __future__ import annotations

from lasercontrolsuite.cad.io.dxf_importer import DxfImportResult, import_dxf
from lasercontrolsuite.cad.io.svg_importer import SvgImportResult, import_svg

__all__ = [
    "DxfImportResult",
    "import_dxf",
    "SvgImportResult",
    "import_svg",
]