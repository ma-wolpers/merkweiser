"""Inhalt der Morgen-Benachrichtigung (W5): offene Todos des Auslösetags plus offene dringende aller Tage.

Dringende stehen zuerst (W1), jedes Todo nur einmal. Verschobene Todos stehen
seit dem 2026-10-22 ohne Kopfzeile direkt in der Zieldatei und zählen damit
zum Auslösetag.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from ..core.query import Filter, StatusFilter, UrgentFilter
from .views import hit_rows

if TYPE_CHECKING:
    from .notes_service import NotesService


def content_lines(service: "NotesService", day: date) -> list[str]:
    """Zeilen der Inhaltsbenachrichtigung für ``day`` (leer = keine Inhaltsbenachrichtigung).

    Args:
        service: Geöffneter Service.
        day: Auslösetag.

    Returns:
        ``⭐ Text (TT.MM.)`` für dringende, ``• Text`` für die übrigen Todos des Tages.
    """
    urgent = service.search(Filter(nur_todos=True, status=StatusFilter.OFFEN, dringend=UrgentFilter.JA))
    of_day = service.search(Filter(nur_todos=True, status=StatusFilter.OFFEN, von=day, bis=day))
    seen: set[tuple[str, int]] = set()
    lines: list[str] = []
    for hit, row in zip(urgent, hit_rows(urgent)):
        seen.add((hit.relpath, hit.line_no))
        lines.append(f"⭐ {row.text.strip('=').strip()} ({hit.day:%d.%m.})")
    for hit, row in zip(of_day, hit_rows(of_day)):
        if (hit.relpath, hit.line_no) not in seen:
            lines.append(f"• {row.text}")
    return lines
