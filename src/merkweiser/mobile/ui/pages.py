"""Unterseiten der Mobile-App (Stapel je Tab, ``app.nav.Nav``).

Jede Unterseite ist ein ``PageRef`` (Daten) und wird hier frisch gebaut. Die
Kopfzeile hat immer einen Zurück-Knopf; Android-Zurück wirkt gleich
(``MobileApp._on_confirm_pop``).

Bisher: ``tag`` – die Tag-Seite (W2): alle Notizen mit diesem Tag als ganze,
bedienbare Karten, neueste zuerst, Karten mit offenem dringendem Todo vorn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.nav import PageRef
from ...app.ordering import note_is_pressing, stable_first
from ...core.query import Filter
from .note_view import note_card
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
    ordered = stable_first(matches, lambda m: note_is_pressing(m.relpath, m.document, m.note))
    cards = (note_card(app, m.relpath, m.document, m.note, date_button(app, m.day)) for m in ordered)
    controls: list[ft.Control] = [page_header(app, f"#{tag}")]
    controls += [card for card in cards if card is not None] or [ft.Text("Keine Notizen mit diesem Tag.")]
    return controls


BUILDERS = {"tag": tag_page}


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
