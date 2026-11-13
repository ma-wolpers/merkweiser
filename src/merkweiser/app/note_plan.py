"""Notizweise Konfliktauflösung: UI-neutrales Anzeigemodell und Ergebnis (W8).

Ein ``NotePlan`` zerlegt einen Konfliktfall in Einträge je Notiz
(``core/merge/notes.py``) und ggf. einen Eintrag für den YAML-Kopf. Wahl und
Ergebnis stehen in ``note_conflicts``; die Oberfläche rendert nur.

Arten und Wahlen (Nutzerentscheidungen 2026-11-10, ``PLAN-SPAETERE-SCHRITTE.md`` W8):

* ``GLEICH`` – in beiden Fassungen gleich (eingeklappt, keine Wahl),
* ``STATUS`` – nur Häkchen verschieden: nur die Todo-Wahl erledigt/offen,
* ``GEAENDERT`` – Hauptdatei / Konfliktversion / Beide / Bearbeitet,
* ``NUR_HAUPT`` – Behalten / Entfernen / Bearbeitet,
* ``NUR_KONFLIKT`` – Übernehmen (bei fehlender Hauptdatei: Wiederherstellen) / Weglassen / Bearbeitet.

„Beide“ übernimmt Gemeinsames einmal, abweichende Zeilen erst aus der
Hauptdatei, dann aus der Konfliktversion. Todos mit verschiedenem Häkchen
werden **nie** vorausgewählt; Notizen mit Hunk-Überlappung auch nicht. Sonst
ist der Merge-Vorschlag (``case.merge``) vorausgewählt, wo er eindeutig passt.

Ergibt die Wahl Zeile für Zeile genau eine der beiden Fassungen, sind die
Ergebnis-Bytes **byte-genau** deren Inhalt (Schnellwahl „Hauptdatei behalten“
bzw. „Konfliktversion übernehmen“). Offener Kopf oder nicht unterstütztes
Encoding → nur ganze Fassungen (``whole_only``).

BAUSTELLE(Vorschläge): Vorschläge aus der Beobachtungs-Historie gibt es noch nicht.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.conflicts import ConflictCase
from ..core.inline import parse_list_item
from ..core.merge.frontmatter import OPEN, FmMerge, Head, merge_frontmatter, split
from ..core.merge.model import A, B, Cert, Hunk
from ..core.merge.notes import STATUS_MASK, BodyNotes, Row, body_notes, note_rows, pair_notes, status_key
from ..core.source import SourceText

class Kind(Enum):
    """Art eines Notiz-Eintrags."""

    GLEICH = "gleich"
    STATUS = "status"
    GEAENDERT = "geaendert"
    NUR_HAUPT = "nur_haupt"
    NUR_KONFLIKT = "nur_konflikt"


class Pick(Enum):
    """Wahl für einen Eintrag (Bedeutung je ``Kind``, siehe ``pick_labels``)."""

    HAUPT = "haupt"
    KONFLIKT = "konflikt"
    BEIDE = "beide"
    BEARBEITET = "bearbeitet"


@dataclass(frozen=True)
class Todo:
    """Ein Todo, dessen Häkchen sich zwischen den Fassungen unterscheidet (R1).

    Attributes:
        row: Index des Abschnitts in ``NoteEntry.rows``.
        open_line: Zeile mit ``[ ]`` (byte-genau aus der Fassung, in der es offen ist).
        done_line: Zeile mit ``[x]``/``[X]`` (byte-genau aus der anderen Fassung).
        main_done: In der Hauptdatei erledigt.
    """

    row: int
    open_line: str
    done_line: str
    main_done: bool

    @property
    def text(self) -> str:
        """Text des Todos ohne Marker und Häkchen (für die Anzeige)."""
        item = parse_list_item(self.open_line)
        return self.open_line[item.body_start:].strip() if item else self.open_line.strip()


@dataclass(frozen=True)
class NoteEntry:
    """Eine Notiz (bzw. ein Notizpaar) mit Vorschlag.

    Attributes:
        kind: Art.
        number: Anzeigenummer (ab 1; ``0`` bei ``GLEICH``).
        a_index: Notiz in der Hauptdatei oder ``None``.
        b_index: Notiz in der Konfliktversion oder ``None``.
        a_lines: Zeilen in der Hauptdatei.
        b_lines: Zeilen in der Konfliktversion.
        rows: Zeilenabschnitte eines Paars (sonst leer).
        todos: Todos mit verschiedenem Häkchen.
        suggested: Vorausgewählte Wahl oder ``None``.
        moved: Gleicher Text steht in der anderen Fassung an anderer Stelle.
    """

    kind: Kind
    number: int
    a_index: int | None
    b_index: int | None
    a_lines: tuple[str, ...]
    b_lines: tuple[str, ...]
    rows: tuple[Row, ...] = ()
    todos: tuple[Todo, ...] = ()
    suggested: Pick | None = None
    moved: bool = False


@dataclass(frozen=True)
class HeadEntry:
    """Der YAML-Kopf, falls er sich unterscheidet.

    Attributes:
        main: Kopfzeilen der Hauptdatei (inkl. Begrenzer; leer ohne Kopf).
        other: Kopfzeilen der Konfliktversion.
        fm: Kopf-Merge für „Beide“ (``None``, wenn die Hauptdatei fehlt).
        suggested: ``BEIDE``, wenn der Fall schon einen Kopf-Merge hat, sonst ``None``.
    """

    main: tuple[str, ...]
    other: tuple[str, ...]
    fm: FmMerge | None
    suggested: Pick | None


@dataclass(frozen=True)
class NotePlan:
    """Anzeigemodell eines Konfliktfalls.

    Attributes:
        case: Der Fall.
        head: Kopf-Eintrag oder ``None``.
        entries: Einträge in Anzeigereihenfolge.
        a: Rumpf der Hauptdatei (``None``, wenn sie fehlt oder ``whole_only``).
        b: Rumpf der Konfliktversion (``None`` bei ``whole_only``).
        whole_only: Grund, warum nur ganze Fassungen wählbar sind, sonst ``""``.
    """

    case: ConflictCase
    head: HeadEntry | None
    entries: tuple[NoteEntry, ...]
    a: BodyNotes | None
    b: BodyNotes | None
    whole_only: str = ""

    @property
    def main_missing(self) -> bool:
        """``True``, wenn die Hauptdatei fehlt (Wiederherstellen statt Übernehmen)."""
        return self.case.main_bytes is None




#: Optionen je Art: (Wahl, Anzeigetext, Kurztext für die Umschaltleiste). Einzige Quelle der Texte.
_LABELS = {
    Kind.GEAENDERT: ((Pick.HAUPT, "Hauptdatei", "Haupt"), (Pick.KONFLIKT, "Konfliktversion", "Konflikt"),
                     (Pick.BEIDE, "Beide", "Beide"), (Pick.BEARBEITET, "Bearbeitet", "✎")),
    Kind.NUR_HAUPT: ((Pick.HAUPT, "Behalten", "Behalten"), (Pick.KONFLIKT, "Entfernen", "Entfernen"),
                     (Pick.BEARBEITET, "Bearbeitet", "✎")),
    Kind.NUR_KONFLIKT: ((Pick.KONFLIKT, "Übernehmen", "Übernehmen"), (Pick.HAUPT, "Weglassen", "Weglassen"),
                        (Pick.BEARBEITET, "Bearbeitet", "✎")),
}
_RESTORE = (Pick.KONFLIKT, "Wiederherstellen", "Wiederherstellen")
_HEAD = ((Pick.HAUPT, "Hauptdatei", "Haupt"), (Pick.KONFLIKT, "Konfliktversion", "Konflikt"),
         (Pick.BEIDE, "Beide (je Eigenschaft)", "Beide"))

#: Kurze Anzeigetexte der Arten (Kopfzeile einer Notiz-Karte).
KIND_LABELS = {Kind.GLEICH: "gleich", Kind.STATUS: "nur Häkchen", Kind.GEAENDERT: "geändert",
               Kind.NUR_HAUPT: "nur Hauptdatei", Kind.NUR_KONFLIKT: "nur Konfliktversion"}


def _pairs(labels, short: bool) -> tuple[tuple[Pick, str], ...]:
    """``(Wahl, Text)`` aus der Tabelle, lang oder kurz."""
    return tuple((pick, brief if short else text) for pick, text, brief in labels)


def pick_labels(plan: NotePlan, entry: NoteEntry, short: bool = False) -> tuple[tuple[Pick, str], ...]:
    """Wählbare Optionen eines Eintrags mit Anzeigetext (leer bei ``GLEICH``/``STATUS``).

    Args:
        plan: Plan (bei fehlender Hauptdatei heißt „Übernehmen“ „Wiederherstellen“).
        entry: Eintrag.
        short: Kurztexte für die Umschaltleiste statt der Texte für Entscheidung und Hinweise.
    """
    labels = _LABELS.get(entry.kind, ())
    if plan.main_missing and entry.kind is Kind.NUR_KONFLIKT:
        labels = (_RESTORE,) + labels[1:]
    return _pairs(labels, short)


def head_labels(plan: NotePlan, short: bool = False) -> tuple[tuple[Pick, str], ...]:
    """Optionen für den Kopf (ohne „Beide“, wenn die Hauptdatei fehlt)."""
    if plan.main_missing:
        return _pairs((_RESTORE, _LABELS[Kind.NUR_KONFLIKT][1]), short)
    return _pairs(_HEAD, short)


# --- Plan ------------------------------------------------------------------------------


def note_plan(case: ConflictCase) -> NotePlan:
    """Baut das Anzeigemodell eines Konfliktfalls.

    Args:
        case: Der Fall (``BUSY`` wird von der Oberfläche nicht entschieden).

    Returns:
        Einträge je Notiz mit Vorschlägen; bei offenem Kopf oder nicht
        unterstütztem Encoding nur ``whole_only``.
    """
    sides = [raw for raw in (case.main_bytes, case.conflict_bytes) if raw is not None]
    if not all(SourceText.from_bytes(raw).writable for raw in sides):
        return NotePlan(case, None, (), None, None, "Encoding nicht unterstützt – nur ganze Fassungen wählbar")
    heads = [split(raw) for raw in sides]
    if any(head.state == OPEN for head, _body in heads):
        return NotePlan(case, None, (), None, None, "Kopfbereich ohne schließendes --- – nur ganze Fassungen wählbar")
    (head_b, b_body) = heads[-1]
    head_a, a_body = heads[0] if case.main_bytes is not None else (None, None)
    a, b = (body_notes(a_body) if a_body is not None else None), body_notes(b_body)
    return NotePlan(case, _head_entry(case, head_a, head_b), _entries(a, b, case), a, b)


def _head_entry(case: ConflictCase, head_a: Head | None, head_b: Head) -> HeadEntry | None:
    """Kopf-Eintrag, wenn sich die Köpfe unterscheiden."""
    main = head_a.lines if head_a is not None else ()
    if main == head_b.lines:
        return None
    if head_a is None:
        return HeadEntry(main, head_b.lines, None, None)
    fm = case.frontmatter if case.frontmatter is not None else merge_frontmatter(head_a, head_b)
    return HeadEntry(main, head_b.lines, fm, Pick.BEIDE if case.frontmatter is not None else None)


def _entries(a: BodyNotes | None, b: BodyNotes, case: ConflictCase) -> tuple[NoteEntry, ...]:
    """Einträge aus der Notiz-Zuordnung, mit Nummern, Verschiebe-Hinweis und Vorschlag."""
    pairs = pair_notes(a, b) if a is not None else [(None, j) for j in range(len(b.spans))]
    raw = [_entry(a, b, i, j) for i, j in pairs]
    texts_a = {e.a_lines for e in raw if e.kind is Kind.NUR_HAUPT}
    texts_b = {e.b_lines for e in raw if e.kind is Kind.NUR_KONFLIKT}
    suggestions = _suggestions(raw, a, b, case)
    out, number = [], 0
    for entry, suggested in zip(raw, suggestions):
        number += entry.kind is not Kind.GLEICH
        moved = (entry.kind is Kind.NUR_HAUPT and entry.a_lines in texts_b) or \
                (entry.kind is Kind.NUR_KONFLIKT and entry.b_lines in texts_a)
        out.append(NoteEntry(entry.kind, number if entry.kind is not Kind.GLEICH else 0, entry.a_index,
                             entry.b_index, entry.a_lines, entry.b_lines, entry.rows, entry.todos, suggested, moved))
    return tuple(out)


def _entry(a: BodyNotes | None, b: BodyNotes, i: int | None, j: int | None) -> NoteEntry:
    """Ein Eintrag ohne Nummer und Vorschlag."""
    a_lines = a.note(i) if a is not None and i is not None else ()
    b_lines = b.note(j) if j is not None else ()
    if i is None:
        return NoteEntry(Kind.NUR_KONFLIKT, 0, None, j, a_lines, b_lines)
    if j is None:
        return NoteEntry(Kind.NUR_HAUPT, 0, i, None, a_lines, b_lines)
    rows = note_rows(a_lines, a.note_keys(i), b_lines, b.note_keys(j))
    todos = tuple(_todo(r, row) for r, row in enumerate(rows) if row.cert is Cert.R1)
    if all(row.same for row in rows):
        kind = Kind.GLEICH
    elif all(row.same or row.cert is not None for row in rows):
        kind = Kind.STATUS
    else:
        kind = Kind.GEAENDERT
    return NoteEntry(kind, 0, i, j, a_lines, b_lines, rows, todos)


def _todo(index: int, row: Row) -> Todo:
    """Todo aus einem R1-Abschnitt (offene und erledigte Zeile byte-genau)."""
    a_line, b_line = row.a[0], row.b[0]
    main_done = a_line[status_key(a_line).index(STATUS_MASK)] in "xX"
    return Todo(index, b_line if main_done else a_line, a_line if main_done else b_line, main_done)


def _suggestions(entries: list[NoteEntry], a: BodyNotes | None, b: BodyNotes,
                 case: ConflictCase) -> list[Pick | None]:
    """Vorauswahl je Eintrag aus dem Merge-Vorschlag (``None`` bei Hunk-Überlappung oder ohne Treffer).

    Jede Ausgabezeile des Merges gehört zum Eintrag ihrer ersten A-Quelle,
    sonst ihrer ersten B-Quelle; Zeilen in Lücken zählen nicht. Verglichen wird
    mit maskierten Häkchen (Todos werden nie vorausgewählt).
    """
    if case.merge is None or a is None:
        return [None] * len(entries)
    owner_a = {line: k for k, e in enumerate(entries) if e.a_index is not None for line in range(*a.spans[e.a_index])}
    owner_b = {line: k for k, e in enumerate(entries) if e.b_index is not None for line in range(*b.spans[e.b_index])}
    outputs: dict[int, list[str]] = {k: [] for k in range(len(entries))}
    conflicted: set[int] = set()
    for segment in case.merge.segments:
        if isinstance(segment, Hunk):
            conflicted |= {owner_a[i] for i in range(*segment.a_range) if i in owner_a}
            conflicted |= {owner_b[j] for j in range(*segment.b_range) if j in owner_b}
            continue
        source = next((o for o in segment.sources if o.side == A), None) \
            or next((o for o in segment.sources if o.side == B), None)
        owner = None if source is None else (owner_a if source.side == A else owner_b).get(source.index)
        if owner is not None:
            outputs[owner].append(status_key(segment.text))
    return [None if k in conflicted or e.kind in (Kind.GLEICH, Kind.STATUS) else _matching_pick(e, outputs[k])
            for k, e in enumerate(entries)]


def _matching_pick(entry: NoteEntry, output: list[str]) -> Pick | None:
    """Erste Wahl, deren Ergebnis (Häkchen maskiert) dem Merge-Vorschlag entspricht."""
    for pick, _label, _short in _LABELS[entry.kind]:
        if pick is not Pick.BEARBEITET and [status_key(l) for l in render_entry(entry, pick, {})] == output:
            return pick
    return None

def render_entry(entry: NoteEntry, pick: Pick, todos: dict[int, bool], text: str = "") -> tuple[str, ...]:
    """Zeilen eines Eintrags für eine Wahl (leer = Notiz entfällt).

    Args:
        entry: Eintrag.
        pick: Wahl (bei ``GLEICH``/``STATUS`` zählt nur ``KONFLIKT`` für ``[x]``/``[X]``).
        todos: Abschnitt → erledigt; fehlt ein Todo, gilt der Stand der Hauptdatei.
        text: Bearbeiteter Text (nur bei ``BEARBEITET``).

    Returns:
        Zeilen ohne Zeilenende.
    """
    if pick is Pick.BEARBEITET:
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return tuple(lines)
    if entry.kind is Kind.NUR_HAUPT:
        return entry.a_lines if pick is Pick.HAUPT else ()
    if entry.kind is Kind.NUR_KONFLIKT:
        return entry.b_lines if pick is Pick.KONFLIKT else ()
    by_row = {todo.row: todo for todo in entry.todos}
    out: list[str] = []
    for r, row in enumerate(entry.rows):
        if row.same:
            out += row.a
        elif row.cert is Cert.R1:
            todo = by_row[r]
            out.append(todo.done_line if todos.get(r, todo.main_done) else todo.open_line)
        elif row.cert is Cert.R2:
            out += row.b if pick is Pick.KONFLIKT else row.a
        else:
            out += {Pick.HAUPT: row.a, Pick.KONFLIKT: row.b, Pick.BEIDE: row.a + row.b}[pick]
    return tuple(out)
