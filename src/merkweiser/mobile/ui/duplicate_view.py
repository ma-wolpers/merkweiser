"""Abschnitt „Doppelte Notizen“ auf der Konflikte-Seite (W3).

Je Gruppe: die Notiz (gekürzt) und alle Fundstellen mit Datum. Bei zwei
Fundstellen „Neuere behalten“ / „Ältere behalten“; ab drei je Fundstelle
„Diese behalten“ plus die Schnellwahl „Neueste“ / „Älteste“. Jede Wahl wird
bestätigt; die anderen Fundstellen werden gelöscht (Backup bleibt).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.duplicate_service import duplicates, keep
from ...app.views import day_label
from ...core.duplicates import DuplicateGroup

if TYPE_CHECKING:
    from .app import MobileApp

PREVIEW_LINES = 4


def duplicate_controls(app: "MobileApp") -> list[ft.Control]:
    """Controls des Abschnitts; leer ohne Duplikate.

    Args:
        app: Die laufende App.

    Returns:
        Überschrift und je Gruppe ein Block.
    """
    groups = duplicates(app.service)
    if not groups:
        return []
    controls: list[ft.Control] = [ft.Text("Doppelte Notizen", size=18, weight=ft.FontWeight.BOLD),
                                  ft.Text("Diese Notizen stehen gleich in mehreren Tagesdateien. Wähle, welche "
                                          "bleibt; die anderen werden gelöscht.", size=12)]
    for group in groups:
        controls += [ft.Divider(), *_group(app, group)]
    return controls


def _group(app: "MobileApp", group: DuplicateGroup) -> list[ft.Control]:
    """Eine Gruppe mit Vorschau, Fundstellen und Wahlknöpfen."""
    today = app.service.clock.today()
    preview = list(group.lines[:PREVIEW_LINES]) + (["…"] if len(group.lines) > PREVIEW_LINES else [])
    controls: list[ft.Control] = [ft.Container(content=ft.Text("\n".join(preview), size=12, font_family="monospace"),
                                               padding=6, bgcolor=ft.Colors.SURFACE_CONTAINER)]
    newest, oldest = len(group.places) - 1, 0
    if len(group.places) == 2:
        controls += [ft.Text(f"{day_label(p.day, today)} · {p.relpath}", size=12) for p in group.places]
        controls.append(ft.Row([_choice(app, group, newest, "Neuere behalten"),
                                _choice(app, group, oldest, "Ältere behalten")], wrap=True))
        return controls
    for index, place in enumerate(group.places):
        controls.append(ft.Row([ft.Text(f"{day_label(place.day, today)} · {place.relpath}", size=12, expand=True),
                                _choice(app, group, index, "Diese behalten")]))
    controls.append(ft.Row([_choice(app, group, newest, "Neueste behalten"),
                            _choice(app, group, oldest, "Älteste behalten")], wrap=True))
    return controls


def _choice(app: "MobileApp", group: DuplicateGroup, index: int, label: str) -> ft.Control:
    """Knopf mit Bestätigung: behält Fundstelle ``index``."""
    place = group.places[index]
    others = len(group.places) - 1

    async def run(_e) -> None:
        app.page.pop_dialog()
        message = await app.act(lambda s: keep(s, group, index))
        if message:
            app.say(message)
            app.render()

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    async def click(_e) -> None:
        text = (f"Die Notiz bleibt in {place.relpath} ({place.day:%d.%m.%Y}). An {others} anderen Stelle(n) wird "
                "sie gelöscht; das Backup bleibt.")
        app.page.show_dialog(ft.AlertDialog(title=ft.Text("Doppelte Notiz bereinigen"), content=ft.Text(text),
                                            actions=[ft.TextButton("Abbrechen", on_click=cancel),
                                                     ft.TextButton("Bereinigen", on_click=run)]))
    return ft.TextButton(label, on_click=click)
