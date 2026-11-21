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

W10: Ein Eintrag ist ein **Todo-Baum** (``todo_trees``): Unter-Todos stehen
nicht mehr als eigene Einträge da, sondern unter ihrem obersten Eltern-Todo;
eingeklappt sichtbar bleiben offene Todos und Todos mit dem gefilterten
Status (``fold_keep``). Die Abschnittszahl zählt Bäume. Die Benachrichtigung
bleibt eine flache Liste (Nutzerentscheidung 2026-11-21).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import TYPE_CHECKING

from ..core.inline import TodoStatus
from ..core.query import STATUS_OF_FILTER, Filter, Hit, StatusFilter, TagMode, node_hit
from .ordering import todo_groups, urgent_first
from .routine_preview import preview_rows
from .todo_tree import OPEN_ONLY, top_todo, tree_rows
from .views import HitRow, hit_rows, note_rows, tag_list

if TYPE_CHECKING:
    from .notes_service import NotesService

DEFAULT_FILTER: dict = {"status": "offen", "zeitraum": "aktuell", "tags": "", "oder": False}
STATUS_LABELS = {f.value: f.value
                 for f in (StatusFilter.OFFEN, StatusFilter.ERLEDIGT, StatusFilter.VERPASST, StatusFilter.ALLE)}
"""Status-Optionen des Filter-Dialogs in Anzeigereihenfolge (Werte aus ``StatusFilter``)."""
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
    wanted = criteria(normalized(state), today)
    rows = todo_trees(service, service.search(wanted)) + preview_rows(service, wanted, today)  # W9: kommende Routinen
    groups = todo_groups(rows, today)
    sections = [("Sehr dringend", groups.red), ("Zukünftig", groups.future), ("Heute", groups.today),
                ("Frühere Tage", groups.past)]
    return [(f"{title} ({len(rows)})", rows) for title, rows in sections if rows]


def todo_trees(service: "NotesService", hits: list[Hit]) -> list[HitRow]:
    """Treffer als Todo-Bäume (W10): ein Eintrag je oberstem Todo, Unter-Todos stehen in seinem ``tree``.

    Jeder Treffer gehört zum Baum seines obersten Todo-Vorfahren
    (``todo_tree.top_todo``). Die Wurzel erscheint auch, wenn sie selbst nicht
    zum Filter passt (z. B. schon erledigt; Treffer über ``query.node_hit``).
    Reihenfolge: erster Treffer je Baum; die Abschnitte ordnet danach
    ``ordering.todo_groups`` (Rang über den ganzen Baum, ``ordering.rank``).

    Args:
        service: Geöffneter Service (Dokumente aus dem Cache).
        hits: Treffer aus ``service.search``.

    Returns:
        Eine Trefferzeile je Baum mit ``tree`` (Wurzel mit Tiefe 0, nach ``urgent_first``).
    """
    roots: dict[tuple[str, int, int], Hit] = {}
    for hit in hits:
        doc = service.cache.get(hit.relpath)
        note = doc.notes[hit.note_index]
        top = top_todo(note, note.outline.nodes[hit.node_index])
        key = (hit.relpath, hit.note_index, top.index)
        if key not in roots:
            roots[key] = hit if top.index == hit.node_index else node_hit(hit.relpath, hit.day, doc, note, top)
    rows = []
    for (relpath, note_index, _top), root in roots.items():
        doc = service.cache.get(relpath)
        lines = urgent_first(note_rows(relpath, doc, doc.notes[note_index]))
        rows += [replace(row, tree=tree_rows(lines, root.line_no)) for row in hit_rows([root])]
    return rows


def fold_keep(state: dict) -> frozenset[TodoStatus]:
    """Todo-Zustände, die im Tab „Todos“ eingeklappt sichtbar bleiben: offen plus der gefilterte Status (W10).

    Args:
        state: Filterzustand.

    Returns:
        Bei „alle“ alle Todo-Zustände, sonst ``OPEN_ONLY`` plus den Status des Filters.
    """
    wanted = STATUS_OF_FILTER.get(StatusFilter(normalized(state)["status"]))
    return frozenset(STATUS_OF_FILTER.values()) if wanted is None else OPEN_ONLY | {wanted}


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
