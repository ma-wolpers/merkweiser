"""UI-neutrale Anzeigemodelle für Desktop und Mobile (keine Flet-/Tk-Abhängigkeit).

Wandelt Dokumente, Suchtreffer und Konfliktfälle in einfache, testbare Zeilen
um. Die Oberflächen rendern nur noch und reichen ``Target``-Adressen an den
``NotesService`` zurück.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from enum import Enum

from ..core.conflicts import ConflictCase, render
from ..core.document import Document, ParsedNote
from ..core.inline import TodoStatus
from ..core.merge.union import merge2
from ..core.outline import Node, NodeKind
from ..core.patch import Target
from ..core.query import Hit
from ..core.source import SourceText


@dataclass(frozen=True)
class Row:
    """Eine Anzeigezeile einer Notiz.

    Attributes:
        kind: ``heading``, ``topic``, ``item``, ``todo`` oder ``other``.
        text: Anzeigetext (Marker und Checkbox entfernt).
        depth: Einrückungstiefe im Baum (0 = oberste Ebene).
        done: Erledigt-Status bei Todos, sonst ``None``.
        urgent: Dringlichkeit.
        tags: Effektive Tags (sortiert).
        target: Adresse der ersten Zeile (für Aktionen) oder ``None``.
    """

    kind: str
    text: str
    depth: int
    done: bool | None
    urgent: bool
    tags: tuple[str, ...]
    target: Target | None


def note_rows(relpath: str, doc: Document, note: ParsedNote) -> list[Row]:
    """Anzeigezeilen einer Notiz in Dateireihenfolge.

    Args:
        relpath: Datei relativ zum Vault.
        doc: Dokument.
        note: Notiz im Dokument.

    Returns:
        Zeilen; implizite Themen erscheinen nicht.
    """
    rows = []
    for node in note.outline.nodes:
        if node.implicit or not node.lines:
            continue
        line = doc.line_text(node.lines[0])
        item = node.item
        is_todo = bool(item and item.is_todo)
        rows.append(Row(kind="todo" if is_todo else node.kind.value, text=display_text(line, node),
                        depth=_depth(note, node), done=(item.status is TodoStatus.DONE) if is_todo else None,
                        urgent=bool(item and item.urgent), tags=tuple(sorted(note.tags[node.index].effective)),
                        target=Target(relpath, node.lines[0], line)))
    return rows


def display_text(line: str, node: Node) -> str:
    """Anzeigetext ohne Listenmarker, Checkbox bzw. ``#``-Präfix einer Überschrift.

    Args:
        line: Erste Zeile des Knotens.
        node: Der Knoten.

    Returns:
        Getrimmter Anzeigetext.
    """
    if node.item is not None:
        return line[node.item.body_start:].strip()
    if node.kind is NodeKind.HEADING:
        return line.strip().lstrip("#").strip()
    return line.strip()


def _depth(note: ParsedNote, node: Node) -> int:
    """Tiefe eines Knotens: Anzahl der sichtbaren Vorfahren."""
    depth, parent = 0, node.parent
    while parent is not None:
        if not note.outline.nodes[parent].implicit:
            depth += 1
        parent = note.outline.nodes[parent].parent
    return depth


@dataclass(frozen=True)
class HitRow:
    """Ein Suchtreffer für Listen (Todos, Suche)."""

    day: str
    text: str
    context: str
    done: bool | None
    urgent: bool
    target: Target


def hit_rows(hits: list[Hit]) -> list[HitRow]:
    """Anzeigezeilen für Suchtreffer.

    Args:
        hits: Treffer aus ``NotesService.search``.

    Returns:
        Zeilen mit Datum, Anzeigetext und Kontextpfad.
    """
    rows = []
    for hit in hits:
        is_todo = hit.status in (TodoStatus.OPEN, TodoStatus.DONE)
        text = hit.text.strip()
        if is_todo:
            text = text.split("]", 1)[1].strip() if "]" in text else text
        elif text[:2] in ("- ", "* ", "+ "):
            text = text[2:].strip()
        rows.append(HitRow(day=hit.day.isoformat(), text=text, context=" › ".join(hit.context),
                           done=(hit.status is TodoStatus.DONE) if is_todo else None, urgent=hit.urgent,
                           target=Target(hit.relpath, hit.line_no, hit.text)))
    return rows


class Choice(Enum):
    """Einfache Konfliktentscheidung für Fälle ohne Hunk-Auswahl."""

    HAUPTDATEI = "hauptdatei"
    KONFLIKTVERSION = "konfliktversion"
    BEIDE = "beide"


def conflict_result(case: ConflictCase, choice: Choice) -> bytes:
    """Ergebnis-Bytes einer einfachen Konfliktentscheidung.

    ``BEIDE`` vereinigt verlustfrei (Union, Hauptdatei zuerst) im Zeilenende-Stil
    der Hauptdatei bzw. der Konfliktversion, falls die Hauptdatei fehlt.

    Args:
        case: Konfliktfall.
        choice: Wahl.

    Returns:
        Bytes für ``NotesService.resolve``.
    """
    if choice is Choice.HAUPTDATEI and case.main_bytes is not None:
        return case.main_bytes
    if choice is Choice.KONFLIKTVERSION or case.main_bytes is None:
        return case.conflict_bytes
    a = [l.text for l in SourceText.from_bytes(case.main_bytes).lines]
    b = [l.text for l in SourceText.from_bytes(case.conflict_bytes).lines]
    return render(merge2(a, b).lines(), case.main_bytes)


@dataclass(frozen=True)
class DiffRow:
    """Eine Zeile im Vergleich Hauptdatei ↔ Konfliktversion.

    Attributes:
        side: ``"beide"`` (in beiden gleich), ``"haupt"`` (nur in der
            Hauptdatei), ``"konflikt"`` (nur in der Konfliktversion) oder
            ``"ausgelassen"`` (Platzhalter für übersprungene gleiche Zeilen).
        text: Zeilentext ohne Zeilenende (bei ``"ausgelassen"``: Hinweistext).
    """

    side: str
    text: str


def conflict_diff(case: ConflictCase, context: int = 1) -> list[DiffRow]:
    """Zeilenvergleich für die Konfliktanzeige; lange gleiche Strecken werden gekürzt.

    Args:
        case: Konfliktfall (fehlt die Hauptdatei, ist alles „nur Konfliktversion“).
        context: Gleiche Zeilen, die um jede Abweichung herum sichtbar bleiben.

    Returns:
        Zeilen in Lesereihenfolge. Sind beide Fassungen gleich, nur ``"beide"``-
        bzw. ``"ausgelassen"``-Zeilen.
    """
    main = [l.text for l in SourceText.from_bytes(case.main_bytes or b"").lines]
    other = [l.text for l in SourceText.from_bytes(case.conflict_bytes).lines]
    rows: list[DiffRow] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=main, b=other, autojunk=False).get_opcodes():
        if tag == "equal":
            same = main[i1:i2]
            head = same[:context] if rows else []
            tail = same[len(head):][-context:] if i2 < len(main) or j2 < len(other) else []
            skipped = len(same) - len(head) - len(tail)
            rows += [DiffRow("beide", t) for t in head]
            if skipped > 0:
                rows.append(DiffRow("ausgelassen", f"… {skipped} gleiche Zeile(n) …"))
            rows += [DiffRow("beide", t) for t in tail]
            continue
        rows += [DiffRow("haupt", t) for t in main[i1:i2]]
        rows += [DiffRow("konflikt", t) for t in other[j1:j2]]
    return rows


def conflict_origin(case: ConflictCase) -> str:
    """Woher die Konfliktversion stammt, für Menschen lesbar.

    Args:
        case: Konfliktfall.

    Returns:
        z. B. „von Merkweiser selbst, 21.10.2026 14:03“ oder
        „von Syncthing-Gerät ABCDEFG, 21.10.2026 14:03“.
    """
    stamp = case.conflict.stamp
    when = f"{stamp[6:8]}.{stamp[4:6]}.{stamp[:4]} {stamp[9:11]}:{stamp[11:13]}" if len(stamp) == 15 else stamp
    who = "von Merkweiser selbst" if case.conflict.own else f"von Syncthing-Gerät {case.conflict.device}"
    return f"{who}, {when}"


@dataclass(frozen=True)
class NoteRef:
    """Alles, was eine Oberfläche zum Bearbeiten oder Löschen einer Notiz braucht.

    Attributes:
        relpath: Tagesdatei.
        planned_raw: Dateiinhalt beim Öffnen (Planungsstand; Basis einer
            eventuellen Konfliktdatei in ``NotesService.replace_note_text``).
        original: Inhaltszeilen der Notiz beim Öffnen (Adresse statt ID).
        text: Notiztext für den Editor (Zeilen mit ``\n`` verbunden).
    """

    relpath: str
    planned_raw: bytes
    original: tuple[str, ...]
    text: str


def note_ref(relpath: str, doc: Document, note: ParsedNote) -> NoteRef | None:
    """Adresse und Editortext einer Notiz zum Planungszeitpunkt.

    Args:
        relpath: Tagesdatei.
        doc: Dokument, aus dem die Notiz stammt.
        note: Die Notiz.

    Returns:
        ``NoteRef`` oder ``None`` bei leerer Notiz (nichts zu bearbeiten).
    """
    content = note.note.content
    if content is None:
        return None
    original = tuple(line.text for line in doc.source.lines[content.start:content.end])
    return NoteRef(relpath, doc.source.raw, original, "\n".join(original))
