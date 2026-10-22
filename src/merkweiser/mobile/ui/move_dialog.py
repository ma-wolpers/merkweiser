"""Todo verschieben (Mobile): Schnellwahl der Zieldaten plus Kalender.

Der Dialog bietet die Daten aus ``move_choices`` als Knöpfe an und „Datum
wählen …“ für den gemeinsamen Kalender (``date_pick.open_date_picker``). Verschoben wird immer über
``NotesService.move_todo`` (Move-Protokoll, Teilbaum, geerbte Tags explizit).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import flet as ft

from ...app.notes_service import MoveTag
from ...app.views import move_choices
from ...core.patch import Target
from .date_pick import open_date_picker

if TYPE_CHECKING:
    from .app import MobileApp


def show_move_dialog(app: "MobileApp", target: Target, tag: MoveTag | None = None) -> None:
    """Öffnet den Verschieben-Dialog für ein Todo.

    Args:
        app: Die laufende App.
        target: Adresse des Todos.
        tag: Tag aus dem Tag-Dialog; geschrieben wird er erst nach der Datumswahl (im Service).
    """
    app.page.show_dialog(move_dialog(app, target, tag))


def move_dialog(app: "MobileApp", target: Target, tag: MoveTag | None = None) -> ft.AlertDialog:
    """Baut den Dialog mit Schnellwahl und Kalender.

    Das Datum der Quelldatei wird nicht angeboten (der Service lehnt es
    ohnehin vor jedem Schreiben ab).

    Args:
        app: Die laufende App.
        target: Adresse des Todos.
        tag: Optionaler Tag, den ``NotesService.move_todo`` vor dem Verschieben schreibt.

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    today = app.service.clock.today()
    source_day = app.service.day_of(target.relpath) or today

    async def move_to(day: date) -> None:
        app.page.pop_dialog()
        await app.act(lambda s: s.move_todo(target, day, tag))

    def quick(label: str, day: date) -> ft.Control:
        async def click(_e) -> None:
            await move_to(day)
        return ft.TextButton(label, on_click=click)

    async def chosen(day: date) -> None:
        if day != source_day:
            await move_to(day)

    async def calendar(_e) -> None:
        open_date_picker(app, source_day + timedelta(days=1), "Todo verschieben auf", chosen)

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    buttons = [quick(label, day) for label, day in move_choices(today) if day != source_day]
    buttons.append(ft.TextButton("Datum wählen …", icon=ft.Icons.CALENDAR_MONTH, on_click=calendar))
    return ft.AlertDialog(modal=True, title="Todo verschieben auf …", content=ft.Column(buttons, tight=True),
                          actions=[ft.TextButton("Abbrechen", on_click=cancel)])
