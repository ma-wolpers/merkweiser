"""Tag-Picker (W7): Popup über dem Editor, geöffnet vom #-Knopf (nicht von der Tastatur).

Suchfeld (regulärer Ausdruck, ``tag_index.filter_tags``) und scrollbare Liste der
verwendeten Tags (``tag_index.used_tags``). Ist die Suche ein gültiger neuer
Name (``tags.tag_from_input``), steht oben „#name neu verwenden“. Ein Tipp
schließt **nur** das Popup (Dialogstapel von Flet 0.86.5) und reicht den Namen
an den Editor weiter.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import flet as ft

from ...app.tag_index import filter_tags, used_tags
from ...core.tags import tag_from_input

if TYPE_CHECKING:
    from .app import MobileApp

LIST_HEIGHT = 320


def new_name(raw: str, known: set[str], prefix: str) -> str | None:
    """Gültiger Tag-Name aus der Suche, der noch nicht verwendet wird.

    Args:
        raw: Sucheingabe.
        known: Schlüssel (``casefold``) der verwendeten Tags.
        prefix: Projekt-Präfix.

    Returns:
        Der Name oder ``None`` (leer, ungültig oder schon vorhanden).
    """
    try:
        name = tag_from_input(raw, False, prefix)
    except ValueError:
        return None
    return None if name.casefold() in known else name


def show_tag_picker(app: "MobileApp", initial: str, on_pick: Callable[[str], Awaitable[None]],
                    refresh: Callable[[ft.Control], None] = ft.Control.update) -> ft.AlertDialog:
    """Öffnet das Popup über dem Editor.

    Args:
        app: Die laufende App.
        initial: Vorbelegung der Suche (markierter Text).
        on_pick: Erhält den gewählten Namen ohne ``#``, nachdem das Popup geschlossen ist.
        refresh: Zeichnet ein Control neu (Tests ersetzen das, weil dort keine Seite hängt).

    Returns:
        Der geöffnete Dialog.
    """
    tags = used_tags(app.service)
    known = {name.casefold() for name, _count in tags}
    search = ft.TextField(label="Tag suchen (regulärer Ausdruck)", value=initial, autofocus=True)
    hint = ft.Text("", size=12, color=ft.Colors.ERROR)
    listing = ft.Column(scroll=ft.ScrollMode.AUTO, height=LIST_HEIGHT, spacing=0)

    def choose(name: str):
        async def click(_e) -> None:
            app.page.pop_dialog()
            await on_pick(name)
        return click

    def fill() -> None:
        found, hint.value = filter_tags(tags, search.value or "")
        fresh = new_name(search.value or "", known, app.settings.project_prefix)
        tiles: list[ft.Control] = []
        if fresh:
            tiles.append(ft.ListTile(leading=ft.Icon(ft.Icons.ADD), title=ft.Text(f"#{fresh} neu verwenden"),
                                     on_click=choose(fresh)))
        tiles += [ft.ListTile(title=ft.Text(f"#{name}"), trailing=ft.Text(str(count)), on_click=choose(name))
                  for name, count in found]
        listing.controls = tiles or [ft.Text("Keine passenden Tags.")]

    async def changed(_e) -> None:
        fill()
        refresh(listing)
        refresh(hint)

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    search.on_change = changed
    fill()
    dialog = ft.AlertDialog(modal=True, title="Tag einfügen", content=ft.Column([search, hint, listing], tight=True),
                            actions=[ft.TextButton("Abbrechen", on_click=cancel)])
    app.page.show_dialog(dialog)
    return dialog
