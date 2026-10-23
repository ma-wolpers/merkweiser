"""Diagnosebericht speichern (Mobile): Bericht ohne Notizinhalte in einen gewählten Ordner.

Aus ``app.py`` ausgelagert (Dateigröße); Verhalten unverändert.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from ...app.diagnostics import build_report, write_report
from ...app.settings import save_settings

if TYPE_CHECKING:
    from .app import MobileApp


async def save_diagnostics(app: "MobileApp", folder: str | None) -> None:
    """Schreibt einen Diagnosebericht (ohne Notizinhalte) und merkt sich den Ordner.

    Args:
        app: Die laufende App.
        folder: Zielordner (eingetippt) oder ``None`` für die Systemauswahl.
    """
    folder = folder or await app.access.pick_folder()
    if not folder:
        app.say("Kein Ordner für den Diagnosebericht gewählt.")
        app.render()
        return
    now = datetime.now()
    text = build_report(app.settings, app.service, app.report, list(app.messages), now,
                        {"flet": ft.__version__})
    try:
        path = write_report(Path(folder), text, now)
    except OSError as exc:
        hint = (" Android sperrt die privaten Ordner anderer Apps (…/Android/data/…), auch mit „Alle Dateien“. "
                "Bitte einen Ordner außerhalb davon wählen, z. B. /storage/emulated/0/Download."
                if "/Android/" in folder else "")
        app.say(f"Diagnosebericht nicht gespeichert: {type(exc).__name__}: {exc}.{hint}")
        app.render()
        return
    if folder != app.settings.report_dir:
        app.settings = replace(app.settings, report_dir=folder)
        save_settings(app.storage.data_dir, app.settings)
    app.status.value, app.status.visible = f"Diagnosebericht gespeichert: {path.name}", True
    app.status.color = ft.Colors.PRIMARY
    app.render()
