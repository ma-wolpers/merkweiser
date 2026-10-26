"""Planung des Verschiebens eines Todos auf ein anderes Datum (ohne Schreiben).

Bausteine für das Move-Protokoll aus ``docs/PLAN.md`` (Regeln: ``docs/FORMAT.md``,
„Todo verschieben“). Es gibt **kein** Verschiebe-Tracking: keine Kopfzeile
„Verschoben aus“, Zusammenhänge laufen nur über Tags.

* ``plan_move`` entscheidet den Fall:

  - **Ganze Notiz** (``mode == "notiz"``): Das Todo ist das alleinige Todo
    seiner Notiz (alle Todos, auch abgehakte, liegen in seinem Teilbaum). Dann
    wandert die ganze Notiz unverändert.
  - **Einzelnes Todo** (``mode == "todo"``): Todo mit Kindern und
    Fortsetzungszeilen, Wurzel auf Ebene 0. Ein normales Thema wird als
    Themenzeile mitgenommen; geerbte Tags werden an die Wurzel geschrieben,
    außer denen, die diese Themenzeile schon trägt.

* ``plan_target`` wählt **einmal** die Zielnotiz (genau eine Notiz mit gleichem,
  zusammenführbarem Themenschlüssel) oder „neu“. Die Wahl wird im Manifest
  gespeichert und beim Neuplanen nur exakt wiedergefunden, nie neu gesucht.
* ``insert_moved`` hängt an bzw. führt zusammen; ``moved_chunks`` liefert die
  eingefügten Zeilenfolgen für den Zielnachweis.
* ``remove_moved_source`` entfernt den Quellblock nur, wenn er **exakt und
  eindeutig** noch vorhanden ist (sonst ``StaleTargetError``).

Die Reihenfolge „erst Ziel, dann Quelle“ und die Absturzsicherheit gehören zum
Protokoll (``move_exec``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .document import Document, ParsedNote, parse_document
from .edits import tagged_line, with_tags
from .inline import find_tags
from .note_ops import append_note, delete_note
from .outline import Node, NodeKind, Outline
from .patch import BlockTarget, LineEdit, StaleTargetError, Target, apply_edits, resolve_block, resolve_line
from .topics import find_topic_note, is_empty_topic, mergeable, topic_key, topic_line

NEW = {"art": "neu"}


@dataclass(frozen=True)
class MovePlan:
    """Geplanter Move.

    Attributes:
        source_block: Exakter Quellblock (Todo-Teilbaum bzw. ganze Notiz).
        moved_lines: Einzufügende Zeilen ``B'``: der Todo-Teilbaum (Wurzel auf
            Ebene 0, Tags materialisiert) bzw. die ganze Notiz unverändert.
        mode: ``"todo"`` oder ``"notiz"``.
        topic: Mitzuschreibende Themenzeile (nur ``"todo"`` mit normalem
            Thema), sonst ``None``.
        key: Themenschlüssel für das Zusammenführen oder ``None`` (ohne Thema
            bzw. reines ``...``: nie zusammenführen).
    """

    source_block: BlockTarget
    moved_lines: tuple[str, ...]
    mode: str = "todo"
    topic: str | None = None
    key: str | None = None


def plan_move(doc: Document, target: Target) -> MovePlan:
    """Plant das Verschieben des Todos an ``target``.

    Args:
        doc: Aktuelles Dokument der Quelldatei.
        target: Zeile des Todos.

    Returns:
        Der Plan (Fall „ganze Notiz“ oder „einzelnes Todo“).

    Raises:
        StaleTargetError: Ziel nicht eindeutig oder kein Listenpunkt.
    """
    line_no = resolve_line(doc.source, target)
    note, node = doc.item_at(line_no)
    topic = topic_line(doc, note)
    key = topic_key(topic) if mergeable(topic) else None
    if is_sole_todo(note, node):
        content = note.note.content
        assert content is not None  # Notizen haben seit 2026-10-21 immer Inhalt
        lines = tuple(doc.line_text(no) for no in range(content.start, content.end))
        return MovePlan(BlockTarget(target.relpath, content.start, lines), lines, "notiz", None, key)
    end = note.outline.subtree_end(node)
    lines = tuple(doc.line_text(no) for no in range(line_no, end + 1))
    prefix = lines[0][: len(lines[0]) - len(lines[0].lstrip(" \t"))]
    dedented = [line[len(prefix):] if line.startswith(prefix) else line for line in lines]
    written = topic if topic is not None and not is_empty_topic(topic) else None
    present = {tag.key for tag in find_tags(written)} if written else set()
    names = [name for name in _inherited_tag_names(note, node.index) if name.casefold() not in present]
    dedented[0] = with_tags(dedented[0], names)
    return MovePlan(BlockTarget(target.relpath, line_no, lines), tuple(dedented), "todo", written, key)


def is_sole_todo(note: ParsedNote, node: Node) -> bool:
    """Ob alle Todos der Notiz (offen und abgehakt) im Teilbaum von ``node`` liegen.

    Args:
        note: Notiz des Todos.
        node: Das zu verschiebende Todo.

    Returns:
        ``True``, wenn ``node`` das alleinige Todo seiner Notiz ist.
    """
    inside = _subtree(note.outline, node)
    return all(n.index in inside for n in note.outline.items() if n.item and n.item.is_todo)


def _subtree(outline: Outline, node: Node) -> set[int]:
    """Indizes von ``node`` und allen Nachfahren."""
    result, stack = set(), [node.index]
    while stack:
        index = stack.pop()
        result.add(index)
        stack.extend(outline.nodes[index].children)
    return result


def plan_target(doc: Document, plan: MovePlan) -> dict:
    """Wählt die Zielnotiz einmalig (wird im Manifest gespeichert).

    Args:
        doc: Aktuelles Dokument der Zieldatei (auch leer).
        plan: Ergebnis von ``plan_move``.

    Returns:
        ``{"art": "neu"}`` oder ``{"art": "anhaengen", "notiz": [Inhaltszeilen]}``
        bei genau einer Notiz mit gleichem, zusammenführbarem Themenschlüssel.
    """
    match = find_topic_note(doc, plan.key) if plan.key else None
    if match is None or match.note.content is None:
        return dict(NEW)
    content = match.note.content
    return {"art": "anhaengen", "notiz": [doc.line_text(no) for no in range(content.start, content.end)]}


def insert_moved(doc: Document, plan: MovePlan, ziel: dict) -> bytes:
    """Fügt die verschobenen Zeilen in die Zieldatei ein.

    Args:
        doc: Aktuelles Dokument der Zieldatei (auch leer).
        plan: Ergebnis von ``plan_move``.
        ziel: Gespeicherte Zielwahl aus ``plan_target``.

    Returns:
        Neue Bytes der Zieldatei.

    Raises:
        StaleTargetError: Die gewählte Zielnotiz steht nicht mehr exakt und
            eindeutig als ganze Notiz in der Datei (es wird **nicht** neu gesucht).
    """
    if ziel.get("art") != "anhaengen":
        return append_note(doc, "\n".join(((plan.topic,) if plan.topic else ()) + plan.moved_lines))
    start, end, first_item = _locate(doc, tuple(ziel["notiz"]))
    if plan.mode == "todo":
        return apply_edits(doc.source, [LineEdit(end, end, plan.moved_lines)])
    explanation, rest = _split_note(plan.moved_lines)
    if first_item is None:
        return apply_edits(doc.source, [LineEdit(end, end, explanation + rest)])
    return apply_edits(doc.source, [LineEdit(first_item, first_item, explanation), LineEdit(end, end, rest)])


def moved_chunks(plan: MovePlan, ziel: dict) -> tuple[tuple[str, ...], ...]:
    """Die Zeilenfolgen, die ``insert_moved`` am Stück einfügt (für den Zielnachweis).

    Args:
        plan: Der Plan.
        ziel: Gespeicherte Zielwahl.

    Returns:
        Nicht leere Zeilenfolgen in Einfügereihenfolge.
    """
    if ziel.get("art") != "anhaengen":
        return (((plan.topic,) if plan.topic else ()) + plan.moved_lines,)
    if plan.mode == "todo":
        return (plan.moved_lines,)
    explanation, rest = _split_note(plan.moved_lines)
    return tuple(chunk for chunk in (explanation, rest) if chunk)


def _locate(doc: Document, lines: tuple[str, ...]) -> tuple[int, int, int | None]:
    """Findet die gespeicherte Zielnotiz exakt und eindeutig als ganze Notiz.

    Args:
        doc: Zieldokument.
        lines: Inhaltszeilen der Zielnotiz bei der Planung.

    Returns:
        ``(start, ende, erster_listenpunkt)``; der Listenpunkt ist ``None``,
        wenn die Notiz keinen hat.

    Raises:
        StaleTargetError: nicht exakt, mehrfach oder nicht mehr als ganze Notiz.
    """
    try:
        start = resolve_block(doc.source, BlockTarget("", 0, lines), unique=True)
    except StaleTargetError as exc:
        raise StaleTargetError("Zielnotiz wurde inzwischen verändert – nichts verschoben") from exc
    for note in doc.notes:
        content = note.note.content
        if content and (content.start, content.end) == (start, start + len(lines)):
            items = note.outline.items()
            return content.start, content.end, (items[0].lines[0] if items else None)
    raise StaleTargetError("Zielnotiz wurde inzwischen verändert – nichts verschoben")


def _split_note(lines: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Zerlegt eine ganze Notiz in Erläuterung und übrigen Inhalt (ohne Themenzeile).

    Erläuterung sind alle Zeilen nach der Themenzeile vor dem ersten
    Listenpunkt (die Zeilen des Themenknotens). Ohne Thema gibt es keine
    Erläuterung, und alles ist übriger Inhalt.

    Args:
        lines: Inhaltszeilen der Quellnotiz.

    Returns:
        ``(erläuterung, rest)``.
    """
    doc = parse_document("\n".join(lines).encode("utf-8"), "")
    root = doc.notes[0].outline.roots[0] if doc.notes and doc.notes[0].outline.roots else None
    if root is None or root.kind is not NodeKind.TOPIC or root.implicit or not root.lines:
        return (), lines
    own = len(root.lines)
    return lines[1:own], lines[own:]


def remove_moved_source(doc: Document, plan: MovePlan) -> bytes:
    """Entfernt den Quellblock, wenn er exakt und eindeutig noch vorhanden ist.

    Ist der Block eine ganze Notiz (Fall „ganze Notiz“ oder ein Todo zwischen
    Leerzeilen), wird sie wie mit „Notiz löschen“ samt einer angrenzenden Lücke
    entfernt, damit keine doppelten Leerzeilen zurückbleiben.

    Args:
        doc: Aktuelles Dokument der Quelldatei.
        plan: Ergebnis von ``plan_move``.

    Returns:
        Neue Bytes der Quelldatei.

    Raises:
        StaleTargetError: Block verändert, verschwunden oder mehrfach vorhanden.
    """
    expected = plan.source_block.expected_lines
    start = resolve_block(doc.source, plan.source_block, unique=True)
    if any(n.note.span.start == start and n.note.span.end == start + len(expected) for n in doc.notes):
        return delete_note(doc, tuple(expected))
    return apply_edits(doc.source, [LineEdit(start, start + len(expected), ())])


def _inherited_tag_names(note: ParsedNote, node_index: int) -> list[str]:
    """Sammelt geerbte Tag-Namen (Originalschreibweise), die nicht explizit am Knoten stehen.

    Args:
        note: Notiz des Knotens.
        node_index: Index des Wurzel-Todos.

    Returns:
        Namen in der Reihenfolge Thema → Eltern-Punkt, ohne Duplikate.
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


@dataclass(frozen=True)
class MoveContext:
    """Was die Oberfläche vor dem Verschieben eines Todos wissen muss.

    Attributes:
        sole_todo: Das Todo ist das alleinige seiner Notiz (dann wandert sie ganz, ohne Tag-Dialog).
        parent: Zeile des Überpunkts (Eltern-Punkt bzw. Themenzeile) oder ``None``
            (Todo auf oberster Ebene einer Notiz ohne Thema).
        t_projects: Effektive Projekte des Todos.
        p_projects: Effektive Projekte des Überpunkts.
        shared_projects: Projekte, die beide haben (ohne Groß-/Kleinschreibung).
        inherited_tags: Tags, die das Todo von Thema bzw. Überpunkten erbt (Originalschreibweise,
            ohne eigene). Nicht leer → kein Tag-Dialog (W7): Das Todo hat schon einen Tag, und
            ``plan_move`` schreibt geerbte Tags beim Verschieben ohnehin explizit an das Todo.
    """

    sole_todo: bool
    parent: Target | None
    t_projects: tuple[str, ...]
    p_projects: tuple[str, ...]
    shared_projects: tuple[str, ...]
    inherited_tags: tuple[str, ...] = ()

    @property
    def needs_tag_dialog(self) -> bool:
        """Ob vor dem Verschieben der Tag-Dialog erscheint: nur bei weiteren Todos und ohne geerbten Tag."""
        return not self.sole_todo and not self.inherited_tags

    def project_conflict(self, name: str) -> str | None:
        """Prüft, ob ein neues Projekt ``name`` eine bestehende Zuordnung überschreiben würde.

        Projekte werden nie ersetzt: Haben Todo oder Überpunkt schon ein anderes
        (effektives) Projekt, wird abgelehnt.

        Args:
            name: Projektname ohne Präfix.

        Returns:
            Erklärung für die Oberfläche oder ``None``, wenn kein Konflikt besteht.
        """
        other = [p for p in (*self.t_projects, *self.p_projects) if p.casefold() != name.casefold()]
        if not other:
            return None
        parts = [f"Todo: {', '.join(self.t_projects) or 'kein Projekt'}"]
        if self.parent is not None:
            parts.append(f"Überpunkt: {', '.join(self.p_projects) or 'kein Projekt'}")
        return f"Projekte werden nicht überschrieben ({'; '.join(parts)})."


def move_context(doc: Document, target: Target) -> MoveContext:
    """Analysiert ein Todo vor dem Verschieben (für den Tag-Dialog).

    Args:
        doc: Aktuelles Dokument der Quelldatei.
        target: Zeile des Todos.

    Returns:
        Der Kontext.

    Raises:
        StaleTargetError: Todo nicht eindeutig auffindbar.
    """
    note, node = doc.item_at(resolve_line(doc.source, target))
    parent = note.outline.nodes[node.parent] if node.parent is not None else None
    parent_target = None
    if parent is not None and not parent.implicit and parent.lines:
        parent_target = Target(target.relpath, parent.lines[0], doc.line_text(parent.lines[0]))
    own = note.tags[node.index].effective_projects
    theirs = note.tags[parent.index].effective_projects if parent_target else ()
    shared = tuple(p for p in own if p.casefold() in {q.casefold() for q in theirs})
    return MoveContext(is_sole_todo(note, node), parent_target, own, theirs, shared,
                       tuple(_inherited_tag_names(note, node.index)))


def tag_for_move(doc: Document, target: Target, tag: str) -> tuple[bytes, Target]:
    """Schreibt ``#tag`` an das Todo und seinen Überpunkt (ein Patch), vor dem Verschieben.

    Ohne Überpunkt (oberste Ebene, Notiz ohne Thema) wird ``#tag`` als neue
    Themenzeile eingefügt (Tag-Thema). Vorhandene echte Tags werden nicht
    doppelt geschrieben, nichts wird ersetzt.

    Args:
        doc: Aktuelles Dokument der Quelldatei.
        target: Zeile des Todos.
        tag: Tag-Name ohne ``#`` (bei Projekten mit Präfix).

    Returns:
        ``(neue Bytes, neu aufgelöstes Target des Todos)``. Das Target gilt für
        die neuen Bytes (Zeilennummer nach eingefügter Themenzeile, neuer Text).

    Raises:
        StaleTargetError: Todo nicht eindeutig auffindbar.
    """
    line_no = resolve_line(doc.source, target)
    note, _node = doc.item_at(line_no)
    context = move_context(doc, Target(target.relpath, line_no, doc.line_text(line_no)))
    new_text = tagged_line(doc.line_text(line_no), tag)
    edits = [LineEdit(line_no, line_no + 1, (new_text,))]
    shift = 0
    if context.parent is not None:
        p_no = context.parent.line_no
        edits.append(LineEdit(p_no, p_no + 1, (tagged_line(doc.line_text(p_no), tag),)))
    else:
        start = note.note.content.start  # type: ignore[union-attr]
        edits.append(LineEdit(start, start, (f"#{tag}",)))
        shift = 1
    edits.sort(key=lambda edit: edit.start)
    return apply_edits(doc.source, edits), Target(target.relpath, line_no + shift, new_text)
