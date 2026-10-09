"""Datenmodell des Merges: Vorkommen, Zertifikate, Segmente, Hunks und R1/R2.

Jede Ausgabezeile eines Merges trägt eine **Zuordnung** zu den Eingabe-
Vorkommen, aus denen sie stammt, plus ein **Zertifikat**, das begründet,
warum diese Zuordnung zulässig ist. ``verify`` prüft beides unabhängig.

Merge-Regel „erledigt gewinnt“ (die einzige erlaubte Inhaltsersetzung ohne
Nutzeraktion):

* **R1:** Zeilenpaar unterscheidet sich **nur** im Statuszeichen ``[ ]``
  gegenüber ``[x]``/``[X]`` → die erledigte Zeile byte-genau.
* **R2:** Zeilenpaar unterscheidet sich **nur** in ``[x]`` gegenüber ``[X]``
  → die Zeile der Hauptdatei (A) byte-genau, keine Normalisierung.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..inline import parse_list_item

A, B, BASE = "A", "B", "O"


class Cert(Enum):
    """Begründung einer Zuordnung."""

    ANKER = "anker"                  # Synchronzeile der Ausrichtung
    UEBERNAHME = "uebernahme"        # Zeile stammt aus genau einer Seite
    IDENTISCH = "identisch"          # byte-gleiche Änderung beider Seiten in derselben Region
    R1 = "r1"                        # erledigt gewinnt
    R2 = "r2"                        # [x] gegen [X]: Schreibweise der Hauptdatei


@dataclass(frozen=True)
class Occ:
    """Ein Eingabe-Vorkommen: Seite (``A``, ``B``, ``O`` = Basis) und Zeilenindex."""

    side: str
    index: int


@dataclass(frozen=True)
class OutLine:
    """Eine Ausgabezeile mit Herkunft.

    Attributes:
        text: Zeileninhalt.
        sources: Die Eingabe-Vorkommen, aus denen die Zeile stammt.
        cert: Begründung.
    """

    text: str
    sources: tuple[Occ, ...]
    cert: Cert


@dataclass(frozen=True)
class Hunk:
    """Ein ungelöster Konfliktbereich (beide Seiten bleiben vollständig erhalten).

    Attributes:
        a_range: Bereich in A ``[start, end)``.
        b_range: Bereich in B.
        base_range: Bereich in der Basis oder ``None`` (2-Wege).
        a_lines: Zeilen aus A.
        b_lines: Zeilen aus B.
    """

    a_range: tuple[int, int]
    b_range: tuple[int, int]
    base_range: tuple[int, int] | None
    a_lines: tuple[str, ...]
    b_lines: tuple[str, ...]

    @property
    def offers_both(self) -> bool:
        """„Beide“ (A, dann B) nur, wenn beide Seiten nicht leer und verschieden sind."""
        return bool(self.a_lines) and bool(self.b_lines) and self.a_lines != self.b_lines


@dataclass(frozen=True)
class MergeResult:
    """Ergebnis eines Merges als Folge aus aufgelösten Zeilen und Hunks.

    Attributes:
        segments: ``OutLine`` oder ``Hunk`` in Reihenfolge.
        three_way: ``True`` für diff3 (mit Basis), ``False`` für Union.
    """

    segments: tuple[OutLine | Hunk, ...]
    three_way: bool

    @property
    def clean(self) -> bool:
        """``True``, wenn es keinen Konflikt gibt."""
        return not any(isinstance(s, Hunk) for s in self.segments)

    @property
    def hunks(self) -> tuple[Hunk, ...]:
        """Alle Konflikt-Hunks."""
        return tuple(s for s in self.segments if isinstance(s, Hunk))

    def lines(self) -> tuple[str, ...]:
        """Die Ausgabezeilen eines konfliktfreien Ergebnisses.

        Raises:
            ValueError: wenn noch Konflikte offen sind.
        """
        if not self.clean:
            raise ValueError("Merge enthält Konflikte")
        return tuple(s.text for s in self.segments if isinstance(s, OutLine))


def status_rule(a_line: str, b_line: str) -> tuple[Cert, str] | None:
    """Prüft R1/R2 für ein Zeilenpaar.

    Args:
        a_line: Zeile der Hauptdatei (A).
        b_line: Zeile der anderen Seite (B).

    Returns:
        ``(Cert.R1, erledigte Zeile)``, ``(Cert.R2, a_line)`` oder ``None``,
        wenn sich die Zeilen nicht **nur** im Statuszeichen unterscheiden.
    """
    a_item, b_item = parse_list_item(a_line), parse_list_item(b_line)
    if a_item is None or b_item is None or a_item.status_col is None or a_item.status_col != b_item.status_col:
        return None
    col = a_item.status_col
    if len(a_line) != len(b_line) or a_line[:col] + a_line[col + 1:] != b_line[:col] + b_line[col + 1:]:
        return None
    pair = {a_line[col], b_line[col]}
    if pair in ({" ", "x"}, {" ", "X"}):
        return Cert.R1, a_line if a_line[col] != " " else b_line
    if pair == {"x", "X"}:
        return Cert.R2, a_line
    return None
