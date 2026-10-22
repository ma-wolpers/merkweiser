"""Rückwärts-diff3 für „Rückgängig“ (PLAN-SPAETERE-SCHRITTE.md S4, Y6, Y9) – rein, ohne Dateizugriff.

* Inhalt: ``merge3(base=after, a=aktuell, b=before)``; eine fehlende Datei
  zählt nur **intern** als leer.
* Existenz (diff3 auf einem Wahrheitswert): ``ex = exists(before)``, falls
  ``exists(aktuell) == exists(after)``, sonst ``exists(aktuell)``.
* ``merge_is_safe``: direkt schreiben nur bei sauberem Ergebnis **und** leerer
  Verstoßliste von ``verify``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conflicts import render
from .merge.diff3 import merge3
from .merge.model import MergeResult
from .merge.verify import verify
from .source import SourceText


@dataclass(frozen=True)
class UndoPlan:
    """Ergebnis der Rückwärts-Zusammenführung (rein, ohne Dateizugriff).

    Attributes:
        action: ``schreiben``, ``entfernen``, ``nichts`` oder ``konflikt``.
        data: Neue Bytes bei ``schreiben``.
    """

    action: str
    data: bytes | None = None


def merge_is_safe(result: MergeResult, a: list[str], b: list[str], base: list[str]) -> bool:
    """Eindeutige Sicherheitsentscheidung (Y9): direkt schreiben nur, wenn sauber **und** ``verify`` leer ist.

    ``verify`` liefert die Liste der Verstöße; eine leere Liste heißt bestanden.
    """
    return result.clean and verify(result, a, b, base) == []


def plan_undo(before: bytes | None, after: bytes | None, current: bytes | None) -> UndoPlan:
    """Rückwärts-diff3 mit Existenz-Regel (S4), ohne Dateizugriff.

    Args:
        before: Stand vor der Änderung (``None``: Datei fehlte).
        after: Stand nach der Änderung (``None``: Datei wurde gelöscht).
        current: Aktueller Stand (``None``: Datei fehlt jetzt).

    Returns:
        Was zu tun ist.
    """
    texts = [SourceText.from_bytes(x or b"") for x in (after, current, before)]
    if not all(t.writable for t in texts):
        return UndoPlan("konflikt")
    base, a, b = ([line.text for line in t.lines] for t in texts)
    result = merge3(base, a, b)
    if not merge_is_safe(result, a, b, base):
        return UndoPlan("konflikt")
    merged = result.lines()
    exists = (before is not None) if (current is not None) == (after is not None) else (current is not None)
    if not exists:
        if merged:
            return UndoPlan("konflikt")
        return UndoPlan("entfernen") if current is not None else UndoPlan("nichts")
    data = render(merged, like=current or before or after or b"")
    if current is not None and data == current:
        return UndoPlan("nichts")
    return UndoPlan("schreiben", data)
