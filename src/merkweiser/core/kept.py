"""Abschlussprüfung: Ist Merkweisers Änderung in der Datei noch erhalten? (Befund S4, 2026-10-21)

Nach dem Installieren von ``N`` darf ein externer Schreiber (z. B. Obsidian)
die Datei ``P`` weiter bearbeiten. Eine Konfliktdatei ist nur nötig, wenn dabei
**Merkweisers Änderung** verloren ging, nicht schon, wenn ``P`` von ``N``
abweicht. Typischer Fall aus S4 Teil E: Merkweiser liest ``ddd`` und hängt ein
Todo an; Obsidian tippt in derselben Zeile weiter (``dddddd``). ``N`` steht
dann nicht mehr wörtlich in ``P``, die Änderung (das Todo) aber schon.

Geprüft wird zeilenweise ohne Zeilenende (LF/CRLF zählt nicht):

* ``change_kept(current, expected, new)``: Für jede Änderung ``E → N``
  (``difflib``) müssen hinzugefügte bzw. ersetzende Zeilen als zusammenhängender
  Block in ``P`` mindestens so oft vorkommen wie in ``N``; bei reinen Löschungen
  darf der gelöschte Block in ``P`` höchstens so oft vorkommen wie in ``N``. Das
  Zählen verhindert, dass eine verlorene Änderung übersehen wird, nur weil eine
  gleiche Zeile zufällig schon existiert (z. B. zwei identische Todos).
* ``contains_all_lines(outer, inner)``: Rückfall ohne bekannten Ausgangsstand
  (Create-only): alle Zeilen von ``N`` in derselben Reihenfolge in ``P``.
"""

from __future__ import annotations

import difflib

from .source import SourceText


def change_kept(current: bytes, expected: bytes | None, new: bytes) -> bool:
    """``True``, wenn Merkweisers Änderung ``expected → new`` in ``current`` erhalten ist.

    Args:
        current: Aktueller Inhalt von ``P``.
        expected: Ausgangsstand ``E`` oder ``None`` (Create-only: dann
            ``contains_all_lines``).
        new: ``N``.

    Returns:
        Ob keine Zeile der Änderung fehlt bzw. keine Löschung zurückgekehrt ist.
    """
    if current == new:
        return True
    if expected is None:
        return contains_all_lines(current, new)
    base, ours, theirs = _texts(expected), _texts(new), _texts(current)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=base, b=ours, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        added, removed = ours[j1:j2], base[i1:i2]
        if added and _count(theirs, added) < _count(ours, added):
            return False
        if not added and _count(theirs, removed) > _count(ours, removed):
            return False
    return True


def contains_all_lines(outer: bytes, inner: bytes) -> bool:
    """``True``, wenn alle Zeilen von ``inner`` in derselben Reihenfolge in ``outer`` vorkommen.

    Args:
        outer: Aktueller Inhalt von ``P``.
        inner: ``N``.

    Returns:
        Ob ``inner`` als Zeilen-Teilfolge in ``outer`` steckt (Einschübe erlaubt).
    """
    remaining = iter(_texts(outer))
    return all(any(candidate == wanted for candidate in remaining) for wanted in _texts(inner))


def _texts(raw: bytes) -> list[str]:
    """Zeilentexte ohne Zeilenende.

    Args:
        raw: Dateiinhalt.

    Returns:
        Eine Zeichenkette je Zeile.
    """
    return [line.text for line in SourceText.from_bytes(raw).lines]


def _count(lines: list[str], block: list[str]) -> int:
    """Anzahl der (auch überlappenden) Vorkommen eines zusammenhängenden Zeilenblocks.

    Args:
        lines: Zeilen der Datei.
        block: Gesuchter Block (nicht leer).

    Returns:
        Anzahl der Startpositionen, an denen der Block vollständig steht.
    """
    size = len(block)
    return sum(1 for start in range(len(lines) - size + 1) if lines[start:start + size] == block)
