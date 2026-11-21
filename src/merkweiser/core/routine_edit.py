"""Minimale Zeilen-Edits auf ``Routinen.md`` für den Formular-Editor (W9): rein.

Wie bei allen Edits in Merkweiser: frisch gelesenes ``Document`` rein, neue
Bytes raus; Regeln werden über ``patch.Target`` (Zeile + erwarteter Text)
adressiert, nie über IDs. Es ändern sich nur die betroffenen Zeilen;
Doku-Block, Frontmatter, Zeilenenden und fremde Abschnitte bleiben
byte-genau.

* Eine neue Regel kommt ans Ende des **ersten** Abschnitts mit gleichem
  Rhythmus, gleichen Optionen und gleichen Tags (verglichen wird das
  Gelesene, nicht der Text – ``## Wöchentlich mo`` passt also zu
  ``wöchentlich Mo``). Gibt es keinen, entsteht ein Abschnitt mit
  kanonischer Überschrift vor ``## Pausen`` bzw. am Dateiende.
* Wird ein Abschnitt durch Löschen oder Ändern leer, verschwindet er samt
  einer angrenzenden Leerzeile.
"""

from __future__ import annotations

from datetime import date

from .document import Document, parse_document
from .note_ops import append_note
from .patch import LineEdit, Target, apply_edits, resolve_line
from .rhythm import Options, Rhythm, options_text, rhythm_text
from .routines import DEFAULT_TEXT, HEADING, PAUSES_HEADING, RoutineFile, Section, parse_routines, pause_text


def heading_line(rhythm: Rhythm, options: Options, tags: tuple[str, ...] = ()) -> str:
    """Kanonische Überschrift: ``## rhythmus #tags (optionen)``.

    Args:
        rhythm: Rhythmus.
        options: Optionen.
        tags: Vererbte Tags ohne ``#``.

    Returns:
        Die Überschriftzeile.
    """
    opts = options_text(options)
    return HEADING + rhythm_text(rhythm) + "".join(f" #{tag}" for tag in tags) + (f" ({opts})" if opts else "")


def rule_line(body: str, active: bool = True) -> str:
    """Regelzeile: ``- [ ] body`` (aktiv) bzw. ``- [x] body`` (pausiert)."""
    return f"- [{' ' if active else 'x'}] {body.strip()}"


def new_file() -> bytes:
    """Inhalt einer neuen ``Routinen.md`` (nur der Doku-Block)."""
    return DEFAULT_TEXT.encode("utf-8")


def add_rule(doc: Document, rhythm: Rhythm, options: Options, tags: tuple[str, ...], line: str) -> bytes:
    """Fügt eine Regelzeile in den passenden Abschnitt ein (siehe Moduldoku).

    Args:
        doc: Aktuelle ``Routinen.md`` (leer → mit Doku-Block anlegen).
        rhythm: Rhythmus.
        options: Optionen.
        tags: Tags der Überschrift.
        line: Fertige Regelzeile (``rule_line``).

    Returns:
        Neue Bytes.
    """
    if not doc.source.lines or not doc.source.to_bytes().strip():
        doc = parse_document(new_file())
    rf = parse_routines(doc)
    section = next((s for s in rf.sections if _same_heading(s, rhythm, options, tags)), None)
    if section is not None:
        end = (section.items[-1].line_no if section.items else section.line_no) + 1
        return apply_edits(doc.source, [LineEdit(end, end, (line,))])
    block = (heading_line(rhythm, options, tags), line)
    if rf.pauses_line is not None:
        return apply_edits(doc.source, [LineEdit(rf.pauses_line, rf.pauses_line, (*block, ""))])
    return append_note(doc, "\n".join(block))


def update_rule(doc: Document, target: Target, rhythm: Rhythm, options: Options, tags: tuple[str, ...],
                line: str) -> bytes:
    """Ändert eine Regel; bei anderem Rhythmus, Optionen oder Tags wandert sie in den passenden Abschnitt.

    Args:
        doc: Aktuelle ``Routinen.md``.
        target: Die bisherige Regelzeile.
        rhythm: Neuer Rhythmus.
        options: Neue Optionen.
        tags: Neue Tags der Überschrift.
        line: Neue Regelzeile.

    Returns:
        Neue Bytes.

    Raises:
        StaleTargetError: Regel nicht mehr eindeutig auffindbar.
    """
    line_no = resolve_line(doc.source, target)
    section = _section_of(parse_routines(doc), line_no)
    if section is not None and _same_heading(section, rhythm, options, tags):
        return apply_edits(doc.source, [LineEdit(line_no, line_no + 1, (line,))])
    return add_rule(parse_document(delete_rule(doc, target)), rhythm, options, tags, line)


def delete_rule(doc: Document, target: Target) -> bytes:
    """Entfernt eine Regel; ein dadurch leerer Abschnitt verschwindet samt einer angrenzenden Leerzeile.

    Raises:
        StaleTargetError: Regel nicht mehr eindeutig auffindbar.
    """
    line_no = resolve_line(doc.source, target)
    section = _section_of(parse_routines(doc), line_no)
    if section is None or len(section.items) > 1:
        return apply_edits(doc.source, [LineEdit(line_no, line_no + 1, ())])
    return apply_edits(doc.source, [_without_gap(doc, section.line_no, line_no + 1)])


def add_pause(doc: Document, start: date, end: date) -> bytes:
    """Fügt eine Pause an (``## Pausen`` entsteht bei Bedarf am Dateiende).

    Args:
        doc: Aktuelle ``Routinen.md``.
        start: Erster Tag.
        end: Letzter Tag (gleich ``start`` für einen einzelnen Tag).

    Returns:
        Neue Bytes.

    Raises:
        ValueError: ``end`` vor ``start``.
    """
    if end < start:
        raise ValueError("Pause endet vor ihrem Beginn")
    line = f"- {pause_text(start, end)}"
    if not doc.source.lines or not doc.source.to_bytes().strip():
        doc = parse_document(new_file())
    rf = parse_routines(doc)
    if rf.pauses_line is None:
        return append_note(doc, f"{HEADING}{PAUSES_HEADING}\n{line}")
    last = max([p.line_no for p in rf.pauses] + [rf.pauses_line]) + 1
    return apply_edits(doc.source, [LineEdit(last, last, (line,))])


def delete_line(doc: Document, target: Target) -> bytes:
    """Entfernt eine einzelne Zeile (z. B. eine Pause).

    Raises:
        StaleTargetError: Zeile nicht mehr eindeutig auffindbar.
    """
    line_no = resolve_line(doc.source, target)
    return apply_edits(doc.source, [LineEdit(line_no, line_no + 1, ())])


def replace_all(doc: Document, text: str) -> bytes:
    """Ersetzt den ganzen Inhalt (Rohtext-Editor); Zeilenende-Stil, BOM und Schluss-Umbruch bleiben.

    Args:
        doc: Aktuelle ``Routinen.md``.
        text: Neuer Text (Zeilenenden beliebig).

    Returns:
        Neue Bytes.
    """
    lines = tuple(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    if lines and lines[-1] == "" and len(lines) > 1:
        lines = lines[:-1]
    return apply_edits(doc.source, [LineEdit(0, len(doc.source.lines), lines)])


def _same_heading(section: Section, rhythm: Rhythm, options: Options, tags: tuple[str, ...]) -> bool:
    """Gleicher Rhythmus, gleiche Optionen und gleiche Tags (ohne Groß-/Kleinschreibung, Reihenfolge egal)."""
    return (section.rhythm, section.options) == (rhythm, options) \
        and sorted(t.casefold() for t in section.tags) == sorted(t.casefold() for t in tags)


def _section_of(rf: RoutineFile, line_no: int) -> Section | None:
    """Abschnitt, zu dem eine Regelzeile gehört."""
    return next((s for s in rf.sections if any(i.line_no == line_no for i in s.items)), None)


def _without_gap(doc: Document, first: int, end: int) -> LineEdit:
    """Entfernt ``[first, end)`` samt einer angrenzenden Leerzeile (danach bevorzugt, sonst davor)."""
    lines = doc.source.lines
    if end < len(lines) and not lines[end].text.strip():
        return LineEdit(first, end + 1, ())
    if first > 0 and not lines[first - 1].text.strip():
        return LineEdit(first - 1, end, ())
    return LineEdit(first, end, ())
