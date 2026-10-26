"""Inhalt der Morgen-Benachrichtigung (W5, Ampel W7).

Auswahl: offene Todos bis einschließlich Auslösetag. Reihenfolge über die
gemeinsame Funktion ``ordering.todo_groups`` (dieselbe wie im Tab „Todos“),
hier ohne eigene Sortierung:

1. ``🔥 Text (TT.MM.)`` – rote Todos aller Tage bis zum Auslösetag,
2. ``⭐ Text`` – gelbe Todos des Auslösetags,
3. ``• Text`` – übrige Todos des Auslösetags,
4. ``⭐ Text (TT.MM.)`` – gelbe Todos früherer Tage.

Normale Todos früherer Tage und alle zukünftigen stehen nicht darin
(Nutzerentscheidung 2026-10-26). 🔥 gibt es nur hier; die Datei behält
``==🔴…==``. Verschobene Todos stehen seit dem 2026-10-22 ohne Kopfzeile direkt
in der Zieldatei und zählen damit zum Auslösetag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from ..core.inline import Urgency, strip_urgency
from ..core.query import Filter, StatusFilter
from .ordering import rank, todo_groups
from .views import HitRow, hit_rows

if TYPE_CHECKING:
    from .notes_service import NotesService

#: Zeichen je Stufe in der Benachrichtigung.
SYMBOL = {Urgency.ROT: "🔥", Urgency.GELB: "⭐"}
PLAIN = "•"


@dataclass(frozen=True)
class NotifyContent:
    """Inhalt einer Inhaltsbenachrichtigung (vor dem Kürzen auf ``MAX_LINES``).

    Attributes:
        lines: Zeilen in Anzeigereihenfolge; leer = keine Inhaltsbenachrichtigung.
        red: Anzahl roter Todos (für Titel und Kanal).
        yellow: Anzahl enthaltener gelber Todos (heute und früher).
        bold: Indizes der hervorgehobenen Zeilen (🔥 und ⭐) in ``lines``.
    """

    lines: tuple[str, ...] = ()
    red: int = 0
    yellow: int = 0
    bold: tuple[int, ...] = ()


def content(service: "NotesService", day: date) -> NotifyContent:
    """Inhalt der Benachrichtigung für den Auslösetag ``day`` (siehe Moduldoku).

    Args:
        service: Geöffneter Service.
        day: Auslösetag.

    Returns:
        Zeilen samt Zählung und Fett-Indizes.
    """
    rows = hit_rows(service.search(Filter(nur_todos=True, status=StatusFilter.OFFEN, bis=day)))
    groups = todo_groups(rows, day)
    past_yellow = [row for row in groups.past if rank(row) == Urgency.GELB]
    entries = ([(row, True) for row in groups.red] + [(row, False) for row in groups.today]
               + [(row, True) for row in past_yellow])
    lines = [_line(row, dated) for row, dated in entries]
    bold = tuple(i for i, (row, _dated) in enumerate(entries) if rank(row))
    yellow = sum(1 for row in groups.today if rank(row) == Urgency.GELB) + len(past_yellow)
    return NotifyContent(tuple(lines), len(groups.red), yellow, bold)


def _line(row: HitRow, dated: bool) -> str:
    """Eine Zeile: Zeichen der Stufe, Text ohne Markierung, ggf. Datum.

    Args:
        row: Trefferzeile.
        dated: Datum anhängen (rote und vergangene Todos).

    Returns:
        z. B. ``🔥 Antrag (10.01.)`` oder ``• Elternbrief``.
    """
    text = f"{SYMBOL.get(Urgency(rank(row)), PLAIN)} {strip_urgency(row.text).strip()}"
    return f"{text} ({date.fromisoformat(row.day):%d.%m.})" if dated else text
