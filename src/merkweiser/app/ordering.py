"""Anzeige-Reihenfolge nach Dringlichkeit (W1, Ampel W7; PLAN-SPAETERE-SCHRITTE.md).

Nur die **Anzeige** wird umgestellt; Dateien werden nie umsortiert.

Der Rang einer Zeile ist ihre Dringlichkeitsstufe (Rot 2, Gelb 1), aber nur
bei **offenen** Todos; erledigte rücken nie vor, weil es nichts mehr zu tun
gibt. Alle Sortierungen sind **stabil**: Einträge gleichen Rangs behalten
ihre bisherige Reihenfolge.

Zwei Anwendungen:

* **Notizen und Karten** (Tab „Tag“, Suche, Tag-Seite): Rot vor Gelb vor dem
  Rest, in Bäumen **je Geschwistergruppe** (ein Teilbaum bleibt an seinem
  Elternpunkt), Karten nach ihrem höchsten Rang.
* **Todo-Listen** (Tab „Todos“ und Morgen-Benachrichtigung, eine gemeinsame
  Funktion ``todo_groups``): Offene rote Todos stehen in einem eigenen Block
  über allem; sonst gilt die **Tagesgrenze**: Zukünftig, Heute, Vergangen, je
  Abschnitt Gelb vor dem Rest. Ein gelbes Todo von gestern steht damit unter
  einem normalen von heute (Nutzerentscheidung 2026-10-26).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import TypeVar

from ..core.document import Document, ParsedNote
from ..core.inline import TodoStatus, Urgency
from .todo_tree import Fold, flatten, outline_tree
from .views import HitRow, Row, note_rows

T = TypeVar("T")


def rank(row: Row | HitRow) -> int:
    """Rang einer Zeile: Stufe bei offenen Todos, sonst 0.

    Eine Trefferzeile mit Todo-Baum (``HitRow.tree``, Tab „Todos“, W10) hat den
    höchsten Rang ihrer Baumzeilen: Ein rotes offenes Unter-Todo bringt den
    ganzen Baum nach „Sehr dringend“. Ohne Baum (Benachrichtigung, Vorschau)
    zählt nur die Zeile selbst.

    Args:
        row: Notizzeile oder Trefferzeile.

    Returns:
        2 (Rot), 1 (Gelb) oder 0.
    """
    if isinstance(row, HitRow) and row.tree:
        return max(rank(line) for line in row.tree)
    return int(row.urgency) if row.status is TodoStatus.OPEN else 0


def by_rank(items: Sequence[T], key: Callable[[T], int]) -> list[T]:
    """Sortiert absteigend nach Rang, stabil.

    Args:
        items: Einträge in Ausgangsreihenfolge.
        key: Rang eines Eintrags.

    Returns:
        Neue Liste; gleicher Rang behält die Ausgangsreihenfolge.
    """
    return sorted(items, key=lambda item: -key(item))


def urgent_first(rows: Sequence[Row]) -> list[Row]:
    """Sortiert Notizzeilen je Geschwistergruppe, Teilbäume mit höherem Rang zuerst.

    Ein Teilbaum ist eine Zeile samt aller folgenden Zeilen mit größerer
    ``depth``. Sein Rang ist der seiner **ersten** Zeile; seine Kinder werden
    rekursiv ebenso sortiert.

    Args:
        rows: Zeilen in Dateireihenfolge (``views.note_rows``).

    Returns:
        Neue Liste mit derselben Zeilenmenge.
    """
    return flatten(_sorted(outline_tree(rows)))


def _sorted(folds: Sequence[Fold]) -> list[Fold]:
    """Sortiert Geschwister-Teilbäume stabil nach dem Rang ihrer ersten Zeile, Kinder rekursiv.

    Den Baum baut ``todo_tree.outline_tree`` (einzige Teilbaum-Zerlegung, W10).
    """
    return by_rank([replace(fold, children=tuple(_sorted(fold.children))) for fold in folds],
                   lambda fold: rank(fold.row))


def note_rank(relpath: str, doc: Document, note: ParsedNote) -> int:
    """Höchster Rang einer Notiz (Notizkarten in Suche und Tag-Seite).

    Args:
        relpath: Tagesdatei.
        doc: Dokument.
        note: Die Notiz.

    Returns:
        Höchster Rang ihrer Zeilen, 0 ohne offene dringende Todos.
    """
    return max((rank(row) for row in note_rows(relpath, doc, note)), default=0)


@dataclass(frozen=True)
class TodoGroups:
    """Todo-Zeilen in Anzeige-Abschnitten; jede Eingabezeile steht in **genau einem**.

    Attributes:
        red: Offene rote Todos aller Tage: heute, dann vergangene (neueste
            zuerst), dann zukünftige (nächster zuerst).
        future: Übrige Zeilen nach ``today``: Rang absteigend, je Rang nächster Tag zuerst.
        today: Übrige Zeilen von ``today``: Rang absteigend.
        past: Übrige Zeilen vor ``today``: Rang absteigend, je Rang neuester Tag zuerst.
    """

    red: list[HitRow] = field(default_factory=list)
    future: list[HitRow] = field(default_factory=list)
    today: list[HitRow] = field(default_factory=list)
    past: list[HitRow] = field(default_factory=list)


def todo_groups(rows: Sequence[HitRow], today: date) -> TodoGroups:
    """Ordnet Todo-Zeilen in Abschnitte (gemeinsam für Tab „Todos“ und Benachrichtigung).

    Nur **offene** rote Todos durchbrechen die Tagesgrenze; erledigte rote
    stehen ohne Vorziehen in ihrem Tagesabschnitt. Innerhalb eines Tages bleibt
    die Eingabereihenfolge (``search``: Datei, Position) erhalten.

    Args:
        rows: Trefferzeilen (beliebige Reihenfolge der Tage).
        today: Bezugstag (Tab: ``service.clock.today()``, Benachrichtigung: Auslösetag).

    Returns:
        Die Abschnitte; die Auswahl (welche Tage, welcher Status) trifft der Aufrufer.
    """
    groups = TodoGroups()
    for row in rows:
        day = date.fromisoformat(row.day)
        if rank(row) == Urgency.ROT:
            groups.red.append(row)
        elif day > today:
            groups.future.append(row)
        elif day == today:
            groups.today.append(row)
        else:
            groups.past.append(row)

    def ordinal(row: HitRow) -> int:
        return date.fromisoformat(row.day).toordinal()

    def red_key(row: HitRow) -> tuple[int, int]:
        day = date.fromisoformat(row.day)
        if day == today:
            return (0, 0)
        return (1, -day.toordinal()) if day < today else (2, day.toordinal())

    groups.red.sort(key=red_key)
    groups.future.sort(key=lambda row: (-rank(row), ordinal(row)))
    groups.today.sort(key=lambda row: -rank(row))
    groups.past.sort(key=lambda row: (-rank(row), -ordinal(row)))
    return groups
