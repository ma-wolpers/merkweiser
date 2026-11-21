"""Zeilenbaum einer Notiz und Faltregel für einklappbare Todos (W10, UI-neutral).

``views.note_rows`` liefert Zeilen flach mit ``depth``; hier wird daraus
**einmal** der Baum gebaut (``outline_tree``). Ihn nutzen

* ``ordering.urgent_first`` zum Sortieren je Geschwistergruppe und
* ``fold_rows`` für das Einklappen in allen Ansichten (Tag, Suche,
  Notiz-Seite, Tab „Todos“).

Faltregel (Nutzerentscheidung 2026-11-21): Nur **Todos** sind einklappbar.
Ein Kind eines Todos bleibt auch eingeklappt sichtbar (``pinned``), wenn sein
Teilbaum ein Todo mit einem Status aus ``keep`` enthält – standardmäßig
**offen**. Offene Todos werden so nie versteckt; erledigte und verpasste
Unter-Todos, Punkte und Sonstiges gehören zum einklappbaren Teil. Kinder von
Nicht-Todos sind immer sichtbar. Ein **Unter-Todo** ist ein Todo mit einem
Todo als Vorfahr (auch über einen Punkt dazwischen); die Oberfläche
kennzeichnet es mit ↳.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..core.inline import TodoStatus
from .views import Row

OPEN_ONLY: frozenset[TodoStatus] = frozenset({TodoStatus.OPEN})
"""Standard für ``keep``: nur offene Todos bleiben eingeklappt sichtbar."""


@dataclass(frozen=True)
class Fold:
    """Ein Knoten des Zeilenbaums.

    Attributes:
        row: Die Zeile.
        children: Teilbäume der direkten Kinder in Anzeigereihenfolge.
        pinned: Auch eingeklappt sichtbar (siehe Moduldoku); Wurzeln immer.
        sub_todo: Todo mit einem Todo als Vorfahr (Anzeige mit ↳).
    """

    row: Row
    children: tuple["Fold", ...] = ()
    pinned: bool = True
    sub_todo: bool = False


def outline_tree(rows: Sequence[Row]) -> list[Fold]:
    """Baut den Baum aus flachen Zeilen: Kinder sind die folgenden Zeilen mit größerer ``depth``.

    Args:
        rows: Zeilen in Anzeigereihenfolge (z. B. ``views.note_rows``).

    Returns:
        Die Wurzeln (alle Knoten ``pinned``, kein ``sub_todo``).
    """
    return _forest(list(rows), 0, len(rows))


def _forest(rows: list[Row], start: int, end: int) -> list[Fold]:
    """Teilbäume von ``rows[start:end]``."""
    folds, i = [], start
    while i < end:
        j = i + 1
        while j < end and rows[j].depth > rows[i].depth:
            j += 1
        folds.append(Fold(rows[i], tuple(_forest(rows, i + 1, j))))
        i = j
    return folds


def flatten(folds: Sequence[Fold]) -> list[Row]:
    """Zeilen eines Baums in Anzeigereihenfolge (Umkehrung von ``outline_tree``)."""
    return [row for fold in folds for row in (fold.row, *flatten(fold.children))]


def fold_rows(rows: Sequence[Row], keep: frozenset[TodoStatus] = OPEN_ONLY) -> list[Fold]:
    """Baum mit Faltregel (siehe Moduldoku).

    Args:
        rows: Zeilen in Anzeigereihenfolge.
        keep: Todo-Zustände, die eingeklappt sichtbar bleiben (Tab „Todos“:
            offen plus der gefilterte Status).

    Returns:
        Die Wurzeln mit gesetztem ``pinned`` und ``sub_todo``.
    """
    return [_mark(fold, keep, todo_above=False, pinned=True) for fold in outline_tree(rows)]


def _mark(fold: Fold, keep: frozenset[TodoStatus], todo_above: bool, pinned: bool) -> Fold:
    """Setzt ``pinned``/``sub_todo`` rekursiv."""
    is_todo = fold.row.status is not None
    children = tuple(_mark(child, keep, todo_above or is_todo, pinned=not is_todo or _keeps(child, keep))
                     for child in fold.children)
    return replace(fold, children=children, pinned=pinned, sub_todo=is_todo and todo_above)


def _keeps(fold: Fold, keep: frozenset[TodoStatus]) -> bool:
    """``True``, wenn der Teilbaum ein Todo mit einem Status aus ``keep`` enthält."""
    return fold.row.status in keep or any(_keeps(child, keep) for child in fold.children)


def hidden(fold: Fold) -> int:
    """Anzahl der Kinder, die eingeklappt verborgen sind (für „▸ N weitere“)."""
    return sum(1 for child in fold.children if not child.pinned)


def fold_key(row: Row) -> tuple[str, str]:
    """Schlüssel des Klappzustands: Datei und Anzeigetext ohne Checkbox (Abhaken ändert ihn nicht).

    Args:
        row: Zeile eines einklappbaren Todos.

    Returns:
        ``(relpath, Text)``; zwei gleichlautende Todos einer Datei teilen sich den Zustand.
    """
    return (row.target.relpath if row.target else "", row.text)
