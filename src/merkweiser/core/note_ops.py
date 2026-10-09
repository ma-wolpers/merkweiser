"""Notiz-Operationen: anhängen, Rohtext ersetzen, löschen (reine Planung).

* ``append_note``: neue Notiz ans Dateiende, Trenner mit Leerzeile davor und
  danach (FORMAT.md). Eine leere Datei bzw. eine Datei nur mit Frontmatter
  bekommt die Notiz ohne Trenner.
* ``replace_note_text``: ersetzt genau den Inhalt einer Notiz. Die alte Notiz
  wird nur gefunden, wenn ihre Inhaltszeilen **genau einmal** vorkommen **und**
  im aktuellen Parse genau den Inhalt einer Notiz bilden. Sonst
  ``NoteNotFoundError``; der Aufrufer legt dann eine eigene Konfliktdatei an,
  weil getippter Text nie verloren gehen darf (PLAN.md).
* ``delete_note``: entfernt die Notiz und genau einen angrenzenden Trenner,
  räumt nur Leerzeilen an der Naht auf.
"""

from __future__ import annotations

from .document import Document
from .patch import LineEdit, StaleTargetError, UnsupportedEncodingError, apply_edits
from .source import Line, SourceText, split_lines


class NoteNotFoundError(StaleTargetError):
    """Die ursprüngliche Notiz ist nicht mehr eindeutig als Notiz auffindbar."""


def append_note(doc: Document, text: str) -> bytes:
    """Hängt eine neue Notiz an das Dateiende an.

    Alle Zeilen bis zur letzten Inhaltszeile bleiben byte-genau erhalten
    (fehlt dieser Zeile das Zeilenende, bekommt sie eines). Leerzeilen am
    Dateiende werden durch den Block „Leerzeile, ``---``, Leerzeile, Notiz“
    ersetzt; jede neue Zeile endet mit dem dominanten Zeilenende.

    Args:
        doc: Aktuelles Dokument (auch leer oder nur Frontmatter).
        text: Notizinhalt; Zeilen durch ``\n`` getrennt, Leerzeilen am Rand
            werden entfernt.

    Returns:
        Neue Bytes.

    Raises:
        UnsupportedEncodingError: Datei ist schreibgeschützt (Encoding).
        ValueError: leerer Text.
    """
    if not doc.source.writable:
        raise UnsupportedEncodingError("Datei ist schreibgeschützt (Encoding)")
    new = _content_lines(text)
    lines = doc.source.lines
    eol = doc.source.dominant_eol()
    body_start = doc.layout.frontmatter.end if doc.layout.frontmatter else 0
    content_nos = [line.no for line in lines[body_start:] if not line.is_blank]
    keep_until = content_nos[-1] + 1 if content_nos else body_start
    kept = list(lines[:keep_until])
    if kept and kept[-1].eol == "":
        kept[-1] = Line(kept[-1].no, kept[-1].text, eol)
    block = (("", "---", "") if content_nos else ()) + new
    rebuilt = "".join(line.text + line.eol for line in kept) + "".join(b + eol for b in block)
    return SourceText(doc.source.raw, doc.source.encoding, split_lines(rebuilt)).to_bytes()


def replace_note_text(doc: Document, original: tuple[str, ...], text: str) -> bytes:
    """Ersetzt den Inhalt einer Notiz durch bearbeiteten Rohtext.

    Args:
        doc: Aktuelles Dokument.
        original: Inhaltszeilen der Notiz zum Planungszeitpunkt.
        text: Neuer Inhalt (Zeilen durch ``\\n`` getrennt).

    Returns:
        Neue Bytes; außerhalb des Notizinhalts bleibt alles unverändert.

    Raises:
        NoteNotFoundError: Notiz nicht eindeutig als ganze Notiz auffindbar.
        ValueError: leerer Text (zum Löschen gibt es ``delete_note``).
    """
    note = _find_note(doc, original)
    assert note.content is not None
    return apply_edits(doc.source, [LineEdit(note.content.start, note.content.end, _content_lines(text))])


def delete_note(doc: Document, original: tuple[str, ...]) -> bytes:
    """Löscht eine Notiz samt genau einem angrenzenden Trenner.

    Bevorzugt wird der Trenner davor; bei der ersten Notiz der danach. Leerzeilen
    an der entstehenden Naht werden auf die der verbleibenden Nachbarn reduziert.

    Args:
        doc: Aktuelles Dokument.
        original: Inhaltszeilen der zu löschenden Notiz.

    Returns:
        Neue Bytes.

    Raises:
        NoteNotFoundError: Notiz nicht eindeutig auffindbar.
    """
    note = _find_note(doc, original)
    separators = doc.layout.separators
    before = [s for s in separators if s < note.span.start]
    after = [s for s in separators if s >= note.span.end]
    if before:
        start, end = before[-1], note.span.end
        if not after:  # letzte Notiz: Leerzeilen davor gehören jetzt zum Dateiende
            while start > 0 and doc.source.lines[start - 1].is_blank:
                start -= 1
    elif after:
        start, end = note.span.start, after[0] + 1
        while end < len(doc.source.lines) and doc.source.lines[end].is_blank:
            end += 1
    else:
        start, end = note.span.start, note.span.end
    return apply_edits(doc.source, [LineEdit(start, end, ())])


def _find_note(doc: Document, original: tuple[str, ...]):
    """Löst eine Notiz über ihre Inhaltszeilen auf (eindeutig und als ganze Notiz).

    Args:
        doc: Aktuelles Dokument.
        original: Inhaltszeilen zum Planungszeitpunkt.

    Returns:
        Die passende ``NoteSpan``.

    Raises:
        NoteNotFoundError: kein oder mehrere Vorkommen, oder das Vorkommen ist
            nicht (mehr) genau der Inhalt einer Notiz.
    """
    texts = [line.text for line in doc.source.lines]
    size = len(original)
    hits = [i for i in range(len(texts) - size + 1) if tuple(texts[i:i + size]) == original] if size else []
    if len(hits) != 1:
        raise NoteNotFoundError(f"Notiz {len(hits)}-mal gefunden")
    for parsed in doc.notes:
        content = parsed.note.content
        if content and (content.start, content.end) == (hits[0], hits[0] + size):
            return parsed.note
    raise NoteNotFoundError("Notizgrenzen haben sich verändert")


def _content_lines(text: str) -> tuple[str, ...]:
    """Zerlegt Text in Zeilen ohne Leerzeilen am Rand.

    Args:
        text: Eingabe (``\\n``, ``\\r\\n`` oder ``\\r``).

    Returns:
        Zeilen ohne Zeilenende.

    Raises:
        ValueError: wenn nichts übrig bleibt.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise ValueError("leerer Notiztext")
    return tuple(lines)
