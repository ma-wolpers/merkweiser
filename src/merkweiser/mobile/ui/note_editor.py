"""Einfüge-Leiste für die Notiz-Editoren (Mobile): Checkbox, Einrücken, Ausrücken, ``#``.

Die Textlogik steckt UI-neutral in ``app.text_tools``; hier geht es nur um Flet:

* Die letzte Auswahl wird über ``on_selection_change`` gemerkt, weil ein Tipp
  auf einen Knopf dem Feld den Fokus nehmen kann.
* Nach der Änderung: ``value`` setzen, ``update()``, ``await focus()``, dann
  ``selection`` (laut Flet-Doku muss das Feld vor dem Setzen der Auswahl den
  Fokus haben), ``update()``.
* **BAUSTELLE(Offsets):** Flutter zählt Positionen in UTF-16-Einheiten. Ob Flet
  0.86.5 sie umrechnet, ist ohne Gerät nicht prüfbar. Deshalb wird bei einer
  nicht leeren Auswahl gegen ``selected_text`` geprüft, welche Zählung passt;
  vorher gilt UTF-16. Bestätigung im Gerätetest mit Emoji vor dem Caret.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from ...app.text_tools import index_to_utf16, indent, insert_tag, toggle_todo, utf16_to_index

Tool = Callable[[str, int | None, int | None], tuple[str, int | None, int | None]]


def editor_toolbar(field: ft.TextField) -> ft.Row:
    """Knopfleiste über einem Notiz-Editor.

    Args:
        field: Mehrzeiliges Textfeld; ``on_selection_change`` wird hier belegt.

    Returns:
        Eine Zeile mit vier Symbolknöpfen.
    """
    state: dict = {"start": None, "end": None, "utf16": True}

    def to_index(text: str, offset: int) -> int:
        return utf16_to_index(text, offset) if state["utf16"] else min(offset, len(text))

    async def remember(event) -> None:
        text = field.value or ""
        selection = event.selection
        if selection is None or not selection.is_valid:
            state["start"] = state["end"] = None
            return
        if not selection.is_collapsed and event.selected_text:  # Zählung eindeutig bestimmbar
            state["utf16"] = text[selection.start:selection.end] != event.selected_text
        state["start"], state["end"] = to_index(text, selection.start), to_index(text, selection.end)

    async def run(tool: Tool) -> None:
        text = field.value or ""
        new_text, start, end = tool(text, state["start"], state["end"])
        if start is None or end is None or (new_text, start, end) == (text, state["start"], state["end"]):
            return
        field.value = new_text
        field.update()
        await field.focus()
        convert = (lambda i: index_to_utf16(new_text, i)) if state["utf16"] else (lambda i: i)
        field.selection = ft.TextSelection(base_offset=convert(start), extent_offset=convert(end))
        field.update()
        state["start"], state["end"] = start, end

    def button(icon, tooltip: str, tool: Tool) -> ft.IconButton:
        async def click(_e) -> None:
            await run(tool)
        return ft.IconButton(icon=icon, tooltip=tooltip, on_click=click)

    field.on_selection_change = remember
    return ft.Row([button(ft.Icons.CHECK_BOX_OUTLINED, "Checkbox", toggle_todo),
                   button(ft.Icons.FORMAT_INDENT_INCREASE, "Einrücken", lambda t, s, e: indent(t, s, e, 1)),
                   button(ft.Icons.FORMAT_INDENT_DECREASE, "Ausrücken", lambda t, s, e: indent(t, s, e, -1)),
                   button(ft.Icons.TAG, "Tag (#)", insert_tag)], spacing=0)
