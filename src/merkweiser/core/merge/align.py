"""Ausrichtung von 2 oder 3 Zeilenfolgen mit eindeutigen Ankern (Patience-Prinzip).

Regeln (PLAN.md, „Merge“):

* **Anker** sind nur Zeilen, die im betrachteten Bereich in **jeder** Folge
  genau einmal vorkommen und nicht leer sind. Leerzeilen und wiederholte
  Zeilen (z. B. zwei identische Todos) verankern nie allein. Unter mehreren
  Ankern wird die längste in allen Folgen aufsteigende Kette gewählt.
* Zwischen Ankern wird rekursiv weiter verankert (Eindeutigkeit dann bezogen
  auf den Teilbereich).
* Gleiche Zeilen unmittelbar am Rand eines Bereichs (gemeinsamer Anfang bzw.
  gemeinsames Ende in allen Folgen) gelten ebenfalls als synchron. Das ordnet
  z. B. Leerzeilen neben einem Anker positionsgenau zu.
* Alles Übrige bildet **Lücken** (Änderungsregionen). Benachbarte Lücken
  ohne Synchronzeile dazwischen sind per Konstruktion eine einzige Region.

Die Funktion ist deterministisch; ``verify`` berechnet die Ausrichtung zur
Prüfung der Anker-Zertifikate selbst neu.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

Range = tuple[int, int]


@dataclass(frozen=True)
class Region:
    """Abschnitt der Ausrichtung.

    Attributes:
        sync: ``True`` für eine Synchronzeile (in allen Folgen gleich), sonst Lücke.
        ranges: Je Folge der Bereich ``[start, end)``; bei ``sync`` jeweils Länge 1.
    """

    sync: bool
    ranges: tuple[Range, ...]


def align(seqs: Sequence[Sequence[str]]) -> tuple[Region, ...]:
    """Richtet 2 oder 3 Zeilenfolgen aus.

    Args:
        seqs: Die Folgen (z. B. ``[A, B]`` oder ``[Basis, A, B]``).

    Returns:
        Synchronzeilen und Lücken in Reihenfolge; deckt jede Folge lückenlos ab.
    """
    out: list[Region] = []
    _align(seqs, tuple((0, len(s)) for s in seqs), out)
    return tuple(out)


def _align(seqs: Sequence[Sequence[str]], bounds: tuple[Range, ...], out: list[Region]) -> None:
    """Rekursive Ausrichtung eines Teilbereichs.

    Args:
        seqs: Alle Folgen.
        bounds: Je Folge der Teilbereich.
        out: Ergebnisliste (wird erweitert).
    """
    starts = [b[0] for b in bounds]
    ends = [b[1] for b in bounds]
    while all(s < e for s, e in zip(starts, ends)) and _equal_at(seqs, starts):
        out.append(Region(True, tuple((s, s + 1) for s in starts)))
        starts = [s + 1 for s in starts]
    tail: list[Region] = []
    while all(s < e for s, e in zip(starts, ends)) and _equal_at(seqs, [e - 1 for e in ends]):
        ends = [e - 1 for e in ends]
        tail.append(Region(True, tuple((e, e + 1) for e in ends)))
    anchors = _anchor_chain(seqs, tuple(zip(starts, ends)))
    cursor = list(starts)
    for anchor in anchors:
        _align(seqs, tuple(zip(cursor, anchor)), out)
        out.append(Region(True, tuple((p, p + 1) for p in anchor)))
        cursor = [p + 1 for p in anchor]
    if anchors:
        _align(seqs, tuple(zip(cursor, ends)), out)
    elif any(s < e for s, e in zip(starts, ends)):
        out.append(Region(False, tuple(zip(starts, ends))))
    out.extend(reversed(tail))


def _equal_at(seqs: Sequence[Sequence[str]], positions: Sequence[int]) -> bool:
    """``True``, wenn alle Folgen an den Positionen dieselbe Zeile haben."""
    first = seqs[0][positions[0]]
    return all(seq[pos] == first for seq, pos in zip(seqs, positions))


def _anchor_chain(seqs: Sequence[Sequence[str]], bounds: tuple[Range, ...]) -> list[tuple[int, ...]]:
    """Bestimmt die längste aufsteigende Kette eindeutiger Anker im Teilbereich.

    Args:
        seqs: Alle Folgen.
        bounds: Je Folge der Teilbereich.

    Returns:
        Anker als Positionstupel (eine Position je Folge), aufsteigend.
    """
    counts = [Counter(seq[s:e]) for seq, (s, e) in zip(seqs, bounds)]
    unique = {line for line, n in counts[0].items() if n == 1 and line.strip()
              and all(c.get(line) == 1 for c in counts[1:])}
    if not unique:
        return []
    positions = [{seq[i]: i for i in range(s, e) if seq[i] in unique} for seq, (s, e) in zip(seqs, bounds)]
    candidates = sorted(tuple(p[line] for p in positions) for line in unique)
    best: list[int] = [1] * len(candidates)
    prev: list[int] = [-1] * len(candidates)
    for i, cand in enumerate(candidates):
        for j in range(i):
            if all(a < b for a, b in zip(candidates[j], cand)) and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(len(candidates)), key=lambda k: (best[k], -k))
    chain = []
    while i != -1:
        chain.append(candidates[i])
        i = prev[i]
    return list(reversed(chain))
