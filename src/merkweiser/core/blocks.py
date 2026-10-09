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
  Code, direkt nach einer Leerzeile oder am Notizanfang.
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

    Attributes:
        span: Alle Zeilen zwischen den Trennern, inklusive Leerzeilen am Rand.
        content: Der Bereich ohne Leerzeilen am Rand; ``None`` bei leerer Notiz.
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
        separators: Zeilenindizes der Notiz-Trenner.
        notes: Notizen in Dateireihenfolge (mindestens eine, ggf. leer).
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
    separators: list[int] = []
    note_start = body_start
    for line in lines[body_start:]:
        if line.no in code_lines or line.text.strip() != "---":
            continue
        at_note_start = line.no == note_start
        after_blank = line.no > 0 and lines[line.no - 1].is_blank and (line.no - 1) not in code_lines
        if at_note_start or after_blank:
            separators.append(line.no)
            note_start = line.no + 1
    notes = _note_spans(lines, body_start, separators)
    return FileLayout(frontmatter, tuple(fences), tuple(separators), notes)


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


def _note_spans(lines: tuple[Line, ...], body_start: int, separators: list[int]) -> tuple[NoteSpan, ...]:
    """Bildet die Notiz-Spannen zwischen den Trennern.

    Args:
        lines: Alle Zeilen.
        body_start: Erste Zeile nach dem Frontmatter.
        separators: Trenner-Zeilen in aufsteigender Reihenfolge.

    Returns:
        Eine Notiz pro Bereich zwischen Trennern (auch leere).
    """
    bounds = [body_start - 1, *separators, len(lines)]
    notes = []
    for before, after in zip(bounds, bounds[1:]):
        span = Span(before + 1, after)
        content_lines = [no for no in range(span.start, span.end) if not lines[no].is_blank]
        content = Span(content_lines[0], content_lines[-1] + 1) if content_lines else None
        notes.append(NoteSpan(span, content))
    return tuple(notes)
