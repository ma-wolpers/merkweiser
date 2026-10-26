"""Unterseiten der Mobile-App (Stapel je Tab, ``app.nav.Nav``).

Jede Unterseite ist ein ``PageRef`` (Daten) und wird hier frisch gebaut. Die
Kopfzeile hat immer einen Zurück-Knopf; Android-Zurück wirkt gleich
(``MobileApp._on_confirm_pop``).

Seiten:

* ``tag`` – die Tag-Seite (W2): alle Notizen mit diesem Tag als ganze,
  bedienbare Karten, neueste zuerst, Karten mit offenem dringendem Todo vorn (Rot vor Gelb).
* ``konflikte`` – unter Einstellungen (W4): unterbrochene Vorgänge, offene
  Sync-Konflikte und automatisch zusammengeführte Konflikte.
* ``backups`` und ``backup_datei`` – unter Einstellungen (W4): Dateien mit
  Änderungen bzw. die Änderungen einer Datei mit „Rückgängig“ (``backup_view``).
* ``taetigkeiten`` – im Tab „Zeit“ (W6): Tätigkeiten verwalten (``time_view``).
* ``benachrichtigungen`` – unter Einstellungen (W5, ``notify_view``).
* ``notiz`` – im Tab „Todos“ (W7): die ganze Notiz eines Todos, frisch
  aufgelöst, mit „Notiz verschieben“; Zurück führt zur Liste mit Filter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.nav import PageRef, parse_note_arg
from ...app.ordering import by_rank, note_rank
from ...core.query import Filter
from . import backup_view, conflict_view, time_view
from .duplicate_view import duplicate_controls
from .interrupted_view import interrupted_controls
from .move_dialog import show_note_move_dialog
from .note_view import note_card
from .notify_view import notify_page
from .tabs import date_button

if TYPE_CHECKING:
    from .app import MobileApp


def page_header(app: "MobileApp", title: str) -> ft.Control:
    """Kopfzeile einer Unterseite: Zurück-Knopf und Titel.

    Args:
        app: Die laufende App.
        title: Seitentitel.

    Returns:
        Eine Zeile.
    """
    async def back(_e) -> None:
        app.go_back()

    return ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Zurück", on_click=back),
                   ft.Text(title, size=20, weight=ft.FontWeight.BOLD)], spacing=4)


def tag_page(app: "MobileApp", tag: str) -> list[ft.Control]:
    """Tag-Seite: alle Notizen mit dem Tag (Themen und Todos, je Notiz einmal).

    Args:
        app: Die laufende App.
        tag: Tag-Schlüssel ohne ``#``.

    Returns:
        Kopfzeile und Notizkarten (mit Datum, das den Tab „Tag“ öffnet).
    """
    matches = list(reversed(app.service.search_notes(Filter(tags=(tag,)))))
    ordered = by_rank(matches, lambda m: note_rank(m.relpath, m.document, m.note))
    cards = (note_card(app, m.relpath, m.document, m.note, date_button(app, m.day)) for m in ordered)
    controls: list[ft.Control] = [page_header(app, f"#{tag}")]
    controls += [card for card in cards if card is not None] or [ft.Text("Keine Notizen mit diesem Tag.")]
    return controls


def conflicts_page(app: "MobileApp", _arg: str) -> list[ft.Control]:
    """Konflikte-Seite: unterbrochene Vorgänge, doppelte Notizen, dann Sync-Konflikte und Auto-Merges.

    Args:
        app: Die laufende App.
        _arg: unbenutzt.

    Returns:
        Kopfzeile und Inhalt.
    """
    return [page_header(app, "Konflikte"), *interrupted_controls(app), *duplicate_controls(app),
            *conflict_view.conflicts_view(app)]


def backups_page(app: "MobileApp", _arg: str) -> list[ft.Control]:
    """Backups: Dateiliste."""
    return [page_header(app, "Backups"), *backup_view.backups_page(app, _arg)]


def backup_file_page(app: "MobileApp", relpath: str) -> list[ft.Control]:
    """Backups einer Datei."""
    return [page_header(app, relpath), *backup_view.backup_file_page(app, relpath)]


def activities_page(app: "MobileApp", _arg: str) -> list[ft.Control]:
    """Tätigkeiten verwalten."""
    return [page_header(app, "Tätigkeiten"), *time_view.activities_page(app, _arg)]


def notifications_page(app: "MobileApp", _arg: str) -> list[ft.Control]:
    """Benachrichtigungen."""
    return [page_header(app, "Benachrichtigungen"), *notify_page(app, _arg)]


def note_page(app: "MobileApp", arg: str) -> list[ft.Control]:
    """Notiz-Unterseite: die ganze Notiz, die das Todo enthält (W7).

    Die Notiz wird bei jedem Aufbau frisch aus der Datei aufgelöst
    (``NotesService.note_of``). Ist das nicht eindeutig möglich, erscheint ein
    Hinweis – es wird nie eine andere Notiz gezeigt.

    Args:
        app: Die laufende App.
        arg: ``nav.note_arg`` des Todos.

    Returns:
        Kopfzeile und Notizkarte (mit Datum und „Notiz verschieben“) bzw. Hinweis.
    """
    controls: list[ft.Control] = [page_header(app, "Notiz")]
    target = parse_note_arg(arg)
    found = app.service.note_of(target) if target is not None else None
    if target is None or found is None:
        controls.append(ft.Text("Diese Notiz hat sich inzwischen geändert oder ist nicht mehr eindeutig "
                                "auffindbar. Bitte zurück zur Liste."))
        return controls
    doc, note = found
    day = app.service.day_of(target.relpath)

    def extra(ref) -> list[ft.Control]:
        async def move(_e) -> None:
            show_note_move_dialog(app, ref, after=app.go_back)
        return [ft.IconButton(icon=ft.Icons.EVENT, on_click=move, tooltip="Notiz verschieben")]

    card = note_card(app, target.relpath, doc, note, date_button(app, day) if day else None, extra)
    return controls + ([card] if card is not None else [ft.Text("Diese Notiz ist leer.")])


BUILDERS = {"tag": tag_page, "konflikte": conflicts_page, "backups": backups_page, "backup_datei": backup_file_page,
            "taetigkeiten": activities_page, "benachrichtigungen": notifications_page, "notiz": note_page}


def build_page(app: "MobileApp", page: PageRef) -> list[ft.Control]:
    """Baut eine Unterseite.

    Args:
        app: Die laufende App.
        page: Die Seite.

    Returns:
        Ihre Controls; unbekannte Arten zeigen nur Kopf und Hinweis.
    """
    builder = BUILDERS.get(page.kind)
    if builder is None:
        return [page_header(app, "Unbekannte Seite"), ft.Text(page.kind)]
    return builder(app, page.arg)
