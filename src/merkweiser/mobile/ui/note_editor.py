"""Einfüge-Leiste und Listen-Verhalten der Notiz-Editoren (Mobile).

Knöpfe: Checkbox, Listenpunkt, Einrücken, Ausrücken, ``#``. Dazu setzt Enter
in einem Listenpunkt/Todo die Liste fort bzw. beendet sie. Die Textlogik
steckt UI-neutral in ``app.text_tools`` und ``app.list_editing``; hier geht es
nur um Flet:

* Die letzte Auswahl wird über ``on_selection_change`` gemerkt, weil ein Tipp
  auf einen Knopf dem Feld den Fokus nehmen kann.
* Enter wird über ``on_change`` erkannt: Der neue Wert ist der alte plus genau
  ein ``\\n`` (``list_editing.continue_list``); der gemerkte Caret entscheidet,
  wenn die Position mehrdeutig ist. GRENZE(Enter): Tastaturen, die beim Enter
  zugleich ein Wort autokorrigieren, liefern mehr als ein Zeichen auf einmal;
  dann bleibt es beim normalen Zeilenumbruch.
* Nach einer Änderung: ``value`` **und** ``selection`` in einem ``update()``
  (sonst setzt Flutter beim neuen Text den Caret kurz ans Ende), dann
  ``await focus()`` und die Auswahl noch einmal (laut Flet-Doku gilt sie nur
  bei fokussiertem Feld). Auswahl-Ereignisse ohne Nutzerursache (``cause``
  ``None``/``UNKNOWN``) werden danach ``QUIET_SECONDS`` lang ignoriert: Es sind
  Echos der eigenen Änderung, die sonst die gemerkte Position überschreiben
  (Nutzerbefund 2026-10-22: Cursor sprang nach Checkbox/Liste/Einrücken).
  BAUSTELLE(Caret): Wirksamkeit nur auf dem Gerät prüfbar.
* **BAUSTELLE(Offsets):** Flutter zählt Positionen in UTF-16-Einheiten. Ob Flet
  0.86.5 sie umrechnet, ist ohne Gerät nicht prüfbar. Deshalb wird bei einer
  nicht leeren Auswahl gegen ``selected_text`` geprüft, welche Zählung passt;
  vorher gilt UTF-16. Bestätigung im Gerätetest mit Emoji vor dem Caret.
"""

from __future__ import annotations

import time
from typing import Callable

import flet as ft

from ...app.list_editing import continue_list, shift_item
from ...app.text_tools import index_to_utf16, insert_tag, toggle_list, toggle_todo, utf16_to_index

Tool = Callable[[str, int | None, int | None], tuple[str, int | None, int | None]]

# Auswahl-Ereignisse ohne Nutzerursache; kurz nach einer eigenen Änderung sind das Echos.
PROGRAMMATIC = (None, ft.TextSelectionChangeCause.UNKNOWN)
QUIET_SECONDS = 1.0


def editor_toolbar(field: ft.TextField, indent_width: int = 4) -> ft.Row:
    """Knopfleiste über einem Notiz-Editor; belegt auch Enter (Listen fortsetzen).

    Args:
        field: Mehrzeiliges Textfeld; ``on_selection_change`` und ``on_change``
            werden hier belegt.
        indent_width: Leerzeichen je Einrückungsebene (Einstellung, 2 oder 4).

    Returns:
        Eine Zeile mit fünf Symbolknöpfen.
    """
    state: dict = {"start": None, "end": None, "utf16": True, "value": field.value or "", "quiet_until": 0.0}

    def to_index(text: str, offset: int) -> int:
        return utf16_to_index(text, offset) if state["utf16"] else min(offset, len(text))

    async def remember(event) -> None:
        if getattr(event, "cause", None) in PROGRAMMATIC and time.monotonic() < state["quiet_until"]:
            return  # Echo unserer eigenen Änderung (z. B. Caret ans Textende nach neuem ``value``)
        text = field.value or ""
        selection = event.selection
        if selection is None or not selection.is_valid:
            state["start"] = state["end"] = None
            return
        if not selection.is_collapsed and event.selected_text:  # Zählung eindeutig bestimmbar
            state["utf16"] = text[selection.start:selection.end] != event.selected_text
        state["start"], state["end"] = to_index(text, selection.start), to_index(text, selection.end)

    async def show(new_text: str, start: int, end: int) -> None:
        """Schreibt Text und Auswahl ins Feld (Reihenfolge siehe Moduldokumentation)."""
        convert = (lambda i: index_to_utf16(new_text, i)) if state["utf16"] else (lambda i: i)

        def selection() -> ft.TextSelection:
            return ft.TextSelection(base_offset=convert(start), extent_offset=convert(end))

        state.update(value=new_text, start=start, end=end, quiet_until=time.monotonic() + QUIET_SECONDS)
        field.value = new_text
        field.selection = selection()  # zusammen mit dem Text: kein Zwischenstand mit Caret am Ende
        field.update()
        await field.focus()
        field.selection = selection()  # nach dem Fokus erneut, damit sie sichtbar gilt
        field.update()

    async def changed(_e) -> None:
        old, new = state["value"], field.value or ""
        state["value"] = new
        result = continue_list(old, new, state["start"] if state["start"] == state["end"] else None)
        if result is not None:
            await show(result[0], result[1], result[1])

    async def run(tool: Tool) -> None:
        text = field.value or ""
        new_text, start, end = tool(text, state["start"], state["end"])
        if start is None or end is None or (new_text, start, end) == (text, state["start"], state["end"]):
            return
        await show(new_text, start, end)

    def button(icon, tooltip: str, tool: Tool) -> ft.IconButton:
        async def click(_e) -> None:
            await run(tool)
        return ft.IconButton(icon=icon, tooltip=tooltip, on_click=click)

    field.on_selection_change = remember
    field.on_change = changed
    return ft.Row([
        button(ft.Icons.CHECK_BOX_OUTLINED, "Checkbox", toggle_todo),
        button(ft.Icons.FORMAT_LIST_BULLETED, "Listenpunkt", toggle_list),
        button(ft.Icons.FORMAT_INDENT_INCREASE, "Einrücken", lambda t, s, e: shift_item(t, s, e, 1, indent_width)),
        button(ft.Icons.FORMAT_INDENT_DECREASE, "Ausrücken", lambda t, s, e: shift_item(t, s, e, -1, indent_width)),
        button(ft.Icons.TAG, "Tag (#)", insert_tag)], spacing=0)
