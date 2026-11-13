"""UI-neutrale Anzeigemodelle für Konflikte (Desktop und Mobile; keine Flet-/Tk-Abhängigkeit).

Schnellwahl (``Choice``; die notizweise Entscheidung steht in ``note_plan``
und ``note_conflicts``), Zeilenvergleich (``conflict_diff``, ``line_diff``),
Herkunft der Konfliktversion und deutsche Anzeigetexte der Fallarten
(``case_headline``). Die Oberflächen rendern nur noch.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from enum import Enum

from ..core.conflicts import CaseKind, ConflictCase
from ..core.source import SourceText


class Choice(Enum):
    """Schnellwahl für alle Notizen eines Falls (``note_conflicts.quick_select``)."""

    HAUPTDATEI = "hauptdatei"
    KONFLIKTVERSION = "konfliktversion"
    BEIDE = "beide"




@dataclass(frozen=True)
class DiffRow:
    """Eine Zeile im Vergleich Hauptdatei ↔ Konfliktversion.

    Attributes:
        side: ``"beide"`` (in beiden gleich), ``"haupt"`` (nur in der
            Hauptdatei), ``"konflikt"`` (nur in der Konfliktversion) oder
            ``"ausgelassen"`` (Platzhalter für übersprungene gleiche Zeilen).
        text: Zeilentext ohne Zeilenende (bei ``"ausgelassen"``: Hinweistext).
    """

    side: str
    text: str


def conflict_diff(case: ConflictCase, context: int = 1) -> list[DiffRow]:
    """Zeilenvergleich für die Konfliktanzeige (Hauptdatei ↔ Konfliktversion).

    Args:
        case: Konfliktfall (fehlt die Hauptdatei, ist alles „nur Konfliktversion“).
        context: Gleiche Zeilen, die um jede Abweichung herum sichtbar bleiben.

    Returns:
        Siehe ``line_diff``.
    """
    return line_diff(case.main_bytes, case.conflict_bytes, context)


def line_diff(first: bytes | None, second: bytes, context: int = 1) -> list[DiffRow]:
    """Zeilenvergleich zweier Fassungen; lange gleiche Strecken werden gekürzt.

    Die Seiten heißen ``"haupt"`` (nur in ``first``) und ``"konflikt"`` (nur in
    ``second``); beim Auto-Merge-Protokoll bedeuten sie „vorher“ bzw. „nachher“.

    Args:
        first: Erste Fassung oder ``None`` (fehlt: alles gehört zur zweiten).
        second: Zweite Fassung.
        context: Gleiche Zeilen, die um jede Abweichung herum sichtbar bleiben.

    Returns:
        Zeilen in Lesereihenfolge. Sind beide Fassungen gleich, nur ``"beide"``-
        bzw. ``"ausgelassen"``-Zeilen.
    """
    main = [l.text for l in SourceText.from_bytes(first or b"").lines]
    other = [l.text for l in SourceText.from_bytes(second).lines]
    rows: list[DiffRow] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=main, b=other, autojunk=False).get_opcodes():
        if tag == "equal":
            same = main[i1:i2]
            head = same[:context] if rows else []
            tail = same[len(head):][-context:] if i2 < len(main) or j2 < len(other) else []
            skipped = len(same) - len(head) - len(tail)
            rows += [DiffRow("beide", t) for t in head]
            if skipped > 0:
                rows.append(DiffRow("ausgelassen", f"… {skipped} gleiche Zeile(n) …"))
            rows += [DiffRow("beide", t) for t in tail]
            continue
        rows += [DiffRow("haupt", t) for t in main[i1:i2]]
        rows += [DiffRow("konflikt", t) for t in other[j1:j2]]
    return rows


def conflict_origin(case: ConflictCase) -> str:
    """Woher die Konfliktversion stammt, für Menschen lesbar.

    Args:
        case: Konfliktfall.

    Returns:
        z. B. „von Merkweiser selbst, 21.10.2026 14:03“ oder
        „von Syncthing-Gerät ABCDEFG, 21.10.2026 14:03“.
    """
    stamp = case.conflict.stamp
    when = f"{stamp[6:8]}.{stamp[4:6]}.{stamp[:4]} {stamp[9:11]}:{stamp[11:13]}" if len(stamp) == 15 else stamp
    who = "von Merkweiser selbst" if case.conflict.own else f"von Syncthing-Gerät {case.conflict.device}"
    return f"{who}, {when}"


#: Anzeigetexte der Fallarten (statt der internen Enum-Werte).
CASE_KIND_LABELS = {
    CaseKind.AUTO: "Automatisch zusammenführbar",
    CaseKind.MANUAL: "Entscheidung nötig",
    CaseKind.MAIN_DELETED: "Hauptdatei fehlt",
    CaseKind.BUSY: "Wird gerade von einer anderen Merkweiser-Instanz bearbeitet",
}

def case_headline(case: ConflictCase) -> str:
    """Kopfzeile eines Falls: Fallart, dahinter die Begründung nur, wenn sie etwas hinzufügt.

    Args:
        case: Konfliktfall.

    Returns:
        z. B. „Hauptdatei fehlt“ oder „Entscheidung nötig: verschachtelte Konfliktdatei“.
    """
    label = CASE_KIND_LABELS[case.kind]
    return f"{label}: {case.reason}" if case.reason and case.reason != label else label
