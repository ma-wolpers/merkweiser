"""UI-neutrale Anzeigemodelle für Konflikte (Desktop und Mobile; keine Flet-/Tk-Abhängigkeit).

Einfache Entscheidungen (``Choice``/``conflict_result``), abschnittsweise
Entscheidungen (``hunk_result``), Zeilenvergleich (``conflict_diff``,
``line_diff``), Herkunft der Konfliktversion und deutsche Anzeigetexte der
Fallarten. Die Oberflächen rendern nur noch.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from enum import Enum

from ..core.conflicts import CaseKind, ConflictCase, HunkPick, apply_hunk_picks, render
from ..core.merge.union import merge2
from ..core.source import SourceText


class Choice(Enum):
    """Einfache Konfliktentscheidung für Fälle ohne Hunk-Auswahl."""

    HAUPTDATEI = "hauptdatei"
    KONFLIKTVERSION = "konfliktversion"
    BEIDE = "beide"


def conflict_result(case: ConflictCase, choice: Choice) -> bytes:
    """Ergebnis-Bytes einer einfachen Konfliktentscheidung.

    ``BEIDE`` vereinigt verlustfrei (Union, Hauptdatei zuerst) im Zeilenende-Stil
    der Hauptdatei bzw. der Konfliktversion, falls die Hauptdatei fehlt.

    Args:
        case: Konfliktfall.
        choice: Wahl.

    Returns:
        Bytes für ``NotesService.resolve``.
    """
    if choice is Choice.HAUPTDATEI and case.main_bytes is not None:
        return case.main_bytes
    if choice is Choice.KONFLIKTVERSION or case.main_bytes is None:
        return case.conflict_bytes
    a = [l.text for l in SourceText.from_bytes(case.main_bytes).lines]
    b = [l.text for l in SourceText.from_bytes(case.conflict_bytes).lines]
    return render(merge2(a, b).lines(), case.main_bytes)


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

#: Anzeigenamen der Hunk-Wahl (Reihenfolge = Reihenfolge der Auswahl).
HUNK_PICK_LABELS = ((HunkPick.HAUPT, "Hauptdatei"), (HunkPick.KONFLIKT, "Konfliktversion"),
                    (HunkPick.BEIDE, "Beide"), (HunkPick.BEARBEITET, "Bearbeitet"))


def hunk_result(case: ConflictCase, picks: list[tuple[HunkPick, str]]) -> tuple[bytes, str]:
    """Ergebnis-Bytes und lesbare Entscheidung einer abschnittsweisen Konfliktauflösung.

    Args:
        case: Konfliktfall mit Merge (``case.merge`` hat Hunks) und vorhandener Hauptdatei.
        picks: Je Hunk ``(Wahl, Text)`` (siehe ``apply_hunk_picks``).

    Returns:
        ``(Bytes für NotesService.resolve, Entscheidung wie „Abschnitt 1: Beide, 2: Hauptdatei“)``.

    Raises:
        ValueError: kein Merge bzw. keine Hauptdatei, oder ungültige Wahl.
    """
    if case.merge is None or case.main_bytes is None:
        raise ValueError("Dieser Konflikt hat keine Abschnitte")
    lines = apply_hunk_picks(case.merge, picks)
    names = dict(HUNK_PICK_LABELS)
    decision = "Abschnitt " + ", ".join(f"{i}: {names[pick]}" for i, (pick, _text) in enumerate(picks, 1))
    return render(lines, case.main_bytes), decision
