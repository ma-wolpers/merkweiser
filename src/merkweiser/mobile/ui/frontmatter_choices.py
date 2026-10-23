"""Kopfbereich (YAML) im Konfliktdialog: eine Entscheidung je Kopf-Konflikt (W6, Y5).

* **Eigenschaft** bzw. ganzer **undurchsichtiger Kopf**: Hauptdatei oder
  Konfliktversion.
* **Laufende Messungen**: genau die Optionen aus ``StampConflict.options``
  (einseitig: weiterlaufen/verwerfen; zwei Stempel: „nur die spätere“ plus
  „die frühere“ bei gleicher bzw. „die frühere endet …“ bei verschiedener
  Tätigkeit; beschädigt: verwerfen oder den gültigen behalten).

Die Wahl wird je Konfliktdatei in ``app._fm_decisions`` gemerkt und von
„Zusammenführen“ und „Auswahl übernehmen“ (``hunk_view``) genutzt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...core.merge.frontmatter import BlockConflict, PropertyConflict, StampConflict

if TYPE_CHECKING:
    from .app import MobileApp


def fm_decisions(app: "MobileApp", case) -> dict[int, str]:
    """Bisherige Entscheidungen für den Kopf dieses Falls (leer, falls keine oder ohne Kopf)."""
    if getattr(case, "frontmatter", None) is None:
        return {}
    return app.__dict__.setdefault("_fm_decisions", {}).setdefault(case.conflict.relpath, {})


def frontmatter_controls(app: "MobileApp", case) -> list[ft.Control]:
    """Auswahl je Kopf-Konflikt; leer, wenn der Kopf ohne Entscheidung auflösbar ist.

    Args:
        app: Die laufende App.
        case: Konfliktfall.

    Returns:
        Überschrift, Erklärung und je Konflikt eine Auswahl.
    """
    merged = getattr(case, "frontmatter", None)
    if merged is None or not merged.conflicts:
        return []
    chosen = fm_decisions(app, case)
    controls: list[ft.Control] = [ft.Text("Kopfbereich (YAML)", weight=ft.FontWeight.BOLD),
                                  ft.Text("Zuerst hier entscheiden; danach „Zusammenführen“ bzw. „Auswahl übernehmen“.",
                                          size=12)]
    for index, conflict in enumerate(merged.conflicts):
        title, options = _describe(conflict)

        def changed(e, i=index) -> None:
            chosen[i] = e.control.value
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
