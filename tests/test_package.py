"""Smoke-Tests für das Paket-Gerüst."""

import importlib

import merkweiser


def test_version_is_dev() -> None:
    """Das Paket meldet die aktuelle Entwicklungsversion."""
    assert merkweiser.__version__ == "0.1.0-dev"


def test_layer_packages_import_without_ui_frameworks() -> None:
    """Core, Ports und App laden weder Flet noch Tk (Schichtenregel).

    Läuft in einem eigenen Prozess: Andere Tests (Mobile-Rauchtest) laden Flet
    im Testprozess, ``sys.modules`` wäre dort also nicht aussagekräftig.
    """
    import subprocess
    import sys

    modules = ("merkweiser.core", "merkweiser.ports", "merkweiser.app", "merkweiser.app.notes_service",
               "merkweiser.app.views")
    code = (f"import sys, importlib; [importlib.import_module(n) for n in {modules!r}]; "
            "assert 'flet' not in sys.modules and 'tkinter' not in sys.modules")
    subprocess.run([sys.executable, "-c", code], check=True)
