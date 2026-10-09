"""Strukturierte Edit-Operationen auf Listenpunkten (reine Planung).

Jede Operation nimmt das **aktuell gelesene** ``Document`` und ein flüchtiges
``Target`` und liefert die neuen Bytes. Weil das Ziel bei jedem Aufruf neu
aufgelöst wird, ist „neu planen auf frischem Stand“ einfach ein erneuter
Aufruf mit dem neu gelesenen Dokument (PLAN.md, Schreibprotokoll Schritt 0).

Minimal-Diff: Es ändert sich jeweils nur die betroffene Zeile bzw. es kommt
genau eine Zeile hinzu. Operationen sind idempotent: Ist der gewünschte
Zustand schon erreicht, kommen die unveränderten Bytes zurück.

Hinweis zur Benennung: ``set_done(done)`` statt „toggle“. Die UI kennt den
gewünschten Zielzustand; ein Umschalten, das neu geplant wird, könnte sonst
nach einer fremden Änderung in die falsche Richtung kippen.
"""

from __future__ import annotations

import re

from .document import Document, ParsedNote
from .inline import ListItem, TodoStatus, find_tags, leading_whitespace, parse_list_item, project_name
from .outline import Node
from .patch import LineEdit, StaleTargetError, Target, apply_edits, resolve_line

_PROJECT_NAME_RE = re.compile(r"^[\w\-]+(?:/[\w\-]+)*$")


class NotATodoError(ValueError):
    """Die Zielzeile ist kein Todo (bzw. kein Listenpunkt)."""


def set_done(doc: Document, target: Target, done: bool) -> bytes:
    """Setzt den Erledigt-Status eines Todos.

    Erledigt schreibt ``[x]``; ein vorhandenes ``[X]`` bleibt beim Erledigen
    stehen (keine Normalisierung).

    Args:
        doc: Aktuelles Dokument.
        target: Zeile des Todos.
        done: Gewünschter Zustand.

    Returns:
        Neue Bytes (unverändert, wenn der Zustand schon stimmt).

    Raises:
        StaleTargetError: Ziel nicht eindeutig auffindbar.
        NotATodoError: Zeile ist kein offenes oder erledigtes Todo.
    """
    line_no, item = _todo_at(doc, target)
    if (item.status is TodoStatus.DONE) == done:
        return doc.source.to_bytes()
    text = doc.line_text(line_no)
    col = item.status_col
    assert col is not None
    new_text = text[:col] + ("x" if done else " ") + text[col + 1:]
    return apply_edits(doc.source, [LineEdit(line_no, line_no + 1, (new_text,))])


def set_urgent(doc: Document, target: Target, urgent: bool) -> bytes:
    """Markiert ein Todo als dringend (``==…==`` um den Inhalt) oder hebt es auf.

    Beim Markieren bleiben Tags am Zeilenende außerhalb der Hervorhebung:
    ``- [ ] Kisten #keller`` → ``- [ ] ==Kisten== #keller``.

    Args:
        doc: Aktuelles Dokument.
        target: Zeile des Todos.
        urgent: Gewünschter Zustand.

    Returns:
        Neue Bytes (unverändert, wenn der Zustand schon stimmt).

    Raises:
        StaleTargetError: Ziel nicht eindeutig auffindbar.
        NotATodoError: kein Todo.
        ValueError: Der Inhalt ist leer.
    """
    line_no, item = _todo_at(doc, target)
    if item.urgent == urgent:
        return doc.source.to_bytes()
    text = doc.line_text(line_no)
    start = item.body_start + len(leading_whitespace(text[item.body_start:]))
    if urgent:
        end = _content_end(text, start)
        if end <= start:
            raise ValueError("leerer Inhalt kann nicht dringend markiert werden")
        new_text = text[:start] + "==" + text[start:end] + "==" + text[end:]
    else:
        close = text.find("==", start + 3)
        new_text = text[:start] + text[start + 2:close] + text[close + 2:]
    return apply_edits(doc.source, [LineEdit(line_no, line_no + 1, (new_text,))])


def set_project(doc: Document, target: Target, name: str | None, prefix: str) -> bytes:
    """Setzt das explizite Projekt eines Todos (ersetzt alle Projekt-Tags der Zeile).

    Geerbte Projekte bleiben unberührt. ``name=None`` entfernt nur die
    expliziten Projekt-Tags der Zeile.

    Args:
        doc: Aktuelles Dokument.
        target: Zeile des Todos.
        name: Projektname (z. B. ``Umzug``) oder ``None``.
        prefix: Projekt-Präfix (z. B. ``projekt``).

    Returns:
        Neue Bytes.

    Raises:
        StaleTargetError: Ziel nicht eindeutig auffindbar.
        NotATodoError: kein Todo.
        ValueError: ungültiger Projektname.
    """
    if name is not None and not _PROJECT_NAME_RE.match(name):
        raise ValueError(f"ungültiger Projektname: {name!r}")
    line_no, _item = _todo_at(doc, target)
    text = doc.line_text(line_no)
    for tag in reversed(find_tags(text)):
        if project_name(tag, prefix) is not None:
            cut = tag.start - 1 if tag.start > 0 and text[tag.start - 1] == " " else tag.start
            text = text[:cut] + text[tag.end:]
    if name is not None:
        body = text.rstrip()
        text = f"{body} #{prefix}/{name}" + text[len(body):]
    if text == doc.line_text(line_no):
        return doc.source.to_bytes()
    return apply_edits(doc.source, [LineEdit(line_no, line_no + 1, (text,))])


def add_todo(doc: Document, note_index: int, text: str, parent: Target | None = None) -> bytes:
    """Fügt ein neues offenes Todo in eine Notiz ein.

    Ohne ``parent`` wird ``- [ ] text`` hinter der letzten Inhaltszeile der
    Notiz eingefügt. Mit ``parent`` wird das Todo als letztes Kind hinter dem
    gesamten Teilbaum des Eltern-Punkts eingefügt; die Einrückung folgt einem
    vorhandenen Kind bzw. dem Eltern-Punkt plus Markerbreite.

    Args:
        doc: Aktuelles Dokument.
        note_index: Index der Notiz.
        text: Inhalt des Todos (eine Zeile).
        parent: Optionaler Eltern-Listenpunkt.

    Returns:
        Neue Bytes.

    Raises:
        ValueError: mehrzeiliger oder leerer Text, leere Notiz.
        StaleTargetError: Eltern-Punkt nicht eindeutig auffindbar.
    """
    if not text.strip() or "\n" in text or "\r" in text:
        raise ValueError("Ein Todo braucht genau eine nicht leere Zeile")
    note = doc.notes[note_index]
    if parent is None:
        if note.note.content is None:
            raise ValueError("leere Notiz")
        at, indent = note.note.content.end, ""
    else:
        parent_note, node = _item_node(doc, resolve_line(doc.source, parent))
        at, indent = _subtree_end(parent_note, node) + 1, _child_indent(doc, parent_note, node)
    return apply_edits(doc.source, [LineEdit(at, at, (f"{indent}- [ ] {text.strip()}",))])


def _todo_at(doc: Document, target: Target) -> tuple[int, ListItem]:
    """Löst ein Ziel auf und prüft, dass dort ein Todo steht.

    Args:
        doc: Aktuelles Dokument.
        target: Zieladresse.

    Returns:
        Zeilenindex und Listenpunkt-Analyse.

    Raises:
        StaleTargetError: Ziel nicht eindeutig.
        NotATodoError: kein offenes oder erledigtes Todo, oder im Codeblock.
    """
    line_no = resolve_line(doc.source, target)
    item = parse_list_item(doc.line_text(line_no))
    if item is None or not item.is_todo or doc.layout.in_code(line_no):
        raise NotATodoError(f"{target.relpath}:{line_no + 1} ist kein Todo")
    return line_no, item


def _content_end(text: str, start: int) -> int:
    """Ende des Inhalts vor abschließenden Tags und Leerraum.

    Args:
        text: Zeile.
        start: Inhaltsbeginn.

    Returns:
        Spalte, bis zu der die Hervorhebung reichen soll.
    """
    end = len(text.rstrip())
    for tag in reversed(find_tags(text)):
        if tag.end == end and tag.start >= start:
            end = len(text[:tag.start].rstrip())
    return max(end, start)


def _item_node(doc: Document, line_no: int) -> tuple[ParsedNote, Node]:
    """Findet den Listenpunkt-Knoten, der in ``line_no`` beginnt.

    Args:
        doc: Dokument.
        line_no: Erste Zeile des Punkts.

    Returns:
        Notiz und Knoten.

    Raises:
        StaleTargetError: Dort beginnt kein Listenpunkt.
    """
    for note in doc.notes:
        for node in note.outline.items():
            if node.lines[0] == line_no:
                return note, node
    raise StaleTargetError(f"Zeile {line_no + 1} ist kein Listenpunkt")


def _subtree_end(note: ParsedNote, node: Node) -> int:
    """Letzte Zeile eines Knotens inklusive aller Nachfahren.

    Args:
        note: Notiz des Knotens.
        node: Knoten.

    Returns:
        Größter Zeilenindex im Teilbaum.
    """
    last = node.lines[-1]
    for child in node.children:
        last = max(last, _subtree_end(note, note.outline.nodes[child]))
    return last


def _child_indent(doc: Document, note: ParsedNote, node: Node) -> str:
    """Einrückung für ein neues Kind eines Listenpunkts.

    Args:
        doc: Dokument.
        note: Notiz.
        node: Eltern-Punkt.

    Returns:
        Führender Leerraum eines vorhandenen Kind-Punkts, sonst der des Eltern-
        Punkts plus Tab (bei Tab-Einrückung) bzw. Markerbreite + 1 Leerzeichen.
    """
    for child in node.children:
        child_node = note.outline.nodes[child]
        if child_node.item is not None:
            return leading_whitespace(doc.line_text(child_node.lines[0]))
    own = leading_whitespace(doc.line_text(node.lines[0]))
    assert node.item is not None
    return own + ("\t" if "\t" in own else " " * (len(node.item.marker) + 1))
