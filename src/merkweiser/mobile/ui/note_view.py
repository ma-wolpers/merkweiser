"""Darstellung von Notizzeilen (Mobile): Thema, Erläuterung, Punkte, Todos, Fortsetzungen.

Layout (Nutzerwunsch vom 2026-10-21):

* **Thema** fett, die **Erläuterung** direkt darunter in deutlich schwächerer
  Schrift (``style.EXPLANATION``, hell und dunkel lesbar).
* **Todos und Listenpunkte** haben eine gleich breite Markerspalte (Checkbox
  bzw. „•“), damit ihre Texte auf derselben Kante stehen.
* **Fortsetzungen** stehen auf dieser Textkante unter ihrem Punkt.

Ein Tipp auf den Todo-Text hakt ab wie ein Tipp auf die Checkbox. „verschieben …“
startet ``tag_dialog.show_move_flow`` (Tag-Dialog nur bei weiteren Todos der Notiz).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.views import Row
from .tag_dialog import show_move_flow
from .style import EXPLANATION

if TYPE_CHECKING:
    from .app import MobileApp

INDENT = 18
MARKER_WIDTH = 40


def note_row(app: "MobileApp", row: Row) -> ft.Control:
    """Eine Notizzeile samt weiterer Zeilen (Erläuterung bzw. Fortsetzungen).

    Args:
        app: Die laufende App.
        row: Anzeigezeile aus ``note_rows``.

    Returns:
        Ein Control, eingerückt nach ``row.depth``.
    """
    pad = ft.Padding.only(left=row.depth * INDENT)
    if row.kind == "topic":
        head = ft.Text(row.text, italic=True, color=EXPLANATION) if row.empty_topic \
            else ft.Text(row.text, weight=ft.FontWeight.BOLD)
        lines = [head]
        lines += [ft.Text(line, color=EXPLANATION) for line in row.more]
        return ft.Container(content=ft.Column(lines, spacing=2), padding=pad)
    if row.kind == "todo":
        head = todo_line(app, row.text, row.done, row.urgent, row.target)
    elif row.kind == "item":
        head = _marked(ft.Text("•", size=18), ft.Text(row.text))
    else:
        return ft.Container(content=ft.Text("\n".join((row.text, *row.more))), padding=pad)
    continuation = [ft.Container(content=ft.Text(line), padding=ft.Padding.only(left=MARKER_WIDTH))
                    for line in row.more]
    return ft.Container(content=ft.Column([head, *continuation], spacing=0), padding=pad)


def todo_line(app: "MobileApp", text: str, done: bool | None, urgent: bool, target) -> ft.Control:
    """Todo mit Checkbox, antippbarem Text und Schnellaktionen (dringend, verschieben).

    Args:
        app: Die laufende App.
        text: Anzeigetext (ohne Checkbox).
        done: Erledigt-Status.
        urgent: Dringend markiert.
        target: Adresse des Todos.

    Returns:
        Eine Zeile mit Markerspalte, Text und zwei Symbolknöpfen.
    """
    async def set_done(value: bool) -> None:
        await app.act(lambda s: s.set_done(target, value))

    async def toggle(e) -> None:
        await set_done(bool(e.control.value))

    async def tap(_e) -> None:
        await set_done(not done)

    async def urgency(_e) -> None:
        await app.act(lambda s: s.set_urgent(target, not urgent))

    async def move(_e) -> None:
        await show_move_flow(app, target)

    label = text.strip("=") if urgent else text
    checkbox = ft.Checkbox(value=bool(done), on_change=toggle, visual_density=ft.VisualDensity.COMPACT)
    return _marked(checkbox, ft.GestureDetector(content=ft.Text(label), on_tap=tap), [
        ft.IconButton(icon=ft.Icons.STAR if urgent else ft.Icons.STAR_BORDER, on_click=urgency, tooltip="dringend"),
        ft.IconButton(icon=ft.Icons.EVENT, on_click=move, tooltip="verschieben …"),
    ])


def _marked(marker: ft.Control, body: ft.Control, actions: list[ft.Control] | None = None) -> ft.Control:
    """Zeile aus fester Markerspalte, Text (füllt die Breite) und optionalen Knöpfen.

    Args:
        marker: Checkbox oder Aufzählungszeichen.
        body: Text bzw. antippbarer Text.
        actions: Symbolknöpfe am Zeilenende.

    Returns:
        Die Zeile; alle Texte beginnen bei ``MARKER_WIDTH``.
    """
    return ft.Row([ft.Container(content=marker, width=MARKER_WIDTH, alignment=ft.Alignment.CENTER),
                   ft.Container(content=body, expand=True), *(actions or [])],
                  spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
