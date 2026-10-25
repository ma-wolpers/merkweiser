"""Dialoge des Zeit-Tabs: Wechseln mit Uhrzeit, Messung abbrechen (Endzeit oder keine Zeit), Tätigkeit umbenennen (W6).

Alle Aktionen laufen über ``app.act`` (Fehler werden angezeigt, danach wird
neu gezeichnet). ``end_from_time`` macht aus einer gewählten Uhrzeit einen
Zeitpunkt zwischen Messbeginn und jetzt.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING

import flet as ft

from ...app import time_service as ts

if TYPE_CHECKING:
    from .app import MobileApp


def end_from_time(picked: time, start: datetime, now: datetime) -> datetime:
    """Endzeitpunkt zu einer gewählten Uhrzeit: heute, oder – falls das nach jetzt läge – am Vortag.

    Args:
        picked: Gewählte Uhrzeit.
        start: Beginn der Messung.
        now: Jetzt (lokal, mit Offset).

    Returns:
        Zeitpunkt mit dem Offset von ``now`` (die Prüfung „zwischen Beginn und
        jetzt“ macht ``time_service.stop``).
    """
    candidate = datetime.combine(now.date(), picked.replace(second=0, microsecond=0), tzinfo=now.tzinfo)
    if candidate > now:
        candidate -= timedelta(days=1)
    return candidate


def show_switch_dialog(app: "MobileApp", activity: str, start: datetime) -> None:
    """„Wechseln zu …“ (W6a): Uhrzeit des Wechsels wählen, vorbelegt mit jetzt.

    Die gewählte Uhrzeit wird über ``end_from_time`` zum Zeitpunkt (heute bzw.
    Vortag); ``time_service.switch`` prüft „nach dem Beginn und spätestens jetzt“.

    Args:
        app: Die laufende App.
        activity: Neue Tätigkeit.
        start: Beginn der laufenden Messung.
    """
    async def picked(e) -> None:
        if e.control.value is not None:
            at = end_from_time(e.control.value, start, app.service.clock.now())
            await _run(app, lambda s: ts.switch(s, activity, at))

    app.page.show_dialog(ft.TimePicker(value=app.service.clock.now().time(),
                                       help_text=f"Wechsel zu „{activity}“ um … (nach {start:%H:%M})",
                                       confirm_text="Wechseln", cancel_text="Abbrechen", on_change=picked))


def show_abort_dialog(app: "MobileApp", start: datetime) -> None:
    """„Messung abbrechen“: Endzeit wählen oder keine Zeit eintragen.

    Args:
        app: Die laufende App.
        start: Beginn der laufenden Messung.
    """
    async def close(_e=None) -> None:
        app.page.pop_dialog()

    async def no_time(_e) -> None:
        app.page.pop_dialog()
        await _run(app, lambda s: ts.abort(s, None))

    async def picked(e) -> None:
        if e.control.value is not None:
            end = end_from_time(e.control.value, start, app.service.clock.now())
            await _run(app, lambda s: ts.abort(s, end))

    async def choose_end(_e) -> None:
        app.page.pop_dialog()
        app.page.show_dialog(ft.TimePicker(value=app.service.clock.now().time(), help_text="Endzeit der Messung",
                                           confirm_text="Eintragen", cancel_text="Abbrechen", on_change=picked))

    app.page.show_dialog(ft.AlertDialog(
        title=ft.Text("Messung abbrechen"),
        content=ft.Text(f"Die Messung läuft seit {start:%H:%M}. Welche Zeit soll eingetragen werden?"),
        actions=[ft.TextButton("Endzeit wählen …", on_click=choose_end),
                 ft.TextButton("Keine Zeit eintragen", on_click=no_time),
                 ft.TextButton("Zurück", on_click=close)]))


def show_rename_dialog(app: "MobileApp", old: str) -> None:
    """Tätigkeit umbenennen; gibt es den neuen Namen schon, fragt ein zweiter Dialog nach dem Zusammenführen.

    Args:
        app: Die laufende App.
        old: Bisheriger Name.
    """
    field = ft.TextField(label="Neuer Name", value=old, autofocus=True)

    async def close(_e=None) -> None:
        app.page.pop_dialog()

    async def rename(_e) -> None:
        app.page.pop_dialog()
        new = field.value or ""

        def action(service):
            try:
                return ts.rename_activity(service, old, new)
            except ts.NeedsConfirmation as exc:
                return exc
        result = await app.act(action)
        if isinstance(result, ts.NeedsConfirmation):
            _confirm_merge(app, old, new, str(result))
        elif result:
            app.say(result)
            app.render()

    app.page.show_dialog(ft.AlertDialog(title=ft.Text(f"„{old}“ umbenennen"), content=field, actions=[
        ft.TextButton("Abbrechen", on_click=close), ft.TextButton("Umbenennen", on_click=rename)]))


def _confirm_merge(app: "MobileApp", old: str, new: str, question: str) -> None:
    """Rückfrage „gibt es schon – zusammenführen?“."""
    async def close(_e=None) -> None:
        app.page.pop_dialog()

    async def merge(_e) -> None:
        app.page.pop_dialog()
        await _run(app, lambda s: ts.rename_activity(s, old, new, merge=True))

    app.page.show_dialog(ft.AlertDialog(title=ft.Text("Name gibt es schon"), content=ft.Text(question), actions=[
        ft.TextButton("Abbrechen", on_click=close), ft.TextButton("Zusammenführen", on_click=merge)]))


async def _run(app: "MobileApp", action) -> None:
    """Aktion ausführen und ihre Meldung zeigen."""
    message = await app.act(action)
    if isinstance(message, str) and message:
        app.say(message)
        app.render()
