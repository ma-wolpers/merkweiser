"""Flet-Einstieg (Shim) für ``flet run`` und ``flet build``.

``flet`` führt diese Datei als eigenständiges Skript aus; sie liegt deshalb neben
dem Paket ``merkweiser`` unter ``src/`` (``[tool.flet.app] path = "src"``), damit der
absolute Import funktioniert. Die App selbst steckt in ``merkweiser.mobile.ui.app``.
"""

from merkweiser.mobile.ui.app import main

if __name__ == "__main__":
    import flet as ft

    ft.run(main)
