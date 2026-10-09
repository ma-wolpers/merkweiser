"""Smoke-Tests für das Paket-Gerüst."""

import importlib

import merkweiser


def test_version_is_dev() -> None:
    """Das Paket meldet die aktuelle Entwicklungsversion."""
    assert merkweiser.__version__ == "0.1.0-dev"


def test_layer_packages_import_without_ui_frameworks() -> None:
    """Core, Ports und App lassen sich ohne bw-gui/Flet importieren (Schichtenregel)."""
    import sys

    for name in ("merkweiser.core", "merkweiser.ports", "merkweiser.app"):
        importlib.import_module(name)
    assert "flet" not in sys.modules
    assert "tkinter" not in sys.modules
