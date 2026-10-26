"""Verschieben (Mobile): Schnellwahl der Zieldaten plus Kalender, für Todo und ganze Notiz.

Der Dialog bietet die Daten aus ``move_choices`` als Knöpfe an und „Datum
wählen …“ für den gemeinsamen Kalender (``date_pick.open_date_picker``). Was
mit dem gewählten Tag geschieht, entscheidet ein Callback (``on_day``):
``NotesService.move_todo`` (Move-Protokoll, Teilbaum, geerbte Tags explizit)
bzw. ``NotesService.move_note`` (ganze Notiz, W7).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import TYPE_CHECKING

import flet as ft

from ...app.notes_service import MoveTag
from ...app.views import NoteRef, move_choices
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


def show_note_move_dialog(app: "MobileApp", ref: NoteRef, after: Callable[[], None] | None = None) -> None:
    """Öffnet den Verschieben-Dialog für eine ganze Notiz (W7).

    Args:
        app: Die laufende App.
        ref: Adresse der Notiz beim Öffnen.
        after: Optional nach erfolgreichem Verschieben (z. B. die Unterseite schließen).
    """
    async def move(day: date) -> None:
        result = await app.act(lambda s: s.move_note(ref, day))
        if result is None:
            return  # Fehler hat ``act`` gemeldet
        if result.state != "DONE":
            app.say(f"Verschieben unvollständig: {result.hint}", link=True)
        elif after is not None:
            after()

    source_day = app.service.day_of(ref.relpath) or app.service.clock.today()
    app.page.show_dialog(day_dialog(app, "Notiz verschieben auf …", source_day, move))


def move_dialog(app: "MobileApp", target: Target, tag: MoveTag | None = None) -> ft.AlertDialog:
    """Baut den Dialog für ein Todo.

    Args:
        app: Die laufende App.
        target: Adresse des Todos.
        tag: Optionaler Tag, den ``NotesService.move_todo`` vor dem Verschieben schreibt.

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    async def move(day: date) -> None:
        await app.act(lambda s: s.move_todo(target, day, tag))

    source_day = app.service.day_of(target.relpath) or app.service.clock.today()
    return day_dialog(app, "Todo verschieben auf …", source_day, move)


def day_dialog(app: "MobileApp", title: str, source_day: date,
               on_day: Callable[[date], Awaitable[None]]) -> ft.AlertDialog:
    """Gemeinsamer Dialog: Schnellwahl und Kalender; ``on_day`` erhält den gewählten Tag.

    Das Datum der Quelldatei wird nicht angeboten (der Service lehnt es
    ohnehin vor jedem Schreiben ab). Der Dialog schließt sich vor ``on_day``.

    Args:
        app: Die laufende App.
        title: Titel, z. B. „Todo verschieben auf …“.
        source_day: Datum der Quelldatei.
        on_day: Aktion mit dem Zieldatum.

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    today = app.service.clock.today()

    async def move_to(day: date) -> None:
        app.page.pop_dialog()
        await on_day(day)

    def quick(label: str, day: date) -> ft.Control:
        async def click(_e) -> None:
            await move_to(day)
        return ft.TextButton(label, on_click=click)

    async def chosen(day: date) -> None:
        if day != source_day:
            await move_to(day)

    async def calendar(_e) -> None:
        open_date_picker(app, source_day + timedelta(days=1), title.removesuffix(" …"), chosen)

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    buttons = [quick(label, day) for label, day in move_choices(today) if day != source_day]
    buttons.append(ft.TextButton("Datum wählen …", icon=ft.Icons.CALENDAR_MONTH, on_click=calendar))
    return ft.AlertDialog(modal=True, title=title, content=ft.Column(buttons, tight=True),
                          actions=[ft.TextButton("Abbrechen", on_click=cancel)])
