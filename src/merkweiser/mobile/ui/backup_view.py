"""Seiten „Backups“ (Einstellungen → Backups): Dateien, dann Änderungen einer Datei (W4).

Je Änderung: Zeit, Art, Vergleich vorher (rot, −) / nachher (grün, +),
Zusammenhang mit Folgenwarnung und „Rückgängig“ mit Bestätigung. Bei
Auto-Merge und Konfliktentscheidung zusätzlich die Gesamtaktion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.backup_views import ChangeView, file_changes, file_entries, undo, undo_group
from ...app.nav import PageRef
from .conflict_view import diff_box

if TYPE_CHECKING:
    from .app import MobileApp


def backups_page(app: "MobileApp", _arg: str) -> list[ft.Control]:
    """Dateiliste: jede Datei mit Anzahl und Zeit der jüngsten Änderung.

    Args:
        app: Die laufende App.
        _arg: unbenutzt.

    Returns:
        Controls ohne Kopfzeile (die setzt ``pages``).
    """
    entries = file_entries(app.service)
    if not entries:
        return [ft.Text("Noch keine Backups (oder alle älter als die Aufbewahrungszeit).")]

    def opener(relpath: str):
        async def click(_e) -> None:
            app.open_page(PageRef("backup_datei", relpath))
        return click

    return [ft.Text("Merkweiser sichert jede eigene Änderung. Tippe eine Datei an, um ihre Änderungen zu sehen.",
                    size=12),
            *[ft.ListTile(title=ft.Text(e.relpath), subtitle=ft.Text(f"{e.count} Änderung(en), zuletzt {e.newest}"),
                          trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT), on_click=opener(e.relpath)) for e in entries]]


def backup_file_page(app: "MobileApp", relpath: str) -> list[ft.Control]:
    """Änderungen einer Datei, neueste zuerst.

    Args:
        app: Die laufende App.
        relpath: Datei.

    Returns:
        Controls ohne Kopfzeile.
    """
    views = file_changes(app.service, relpath)
    controls: list[ft.Control] = [ft.Text("Rot (−) = vorher, grün (+) = nachher. „Rückgängig“ nimmt nur diese "
                                          "Änderung zurück; spätere bleiben erhalten.", size=12)]
    for view in views:
        controls += [ft.Divider(), *_change(app, view)]
    return controls


def _change(app: "MobileApp", view: ChangeView) -> list[ft.Control]:
    """Eine Änderung mit Vergleich, Zusammenhang und Knöpfen."""
    head = f"{view.when} · {view.change.label}" + (" · rückgängig gemacht" if view.undone else "")
    controls: list[ft.Control] = [ft.Text(head, weight=ft.FontWeight.BOLD), diff_box(view.diff)]
    if view.group_note:
        others = ", ".join(sorted({s.relpath for s in view.siblings}))
        controls.append(ft.Text(f"{view.group_note} Andere Dateien: {others}", size=12, color=ft.Colors.TERTIARY))
    buttons = [ft.TextButton("Rückgängig", icon=ft.Icons.UNDO, on_click=_confirm(app, view, single=True))]
    if view.group_action and view.siblings:
        buttons.append(ft.TextButton(view.group_action, on_click=_confirm(app, view, single=False)))
    return [*controls, ft.Row(buttons, wrap=True)]


def _confirm(app: "MobileApp", view: ChangeView, single: bool):
    """Klick-Handler: Bestätigungsdialog, dann Einzel- bzw. Gesamtaktion."""
    async def run(_e) -> None:
        app.page.pop_dialog()
        message = await app.act(lambda s: undo(s, view.change) if single else undo_group(s, view.change))
        if message:
            app.say(message, link="Konfliktdatei" in message)
            app.render()

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    async def click(_e) -> None:
        text = "Nur diese Änderung zurücknehmen?" if single else f"{view.group_action}?"
        if view.group_note and single:
            text += f"\n\n{view.group_note}"
        app.page.show_dialog(ft.AlertDialog(title=ft.Text("Rückgängig"), content=ft.Text(text), actions=[
            ft.TextButton("Abbrechen", on_click=cancel), ft.TextButton("Rückgängig", on_click=run)]))
    return click
