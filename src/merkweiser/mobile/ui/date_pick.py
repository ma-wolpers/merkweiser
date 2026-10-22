"""Gemeinsamer Datumswähler (Mobile) für den Tab „Tag“ und das Verschieben.

``picked_date`` wandelt den Wert eines Flet-``DatePicker`` in ein Kalenderdatum;
``open_date_picker`` öffnet den Kalender mit einheitlichem Bereich und ruft
mit dem gewählten Datum zurück.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Awaitable, Callable

import flet as ft

if TYPE_CHECKING:
    from .app import MobileApp


def picked_date(value: object) -> date | None:
    """Wandelt den Wert eines ``DatePicker`` in ein Kalenderdatum.

    Flet liefert je nach Version ein naives ``datetime`` (lokale Mitternacht)
    oder ein zeitzonenbehaftetes in UTC. Im zweiten Fall würde ``.date()`` in
    Zeitzonen östlich von UTC den Vortag ergeben; deshalb erst in die lokale
    Zeit umrechnen.

    Args:
        value: ``datetime``, ``date`` oder ``None``.

    Returns:
        Das gewählte Datum oder ``None``.
    """
    if isinstance(value, datetime):
        return (value.astimezone() if value.tzinfo else value).date()
    if isinstance(value, date):
        return value
    return None


def open_date_picker(app: "MobileApp", initial: date, help_text: str,
                     on_pick: Callable[[date], Awaitable[None]]) -> None:
    """Öffnet den Kalender und ruft ``on_pick`` mit dem gewählten Datum auf.

    Der Bereich reicht vom 1. Januar des Vorjahres bis zum 31. Dezember in
    zwei Jahren (bezogen auf heute laut Service-Uhr).

    Args:
        app: Die laufende App.
        initial: Vorausgewähltes Datum.
        help_text: Überschrift des Kalenders.
        on_pick: Rückruf mit dem gewählten Datum (nicht bei Abbruch).
    """
    today = app.service.clock.today()

    async def changed(event) -> None:
        day = picked_date(event.control.value)
        if day is not None:
            await on_pick(day)

    app.page.show_dialog(ft.DatePicker(value=datetime.combine(initial, datetime.min.time()),
                                       first_date=datetime(today.year - 1, 1, 1),
                                       last_date=datetime(today.year + 2, 12, 31),
                                       help_text=help_text, on_change=changed))
