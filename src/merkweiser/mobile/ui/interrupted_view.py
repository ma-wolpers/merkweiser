"""Abschnitt „Unterbrochene Vorgänge“ auf der Konflikte-Seite (``app.interrupted``).

Zeigt je Vorgang Art, Zeitpunkt, Kurzbeschreibung und Hinweis sowie die
möglichen Aktionen. Nach jeder Aktion zeichnet ``MobileApp.act`` neu.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.interrupted import Interrupted, action_label, apply_action, interrupted

if TYPE_CHECKING:
    from .app import MobileApp


def interrupted_controls(app: "MobileApp") -> list[ft.Control]:
    """Controls des Abschnitts; leer, wenn nichts unterbrochen ist.

    Args:
        app: Die laufende App.

    Returns:
        Überschrift und je Vorgang ein Block.
    """
    entries = interrupted(app.service.store)
    if not entries:
        return []
    controls: list[ft.Control] = [ft.Text("Unterbrochene Vorgänge", size=18, weight=ft.FontWeight.BOLD),
                                  ft.Text("Merkweiser hat hier bewusst nichts weiter geändert, weil eine Datei nicht "
                                          "mehr zum Plan passte.", size=12)]
    for entry in entries:
        controls += [ft.Divider(), *_entry(app, entry)]
    return controls


def _entry(app: "MobileApp", entry: Interrupted) -> list[ft.Control]:
    """Ein unterbrochener Vorgang mit seinen Aktionsknöpfen.

    Args:
        app: Die laufende App.
        entry: Der Vorgang.

    Returns:
        Texte und eine Knopfzeile.
    """
    def button(action: str) -> ft.Control:
        async def click(_e) -> None:
            message = await app.act(lambda s: apply_action(s, entry.op_id, action))
            if message:
                app.say(message)
                app.render()
        return ft.TextButton(action_label(entry, action), on_click=click)

    when = entry.created[:16].replace("T", " ")
    lines = [ft.Text(f"{entry.label} · {when} (UTC)", weight=ft.FontWeight.BOLD)]
    if entry.detail:
        lines.append(ft.Text(entry.detail, size=12))
    if entry.hint:
        lines.append(ft.Text(entry.hint, color=ft.Colors.ERROR))
    return [*lines, ft.Row([button(a) for a in entry.actions], wrap=True)]
