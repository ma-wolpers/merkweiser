"""Rückwärts-diff3 für „Rückgängig“ (PLAN-SPAETERE-SCHRITTE.md S4, Y6, Y9) – rein, ohne Dateizugriff.

* Inhalt: ``merge3(base=after, a=aktuell, b=before)``; eine fehlende Datei
  zählt nur **intern** als leer.
* Existenz (diff3 auf einem Wahrheitswert): ``ex = exists(before)``, falls
  ``exists(aktuell) == exists(after)``, sonst ``exists(aktuell)``.
* ``merge_is_safe``: direkt schreiben nur bei sauberem Ergebnis **und** leerer
  Verstoßliste von ``verify``.
* YAML-Kopf (Y7): Hat eine Fassung ein Frontmatter, werden Kopf und Rumpf
  getrennt zurückgerechnet; der Kopf per ``merge_frontmatter(reverse=True)``
  (diff3 je Schlüssel bzw. Stempel-Datensatz, **ohne** Maximum). Jeder
  Kopf-Konflikt oder ein Kopf ohne schließendes ``---`` → Konfliktdatei; so
  überschreibt Rückgängig nie still jüngere Zeitwerte, Stempel oder fremde
  Eigenschaften.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conflicts import merge_is_safe, render
from .merge.diff3 import merge3
from .merge.frontmatter import OPEN, merge_frontmatter, split
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
    (h_base, base), (h_a, a), (h_b, b) = (split(x or b"") for x in (after, current, before))
    head: tuple[str, ...] = ()
    if OPEN in (h_base.state, h_a.state, h_b.state):
        return UndoPlan("konflikt")
    if h_base.lines or h_a.lines or h_b.lines:
        fm = merge_frontmatter(h_a, h_b, h_base, reverse=True)
        if fm.conflicts:
            return UndoPlan("konflikt")
        head = fm.resolve()
    result = merge3(base, a, b)
    if not merge_is_safe(result, a, b, base):
        return UndoPlan("konflikt")
    merged = tuple(head) + tuple(result.lines())
    exists = (before is not None) if (current is not None) == (after is not None) else (current is not None)
    if not exists:
        if merged:
            return UndoPlan("konflikt")
        return UndoPlan("entfernen") if current is not None else UndoPlan("nichts")
    data = render(merged, like=current or before or after or b"")
    if current is not None and data == current:
        return UndoPlan("nichts")
    return UndoPlan("schreiben", data)
