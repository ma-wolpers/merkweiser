"""Notizweise Konfliktauflösung: Wahl, Schnellwahl, offene Punkte und Ergebnis (W8).

Das Anzeigemodell (Einträge, Arten, Vorschläge) steht in ``note_plan``; hier
liegt, was die Oberfläche mit der Wahl tut: ``initial_choices`` (nur
Vorschläge, Todos offen), ``quick_select`` (Schnellwahl), ``missing`` (was noch
fehlt), ``note_result`` (Bytes für ``NotesService.resolve``; byte-genau eine der
Fassungen, wenn die Wahl ihr Zeile für Zeile entspricht), ``entry_diff`` und
``edit_prefill`` für die Anzeige.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.conflicts import render
from ..core.merge.frontmatter import split
from ..core.merge.model import Cert
from ..core.merge.notes import STATUS_MASK, BodyNotes, status_key
from ..core.source import SourceText
from .conflict_views import Choice, DiffRow
from .note_plan import Kind, NoteEntry, NotePlan, Pick, pick_labels, render_entry

@dataclass
class NoteChoices:
    """Wahl der Oberfläche (veränderlich).

    Attributes:
        picks: Wahl je Eintragsindex (``None`` = noch offen).
        texts: Bearbeiteter Text je Eintragsindex (nur bei ``BEARBEITET``).
        todos: ``(Eintrag, Abschnitt) → erledigt`` (fehlt = noch offen).
        head: Wahl für den Kopf.
        fm: Entscheidungen je Kopf-Konflikt (bei ``head`` = ``BEIDE``).
        whole: Wahl im Ganzdatei-Modus (nur ``HAUPT``/``KONFLIKT``).
    """

    picks: dict[int, Pick | None] = field(default_factory=dict)
    texts: dict[int, str] = field(default_factory=dict)
    todos: dict[tuple[int, int], bool] = field(default_factory=dict)
    head: Pick | None = None
    fm: dict[int, str] = field(default_factory=dict)
    whole: Pick | None = None

def initial_choices(plan: NotePlan) -> NoteChoices:
    """Startwahl: nur Vorschläge; Todos und Widersprüche bleiben offen."""
    picks = {k: Pick.HAUPT if e.kind in (Kind.GLEICH, Kind.STATUS) else e.suggested
             for k, e in enumerate(plan.entries)}
    return NoteChoices(picks=picks, head=plan.head.suggested if plan.head else None)


def quick_select(plan: NotePlan, choices: NoteChoices, choice: Choice) -> None:
    """Setzt alle Wahlen auf einmal (Schnellwahl; angewendet wird erst mit ``note_result``).

    ``HAUPTDATEI``/``KONFLIKTVERSION`` übernehmen überall diese Seite (Todos wie
    dort). ``BEIDE`` („Zusammenführen“): geänderte Notizen „Beide“, einseitige
    behalten bzw. übernehmen, Todos erledigt (Regel R1), Kopf je Eigenschaft.

    Raises:
        ValueError: ``BEIDE`` im Ganzdatei-Modus.
    """
    side = {Choice.HAUPTDATEI: Pick.HAUPT, Choice.KONFLIKTVERSION: Pick.KONFLIKT}.get(choice)
    if plan.whole_only:
        if side is None:
            raise ValueError(plan.whole_only)
        choices.whole = side
        return
    merge = {Kind.GEAENDERT: Pick.BEIDE, Kind.NUR_HAUPT: Pick.HAUPT, Kind.NUR_KONFLIKT: Pick.KONFLIKT}
    for k, entry in enumerate(plan.entries):
        choices.picks[k] = side or merge.get(entry.kind, Pick.HAUPT)
        for todo in entry.todos:
            choices.todos[(k, todo.row)] = True if side is None else todo.main_done == (side is Pick.HAUPT)
    if plan.head is not None:
        choices.head = side or (Pick.BEIDE if plan.head.fm is not None else Pick.KONFLIKT)


def head_problems(plan: NotePlan, choices: NoteChoices) -> list[str]:
    """Was am Kopfbereich noch fehlt (leer ohne Kopf-Eintrag oder wenn entschieden)."""
    if plan.head is None:
        return []
    if choices.head is None:
        return ["Kopfbereich: Wahl fehlt"]
    if choices.head is Pick.BEIDE:
        try:
            plan.head.fm.resolve(choices.fm)
        except ValueError:
            return ["Kopfbereich: Entscheidung je Eigenschaft fehlt"]
    return []


def entry_problems(plan: NotePlan, choices: NoteChoices, index: int) -> list[str]:
    """Was an Eintrag ``index`` noch fehlt: die Wahl selbst bzw. unentschiedene Todos."""
    entry, pick = plan.entries[index], choices.picks.get(index)
    if pick is None:
        return [f"Notiz {entry.number}: Wahl fehlt"]
    if pick is Pick.BEARBEITET:
        return []
    return [f"Todo „{todo.text}“: erledigt oder offen?"
            for todo in entry.todos if (index, todo.row) not in choices.todos]


def missing(plan: NotePlan, choices: NoteChoices) -> list[str]:
    """Was noch zu entscheiden ist (leer = „Auswahl übernehmen“ möglich).

    Setzt sich aus ``head_problems`` und ``entry_problems`` zusammen (dieselben
    Regeln markieren in der Oberfläche die offenen Karten); danach, wenn sonst
    nichts fehlt, der Hinweis, dass bei fehlender Hauptdatei nichts wiederhergestellt würde.

    Returns:
        Deutsche Hinweise in Anzeigereihenfolge.
    """
    if plan.whole_only:
        return [] if choices.whole else ["Ganze Fassung wählen"]
    out = head_problems(plan, choices)
    for k in range(len(plan.entries)):
        out += entry_problems(plan, choices, k)
    if not out and plan.main_missing and not _body(plan, choices) and choices.head is not Pick.KONFLIKT:
        out.append("Nichts zum Wiederherstellen gewählt – zum Entfernen „Version verwerfen“ nutzen")
    return out


def note_result(plan: NotePlan, choices: NoteChoices) -> tuple[bytes, str]:
    """Ergebnis-Bytes und lesbare Entscheidung für ``NotesService.resolve``.

    Raises:
        ValueError: ``missing`` ist nicht leer.
    """
    problems = missing(plan, choices)
    if problems:
        raise ValueError("; ".join(problems))
    main, conflict = plan.case.main_bytes, plan.case.conflict_bytes
    if plan.whole_only:
        data = main if choices.whole is Pick.HAUPT and main is not None else conflict
    else:
        lines = _head_lines(plan, choices) + _body(plan, choices)
        exact = [raw for raw in (main, conflict) if raw is not None and lines == _texts(raw)]
        data = exact[0] if exact else render(lines, main if main is not None else conflict)
    return data, _decision(plan, choices, data)


def _texts(raw: bytes) -> tuple[str, ...]:
    """Zeilen einer Fassung ohne Zeilenende."""
    return tuple(line.text for line in SourceText.from_bytes(raw).lines)


def _head_lines(plan: NotePlan, choices: NoteChoices) -> tuple[str, ...]:
    """Kopfzeilen laut Wahl (ohne Kopf-Eintrag: der gemeinsame Kopf)."""
    if plan.head is None:
        main = plan.case.main_bytes
        return split(main if main is not None else plan.case.conflict_bytes)[0].lines
    if choices.head is Pick.BEIDE:
        return tuple(plan.head.fm.resolve(choices.fm))
    return plan.head.other if choices.head is Pick.KONFLIKT else plan.head.main


def _body(plan: NotePlan, choices: NoteChoices) -> tuple[str, ...]:
    """Rumpfzeilen laut Wahl, mit Lücken aus der passenden Fassung.

    Zwischen zwei ausgegebenen Notizen steht die Lücke der Fassung, in der sie
    direkt aufeinander folgen (bevorzugt die Hauptdatei, außer beide stammen aus
    der Konfliktversion), sonst eine Leerzeile.
    """
    emitted = []
    for k, entry in enumerate(plan.entries):
        pick = choices.picks.get(k) or Pick.HAUPT
        todos = {row: done for (index, row), done in choices.todos.items() if index == k}
        lines = render_entry(entry, pick, todos, choices.texts.get(k, ""))
        if lines:
            source = "B" if entry.a_index is None or (entry.b_index is not None and pick is Pick.KONFLIKT) else "A"
            emitted.append((entry, source, lines))
    if not emitted:
        return ()
    out = list(_notes(plan, emitted[0][1]).gap(0))
    for number, (entry, source, lines) in enumerate(emitted):
        if number:
            out += _between(plan, emitted[number - 1], (entry, source))
        out += lines
    last = _notes(plan, emitted[-1][1])
    return tuple(out + list(last.gap(len(last.spans))))


def _notes(plan: NotePlan, source: str) -> BodyNotes:
    """Rumpf der Fassung ``A`` bzw. ``B``."""
    return plan.a if source == "A" else plan.b


def _between(plan: NotePlan, prev: tuple, cur: tuple) -> tuple[str, ...]:
    """Lücke zwischen zwei ausgegebenen Einträgen (siehe ``_body``)."""
    order = ("B", "A") if prev[1] == cur[1] == "B" else ("A", "B")
    for side in order:
        index = (lambda e: e.a_index) if side == "A" else (lambda e: e.b_index)
        before, after = index(prev[0]), index(cur[0])
        if before is not None and after is not None and after == before + 1:
            return _notes(plan, side).gap(after)
    return ("",)


def _decision(plan: NotePlan, choices: NoteChoices, data: bytes) -> str:
    """Lesbare Entscheidung (für Op-Manifest, Backups und Hinweise)."""
    if data == plan.case.main_bytes:
        return "Hauptdatei behalten"
    if data == plan.case.conflict_bytes:
        return "Version wiederhergestellt" if plan.main_missing else "Konfliktversion übernehmen"
    names = [f"Notiz {e.number}: {dict(pick_labels(plan, e))[choices.picks[k]]}"
             for k, e in enumerate(plan.entries) if e.kind not in (Kind.GLEICH, Kind.STATUS)]
    done = sum(1 for value in choices.todos.values() if value)
    todos = f"; Todos: {done} erledigt, {len(choices.todos) - done} offen" if choices.todos else ""
    return "Notizweise – " + (", ".join(names) or "nur Todos") + todos


def entry_diff(entry: NoteEntry) -> list[DiffRow]:
    """Vergleichszeilen eines Eintrags; Todos mit verschiedenem Häkchen als ``[?]``."""
    if entry.kind is Kind.NUR_HAUPT:
        return [DiffRow("haupt", line) for line in entry.a_lines]
    if entry.kind is Kind.NUR_KONFLIKT:
        return [DiffRow("konflikt", line) for line in entry.b_lines]
    rows: list[DiffRow] = []
    for row in entry.rows:
        if row.cert is Cert.R1:
            rows.append(DiffRow("beide", status_key(row.a[0]).replace(STATUS_MASK, "?")))
        elif row.same or row.cert is Cert.R2:
            rows += [DiffRow("beide", line) for line in row.a]
        else:
            rows += [DiffRow("haupt", line) for line in row.a] + [DiffRow("konflikt", line) for line in row.b]
    return rows


def edit_prefill(entry: NoteEntry, choices: NoteChoices, index: int) -> str:
    """Vorbefüllung des Bearbeiten-Felds: aktuelle Wahl, sonst „Beide“ bzw. die vorhandene Seite."""
    pick = choices.picks.get(index)
    if pick in (None, Pick.BEARBEITET):
        pick = {Kind.NUR_HAUPT: Pick.HAUPT, Kind.NUR_KONFLIKT: Pick.KONFLIKT}.get(entry.kind, Pick.BEIDE)
    todos = {row: done for (k, row), done in choices.todos.items() if k == index}
    return "\n".join(render_entry(entry, pick, todos))
