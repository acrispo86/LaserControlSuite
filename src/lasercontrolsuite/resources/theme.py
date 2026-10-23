"""Tema centralizzato: due palette (dark/light) + proxy per l'istanza attiva.

Layout tela stile LightBurn:
  * sfondo esterno: grigio (più scuro nel tema dark, più chiaro nel tema light)
  * area di lavoro: bianco puro
  * assi X (rosso) e Y (verde) sui bordi basso e sinistro
  * griglia leggera solo dentro l'area
  * entità scure (visibili su bianco)

Uso
---
``from lasercontrolsuite.resources.theme import THEME``

``THEME`` è un **proxy**: ogni accesso a un attributo (``THEME.accent``,
``THEME.qss()``) viene inoltrato all'istanza di ``Theme`` corrente gestita
da ``ThemeManager``. Questo permette di cambiare tema a runtime senza
dover toccare i moduli che già importano ``THEME``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Theme:
    """Palette e misure di un tema."""

    # ---------- Sfondi UI (chrome dell'app) ----------
    bg_window: str = "#252526"
    bg_panel: str = "#2D2D30"
    bg_canvas: str = "#1E1E1E"        # legacy
    bg_toolbar: str = "#333337"
    bg_input: str = "#3C3C41"

    # ---------- Testi ----------
    fg_primary: str = "#E0E0E0"
    fg_secondary: str = "#A0A0A0"
    fg_disabled: str = "#606060"

    # ---------- Bordi UI ----------
    border: str = "#3F3F46"
    border_strong: str = "#555558"

    # ---------- Accenti ----------
    accent: str = "#00D4FF"
    accent_dim: str = "#0088AA"
    accent_bg: str = "#00D4FF33"

    # ---------- Tela CAD (stile LightBurn) ----------
    canvas_outside_bg: str = "#585858"
    canvas_workarea_bg: str = "#FFFFFF"
    canvas_workarea_border: str = "#303030"
    canvas_axis_x_color: str = "#CC0000"
    canvas_axis_y_color: str = "#009900"
    canvas_axis_width: int = 2

    # ---------- Griglia sulla tela chiara ----------
    grid_minor: str = "#E5E5E5"
    grid_major: str = "#C8C8C8"
    grid_axis_x: str = "#CC0000"
    grid_axis_y: str = "#009900"

    # ---------- Entità (su tela chiara) ----------
    entity_default: str = "#1E1E1E"
    entity_selected: str = "#0066CC"
    entity_preview: str = "#0066CC"

    # ---------- Marker snap / origine ----------
    snap_marker: str = "#0078D4"
    origin_marker: str = "#CC0000"

    # ---------- Anteprima CAM ----------
    cam_travel: str = "#909090"
    cam_path_first: str = "#1565C0"
    cam_path_last: str = "#C62828"
    cam_start_marker: str = "#00A04B"
    cam_hover_boost: str = "#000000"
    cam_legend_bg: str = "#2D2D30F0"
    cam_legend_border: str = "#555558"
    cam_tooltip_bg: str = "#1E1E1EF0"

    # ---------- Console GRBL ----------
    console_bg: str = "#141414"
    console_tx: str = "#00D4FF"
    console_ok: str = "#4EC94E"
    console_error: str = "#FF5555"
    console_alarm: str = "#FF8800"
    console_status: str = "#FFD866"
    console_msg: str = "#A0A0A0"
    console_welcome: str = "#B0E0FF"
    console_info: str = "#888888"
    console_timestamp: str = "#707070"
    console_search_hl_bg: str = "#FFEB3B"
    console_search_hl_fg: str = "#000000"

    # ---------- Dimensioni UI ----------
    icon_size: int = 22
    icon_size_large: int = 26
    toolbar_button_size: int = 32
    toolbar_icon_spacing: int = 4

    # ---------- Font ----------
    font_family: str = "Segoe UI"
    font_mono: str = "Consolas"
    font_size: int = 9

    # ---------------------------------------------------------- alias
    @property
    def cam_outside_bg(self) -> str:
        return self.canvas_outside_bg

    @property
    def cam_workarea_bg(self) -> str:
        return self.canvas_workarea_bg

    @property
    def cam_workarea_border(self) -> str:
        return self.canvas_workarea_border

    @property
    def work_area_border(self) -> str:
        return self.canvas_workarea_border

    @property
    def work_area_outside_fill(self) -> str:
        return self.canvas_outside_bg

    def console_color_for(self, category: str) -> str:
        return {
            "tx": self.console_tx,
            "ok": self.console_ok,
            "error": self.console_error,
            "alarm": self.console_alarm,
            "status": self.console_status,
            "msg": self.console_msg,
            "welcome": self.console_welcome,
            "info": self.console_info,
        }.get(category, self.fg_primary)

    # ---------------------------------------------------------- qss
    def qss(self) -> str:
        return f"""
        QMainWindow, QDialog {{ background-color: {self.bg_window}; }}
        QWidget {{ color: {self.fg_primary}; }}
        QMenuBar {{
            background-color: {self.bg_window};
            color: {self.fg_primary};
            border-bottom: 1px solid {self.border};
        }}
        QMenuBar::item {{ padding: 4px 8px; background: transparent; }}
        QMenuBar::item:selected {{ background-color: {self.bg_panel}; }}
        QMenu {{
            background-color: {self.bg_panel};
            color: {self.fg_primary};
            border: 1px solid {self.border};
        }}
        QMenu::item {{ padding: 4px 24px; }}
        QMenu::item:selected {{ background-color: {self.accent_bg}; }}
        QMenu::separator {{ background: {self.border}; height: 1px; margin: 4px 8px; }}
        QStatusBar {{
            background-color: {self.bg_window};
            color: {self.fg_secondary};
            border-top: 1px solid {self.border};
        }}
        QStatusBar::item {{ border: none; }}
        QToolBar {{
            background-color: {self.bg_toolbar};
            border: none;
            spacing: {self.toolbar_icon_spacing}px;
            padding: 4px;
        }}
        QToolBar::separator {{
            background-color: {self.border};
            height: 1px;
            margin: 4px 2px;
        }}
        QToolButton, QToolBar > QToolButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 3px;
            color: {self.fg_primary};
        }}
        QToolButton:hover, QToolBar > QToolButton:hover {{
            background-color: {self.bg_panel};
            border-color: {self.border};
        }}
        QToolButton:checked, QToolBar > QToolButton:checked {{
            background-color: {self.accent_bg};
            border-color: {self.accent};
        }}
        QToolButton:pressed, QToolBar > QToolButton:pressed {{
            background-color: {self.accent_dim};
        }}
        QToolButton:disabled, QToolBar > QToolButton:disabled {{
            color: {self.fg_disabled};
        }}
        QPushButton {{
            background-color: {self.bg_panel};
            color: {self.fg_primary};
            border: 1px solid {self.border};
            border-radius: 3px;
            padding: 4px 12px;
            min-width: 70px;
        }}
        QPushButton:hover {{ background-color: {self.bg_input}; border-color: {self.accent}; }}
        QPushButton:pressed {{ background-color: {self.accent_dim}; color: #FFFFFF; }}
        QPushButton:disabled {{
            color: {self.fg_disabled};
            background-color: {self.bg_window};
            border-color: {self.border};
        }}
        QToolTip {{
            background-color: {self.bg_panel};
            color: {self.fg_primary};
            border: 1px solid {self.border_strong};
            padding: 3px;
        }}
        QDockWidget {{ color: {self.fg_primary}; }}
        QDockWidget::title {{
            background-color: {self.bg_panel};
            border-bottom: 1px solid {self.border};
            padding: 6px;
        }}
        QDockWidget > QWidget {{ background-color: {self.bg_panel}; }}
        QLabel {{ color: {self.fg_primary}; background: transparent; }}
        QLabel:disabled {{ color: {self.fg_disabled}; }}
        QDoubleSpinBox, QSpinBox, QLineEdit {{
            background-color: {self.bg_input};
            color: {self.fg_primary};
            border: 1px solid {self.border};
            border-radius: 3px;
            padding: 2px 4px;
            selection-background-color: {self.accent};
            selection-color: #FFFFFF;
        }}
        QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus {{ border-color: {self.accent}; }}
        QDoubleSpinBox::up-button, QSpinBox::up-button,
        QDoubleSpinBox::down-button, QSpinBox::down-button {{
            background-color: {self.bg_panel};
            border: none;
            width: 14px;
        }}
        QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
        QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{
            background-color: {self.accent_dim};
        }}
        QComboBox {{
            background-color: {self.bg_input};
            color: {self.fg_primary};
            border: 1px solid {self.border};
            border-radius: 3px;
            padding: 2px 4px;
            min-width: 60px;
        }}
        QComboBox:focus {{ border-color: {self.accent}; }}
        QComboBox::drop-down {{
            border: none;
            width: 18px;
            background-color: {self.bg_panel};
        }}
        QComboBox QAbstractItemView {{
            background-color: {self.bg_panel};
            color: {self.fg_primary};
            selection-background-color: {self.accent_bg};
            selection-color: {self.fg_primary};
            border: 1px solid {self.border};
        }}
        QCheckBox {{ color: {self.fg_primary}; background: transparent; spacing: 6px; }}
        QCheckBox::indicator {{
            width: 14px; height: 14px;
            border: 1px solid {self.border_strong};
            background-color: {self.bg_input};
            border-radius: 2px;
        }}
        QCheckBox::indicator:checked {{ background-color: {self.accent}; border-color: {self.accent}; }}
        QCheckBox::indicator:hover {{ border-color: {self.accent}; }}
        QGroupBox {{
            color: {self.fg_primary};
            border: 1px solid {self.border};
            border-radius: 4px;
            margin-top: 10px;
            padding-top: 10px;
            background-color: transparent;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 8px;
            padding: 0 4px;
            color: {self.fg_secondary};
            background-color: {self.bg_panel};
        }}
        QPlainTextEdit, QTextEdit {{
            background-color: {self.bg_input};
            color: {self.fg_primary};
            border: 1px solid {self.border};
            selection-background-color: {self.accent};
            selection-color: #FFFFFF;
        }}
        QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {self.accent}; }}
        QSplitter::handle {{ background-color: {self.border}; }}
        QSplitter::handle:horizontal {{ width: 3px; }}
        QSplitter::handle:vertical {{ height: 3px; }}
        QTabBar::tab {{
            background-color: {self.bg_window};
            color: {self.fg_secondary};
            border: 1px solid {self.border};
            border-bottom: none;
            padding: 4px 10px;
        }}
        QTabBar::tab:selected {{
            background-color: {self.bg_panel};
            color: {self.fg_primary};
        }}
        QScrollBar:vertical {{ background: {self.bg_panel}; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{
            background: {self.border_strong};
            min-height: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {self.accent_dim}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ background: {self.bg_panel}; height: 10px; margin: 0; }}
        QScrollBar::handle:horizontal {{
            background: {self.border_strong};
            min-width: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {self.accent_dim}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QDialogButtonBox {{ background: transparent; }}
        QTableWidget {{
            background-color: {self.bg_input};
            color: {self.fg_primary};
            gridline-color: {self.border};
            border: 1px solid {self.border};
            selection-background-color: {self.accent_bg};
            selection-color: {self.fg_primary};
        }}
        QHeaderView::section {{
            background-color: {self.bg_panel};
            color: {self.fg_secondary};
            border: 1px solid {self.border};
            padding: 3px 6px;
        }}
        """


# =====================================================================
# Palette: DARK (default) e LIGHT
# =====================================================================

DARK = Theme()  # i default sono già la palette scura


LIGHT = Theme(
    # Chrome chiaro
    bg_window="#F0F0F0",
    bg_panel="#FAFAFA",
    bg_canvas="#FFFFFF",
    bg_toolbar="#E4E4E4",
    bg_input="#FFFFFF",
    # Testi
    fg_primary="#1A1A1A",
    fg_secondary="#505050",
    fg_disabled="#909090",
    # Bordi
    border="#B8B8B8",
    border_strong="#8E8E8E",
    # Accenti
    accent="#0078D4",
    accent_dim="#005A9E",
    accent_bg="#0078D433",
    # Tela: sfondo esterno PIÙ CHIARO per il tema chiaro,
    # area di lavoro bianca, bordo grigio medio.
    canvas_outside_bg="#C8C8C8",
    canvas_workarea_bg="#FFFFFF",
    canvas_workarea_border="#808080",
    canvas_axis_x_color="#CC0000",
    canvas_axis_y_color="#009900",
    # Griglia
    grid_minor="#E5E5E5",
    grid_major="#C8C8C8",
    # Entità
    entity_default="#1E1E1E",
    entity_selected="#0066CC",
    entity_preview="#0066CC",
    # Marker
    snap_marker="#0078D4",
    origin_marker="#CC0000",
    # CAM preview
    cam_travel="#808080",
    cam_path_first="#1565C0",
    cam_path_last="#C62828",
    cam_start_marker="#00A04B",
    cam_hover_boost="#000000",
    cam_legend_bg="#FAFAFAF0",
    cam_legend_border="#8E8E8E",
    cam_tooltip_bg="#FAFAFAF0",
    # Console su sfondo bianco
    console_bg="#FFFFFF",
    console_tx="#0066CC",
    console_ok="#228B22",
    console_error="#CC0000",
    console_alarm="#CC6600",
    console_status="#997700",
    console_msg="#505050",
    console_welcome="#0050A0",
    console_info="#707070",
    console_timestamp="#909090",
    console_search_hl_bg="#FFEB3B",
    console_search_hl_fg="#000000",
)


# =====================================================================
# Proxy per l'istanza attiva
# =====================================================================

class _ThemeProxy:
    """Inoltra gli accessi all'istanza di ``Theme`` corrente."""

    def __getattr__(self, name: str) -> Any:
        from lasercontrolsuite.resources.theme_manager import ThemeManager
        return getattr(ThemeManager.instance().theme(), name)

    def qss(self) -> str:
        from lasercontrolsuite.resources.theme_manager import ThemeManager
        return ThemeManager.instance().qss()


#: Proxy globale. Gli accessi a `THEME.x` leggono il tema **corrente**.
THEME = _ThemeProxy()