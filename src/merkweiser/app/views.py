"""UI-neutrale Anzeigemodelle für Desktop und Mobile (keine Flet-/Tk-Abhängigkeit).

Wandelt Dokumente und Suchtreffer in einfache, testbare Zeilen um (Konflikte:
``conflict_views``). Die Oberflächen rendern nur noch und reichen ``Target``-Adressen an den
``NotesService`` zurück.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..core.document import Document, ParsedNote
from ..core.inline import TodoStatus
from ..core.outline import Node
from ..core.patch import Target
from ..core.query import Hit


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
    """Anzeigetext ohne Listenmarker und Checkbox.

    Args:
        line: Erste Zeile des Knotens.
        node: Der Knoten.

    Returns:
        Getrimmter Anzeigetext.
    """
    if node.item is not None:
        return line[node.item.body_start:].strip()
    return line.strip()  # Überschriften sind gewöhnlicher Text: „# Woche“ bleibt sichtbar


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


WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def move_choices(today: date) -> list[tuple[str, date]]:
    """Schnellwahl der Zieldaten beim Verschieben eines Todos.

    Args:
        today: Heutiges Datum (aus der Clock des Service).

    Returns:
        ``(Beschriftung, Datum)`` für morgen, übermorgen, den nächsten Montag
        (nach übermorgen; sonst eine Woche später) und in einer Woche, ohne
        doppelte Daten. Die Beschriftung nennt Wochentag und Datum.
    """
    monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    if monday <= today + timedelta(days=2):
        monday += timedelta(days=7)
    raw = [("Morgen", today + timedelta(days=1)), ("Übermorgen", today + timedelta(days=2)),
           ("Nächster Montag", monday), ("In einer Woche", today + timedelta(days=7))]
    seen: set[date] = set()
    choices = []
    for label, day in raw:
        if day not in seen:
            seen.add(day)
            choices.append((f"{label} ({WEEKDAYS[day.weekday()]}, {day:%d.%m.})", day))
    return choices
