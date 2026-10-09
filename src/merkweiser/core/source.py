"""Verlustfreies Source-Modell einer Markdown-Datei.

Grundlage der Parser-Pipeline (``docs/PLAN.md``, Abschnitt „Parser-Pipeline“):
Eine Datei wird **nie** über einen AST neu gerendert. ``SourceText`` hält die
Rohbytes, das erkannte Encoding und eine Zeilenliste, in der jede Zeile ihr
eigenes Zeilenende behält. Unveränderte Zeilen werden beim Serialisieren
einfach wieder aneinandergehängt; damit gilt die Roundtrip-Invariante
``SourceText.from_bytes(raw).to_bytes() == raw`` für jede unterstützte Datei.

Encoding-Grenze (``docs/FORMAT.md``): Lesen und Schreiben nur für UTF-8 mit
und ohne BOM. Alles andere (ungültige UTF-8-Bytes, UTF-16/32-BOM) wird mit
Ersatzzeichen dekodiert, ist nur anzeig- und durchsuchbar und meldet
``writable == False``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum

UTF8_BOM = b"\xef\xbb\xbf"
_FOREIGN_BOMS = (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff", b"\xff\xfe", b"\xfe\xff")

# Nur \r\n, \n und \r gelten als Zeilenende. str.splitlines() wäre falsch, weil
# es auch an \x0b, \x1c,   … trennt und diese Zeichen damit verlöre.
_LINE_RE = re.compile(r"([^\r\n]*)(\r\n|\n|\r|\Z)")


class Encoding(Enum):
    """Erkanntes Encoding einer Datei."""

    UTF8 = "utf-8"
    UTF8_BOM = "utf-8-sig"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Line:
    """Eine Zeile mit ihrem originalen Zeilenende.

    Attributes:
        no: 0-basierter Zeilenindex in der Datei.
        text: Zeileninhalt ohne Zeilenende.
        eol: ``"\\n"``, ``"\\r\\n"``, ``"\\r"`` oder ``""`` (letzte Zeile ohne
            Zeilenumbruch).
    """

    no: int
    text: str
    eol: str

    @property
    def is_blank(self) -> bool:
        """``True``, wenn die Zeile leer ist oder nur Leerraum enthält."""
        return not self.text.strip()


@dataclass(frozen=True)
class SourceText:
    """Unveränderliche, verlustfreie Sicht auf den Inhalt einer Datei.

    Attributes:
        raw: Die exakten Rohbytes der Datei.
        encoding: Erkanntes Encoding; ``UNSUPPORTED`` heißt schreibgeschützt.
        lines: Alle Zeilen in Dateireihenfolge.
    """

    raw: bytes
    encoding: Encoding
    lines: tuple[Line, ...]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "SourceText":
        """Dekodiert Rohbytes verlustfrei in Zeilen.

        Args:
            raw: Dateiinhalt.

        Returns:
            Das Source-Modell. Bei nicht unterstütztem Encoding wird mit
            Ersatzzeichen dekodiert (nur zur Anzeige und Suche).
        """
        encoding, text = _decode(raw)
        return cls(raw=raw, encoding=encoding, lines=split_lines(text))

    @property
    def writable(self) -> bool:
        """``True``, wenn Merkweiser diese Datei verändern darf (UTF-8 ± BOM)."""
        return self.encoding is not Encoding.UNSUPPORTED

    @property
    def text(self) -> str:
        """Der dekodierte Gesamttext inklusive originaler Zeilenenden."""
        return "".join(line.text + line.eol for line in self.lines)

    def to_bytes(self) -> bytes:
        """Serialisiert die Zeilen zurück in Bytes.

        Returns:
            Für unterstützte Encodings exakt die Bytes, die die Zeilen
            beschreiben (bei unverändertem Modell also ``raw``). Für nicht
            unterstützte Encodings immer ``raw``, weil diese Dateien nie
            geschrieben werden.
        """
        if not self.writable:
            return self.raw
        body = self.text.encode("utf-8")
        return UTF8_BOM + body if self.encoding is Encoding.UTF8_BOM else body

    def dominant_eol(self) -> str:
        """Liefert das häufigste Zeilenende der Datei.

        Neue Zeilen, die Merkweiser einfügt, bekommen dieses Zeilenende, damit
        eine CRLF-Datei nicht plötzlich LF-Zeilen enthält.

        Returns:
            Das häufigste Zeilenende; ``"\\n"`` für Dateien ohne Zeilenumbruch.
            Bei Gleichstand gewinnt ``"\\n"``.
        """
        counts = Counter(line.eol for line in self.lines if line.eol)
        if not counts:
            return "\n"
        best = max(counts.values())
        return "\n" if counts.get("\n") == best else counts.most_common(1)[0][0]


def split_lines(text: str) -> tuple[Line, ...]:
    """Zerlegt Text in Zeilen, wobei jede ihr Zeilenende behält.

    Eine Datei, die mit einem Zeilenumbruch endet, erzeugt **keine** zusätzliche
    leere Zeile; eine leere Datei hat keine Zeilen.

    Args:
        text: Dekodierter Text.

    Returns:
        Die Zeilen in Reihenfolge.
    """
    lines: list[Line] = []
    pos = 0
    while pos < len(text):
        match = _LINE_RE.match(text, pos)
        assert match is not None  # _LINE_RE passt an jeder Position
        lines.append(Line(no=len(lines), text=match.group(1), eol=match.group(2)))
        pos = match.end()
    return tuple(lines)


def _decode(raw: bytes) -> tuple[Encoding, str]:
    """Erkennt das Encoding und dekodiert.

    Args:
        raw: Rohbytes.

    Returns:
        Paar aus Encoding und Text. Nicht unterstützte Inhalte werden mit
        ``errors="replace"`` dekodiert.
    """
    if raw.startswith(UTF8_BOM):
        try:
            return Encoding.UTF8_BOM, raw[len(UTF8_BOM):].decode("utf-8")
        except UnicodeDecodeError:
            return Encoding.UNSUPPORTED, raw.decode("utf-8", errors="replace")
    if any(raw.startswith(bom) for bom in _FOREIGN_BOMS):
        return Encoding.UNSUPPORTED, raw.decode("utf-8", errors="replace")
    try:
        return Encoding.UTF8, raw.decode("utf-8")
    except UnicodeDecodeError:
        return Encoding.UNSUPPORTED, raw.decode("utf-8", errors="replace")
