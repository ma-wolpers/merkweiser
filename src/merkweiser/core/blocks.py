"""Grobstruktur einer Datei: Frontmatter, Codeblöcke, Trenner, Notiz-Spannen.

Zweite Stufe der Parser-Pipeline (``Datei → SourceText → Blocks → …``) und
**alleinige Instanz für Notizgrenzen**: Spätere Stufen (``outline``) erhalten
fertige Notiz-Spannen und entscheiden nie selbst, wo eine Notiz beginnt.

Regeln (verbindlich in ``docs/FORMAT.md``):

* Frontmatter: nur wenn Zeile 0 genau ``---`` ist **und** später eine Zeile
  ``---`` oder ``...`` folgt. Ein nicht geschlossener Block ist kein
  Frontmatter (GRENZE: dann gilt die erste Zeile als Trenner am Notizanfang).
* Codeblock: ≥3 Backticks oder Tilden; geschlossen nur durch dasselbe Zeichen
  in mindestens derselben Anzahl, danach nur Leerraum. Nicht geschlossen →
  bis Dateiende. Inhalt ist opak.
* Trenner: Zeile, deren Inhalt ohne Leerraum genau ``---`` ist, außerhalb von
  Code (auch direkt unter Text; Setext-Überschriften gibt es nicht).
* Notiz: zusammenhängender Lauf von Zeilen ohne Leerzeile und ohne Trenner.
  **Jede** Leerzeile außerhalb von Code beendet eine Notiz (Formatänderung
  vom 2026-10-21); Leerzeilen in Codeblöcken trennen nicht.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .source import Line

_FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")


@dataclass(frozen=True)
class Span:
    """Halboffener Zeilenbereich ``[start, end)``.

    Attributes:
        start: Erste Zeile (inklusive).
        end: Zeile hinter der letzten (exklusive).
    """

    start: int
    end: int

    def __contains__(self, line_no: object) -> bool:
        """``True``, wenn ``line_no`` im Bereich liegt."""
        return isinstance(line_no, int) and self.start <= line_no < self.end

    def __len__(self) -> int:
        """Anzahl der Zeilen im Bereich."""
        return max(0, self.end - self.start)


@dataclass(frozen=True)
class NoteSpan:
    """Eine Notiz innerhalb einer Datei.

    Seit der Formatänderung vom 2026-10-21 enthält eine Notiz nie Leerzeilen
    am Rand; ``span`` und ``content`` sind deshalb gleich. Beide bleiben, damit
    Aufrufer zwischen „Bereich“ und „Inhalt“ nicht unterscheiden müssen.

    Attributes:
        span: Die Zeilen der Notiz.
        content: Derselbe Bereich (nie ``None``; leere Notizen gibt es nicht mehr).
    """

    span: Span
    content: Span | None

    @property
    def is_empty(self) -> bool:
        """``True``, wenn die Notiz keinen Inhalt hat (wird nicht angezeigt)."""
        return self.content is None


@dataclass(frozen=True)
class FileLayout:
    """Ergebnis der Block-Erkennung einer Datei.

    Attributes:
        frontmatter: Zeilen des Frontmatters inklusive beider Begrenzer, oder ``None``.
        fences: Codeblöcke inklusive Begrenzungszeilen.
        separators: Zeilenindizes der Trenner ``---``.
        notes: Notizen in Dateireihenfolge (keine bei leerer Datei).
    """

    frontmatter: Span | None
    fences: tuple[Span, ...]
    separators: tuple[int, ...]
    notes: tuple[NoteSpan, ...]

    def in_code(self, line_no: int) -> bool:
        """Gibt an, ob eine Zeile zu einem Codeblock gehört.

        Args:
            line_no: Zeilenindex.

        Returns:
            ``True`` für Zeilen innerhalb eines Codeblocks (inklusive Fences).
        """
        return any(line_no in fence for fence in self.fences)


def analyze(lines: tuple[Line, ...]) -> FileLayout:
    """Zerlegt die Zeilen einer Datei in Frontmatter, Codeblöcke und Notizen.

    Args:
        lines: Zeilen aus ``SourceText.lines``.

    Returns:
        Das Layout der Datei.
    """
    frontmatter = _find_frontmatter(lines)
    body_start = frontmatter.end if frontmatter else 0
    fences = _find_fences(lines, body_start)
    code_lines = {no for fence in fences for no in range(fence.start, fence.end)}
    separators = tuple(line.no for line in lines[body_start:]
                       if line.no not in code_lines and line.text.strip() == "---")
    breaks = set(separators) | {line.no for line in lines[body_start:] if line.is_blank and line.no not in code_lines}
    notes = _note_spans(len(lines), body_start, breaks)
    return FileLayout(frontmatter, tuple(fences), separators, notes)


def _find_frontmatter(lines: tuple[Line, ...]) -> Span | None:
    """Sucht einen geschlossenen Frontmatter-Block ab Zeile 0.

    Args:
        lines: Alle Zeilen.

    Returns:
        Bereich inklusive Begrenzer oder ``None``.
    """
    if not lines or lines[0].text.rstrip() != "---":
        return None
    for line in lines[1:]:
        if line.text.rstrip() in ("---", "..."):
            return Span(0, line.no + 1)
    return None


def _find_fences(lines: tuple[Line, ...], start: int) -> list[Span]:
    """Findet alle Codeblöcke ab ``start``.

    Args:
        lines: Alle Zeilen.
        start: Erste zu prüfende Zeile (hinter dem Frontmatter).

    Returns:
        Codeblöcke inklusive öffnender und schließender Zeile.
    """
    fences: list[Span] = []
    no = start
    while no < len(lines):
        opening = _FENCE_OPEN_RE.match(lines[no].text)
        if opening is None or (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            no += 1
            continue
        char, length = opening.group(1)[0], len(opening.group(1))
        close = _find_fence_close(lines, no + 1, char, length)
        fences.append(Span(no, close + 1 if close is not None else len(lines)))
        no = close + 1 if close is not None else len(lines)
    return fences


def _find_fence_close(lines: tuple[Line, ...], start: int, char: str, length: int) -> int | None:
    """Sucht die schließende Fence-Zeile.

    Args:
        lines: Alle Zeilen.
        start: Erste Zeile nach der öffnenden Fence.
        char: Fence-Zeichen (Backtick oder Tilde).
        length: Länge der öffnenden Fence.

    Returns:
        Index der schließenden Zeile oder ``None``, wenn der Block offen bleibt.
    """
    pattern = re.compile(r"^[ \t]*" + re.escape(char) + "{" + str(length) + r",}[ \t]*$")
    for line in lines[start:]:
        if pattern.match(line.text):
            return line.no
    return None


def _note_spans(count: int, body_start: int, breaks: set[int]) -> tuple[NoteSpan, ...]:
    """Bildet die Notizen als Läufe von Zeilen zwischen Notiz-Enden.

    Args:
        count: Anzahl der Zeilen der Datei.
        body_start: Erste Zeile nach dem Frontmatter.
        breaks: Zeilen, die eine Notiz beenden (Leerzeilen außerhalb von Code, Trenner).

    Returns:
        Eine Notiz je zusammenhängendem Lauf, in Dateireihenfolge.
    """
    notes: list[NoteSpan] = []
    start: int | None = None
    for no in range(body_start, count + 1):
        if no < count and no not in breaks:
            start = no if start is None else start
            continue
        if start is not None:
            span = Span(start, no)
            notes.append(NoteSpan(span, span))
            start = None
    return tuple(notes)
