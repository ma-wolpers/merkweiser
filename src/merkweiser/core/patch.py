"""Edit-Ziele ohne IDs und das verlustfreie Anwenden von Zeilen-Edits.

* ``Target``/``BlockTarget`` sind **flüchtige Adressen** (``relpath``,
  Zeilennummer, erwarteter Text), keine Identität (PLAN.md, „Edit-Ziele“).
* ``resolve_line``/``resolve_block``: steht das Ziel noch an seiner Stelle,
  ist es getroffen; sonst zählt nur ein **eindeutiges** exaktes Vorkommen.
  Kein oder mehrere Vorkommen → ``StaleTargetError``. Es wird nie geraten.
* ``apply_edits`` ersetzt Zeilenbereiche und lässt alle anderen Bytes
  unverändert (Minimal-Diff). Neue Zeilen erhalten das dominante Zeilenende;
  eine Datei ohne Schluss-Zeilenumbruch behält diesen Zustand.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .source import Line, SourceText, split_lines


class StaleTargetError(Exception):
    """Das Ziel ist im aktuellen Inhalt nicht (eindeutig) auffindbar."""


class UnsupportedEncodingError(Exception):
    """Die Datei hat kein unterstütztes Encoding und wird nie geschrieben."""


@dataclass(frozen=True)
class Target:
    """Adresse einer einzelnen Zeile.

    Attributes:
        relpath: Datei relativ zum Vault.
        line_no: Zeilenindex zum Planungszeitpunkt.
        expected_text: Erwarteter Zeileninhalt (ohne Zeilenende).
    """

    relpath: str
    line_no: int
    expected_text: str


@dataclass(frozen=True)
class BlockTarget:
    """Adresse einer zusammenhängenden Zeilenfolge (Todo mit Kindern, Notiz …).

    Attributes:
        relpath: Datei relativ zum Vault.
        first_line: Erste Zeile zum Planungszeitpunkt.
        expected_lines: Erwartete Zeileninhalte in Reihenfolge.
    """

    relpath: str
    first_line: int
    expected_lines: tuple[str, ...]


@dataclass(frozen=True)
class LineEdit:
    """Ersetzt die Zeilen ``[start, end)`` durch ``new_lines``.

    ``start == end`` fügt vor Zeile ``start`` ein; ``new_lines == ()`` löscht.

    Attributes:
        start: Erste ersetzte Zeile.
        end: Zeile hinter der letzten ersetzten.
        new_lines: Neue Zeileninhalte ohne Zeilenende.
    """

    start: int
    end: int
    new_lines: tuple[str, ...]


def resolve_line(source: SourceText, target: Target) -> int:
    """Findet die Zielzeile im aktuellen Inhalt.

    Args:
        source: Aktueller Inhalt der Datei.
        target: Die Adresse aus der Planung.

    Returns:
        Aktueller Zeilenindex.

    Raises:
        StaleTargetError: kein oder mehrere passende Zeilen.
    """
    lines = source.lines
    if 0 <= target.line_no < len(lines) and lines[target.line_no].text == target.expected_text:
        return target.line_no
    hits = [line.no for line in lines if line.text == target.expected_text]
    if len(hits) != 1:
        raise StaleTargetError(f"{target.relpath}: {len(hits)} Treffer für {target.expected_text!r}")
    return hits[0]


def resolve_block(source: SourceText, target: BlockTarget, *, unique: bool = False) -> int:
    """Findet die erste Zeile eines Blocks im aktuellen Inhalt.

    Args:
        source: Aktueller Inhalt.
        target: Blockadresse.
        unique: ``True`` verlangt **genau ein** Vorkommen in der ganzen Datei,
            auch wenn der Block noch an seiner Stelle steht. Das gilt für das
            Entfernen einer Move-Quelle (PLAN.md, Move-Protokoll Schritt 3),
            damit bei einem zweiten identischen Block nichts geraten wird.

    Returns:
        Aktueller Index der ersten Blockzeile.

    Raises:
        StaleTargetError: kein oder mehrere exakte Vorkommen der Zeilenfolge.
    """
    texts = [line.text for line in source.lines]
    want = list(target.expected_lines)
    size = len(want)
    if not unique and texts[target.first_line:target.first_line + size] == want:
        return target.first_line
    hits = [i for i in range(len(texts) - size + 1) if texts[i:i + size] == want]
    if len(hits) != 1:
        raise StaleTargetError(f"{target.relpath}: Block {len(hits)}-mal gefunden")
    return hits[0]


def apply_edits(source: SourceText, edits: Sequence[LineEdit]) -> bytes:
    """Wendet nicht überlappende Zeilen-Edits an und serialisiert.

    Args:
        source: Ausgangsinhalt (muss schreibbar sein).
        edits: Edits mit Bezug auf die Zeilennummern von ``source``.

    Returns:
        Die neuen Bytes. Unveränderte Zeilen sind byte-identisch.

    Raises:
        UnsupportedEncodingError: bei nicht unterstütztem Encoding.
        ValueError: bei überlappenden oder ungültigen Bereichen.
    """
    if not source.writable:
        raise UnsupportedEncodingError("Datei ist schreibgeschützt (Encoding)")
    eol = source.dominant_eol()
    lines: list[Line] = list(source.lines)
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        if not 0 <= edit.start <= edit.end <= len(lines):
            raise ValueError(f"ungültiger Bereich {edit}")
        lines[edit.start:edit.end] = _new_lines(lines, edit, eol)
    _ensure_line_breaks(lines, eol)
    rebuilt = "".join(line.text + line.eol for line in lines)
    return SourceText(source.raw, source.encoding, split_lines(rebuilt)).to_bytes()


def _new_lines(lines: list[Line], edit: LineEdit, eol: str) -> list[Line]:
    """Erzeugt die Ersatzzeilen eines Edits mit passenden Zeilenenden.

    Die letzte Ersatzzeile übernimmt das Zeilenende der letzten ersetzten
    Zeile (bewahrt „ohne Schluss-Umbruch“); alle anderen bekommen ``eol``.

    Args:
        lines: Aktuelle Zeilenliste.
        edit: Der Edit.
        eol: Dominantes Zeilenende.

    Returns:
        Die neuen Zeilen.
    """
    if not edit.new_lines:
        return []
    tail_eol = lines[edit.end - 1].eol if edit.end > edit.start else eol
    out = [Line(0, text, eol) for text in edit.new_lines]
    out[-1] = Line(0, out[-1].text, tail_eol)
    return out


def _ensure_line_breaks(lines: list[Line], eol: str) -> None:
    """Sorgt dafür, dass nur die letzte Zeile ohne Zeilenende sein darf.

    Wird hinter einer Zeile ohne Umbruch eingefügt, bekommt sie ``eol``;
    die neue letzte Zeile verliert ihn dafür (Zustand bleibt erhalten).

    Args:
        lines: Zeilenliste (wird verändert).
        eol: Dominantes Zeilenende.
    """
    missing = [i for i, line in enumerate(lines[:-1]) if line.eol == ""]
    for i in missing:
        lines[i] = Line(0, lines[i].text, eol)
    if missing and lines:
        lines[-1] = Line(0, lines[-1].text, "")
