"""Finestra principale di LaserControlSuite."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from lasercontrolsuite import __version__
from lasercontrolsuite.cad.shortcuts import Shortcuts
from lasercontrolsuite.cad.toolbar import DrawingToolBar
from lasercontrolsuite.cad.tools import (
    BezierTool, EllipseTool, LineTool, NodeEditTool, PenTool,
    PolygonTool, PolylineTool, RectTool, SelectTool, StarTool, TextTool,
)
from lasercontrolsuite.cad.view import CadGraphicsView
from lasercontrolsuite.comm.controller import GrblController
from lasercontrolsuite.config import Settings
from lasercontrolsuite.core.operations import AlignMode, DistributeMode
from lasercontrolsuite.resources.icons import make_icon
from lasercontrolsuite.resources.theme import THEME
from lasercontrolsuite.resources.theme_manager import ThemeManager
from lasercontrolsuite.ui.dialogs.array_dialog import ArrayDialog
from lasercontrolsuite.ui.dialogs.gcode_viewer_dialog import GCodeViewerDialog
from lasercontrolsuite.ui.dialogs.machine_settings_dialog import MachineSettingsDialog
from lasercontrolsuite.ui.dialogs.trace_dialog import TraceDialog
from lasercontrolsuite.ui.panels.cam_panel import CamPanel
from lasercontrolsuite.ui.panels.console_panel import ConsolePanel
from lasercontrolsuite.ui.panels.property_panel import PropertyPanel
from lasercontrolsuite.ui.widgets.tool_options_bar import ToolOptionsBar


class MainWindow(QMainWindow):
    """Finestra principale dell'applicazione."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"LaserControlSuite v{__version__}")
        self.resize(1440, 900)

        self._settings = Settings()
        self._theme_manager = ThemeManager.instance()
        self._canvas = CadGraphicsView(self)
        self._tool_options = ToolOptionsBar(self)

        central = QWidget(self)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self._tool_options)
        vbox.addWidget(self._canvas, 1)
        self.setCentralWidget(central)

        self._coord_label = QLabel("X:    0.000  Y:    0.000 mm")
        self._zoom_label = QLabel("Zoom: 100%")
        self._tool_label = QLabel("Strumento: Seleziona")
        self._machine_label = QLabel("Disconnesso")
        self._coord_label.setMinimumWidth(200)
        self._zoom_label.setMinimumWidth(90)
        self._tool_label.setMinimumWidth(160)
        self._machine_label.setMinimumWidth(240)

        self._build_tools()
        self._build_drawing_toolbar()
        self._build_action_toolbar()
        self._build_alignment_toolbar()
        self._build_menu()
        self._build_status_bar()
        self._build_docks()
        self._build_controller()
        self._connect_signals()

        self._canvas.set_tool(self._tools["select"])
        self._apply_machine_to_canvas()
        self._refresh_machine_label()

    @property
    def canvas(self) -> CadGraphicsView:
        return self._canvas

    @property
    def grbl_controller(self) -> GrblController:
        return self._grbl_controller

    @property
    def settings(self) -> Settings:
        return self._settings

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        try:
            self._property_panel.detach()
        except (AttributeError, RuntimeError):
            pass
        try:
            doc = self._canvas.cad_scene.document
            if doc is not None:
                doc.unsubscribe(self._cam_panel._on_document_event)
        except (AttributeError, RuntimeError):
            pass
        try:
            if self._canvas.current_tool is not None:
                self._canvas.current_tool.deactivate()
        except (AttributeError, RuntimeError):
            pass
        try:
            self._grbl_controller.shutdown()
            self._grbl_controller.wait(3000)
        except (AttributeError, RuntimeError):
            pass
        super().closeEvent(event)

    # ---------------------------------------------------------------- tools
    def _build_tools(self) -> None:
        v = self._canvas
        self._polygon_tool = PolygonTool(v, sides=self._tool_options.polygon_sides)
        self._star_tool = StarTool(
            v,
            points=self._tool_options.star_points,
            inner_ratio=self._tool_options.star_inner_ratio,
        )
        self._tools = {
            "select": SelectTool(v),
            "nodes": NodeEditTool(v),
            "pen": PenTool(v),
            "line": LineTool(v),
            "polyline": PolylineTool(v),
            "bezier": BezierTool(v),
            "rect": RectTool(v),
            "ellipse": EllipseTool(v),
            "polygon": self._polygon_tool,
            "star": self._star_tool,
            "text": TextTool(v),
        }
        self._tool_labels = {
            "select": "Seleziona", "nodes": "Nodi", "pen": "Penna",
            "line": "Linea", "polyline": "Polilinea", "bezier": "Bézier",
            "rect": "Rettangolo", "ellipse": "Ellisse", "polygon": "Poligono",
            "star": "Stella", "text": "Testo",
        }

        self._tool_options._poly_sides.valueChanged.connect(
            lambda v: setattr(self._polygon_tool, "sides", max(3, v))
        )
        self._tool_options._star_points.valueChanged.connect(
            lambda v: setattr(self._star_tool, "points", max(3, v))
        )
        self._tool_options._star_ratio.valueChanged.connect(
            lambda v: setattr(self._star_tool, "inner_ratio", max(0.05, min(0.95, v)))
        )

    def _build_drawing_toolbar(self) -> None:
        self._drawing_toolbar = DrawingToolBar(self)
        self._drawing_toolbar.toolChanged.connect(self._on_tool_changed)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._drawing_toolbar)

    def _build_action_toolbar(self) -> None:
        tb = QToolBar("Azioni", self)
        tb.setMovable(False)
        tb.setIconSize(QSize(THEME.icon_size, THEME.icon_size))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        stack = self._canvas.cad_scene.undo_stack

        self._undo_action = stack.createUndoAction(self, "Annulla")
        self._undo_action.setShortcut(QKeySequence(Shortcuts.UNDO))
        self._redo_action = stack.createRedoAction(self, "Ripeti")
        self._redo_action.setShortcuts(
            [QKeySequence(Shortcuts.REDO), QKeySequence(Shortcuts.REDO_ALT)]
        )
        tb.addAction(self._undo_action)
        tb.addAction(self._redo_action)
        tb.addSeparator()

        act_copy = QAction("Copia", self)
        act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        act_copy.triggered.connect(self._on_copy)
        tb.addAction(act_copy)

        act_paste = QAction("Incolla", self)
        act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        act_paste.triggered.connect(self._on_paste)
        tb.addAction(act_paste)

        act_dup = QAction("Duplica", self)
        act_dup.setShortcut(QKeySequence("Ctrl+D"))
        act_dup.triggered.connect(self._on_duplicate)
        tb.addAction(act_dup)

        act_del = QAction("Elimina", self)
        act_del.setShortcut(QKeySequence.StandardKey.Delete)
        act_del.triggered.connect(self._on_delete)
        tb.addAction(act_del)

        tb.addSeparator()

        act_convert = QAction("Converti in path", self)
        act_convert.setShortcut(QKeySequence("Ctrl+Shift+P"))
        act_convert.triggered.connect(self._on_convert_to_path)
        tb.addAction(act_convert)

        tb.addSeparator()

        act_array = QAction("Array…", self)
        act_array.triggered.connect(self._on_array)
        tb.addAction(act_array)

        act_union = QAction("Unione", self)
        act_union.triggered.connect(self._on_boolean_union)
        tb.addAction(act_union)

        act_diff = QAction("Sottrai", self)
        act_diff.triggered.connect(self._on_boolean_difference)
        tb.addAction(act_diff)

        act_inter = QAction("Intersezione", self)
        act_inter.triggered.connect(self._on_boolean_intersection)
        tb.addAction(act_inter)

        tb.addSeparator()

        act_zoom_in = QAction(make_icon("zoom_in"), "Zoom +", self)
        act_zoom_in.setShortcut(QKeySequence(Shortcuts.ZOOM_IN_ALT))
        act_zoom_in.triggered.connect(self._canvas.zoom_in)
        tb.addAction(act_zoom_in)

        act_zoom_out = QAction(make_icon("zoom_out"), "Zoom −", self)
        act_zoom_out.setShortcut(QKeySequence(Shortcuts.ZOOM_OUT))
        act_zoom_out.triggered.connect(self._canvas.zoom_out)
        tb.addAction(act_zoom_out)

        act_fit = QAction(make_icon("fit"), "Adatta", self)
        act_fit.setShortcut(QKeySequence(Shortcuts.ZOOM_FIT))
        act_fit.triggered.connect(self._canvas.fit_to_work_area)
        tb.addAction(act_fit)

    def _build_alignment_toolbar(self) -> None:
        tb = QToolBar("Allinea", self)
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        for label, mode in [
            ("⇤ Sx", AlignMode.LEFT),
            ("↔ Cx", AlignMode.CENTER_H),
            ("Dx ⇥", AlignMode.RIGHT),
            ("⇣ Giu", AlignMode.BOTTOM),
            ("↕ Cy", AlignMode.CENTER_V),
            ("Alto ⇡", AlignMode.TOP),
        ]:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, m=mode: self._canvas.editor.align(m))
            tb.addAction(act)

        tb.addSeparator()

        for label, mode in [
            ("↔ Distr.", DistributeMode.HORIZONTAL),
            ("↕ Distr.", DistributeMode.VERTICAL),
        ]:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, m=mode: self._canvas.editor.distribute(m))
            tb.addAction(act)

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        act_import_dxf = QAction("Importa &DXF…", self)
        act_import_dxf.setShortcut(QKeySequence("Ctrl+I"))
        act_import_dxf.triggered.connect(self._on_import_dxf)
        file_menu.addAction(act_import_dxf)

        act_import_svg = QAction("Importa &SVG…", self)
        act_import_svg.setShortcut(QKeySequence("Ctrl+Shift+I"))
        act_import_svg.triggered.connect(self._on_import_svg)
        file_menu.addAction(act_import_svg)

        act_trace = QAction("&Traccia immagine…", self)
        act_trace.triggered.connect(self._on_trace_image)
        file_menu.addAction(act_trace)

        file_menu.addSeparator()
        quit_action = QAction("&Esci", self)
        quit_action.setShortcut(QKeySequence(Shortcuts.QUIT))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = bar.addMenu("&Modifica")
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)
        edit_menu.addSeparator()
        for label, slot in [("Copia", self._on_copy), ("Incolla", self._on_paste),
                            ("Duplica", self._on_duplicate), ("Elimina", self._on_delete)]:
            act = QAction(label, self)
            act.triggered.connect(slot)
            edit_menu.addAction(act)
        edit_menu.addSeparator()
        act_convert = QAction("Converti in &path", self)
        act_convert.setShortcut(QKeySequence("Ctrl+Shift+P"))
        act_convert.triggered.connect(self._on_convert_to_path)
        edit_menu.addAction(act_convert)

        cam_menu = bar.addMenu("&CAM")
        act_gen = QAction("&Genera G-code…", self)
        act_gen.setShortcut(QKeySequence("Ctrl+G"))
        act_gen.triggered.connect(self._on_generate_gcode)
        cam_menu.addAction(act_gen)
        act_save = QAction("&Salva G-code come…", self)
        act_save.triggered.connect(self._on_save_gcode)
        cam_menu.addAction(act_save)

        controller_menu = bar.addMenu("&Controller")
        self._act_show_console = QAction("&Console…", self)
        self._act_show_console.setShortcut(QKeySequence("Ctrl+Shift+K"))
        self._act_show_console.triggered.connect(self._on_show_console)
        controller_menu.addAction(self._act_show_console)
        controller_menu.addSeparator()

        act_machine = QAction("&Impostazioni macchina…", self)
        act_machine.triggered.connect(self._on_machine_settings)
        controller_menu.addAction(act_machine)

        controller_menu.addSeparator()
        act_home = QAction("&Home ($H)", self)
        act_home.triggered.connect(self._on_home)
        controller_menu.addAction(act_home)
        act_unlock = QAction("&Unlock ($X)", self)
        act_unlock.triggered.connect(self._on_unlock)
        controller_menu.addAction(act_unlock)
        act_status = QAction("&Status (?)", self)
        act_status.triggered.connect(self._on_status_query)
        controller_menu.addAction(act_status)
        controller_menu.addSeparator()
        act_pause = QAction("&Pausa (!)", self)
        act_pause.triggered.connect(self._on_feed_hold)
        controller_menu.addAction(act_pause)
        act_resume = QAction("&Riprendi (~)", self)
        act_resume.triggered.connect(self._on_resume)
        controller_menu.addAction(act_resume)
        controller_menu.addSeparator()
        act_reset = QAction("Soft &Reset (Ctrl+X)", self)
        act_reset.triggered.connect(self._on_soft_reset)
        controller_menu.addAction(act_reset)

        view_menu = bar.addMenu("&Vista")
        fit_work = QAction("Adatta all'&area di lavoro", self)
        fit_work.setShortcut(QKeySequence("Ctrl+Shift+F"))
        fit_work.triggered.connect(self._canvas.fit_to_work_area)
        view_menu.addAction(fit_work)
        view_menu.addSeparator()
        reset_zoom = QAction("Zoom &100%", self)
        reset_zoom.setShortcut(QKeySequence(Shortcuts.ZOOM_RESET))
        reset_zoom.triggered.connect(self._canvas.reset_zoom)
        view_menu.addAction(reset_zoom)
        fit = QAction("&Adatta alla finestra", self)
        fit.setShortcut(QKeySequence(Shortcuts.ZOOM_FIT))
        fit.triggered.connect(self._canvas.fit_scene_in_view)
        view_menu.addAction(fit)

        # --- Sottomenu Tema ---
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Tema")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        self._act_theme_dark = QAction("&Scuro", self, checkable=True)
        self._act_theme_light = QAction("&Chiaro", self, checkable=True)
        current = self._theme_manager.current_name()
        self._act_theme_dark.setChecked(current == "dark")
        self._act_theme_light.setChecked(current == "light")
        theme_group.addAction(self._act_theme_dark)
        theme_group.addAction(self._act_theme_light)
        theme_menu.addAction(self._act_theme_dark)
        theme_menu.addAction(self._act_theme_light)

        self._act_theme_dark.triggered.connect(
            lambda: self._theme_manager.set_theme("dark")
        )
        self._act_theme_light.triggered.connect(
            lambda: self._theme_manager.set_theme("light")
        )

        help_menu = bar.addMenu("&?")
        about = QAction("&Informazioni su LaserControlSuite", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _build_status_bar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)
        status.addPermanentWidget(self._tool_label)
        status.addPermanentWidget(self._coord_label)
        status.addPermanentWidget(self._zoom_label)
        status.addPermanentWidget(self._machine_label)
        status.showMessage(
            "Ctrl+G: genera G-code — Ctrl+I: importa DXF — File: importa SVG, traccia immagine"
        )

    def _build_docks(self) -> None:
        self._property_panel = PropertyPanel(self._canvas, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._property_panel)

        self._cam_dock = QDockWidget("CAM", self)
        self._cam_dock.setObjectName("CamPanel")
        self._cam_panel = CamPanel(self._canvas, self._cam_dock, settings=self._settings)
        self._cam_dock.setWidget(self._cam_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._cam_dock)
        self.tabifyDockWidget(self._property_panel, self._cam_dock)
        self._property_panel.raise_()

    def _build_controller(self) -> None:
        self._grbl_controller = GrblController(parent=self)
        self._console_panel = ConsolePanel(self._grbl_controller, self)
        self._console_dock = QDockWidget("Console", self)
        self._console_dock.setObjectName("ConsolePanel")
        self._console_dock.setWidget(self._console_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._console_dock)
        self.tabifyDockWidget(self._cam_dock, self._console_dock)
        self._cam_dock.raise_()

    def _connect_signals(self) -> None:
        self._canvas.cursorMoved.connect(self._on_cursor_moved)
        self._canvas.zoomChanged.connect(self._on_zoom_changed)

        self._grbl_controller.connected.connect(self._on_controller_connected)
        self._grbl_controller.disconnected.connect(self._on_controller_disconnected)
        self._grbl_controller.statusReceived.connect(self._on_machine_status)
        self._grbl_controller.progressChanged.connect(self._on_job_progress)
        self._grbl_controller.jobFinished.connect(self._on_job_finished)
        self._grbl_controller.errorOccurred.connect(self._on_controller_error)
        self._grbl_controller.alarmReceived.connect(self._on_controller_alarm)
        self._grbl_controller.errorResponse.connect(self._on_controller_error_code)

        self._cam_panel.gcodeReady.connect(self._on_gcode_ready)

        # Cambio tema → riapplica QSS + palette + repolish globale.
        self._theme_manager.themeChanged.connect(self._on_theme_changed)

    # ---------------------------------------------------------------- slots
    def _on_theme_changed(self, name: str) -> None:
        app = QApplication.instance()
        if app is not None:
            self._theme_manager.apply_to_app(app)
        self._act_theme_dark.setChecked(name == "dark")
        self._act_theme_light.setChecked(name == "light")

    def _on_tool_changed(self, name: str) -> None:
        tool = self._tools.get(name)
        if tool is None:
            return
        self._canvas.set_tool(tool)
        self._tool_options.show_for_tool(name)
        label = self._tool_labels.get(name, name)
        self._tool_label.setText(f"Strumento: {label}")

    def _on_cursor_moved(self, pos: QPointF) -> None:
        self._coord_label.setText(f"X: {pos.x():8.3f}  Y: {pos.y():8.3f} mm")

    def _on_zoom_changed(self, zoom: float) -> None:
        self._zoom_label.setText(f"Zoom: {zoom * 100:.0f}%")

    def _on_copy(self) -> None:
        n = self._canvas.editor.copy_selection()
        if n:
            self.statusBar().showMessage(f"Copiate {n} entità", 2000)

    def _on_paste(self) -> None:
        n = self._canvas.editor.paste()
        if n:
            self.statusBar().showMessage(f"Incollate {n} entità", 2000)

    def _on_duplicate(self) -> None:
        n = self._canvas.editor.duplicate_selection()
        if n:
            self.statusBar().showMessage(f"Duplicate {n} entità", 2000)

    def _on_delete(self) -> None:
        n = self._canvas.editor.delete_selection()
        if n:
            self.statusBar().showMessage(f"Eliminate {n} entità", 2000)

    def _on_convert_to_path(self) -> None:
        n = self._canvas.editor.convert_selection_to_path()
        if n:
            self.statusBar().showMessage(f"Convertite {n} entità in path", 2000)
        elif self._canvas.editor.selected_entities():
            self.statusBar().showMessage("Nessuna conversione necessaria", 2000)

    def _on_array(self) -> None:
        sources = self._canvas.editor.selected_entities()
        if not sources:
            QMessageBox.information(self, "Array", "Seleziona prima una o più entità.")
            return

        # Calcola il centro del bbox della selezione per il default
        xs = []
        ys = []
        for e in sources:
            x0, y0, x1, y1 = e.world_bounding_box()
            xs.extend([x0, x1])
            ys.extend([y0, y1])
        if xs and ys:
            cx = (min(xs) + max(xs)) / 2.0
            cy = (min(ys) + max(ys)) / 2.0
            default_center = (cx, cy)
        else:
            default_center = (0.0, 0.0)

        dlg = ArrayDialog(self, default_center=default_center)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        if dlg.mode() == "linear":
            rows, cols, dx, dy = dlg.linear_values()
            n = self._canvas.editor.linear_array(rows, cols, dx, dy)
            label = "Array lineare"
        else:
            center, count, total_angle, start_angle, rotate_copies = dlg.polar_values()
            n = self._canvas.editor.polar_array(
                center=center,
                count=count,
                total_angle_deg=total_angle,
                start_angle_deg=start_angle,
                include_original=True,
                rotate_copies=rotate_copies,
            )
            label = "Array circolare"

        if n:
            self.statusBar().showMessage(f"{label}: create {n} copie", 2000)

    def _on_boolean_union(self) -> None:
        n, warnings = self._canvas.editor.boolean_union()
        self._show_boolean_result(n, warnings, "Unione")

    def _on_boolean_difference(self) -> None:
        n, warnings = self._canvas.editor.boolean_difference()
        self._show_boolean_result(n, warnings, "Sottrai")

    def _on_boolean_intersection(self) -> None:
        n, warnings = self._canvas.editor.boolean_intersection()
        self._show_boolean_result(n, warnings, "Intersezione")

    def _show_boolean_result(self, n: int, warnings: list[str], label: str) -> None:
        if n == 0:
            if warnings:
                QMessageBox.warning(self, label, "\n".join(warnings))
            return
        msg = f"{label}: {n} entità generate."
        if warnings:
            self._show_warnings(f"{label} — Avvisi", warnings)
        self.statusBar().showMessage(msg, 3000)

    def _on_import_dxf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importa DXF", "", "File DXF (*.dxf);;Tutti i file (*)"
        )
        if not path:
            return
        try:
            from lasercontrolsuite.cad.io.dxf_importer import import_dxf
            result = import_dxf(path, self._canvas.cad_scene.document.active_layer_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Errore import DXF", str(exc))
            return
        n = self._canvas.editor.import_entities(result.entities, "Importa DXF")
        self._canvas.fit_scene_in_view()
        msg = f"DXF: importate {n} entità (scala {result.unit_scale:g} mm/unità)"
        if result.warnings:
            msg += f" — {len(result.warnings)} avvisi"
        self.statusBar().showMessage(msg, 4000)
        if result.warnings:
            self._show_warnings("Avvisi import DXF", result.warnings)

    def _on_import_svg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importa SVG", "", "File SVG (*.svg);;Tutti i file (*)"
        )
        if not path:
            return
        try:
            from lasercontrolsuite.cad.io.svg_importer import import_svg
            result = import_svg(path, self._canvas.cad_scene.document.active_layer_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Errore import SVG", str(exc))
            return
        n = self._canvas.editor.import_entities(result.entities, "Importa SVG")
        self._canvas.fit_scene_in_view()
        msg = f"SVG: importate {n} entità — {result.width_mm:.1f}×{result.height_mm:.1f} mm"
        if result.warnings:
            msg += f" — {len(result.warnings)} avvisi"
        self.statusBar().showMessage(msg, 4000)
        if result.warnings:
            self._show_warnings("Avvisi import SVG", result.warnings)

    def _on_trace_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Traccia immagine", "",
            "Immagini (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;Tutti i file (*)"
        )
        if not path:
            return
        dlg = TraceDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        options = dlg.options()
        try:
            from lasercontrolsuite.cad.io.image_importer import trace_image_file
            result = trace_image_file(
                path, self._canvas.cad_scene.document.active_layer_id, options,
            )
        except ImportError as exc:
            QMessageBox.warning(self, "Dipendenze mancanti",
                f"{exc}\n\nInstalla con:\n    pip install -e \".[trace]\"")
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Errore tracciamento", str(exc))
            return
        n = self._canvas.editor.import_entities(result.entities, "Traccia immagine")
        self._canvas.fit_scene_in_view()
        self.statusBar().showMessage(
            f"Trace: {n} entità ({result.n_outlines} contorni, "
            f"{result.n_centerlines} centerline) — "
            f"{result.width_mm:.1f}×{result.height_mm:.1f} mm", 4000)

    def _on_generate_gcode(self) -> None:
        self._cam_dock.raise_()
        self._cam_panel._on_preview()

    def _on_save_gcode(self) -> None:
        gcode = self._cam_panel.last_gcode
        if not gcode:
            self._cam_panel._on_generate()
            gcode = self._cam_panel.last_gcode
        if not gcode:
            QMessageBox.information(self, "Salva G-code", "Nessun G-code da salvare. Genera prima.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva G-code", "job.nc", "G-code (*.nc *.gcode *.tap);;Tutti i file (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(gcode)
        except OSError as exc:
            QMessageBox.critical(self, "Errore salvataggio", str(exc))
            return
        self.statusBar().showMessage(f"G-code salvato: {path}", 3000)

    def _on_show_console(self) -> None:
        self._console_dock.show()
        self._console_dock.raise_()

    def _on_machine_settings(self) -> None:
        current = self._settings.get_active_machine()
        dlg = MachineSettingsDialog(current, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_machine = dlg.machine()
        self._settings.set_active_machine(new_machine)
        self._apply_machine_to_canvas()
        self._canvas.fit_to_work_area()
        self._refresh_machine_label()
        self.statusBar().showMessage(
            f"Macchina attiva: {new_machine.name} "
            f"({new_machine.width_mm:g}×{new_machine.height_mm:g} mm)", 4000)

    def _on_home(self) -> None:
        self._grbl_controller.home()

    def _on_unlock(self) -> None:
        self._grbl_controller.unlock()

    def _on_status_query(self) -> None:
        self._grbl_controller.status_query()

    def _on_feed_hold(self) -> None:
        self._grbl_controller.feed_hold()

    def _on_resume(self) -> None:
        self._grbl_controller.resume()

    def _on_soft_reset(self) -> None:
        self._grbl_controller.soft_reset()

    def _on_controller_connected(self, port: str, baud: int) -> None:
        self._machine_label.setText(f"{port} @ {baud}")
        self._cam_panel.set_controller_available(True)

    def _on_controller_disconnected(self) -> None:
        self._machine_label.setText("Disconnesso")
        self._cam_panel.set_controller_available(False)

    def _on_machine_status(self, status: dict) -> None:
        state = status.get("state", "?")
        pos = status.get("wpos") or status.get("mpos")
        if pos:
            self._machine_label.setText(
                f"{state}  X{pos[0]:7.2f} Y{pos[1]:7.2f} Z{pos[2]:7.2f}")
        else:
            self._machine_label.setText(str(state))

    def _on_job_progress(self, sent: int, total: int) -> None:
        if total <= 0:
            return
        self.statusBar().showMessage(f"Streaming: {sent}/{total}")

    def _on_job_finished(self, success: bool) -> None:
        self.statusBar().showMessage("Lavoro completato" if success else "Lavoro interrotto", 4000)

    def _on_controller_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"Errore controller: {msg}", 5000)

    def _on_controller_alarm(self, code: int) -> None:
        from lasercontrolsuite.comm import protocol as grbl
        self.statusBar().showMessage(f"ALARM:{code} — {grbl.describe_alarm(code)}", 8000)

    def _on_controller_error_code(self, code: int) -> None:
        from lasercontrolsuite.comm import protocol as grbl
        self.statusBar().showMessage(f"error:{code} — {grbl.describe_error(code)}", 6000)

    def _on_gcode_ready(self, gcode_text: str) -> None:
        if not gcode_text.strip():
            return
        self._grbl_controller.stream_gcode(gcode_text.splitlines())
        self._console_dock.show()

    def _apply_machine_to_canvas(self) -> None:
        m = self._settings.get_active_machine()
        x0, y0, x1, y1 = m.work_area_bounds()
        rect = QRectF(x0, y0, x1 - x0, y1 - y0)
        self._canvas.set_work_area(rect)

    def _refresh_machine_label(self) -> None:
        m = self._settings.get_active_machine()
        self.setWindowTitle(f"LaserControlSuite v{__version__} — {m.name}")

    def _show_warnings(self, title: str, warnings: list[str]) -> None:
        text = "\n".join(f"• {w}" for w in warnings[:30])
        if len(warnings) > 30:
            text += f"\n… e altri {len(warnings) - 30}"
        QMessageBox.information(self, title, text)

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "Informazioni su LaserControlSuite",
            f"<h3>LaserControlSuite</h3>"
            f"<p>Versione <b>{__version__}</b></p>"
            "<p>Suite CAD/CAM per il controllo di laser basati su GRBL.</p>",
        )