"""Kopfbereich (YAML) im Konfliktdialog: eine Entscheidung je Kopf-Konflikt (W6, Y5).

* **Eigenschaft** bzw. ganzer **undurchsichtiger Kopf**: Hauptdatei oder
  Konfliktversion.
* **Laufende Messungen**: genau die Optionen aus ``StampConflict.options``
  (einseitig: weiterlaufen/verwerfen; zwei Stempel: „nur die spätere“ plus
  „die frühere“ bei gleicher bzw. „die frühere endet …“ bei verschiedener
  Tätigkeit; beschädigt: verwerfen oder den gültigen behalten).

Die Wahl steht in ``NoteChoices.fm`` (``app/note_conflicts.py``) und gilt,
wenn für den Kopf „Beide (je Eigenschaft)“ gewählt ist (W8).
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from ...core.merge.frontmatter import BlockConflict, FmMerge, PropertyConflict, StampConflict


def frontmatter_controls(merged: FmMerge | None, chosen: dict[int, str],
                         on_change: Callable[[], None] = lambda: None) -> list[ft.Control]:
    """Auswahl je Kopf-Konflikt; leer, wenn der Kopf ohne Entscheidung auflösbar ist.

    Args:
        merged: Kopf-Merge des Falls oder ``None``.
        chosen: Entscheidungen je Konfliktindex (wird bei jeder Wahl geändert).
        on_change: Wird nach jeder Wahl aufgerufen (z. B. Seite neu zeichnen).

    Returns:
        Erklärung und je Konflikt eine Auswahl.
    """
    if merged is None or not merged.conflicts:
        return []
    controls: list[ft.Control] = [ft.Text("Je Eigenschaft entscheiden:", size=12)]
    for index, conflict in enumerate(merged.conflicts):
        title, options = _describe(conflict)

        def changed(e, i=index) -> None:
            chosen[i] = e.control.value
            on_change()
        controls += [ft.Text(title, size=12, weight=ft.FontWeight.W_600),
                     ft.RadioGroup(content=ft.Column([ft.Radio(value=code, label=label) for code, label in options]),
                                   value=chosen.get(index), on_change=changed)]
    return controls


def _describe(conflict) -> tuple[str, list[tuple[str, str]]]:
    """Titel und Optionen eines Kopf-Konflikts."""
    if isinstance(conflict, StampConflict):
        return "Laufende Messungen auf zwei Geräten", conflict.options()
    if isinstance(conflict, PropertyConflict):
        show = lambda lines: " / ".join(lines) if lines else "(fehlt)"  # noqa: E731
        return f"Eigenschaft „{conflict.key}“", [("a", f"Hauptdatei: {show(conflict.a)}"),
                                                ("b", f"Konfliktversion: {show(conflict.b)}")]
    assert isinstance(conflict, BlockConflict)
    return "Ganzer Kopfbereich (nicht einzeln lesbar)", [("a", "Kopf der Hauptdatei"), ("b", "Kopf der Konfliktversion")]
