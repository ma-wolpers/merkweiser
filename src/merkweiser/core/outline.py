"""Struktur einer Notiz: Überschriften, Themen, Listenpunkte, Sonstiges.

Dritte Stufe der Parser-Pipeline. Erhält eine fertige ``NoteSpan`` (Grenzen
entscheidet allein ``blocks``) und baut daraus einen Baum, dessen Knoten nur
auf Zeilennummern verweisen; Text wird nie kopiert oder neu gerendert.

Zwei Durchgänge:

1. ``_classify`` gruppiert Zeilen zu Blöcken (Absatz, Überschrift inklusive
   Setext, Listenpunkt mit Fortsetzungszeilen, Sonstiges inklusive Codeblock).
2. ``build_outline`` ordnet die Blöcke nach ``docs/FORMAT.md`` in den Baum ein:
   Überschriften-Bereiche, Themen mit Erläuterungsabsätzen, implizite Themen,
   Listen-Hierarchie nach Einrückungsspalte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .blocks import FileLayout, NoteSpan
from .inline import ListItem, Tag, find_tags, leading_whitespace, parse_list_item
from .source import Line

_ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)")
_SETEXT_RE = re.compile(r"^ {0,3}(={3,}|-{3,})[ \t]*$")
_OTHER_START = (">", "|", "<")
_EMBED_ONLY_RE = re.compile(r"^\s*!\[\[[^\]]*\]\]\s*$|^\s*!\[[^\]]*\]\([^)]*\)\s*$")


class NodeKind(Enum):
    """Art eines Knotens im Notizbaum."""

    HEADING = "heading"
    TOPIC = "topic"
    ITEM = "item"
    OTHER = "other"


@dataclass(frozen=True)
class Node:
    """Ein Knoten des Notizbaums.

    Attributes:
        index: Position in ``Outline.nodes`` (Eltern haben immer kleinere Indizes).
        kind: Art des Knotens.
        lines: Eigene Zeilen (Thema inklusive Erläuterungsabsätzen, Punkt
            inklusive Fortsetzungen); leer bei impliziten Themen.
        parent: Index des Elternknotens oder ``None``.
        children: Indizes der Kinder in Dateireihenfolge.
        level: Überschriftenstufe (1–6), sonst 0.
        item: Analyse der ersten Zeile bei Listenpunkten, sonst ``None``.
        implicit: ``True`` für ein unsichtbares Thema ohne Text.
        tags: Explizite Tags aller eigenen Zeilen.
    """

    index: int
    kind: NodeKind
    lines: tuple[int, ...]
    parent: int | None
    children: tuple[int, ...]
    level: int = 0
    item: ListItem | None = None
    implicit: bool = False
    tags: tuple[Tag, ...] = ()


@dataclass(frozen=True)
class Outline:
    """Notizbaum einer ``NoteSpan``.

    Attributes:
        note: Die zugrunde liegende Notiz.
        nodes: Alle Knoten; Eltern stehen vor ihren Kindern.
    """

    note: NoteSpan
    nodes: tuple[Node, ...]

    @property
    def roots(self) -> tuple[Node, ...]:
        """Knoten ohne Eltern (Überschriften erster Ebene, Themen, …)."""
        return tuple(n for n in self.nodes if n.parent is None)

    def items(self) -> tuple[Node, ...]:
        """Alle Listenpunkte in Dateireihenfolge."""
        return tuple(n for n in self.nodes if n.kind is NodeKind.ITEM)

    def subtree_end(self, node: Node) -> int:
        """Letzte Zeile eines Knotens inklusive aller Nachfahren.

        Args:
            node: Knoten dieses Baums.

        Returns:
            Größter Zeilenindex im Teilbaum.
        """
        last = node.lines[-1] if node.lines else -1
        for child in node.children:
            last = max(last, self.subtree_end(self.nodes[child]))
        return last


@dataclass
class _Block:
    """Zwischenergebnis von Durchgang 1."""

    kind: NodeKind
    lines: list[int]
    level: int = 0
    item: ListItem | None = None


@dataclass
class _Draft:
    """Veränderlicher Knoten während des Aufbaus."""

    kind: NodeKind
    lines: list[int]
    parent: int | None
    level: int = 0
    item: ListItem | None = None
    implicit: bool = False
    children: list[int] = field(default_factory=list)


def build_outline(lines: tuple[Line, ...], layout: FileLayout, note: NoteSpan) -> Outline:
    """Baut den Notizbaum einer Notiz.

    Args:
        lines: Alle Zeilen der Datei (``SourceText.lines``).
        layout: Ergebnis von ``blocks.analyze`` (für Codeblöcke).
        note: Die zu analysierende Notiz.

    Returns:
        Der Notizbaum (leer bei leerer Notiz).
    """
    if note.content is None:
        return Outline(note, ())
    blocks = _classify(lines, layout, range(note.content.start, note.content.end))
    drafts = _build_tree(blocks)
    nodes = tuple(
        Node(index=i, kind=d.kind, lines=tuple(d.lines), parent=d.parent, children=tuple(d.children),
             level=d.level, item=d.item, implicit=d.implicit,
             tags=tuple(tag for no in d.lines for tag in find_tags(lines[no].text) if not _is_setext(lines[no])))
        for i, d in enumerate(drafts))
    return Outline(note, nodes)


def _is_setext(line: Line) -> bool:
    """``True`` für eine Setext-Unterstreichung (enthält nie Tags)."""
    return bool(_SETEXT_RE.match(line.text))


def _classify(lines: tuple[Line, ...], layout: FileLayout, numbers: range) -> list[_Block]:
    """Durchgang 1: gruppiert Zeilen zu Blöcken.

    Args:
        lines: Alle Zeilen.
        layout: Datei-Layout (Codeblöcke).
        numbers: Zeilenindizes des Notizinhalts.

    Returns:
        Blöcke in Dateireihenfolge; Leerzeilen erzeugen keinen Block, beenden
        aber Absätze und Fortsetzungen.
    """
    blocks: list[_Block] = []
    prev: str = "blank"  # Art der vorigen Zeile: blank, paragraph, item, other
    for no in numbers:
        line = lines[no]
        if layout.in_code(no):
            if prev == "code" and blocks:
                blocks[-1].lines.append(no)
            else:
                blocks.append(_Block(NodeKind.OTHER, [no]))
            prev = "code" if not _closes_fence(layout, no) else "other"
            continue
        if line.is_blank:
            prev = "blank"
            continue
        prev = _classify_line(line, blocks, prev)
    return blocks


def _closes_fence(layout: FileLayout, no: int) -> bool:
    """``True``, wenn ``no`` die letzte Zeile eines Codeblocks ist."""
    return any(fence.end - 1 == no for fence in layout.fences)


def _classify_line(line: Line, blocks: list[_Block], prev: str) -> str:
    """Ordnet eine Nicht-Leerzeile außerhalb von Code einem Block zu.

    Args:
        line: Die Zeile.
        blocks: Bisherige Blöcke (wird verändert).
        prev: Art der vorigen Zeile.

    Returns:
        Art dieser Zeile für den nächsten Aufruf.
    """
    text = line.text
    setext = _SETEXT_RE.match(text)
    if setext and prev == "paragraph":
        blocks[-1].kind = NodeKind.HEADING
        blocks[-1].level = 1 if setext.group(1)[0] == "=" else 2
        blocks[-1].lines.append(line.no)
        return "other"
    atx = _ATX_RE.match(text)
    if atx:
        blocks.append(_Block(NodeKind.HEADING, [line.no], level=len(atx.group(1))))
        return "other"
    item = parse_list_item(text)
    if item is not None:
        blocks.append(_Block(NodeKind.ITEM, [line.no], item=item))
        return "item"
    indented = bool(leading_whitespace(text))
    if indented and prev == "item":
        blocks[-1].lines.append(line.no)  # Fortsetzung des Punkts
        return "item"
    if indented or text.lstrip().startswith(_OTHER_START) or _EMBED_ONLY_RE.match(text):
        blocks.append(_Block(NodeKind.OTHER, [line.no]))
        return "other"
    if prev == "paragraph":
        blocks[-1].lines.append(line.no)
    else:
        blocks.append(_Block(NodeKind.TOPIC, [line.no]))  # Absatz; Thema oder Erläuterung
    return "paragraph"


def _build_tree(blocks: list[_Block]) -> list[_Draft]:
    """Durchgang 2: ordnet Blöcke in den Baum ein (Regeln aus FORMAT.md).

    Args:
        blocks: Ergebnis von ``_classify``.

    Returns:
        Knotenentwürfe; Eltern stehen immer vor ihren Kindern.
    """
    drafts: list[_Draft] = []
    headings: list[int] = []        # Stapel offener Überschriften
    topic: int | None = None        # aktuelles Thema
    items_since_topic = False
    item_stack: list[int] = []      # offene Listenpunkte im aktuellen Thema

    def add(draft: _Draft) -> int:
        drafts.append(draft)
        if draft.parent is not None:
            drafts[draft.parent].children.append(len(drafts) - 1)
        return len(drafts) - 1

    def ensure_topic() -> int:
        nonlocal topic
        if topic is None:
            topic = add(_Draft(NodeKind.TOPIC, [], headings[-1] if headings else None, implicit=True))
        return topic

    for block in blocks:
        if block.kind is NodeKind.HEADING:
            while headings and drafts[headings[-1]].level >= block.level:
                headings.pop()
            headings.append(add(_Draft(NodeKind.HEADING, block.lines, headings[-1] if headings else None,
                                       level=block.level)))
            topic, items_since_topic, item_stack = None, False, []
        elif block.kind is NodeKind.TOPIC:
            if topic is None or items_since_topic or drafts[topic].implicit:
                topic = add(_Draft(NodeKind.TOPIC, block.lines, headings[-1] if headings else None))
                items_since_topic, item_stack = False, []
            else:
                drafts[topic].lines.extend(block.lines)  # Erläuterungsabsatz
        elif block.kind is NodeKind.ITEM:
            assert block.item is not None
            owner = ensure_topic()
            while item_stack and drafts[item_stack[-1]].item.indent >= block.item.indent:  # type: ignore[union-attr]
                item_stack.pop()
            item_stack.append(add(_Draft(NodeKind.ITEM, block.lines, item_stack[-1] if item_stack else owner,
                                         item=block.item)))
            items_since_topic = True
        else:
            add(_Draft(NodeKind.OTHER, block.lines, ensure_topic()))
    return drafts
