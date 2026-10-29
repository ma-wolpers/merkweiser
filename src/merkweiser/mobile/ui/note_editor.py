"""Einfüge-Leiste und Listen-Verhalten der Notiz-Editoren (Mobile).

Knöpfe: Checkbox, Listenpunkt, Einrücken, Ausrücken, ``#`` (mit ``tag_picker``:
Popup mit verwendeten Tags, W7). Dazu setzt Enter
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
* Nach einer Änderung (``show``) gehen Text und Auswahl in **zwei** Updates
  raus. Grund ist das Dart-``TextField`` von Flet 0.86.5 (``textfield.dart``,
  ``build``): Ein neuer ``value`` setzt den Controller auf „Caret am Ende“, der
  Controller-Listener schreibt dabei synchron ``selection = Ende`` in die
  Eigenschaften, und erst danach liest der Build ``selection`` – eine im selben
  Patch mitgeschickte Auswahl ist damit schon überschrieben (Nutzerbefund
  2026-10-29: Caret sprang immer ans Ende der Notiz). Deshalb:

  1. nur ``value`` senden; Dart meldet „Caret am Ende“ als Auswahl-Ereignis
     (Echo). ``show`` wartet darauf höchstens ``ECHO_TIMEOUT`` (dann ist der
     Build mit dem neuen Text sicher gelaufen und beide Patches landen nicht
     im selben Frame) und verwirft das Echo, damit es die gemerkte Position
     nicht überschreibt;
  2. ``await focus()`` (laut Flet-Doku gilt eine Auswahl nur mit Fokus);
  3. ``selection`` allein senden, vorher kurz auf ``None``: Flets ``Prop``
     überspringt sonst Werte, die dem letzten bekannten gleichen.

  Flet schickt beim Auswahl-Ereignis kein ``cause`` mit; Echos lassen sich
  daher nur über diesen Ablauf erkennen. BAUSTELLE(Caret): Gerätetest steht aus.
* **BAUSTELLE(Offsets):** Flutter zählt Positionen in UTF-16-Einheiten. Ob Flet
  0.86.5 sie umrechnet, ist ohne Gerät nicht prüfbar. Deshalb wird bei einer
  nicht leeren Auswahl gegen ``selected_text`` geprüft, welche Zählung passt;
  vorher gilt UTF-16. Bestätigung im Gerätetest mit Emoji vor dem Caret.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Callable

import flet as ft

from ...app.list_editing import continue_list, shift_item
from ...app.text_tools import index_to_utf16, insert_tag, insert_tag_name, toggle_list, toggle_todo, utf16_to_index

Tool = Callable[[str, int | None, int | None], tuple[str, int | None, int | None]]
#: Öffnet den Tag-Picker: ``(Vorbelegung, on_pick)``; ``on_pick`` erhält den Namen ohne ``#``.
TagPicker = Callable[[str, Callable[[str], Awaitable[None]]], object]

#: Höchstwartezeit (s) auf das Echo „Caret am Ende“ nach einem neuen ``value`` (siehe Moduldokumentation).
ECHO_TIMEOUT = 0.3


def editor_toolbar(field: ft.TextField, indent_width: int = 4, tag_picker: TagPicker | None = None) -> ft.Row:
    """Knopfleiste über einem Notiz-Editor; belegt auch Enter (Listen fortsetzen).

    Args:
        field: Mehrzeiliges Textfeld; ``on_selection_change`` und ``on_change``
            werden hier belegt.
        indent_width: Leerzeichen je Einrückungsebene (Einstellung, 2 oder 4).
        tag_picker: Mit Picker öffnet ``#`` das Popup (Vorbelegung = markierter
            Text); die gewählte Stelle wird beim Tipp festgehalten und der Tag
            über ``text_tools.insert_tag_name`` eingefügt. Ohne Picker (Tests,
            Desktop) gilt ``insert_tag``.

    Returns:
        Eine Zeile mit fünf Symbolknöpfen.
    """
    state: dict = {"start": None, "end": None, "utf16": True, "value": field.value or "", "echo": None}

    def to_index(text: str, offset: int) -> int:
        return utf16_to_index(text, offset) if state["utf16"] else min(offset, len(text))

    async def remember(event) -> None:
        echo = state["echo"]
        if echo is not None and not echo.is_set():
            echo.set()  # Echo „Caret am Ende“ unseres neuen ``value``: verwerfen, ``show`` setzt die Auswahl
            return
        text = field.value or ""
        selection = event.selection
        if selection is None or not selection.is_valid:
            state["start"] = state["end"] = None
            return
        if not selection.is_collapsed and event.selected_text:  # Zählung eindeutig bestimmbar
            state["utf16"] = text[selection.start:selection.end] != event.selected_text
        state["start"], state["end"] = to_index(text, selection.start), to_index(text, selection.end)

    async def show(new_text: str, start: int, end: int) -> None:
        """Schreibt erst den Text, dann die Auswahl ins Feld (Ablauf und Grund: Moduldokumentation).

        Args:
            new_text: Neuer Feldinhalt.
            start: Auswahlanfang (Python-Index).
            end: Auswahlende (Python-Index).
        """
        convert = (lambda i: index_to_utf16(new_text, i)) if state["utf16"] else (lambda i: i)
        echo = asyncio.Event()
        state.update(value=new_text, start=start, end=end, echo=echo)
        field.value = new_text
        field.update()  # 1. nur der Text – Dart setzt den Caret ans Ende und meldet das
        try:
            await asyncio.wait_for(echo.wait(), ECHO_TIMEOUT)
        except TimeoutError:  # kein Echo (z. B. Caret stand schon dort): Build ist trotzdem durch
            pass
        state["echo"] = None
        await field.focus()  # 2.
        field.selection = None  # 3. erzwingt das Senden, auch bei gleichem Wert wie zuletzt
        field.selection = ft.TextSelection(base_offset=convert(start), extent_offset=convert(end))
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

    async def pick_tag(_e) -> None:
        text, start, end = field.value or "", state["start"], state["end"]
        initial = text[start:end].strip() if start is not None and end is not None and start != end else ""

        async def chosen(name: str) -> None:
            current = field.value or ""
            new_text, new_start, new_end = insert_tag_name(current, start, end, name)
            if new_start is not None and new_end is not None and new_text != current:
                await show(new_text, new_start, new_end)

        tag_picker(initial, chosen)  # type: ignore[misc]

    field.on_selection_change = remember
    field.on_change = changed
    tag_button = ft.IconButton(icon=ft.Icons.TAG, tooltip="Tag (#)", on_click=pick_tag) if tag_picker \
        else button(ft.Icons.TAG, "Tag (#)", insert_tag)
    return ft.Row([
        button(ft.Icons.CHECK_BOX_OUTLINED, "Checkbox", toggle_todo),
        button(ft.Icons.FORMAT_LIST_BULLETED, "Listenpunkt", toggle_list),
        button(ft.Icons.FORMAT_INDENT_INCREASE, "Einrücken", lambda t, s, e: shift_item(t, s, e, 1, indent_width)),
        button(ft.Icons.FORMAT_INDENT_DECREASE, "Ausrücken", lambda t, s, e: shift_item(t, s, e, -1, indent_width)),
        tag_button], spacing=0)
