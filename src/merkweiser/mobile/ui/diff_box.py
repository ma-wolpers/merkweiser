"""Zeilenvergleich als Kasten (Konflikte, Auto-Merge-Liste, Backups).

Rot (−) = nur in der ersten Fassung (Hauptdatei bzw. vorher), grün (+) = nur
in der zweiten (Konfliktversion bzw. nachher), ohne Farbe = in beiden gleich.
Eigenes Modul, weil Konfliktseite, Notiz-Auswahl und Backup-Seite ihn teilen.
"""

from __future__ import annotations

import flet as ft

from ...app.conflict_views import DiffRow
from .style import DIFF_ADDED, DIFF_REMOVED

#: Darstellung je Vergleichsseite: (Präfix, Hintergrund).
_SIDE_STYLE = {
    "haupt": ("− ", DIFF_REMOVED),
    "konflikt": ("+ ", DIFF_ADDED),
    "beide": ("  ", None),
    "ausgelassen": ("", None),
}


def diff_box(rows: list[DiffRow], same_text: str | None = "Beide Fassungen sind inhaltlich gleich.",
             framed: bool = True) -> ft.Control:
    """Zeilenvergleich als Kasten mit farbig hinterlegten Abweichungen.

    Args:
        rows: Vergleichszeilen (``conflict_diff``, ``line_diff`` oder ``note_conflicts.entry_diff``).
        same_text: Hinweis statt der Zeilen, wenn keine Zeile abweicht; ``None`` = Zeilen immer zeigen
            (Notiz-Einträge, deren Unterschied nur im Häkchen ``[?]`` liegt).
        framed: ``False`` = nur die Zeilen, ohne eigenen Kasten (innerhalb einer Karte).

    Returns:
        Ein Container (bzw. ohne Rahmen eine Spalte) mit einer Zeile je ``DiffRow``.
    """
    if same_text is not None and all(row.side in ("beide", "ausgelassen") for row in rows):
        rows_controls = [ft.Text(same_text, size=12, italic=True)]
    else:
        rows_controls = []
        for row in rows:
            prefix, color = _SIDE_STYLE[row.side]
            italic = row.side == "ausgelassen"
            rows_controls.append(ft.Container(content=ft.Text(prefix + row.text, size=12, italic=italic,
                                                              font_family="monospace"), bgcolor=color))
    column = ft.Column(rows_controls, spacing=0)
    return ft.Container(content=column, padding=6, bgcolor=ft.Colors.SURFACE_CONTAINER) if framed else column
