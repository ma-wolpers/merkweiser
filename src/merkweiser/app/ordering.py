"""Anzeige-Reihenfolge: dringende Todos zuerst (W1, PLAN-SPAETERE-SCHRITTE.md).

Nur die **Anzeige** wird umgestellt; Dateien werden nie umsortiert.

„Dringend“ heißt hier: offenes Todo mit ``==…==`` (``Row.urgent`` und nicht
erledigt). Ein erledigtes dringendes Todo rückt nicht nach oben, weil es
nichts mehr zu tun gibt.

Alle Sortierungen sind **stabil**: Einträge gleicher Dringlichkeit behalten
ihre bisherige Reihenfolge. In Bäumen wird **je Geschwistergruppe** sortiert;
ein Teilbaum bleibt an seinem Elternpunkt.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from ..core.document import Document, ParsedNote
from .views import HitRow, Row, note_rows

T = TypeVar("T")


def is_pressing(row: Row | HitRow) -> bool:
    """``True`` für ein offenes, dringendes Todo.

    Args:
        row: Notizzeile oder Trefferzeile.

    Returns:
        Ob die Zeile in der Anzeige nach oben gehört.
    """
    return bool(row.urgent) and row.done is False


def urgent_first(rows: Sequence[Row]) -> list[Row]:
    """Sortiert Notizzeilen je Geschwistergruppe, dringende Teilbäume zuerst.

    Ein Teilbaum ist eine Zeile samt aller folgenden Zeilen mit größerer
    ``depth``. Er gilt als dringend, wenn seine **erste** Zeile dringend ist;
    seine Kinder werden rekursiv ebenso sortiert.

    Args:
        rows: Zeilen in Dateireihenfolge (``views.note_rows``).

    Returns:
        Neue Liste mit derselben Zeilenmenge.
    """
    return [row for block in _blocks(list(rows), 0, len(rows)) for row in block]


def _blocks(rows: list[Row], start: int, end: int) -> list[list[Row]]:
    """Zerlegt ``rows[start:end]`` in Geschwister-Teilbäume und sortiert sie stabil.

    Args:
        rows: Alle Zeilen.
        start: Erster Index.
        end: Index hinter dem letzten.

    Returns:
        Teilbäume als Zeilenlisten, dringende zuerst, Kinder bereits sortiert.
    """
    blocks: list[list[Row]] = []
    i = start
    while i < end:
        head = rows[i]
        j = i + 1
        while j < end and rows[j].depth > head.depth:
            j += 1
        children = [row for block in _blocks(rows, i + 1, j) for row in block]
        blocks.append([head, *children])
        i = j
    return stable_first(blocks, lambda block: is_pressing(block[0]))


def note_is_pressing(relpath: str, doc: Document, note: ParsedNote) -> bool:
    """``True``, wenn eine Notiz ein offenes dringendes Todo enthält (Notizkarten in Suche und Tag-Seite).

    Args:
        relpath: Tagesdatei.
        doc: Dokument.
        note: Die Notiz.

    Returns:
        Ob die Karte nach oben gehört.
    """
    return any(is_pressing(row) for row in note_rows(relpath, doc, note))


def stable_first(items: Sequence[T], pressing: Callable[[T], bool]) -> list[T]:
    """Stellt Einträge mit ``pressing(x)`` nach vorn; sonst bleibt die Reihenfolge.

    Args:
        items: Einträge in Ausgangsreihenfolge.
        pressing: Prädikat „gehört nach oben“.

    Returns:
        Neue Liste.
    """
    return [x for x in items if pressing(x)] + [x for x in items if not pressing(x)]
