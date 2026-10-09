"""Fassade der Lese-Pipeline für eine Datei.

``parse_document`` führt die Stufen ``SourceText → Blocks → Outline → Tags``
in genau dieser Reihenfolge aus und bündelt die Ergebnisse. Spätere Schichten
(Suche, Edit-Ops, NotesService) arbeiten auf ``Document`` statt die Stufen
selbst zu verketten.
"""

from __future__ import annotations

from dataclasses import dataclass

from .blocks import FileLayout, NoteSpan, analyze
from .outline import Node, Outline, build_outline
from .patch import StaleTargetError
from .source import SourceText
from .tags import DEFAULT_PROJECT_PREFIX, NodeTags, compute_tags


@dataclass(frozen=True)
class ParsedNote:
    """Eine Notiz mit Baum und Tags.

    Attributes:
        index: Position der Notiz in der Datei (0-basiert, inklusive leerer Notizen).
        note: Zeilenbereich der Notiz.
        outline: Notizbaum.
        tags: Tags je Knoten (gleiche Reihenfolge wie ``outline.nodes``).
    """

    index: int
    note: NoteSpan
    outline: Outline
    tags: tuple[NodeTags, ...]


@dataclass(frozen=True)
class Document:
    """Vollständig gelesene Datei.

    Attributes:
        source: Verlustfreies Source-Modell.
        layout: Frontmatter, Codeblöcke, Trenner, Notizen.
        notes: Alle Notizen, auch leere (``ParsedNote.note.is_empty``).
    """

    source: SourceText
    layout: FileLayout
    notes: tuple[ParsedNote, ...]

    def line_text(self, line_no: int) -> str:
        """Liefert den Text einer Zeile ohne Zeilenende.

        Args:
            line_no: Zeilenindex.

        Returns:
            Der Zeileninhalt.
        """
        return self.source.lines[line_no].text

    def item_at(self, line_no: int) -> tuple[ParsedNote, Node]:
        """Findet den Listenpunkt, der in ``line_no`` beginnt.

        Args:
            line_no: Erste Zeile des Punkts.

        Returns:
            Notiz und Knoten.

        Raises:
            StaleTargetError: Dort beginnt kein Listenpunkt.
        """
        for note in self.notes:
            for node in note.outline.items():
                if node.lines[0] == line_no:
                    return note, node
        raise StaleTargetError(f"Zeile {line_no + 1} ist kein Listenpunkt")


def parse_document(raw: bytes, project_prefix: str = DEFAULT_PROJECT_PREFIX) -> Document:
    """Liest eine Datei vollständig ein.

    Args:
        raw: Dateiinhalt.
        project_prefix: Einstellbares Projekt-Präfix.

    Returns:
        Das Dokument mit allen Notizen.
    """
    source = SourceText.from_bytes(raw)
    layout = analyze(source.lines)
    notes = []
    for index, note in enumerate(layout.notes):
        outline = build_outline(source.lines, layout, note)
        notes.append(ParsedNote(index, note, outline, compute_tags(outline, project_prefix)))
    return Document(source, layout, tuple(notes))
