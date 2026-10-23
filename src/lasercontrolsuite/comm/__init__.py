"""Serial communication with GRBL-based laser controllers.

Pure-Python modules (``protocol``, ``fake_serial``, ``port_scanner``) have
no Qt dependency and are unit-testable in isolation. The Qt layer lives in
``controller`` (QThread).

The GRBL console UI lives in :mod:`lasercontrolsuite.ui.panels.console_panel`
so that all user-facing docks live under ``ui/`` (see PropertyPanel, CamPanel).
"""