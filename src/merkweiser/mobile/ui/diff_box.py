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


def side_chips(sides: tuple[str, ...], text: str | None = None) -> ft.Control:
    """Farbfeld(er) einer oder beider Fassungen – dieselbe Farbe und dasselbe Zeichen wie im Vergleich.

    Ersetzt in Auswahlen die Wörter „Hauptdatei“/„Konfliktversion“/„Beide“: Das
    Zeichen (−/+) trägt die Bedeutung auch ohne Farbe.

    Args:
        sides: ``("haupt",)``, ``("konflikt",)`` oder ``("haupt", "konflikt")``.
        text: Inhalt statt des Zeichens (z. B. ``☐``/``☑`` für den Todo-Stand je Fassung).

    Returns:
        Ein Feld bzw. zwei direkt aneinander.
    """
    chips = [ft.Container(content=ft.Text(text or _SIDE_STYLE[side][0].strip(), size=12, font_family="monospace"),
                          bgcolor=_SIDE_STYLE[side][1], padding=ft.Padding.symmetric(horizontal=5), border_radius=4)
             for side in sides]
    return chips[0] if len(chips) == 1 else ft.Row(chips, spacing=0, tight=True)


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
