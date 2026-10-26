"""Tab „Todos“ UI-neutral: Filterzustand, Auswahl und Abschnitte (W7, PLAN-SPAETERE-SCHRITTE.md).

Der Filter gilt **je Sitzung** (Nutzerentscheidung 2026-10-26) und liegt als
einfaches ``dict`` an der App. ``DEFAULT_FILTER`` ist die einzige Quelle des
Standards: Startzustand, „Zurücksetzen“, Badge-Zahl (``changed_count``) und
Zusammenfassung leiten sich davon ab.

Zeitraum:

* ``aktuell`` (Standard): bis heute – Abschnitte „Sehr dringend“, „Heute“, „Frühere Tage“;
* ``zukünftig``: ab morgen – „Sehr dringend“, „Zukünftig“;
* ``beides``: alle Tage – „Sehr dringend“, „Zukünftig“, „Heute“, „Frühere Tage“.

Die Reihenfolge stammt aus ``ordering.todo_groups`` (gemeinsam mit der
Benachrichtigung); leere Abschnitte entfallen.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from ..core.query import Filter, StatusFilter, TagMode
from .ordering import todo_groups
from .views import HitRow, hit_rows

if TYPE_CHECKING:
    from .notes_service import NotesService

DEFAULT_FILTER: dict = {"status": "offen", "zeitraum": "aktuell", "tags": "", "oder": False}
STATUS_LABELS = {"offen": "offen", "erledigt": "erledigt", "alle": "alle"}
RANGE_LABELS = {"aktuell": "bis heute", "zukünftig": "ab morgen", "beides": "alle Tage"}


def normalized(state: dict) -> dict:
    """Ergänzt fehlende Schlüssel aus ``DEFAULT_FILTER`` (in place) und liefert den Zustand.

    Args:
        state: Filterzustand der Sitzung (z. B. aus einer älteren Fassung ohne ``zeitraum``).

    Returns:
        Derselbe, nun vollständige Zustand.
    """
    for key, value in DEFAULT_FILTER.items():
        state.setdefault(key, value)
    return state


def tag_list(text: str) -> tuple[str, ...]:
    """Tags aus der Eingabe (Leerzeichen getrennt, ``#`` optional).

    Args:
        text: Eingabe im Filter.

    Returns:
        Tag-Namen ohne ``#``; leere Teile entfallen.
    """
    return tuple(part.lstrip("#") for part in text.split() if part.strip("#"))


def criteria(state: dict, today: date) -> Filter:
    """Suchfilter für den Zustand.

    Args:
        state: Vollständiger Filterzustand.
        today: Heute (einmal aus ``service.clock`` gelesen).

    Returns:
        Filter auf Todos mit Status, Tags, UND/ODER und Datumsbereich.
    """
    span = {"aktuell": (None, today), "zukünftig": (today + timedelta(days=1), None)}.get(state["zeitraum"], (None, None))
    return Filter(nur_todos=True, status=StatusFilter(state["status"]), tags=tag_list(state["tags"]),
                  tag_modus=TagMode.ODER if state["oder"] else TagMode.UND, von=span[0], bis=span[1])


def todo_sections(service: "NotesService", state: dict) -> list[tuple[str, list[HitRow]]]:
    """Abschnitte des Tabs mit Titel und Anzahl der angezeigten Todos.

    Args:
        service: Geöffneter Service.
        state: Filterzustand (wird vervollständigt).

    Returns:
        ``[(„Heute (3)“, Zeilen), …]`` in fester Reihenfolge, leere entfallen.
    """
    today = service.clock.today()
    groups = todo_groups(hit_rows(service.search(criteria(normalized(state), today))), today)
    sections = [("Sehr dringend", groups.red), ("Zukünftig", groups.future), ("Heute", groups.today),
                ("Frühere Tage", groups.past)]
    return [(f"{title} ({len(rows)})", rows) for title, rows in sections if rows]


def changed_count(state: dict) -> int:
    """Wie viele Filter vom Standard abweichen (Badge am Filter-Knopf).

    Args:
        state: Filterzustand.

    Returns:
        Anzahl abweichender Einstellungen (Tags zählen, sobald welche eingetragen sind).
    """
    state = normalized(state)
    changed = [state[key] != DEFAULT_FILTER[key] for key in ("status", "zeitraum", "oder")]
    return sum(changed) + bool(tag_list(state["tags"]))


def filter_summary(state: dict) -> str:
    """Kurze Zusammenfassung neben dem Filter-Knopf.

    Args:
        state: Filterzustand.

    Returns:
        z. B. ``offen · bis heute · #schule #elternabend · ODER``.
    """
    state = normalized(state)
    parts = [STATUS_LABELS[state["status"]], RANGE_LABELS[state["zeitraum"]]]
    tags = tag_list(state["tags"])
    if tags:
        parts.append(" ".join(f"#{tag}" for tag in tags))
    if state["oder"]:
        parts.append("ODER")
    return " · ".join(parts)
