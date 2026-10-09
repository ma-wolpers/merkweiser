"""Planung des Verschiebens eines Todos auf ein anderes Datum (ohne Schreiben).

Bausteine für das Move-Protokoll aus ``docs/PLAN.md``:

* ``plan_move``: liefert den exakten Quellblock (Todo mit Kindern und
  Fortsetzungszeilen) als ``BlockTarget`` sowie die einzufügenden Zeilen
  ``B'``: Die Wurzel wird auf Einrückung 0 gebracht (Kinder behalten ihre
  relative Einrückung), geerbte Tags werden explizit an die Wurzelzeile
  geschrieben, damit Filter nach dem Verschieben weiter greifen.
* ``insert_moved``: hängt ``B'`` an die letzte Notiz mit der Themenzeile
  ``Verschoben aus [[<Quelle>]]`` an oder legt diese Notiz neu an.
* ``remove_moved_source``: entfernt den Quellblock nur, wenn er **exakt und
  eindeutig** noch vorhanden ist (sonst ``StaleTargetError``, Ergebnis
  ``INCOMPLETE`` im Protokoll).

Die Reihenfolge „erst Ziel, dann Quelle“ und die Absicherung gegen
Abstürze gehören zum Protokoll (``safe_write``) und nicht hierher.
"""

from __future__ import annotations

from dataclasses import dataclass

from .document import Document, ParsedNote
from .note_ops import append_note
from .patch import BlockTarget, LineEdit, Target, apply_edits, resolve_block, resolve_line

MOVED_HEADER = "Verschoben aus [[{stem}]]"


@dataclass(frozen=True)
class MovePlan:
    """Geplanter Move.

    Attributes:
        source_block: Exakter Quellblock (für den späteren Nachweis).
        moved_lines: Einzufügende Zeilen ``B'`` (Wurzel auf Ebene 0, Tags materialisiert).
    """

    source_block: BlockTarget
    moved_lines: tuple[str, ...]


def plan_move(doc: Document, target: Target) -> MovePlan:
    """Plant das Verschieben des Todos an ``target`` samt Teilbaum.

    Args:
        doc: Aktuelles Dokument der Quelldatei.
        target: Zeile des Todos.

    Returns:
        Der Plan.

    Raises:
        StaleTargetError: Ziel nicht eindeutig oder kein Listenpunkt.
    """
    line_no = resolve_line(doc.source, target)
    note, node = doc.item_at(line_no)
    end = note.outline.subtree_end(node)
    lines = tuple(doc.line_text(no) for no in range(line_no, end + 1))
    prefix = lines[0][: len(lines[0]) - len(lines[0].lstrip(" \t"))]
    dedented = [line[len(prefix):] if line.startswith(prefix) else line for line in lines]
    dedented[0] = _with_tags(dedented[0], _inherited_tag_names(note, node.index))
    return MovePlan(BlockTarget(target.relpath, line_no, lines), tuple(dedented))


def insert_moved(doc: Document, plan: MovePlan, source_stem: str) -> bytes:
    """Fügt die verschobenen Zeilen in die Zieldatei ein.

    Args:
        doc: Aktuelles Dokument der Zieldatei (auch leer).
        plan: Ergebnis von ``plan_move``.
        source_stem: Dateiname der Quelle ohne ``.md`` (Linkziel, z. B. ``2026-10-08``).

    Returns:
        Neue Bytes der Zieldatei.
    """
    header = MOVED_HEADER.format(stem=source_stem)
    matches = [n for n in doc.notes if n.note.content and doc.line_text(n.note.content.start) == header]
    if not matches:
        return append_note(doc, "\n".join((header, *plan.moved_lines)))
    end = matches[-1].note.content.end  # type: ignore[union-attr]
    return apply_edits(doc.source, [LineEdit(end, end, plan.moved_lines)])


def remove_moved_source(doc: Document, plan: MovePlan) -> bytes:
    """Entfernt den Quellblock, wenn er exakt und eindeutig noch vorhanden ist.

    Args:
        doc: Aktuelles Dokument der Quelldatei.
        plan: Ergebnis von ``plan_move``.

    Returns:
        Neue Bytes der Quelldatei.

    Raises:
        StaleTargetError: Block verändert, verschwunden oder mehrfach vorhanden.
    """
    start = resolve_block(doc.source, plan.source_block, unique=True)
    return apply_edits(doc.source, [LineEdit(start, start + len(plan.source_block.expected_lines), ())])


def _inherited_tag_names(note: ParsedNote, node_index: int) -> list[str]:
    """Sammelt geerbte Tag-Namen (Originalschreibweise), die nicht explizit am Knoten stehen.

    Args:
        note: Notiz des Knotens.
        node_index: Index des Wurzel-Todos.

    Returns:
        Namen in der Reihenfolge äußerste Überschrift → Eltern-Punkt, ohne Duplikate.
    """
    nodes = note.outline.nodes
    own = {tag.key for tag in nodes[node_index].tags}
    chain = []
    parent = nodes[node_index].parent
    while parent is not None:
        chain.append(nodes[parent])
        parent = nodes[parent].parent
    names, seen = [], set(own)
    for ancestor in reversed(chain):
        for tag in ancestor.tags:
            if tag.key not in seen:
                seen.add(tag.key)
                names.append(tag.name)
    return names


def _with_tags(line: str, names: list[str]) -> str:
    """Hängt Tags vor abschließendem Leerraum an eine Zeile an.

    Args:
        line: Zeile.
        names: Tag-Namen ohne ``#``.

    Returns:
        Zeile mit angehängten Tags.
    """
    if not names:
        return line
    body = line.rstrip()
    return body + "".join(f" #{name}" for name in names) + line[len(body):]
