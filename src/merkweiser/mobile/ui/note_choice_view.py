"""Notizweise Konfliktauflösung (Mobile, W8): eine kompakte Karte je Notiz, Todos direkt erledigt/offen.

Aufbau je Fall (Nutzerwunsch 2026-11-13: kompakt, ohne an Übersicht zu verlieren):

* **Schnellwahl** in einer Zeile („Alle: Haupt · Konflikt · Beide“, ausführlich im
  Tooltip): setzt nur alle Wahlen; bei fehlender Hauptdatei „Alle wiederherstellen“
  und „Version verwerfen“ (mit Bestätigung),
* ggf. eine Karte **Kopfbereich (YAML)**,
* je Notiz eine **Karte**: Kopfzeile „Thema · Art“ (rot „offen“, solange etwas
  fehlt), farbige Vergleichszeilen, eine Umschaltleiste mit Kurztexten; Todos
  mit verschiedenem Häkchen als eine Zeile mit „Erledigt | Offen“ ohne Vorauswahl,
* **„Übernehmen (n offen)“** – erst aktiv, wenn nichts mehr fehlt; was fehlt,
  steht im Tooltip und an den Karten.

Die Wahl liegt je Fall (Pfad und Inhalt beider Fassungen) in der App; jede
Wahl zeichnet die Seite neu (``app.render``), ein bearbeiteter Text nicht.
Ändert sich eine Fassung, gilt eine frische Wahl.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.conflict_views import Choice, DiffRow, conflict_diff
from ...app.note_conflicts import NoteChoices, edit_prefill, entry_diff, entry_problems, head_problems, \
    initial_choices, missing, note_result, quick_select
from ...app.note_plan import KIND_LABELS, Kind, NotePlan, Pick, head_labels, note_plan, pick_labels, sides_meaning
from ...core import conflict_files as cf
from ...core.conflicts import CaseKind
from .diff_box import diff_box, side_chips
from .frontmatter_choices import frontmatter_controls
from .style import EXPLANATION, card

if TYPE_CHECKING:
    from .app import MobileApp

#: Schnellwahl: (Wahl, Farbfelder wie im Vergleich, Erklärung im Tooltip).
QUICK = ((Choice.HAUPTDATEI, ("haupt",), "Hauptdatei behalten"),
         (Choice.KONFLIKTVERSION, ("konflikt",), "Konfliktversion übernehmen"),
         (Choice.BEIDE, ("haupt", "konflikt"), "Zusammenführen"))
#: Welche Fassung(en) eine Wahl zeigt, wenn sie wörtlich „diese Fassung“ heißt (``sides_meaning``).
_PICK_SIDES = {Pick.HAUPT: ("haupt",), Pick.KONFLIKT: ("konflikt",), Pick.BEIDE: ("haupt", "konflikt")}
#: Todo-Wahl: (Wert, Symbol, Tooltip).
_TODO_OPTIONS = (("erledigt", "☑", "Erledigt"), ("offen", "☐", "Offen"))
_BOX = {True: "☑", False: "☐"}
_TITLE_LENGTH = 40


def note_choice_controls(app: "MobileApp", case, cases) -> list[ft.Control]:
    """Schnellwahl, Kopf, Notiz-Karten und Übernehmen-Knopf eines Falls (nicht ``BUSY``).

    Args:
        app: Die laufende App.
        case: Der Konfliktfall.
        cases: Alle Fälle (Geschwister derselben fehlenden Hauptdatei).

    Returns:
        Controls des Entscheidungsteils.
    """
    plan = note_plan(case)
    choices = _choices(app, plan)
    siblings = [c for c in cases if c.conflict.main_relpath == case.conflict.main_relpath]
    controls = [_quick_row(app, plan, choices, siblings)]
    if plan.whole_only:
        controls += [ft.Text(plan.whole_only, size=12), diff_box(conflict_diff(case))]
    if plan.head is not None:
        controls.append(_head_card(app, plan, choices))
    for index, entry in enumerate(plan.entries):
        if entry.kind is not Kind.GLEICH:
            controls.append(_entry_card(app, plan, choices, index))
    same = sum(1 for entry in plan.entries if entry.kind is Kind.GLEICH)
    if same:
        controls.append(ft.Text(f"{same} Notiz(en) gleich", size=11, italic=True, color=EXPLANATION))
    return controls + [_apply_button(app, plan, choices, siblings)]


def _choices(app: "MobileApp", plan: NotePlan) -> NoteChoices:
    """Gemerkte Wahl dieses Falls (neu, wenn sich eine Fassung geändert hat)."""
    case = plan.case
    key = (case.conflict.relpath, cf.sha1(case.main_bytes or b""), cf.sha1(case.conflict_bytes))
    store = app.__dict__.setdefault("_note_choices", {})
    if key not in store:
        store[key] = initial_choices(plan)
    return store[key]


def _quick_row(app: "MobileApp", plan: NotePlan, choices: NoteChoices, siblings) -> ft.Control:
    """Eine Zeile Schnellwahl bzw. Wiederherstellen/Verwerfen bei fehlender Hauptdatei."""
    def quick(choice: Choice):
        def click(_e) -> None:
            quick_select(plan, choices, choice)
            app.render()
        return click

    if plan.main_missing:
        buttons: list[ft.Control] = []
        if plan.entries or plan.head or plan.whole_only:
            buttons.append(ft.TextButton("Alle wiederherstellen", on_click=quick(Choice.KONFLIKTVERSION)))
        buttons.append(_discard_button(app, "Version verwerfen", [plan.case]))
        if len(siblings) > 1:
            buttons.append(_discard_button(app, f"Alle {len(siblings)} verwerfen", siblings))
        return ft.Row(buttons, wrap=True, spacing=0)
    offered = [q for q in QUICK if not (plan.whole_only and q[0] is Choice.BEIDE)]
    return ft.Row([ft.Text("Alle:", size=12)] + [ft.TextButton(content=side_chips(sides), tooltip=long,
                                                               on_click=quick(choice))
                                                 for choice, sides, long in offered], wrap=True, spacing=0)


def _discard_button(app: "MobileApp", label: str, targets) -> ft.Control:
    """Knopf „Verwerfen“ mit Bestätigungsdialog (Version(en) ins Backup)."""
    async def run(_e) -> None:
        app.page.pop_dialog()
        await app.act(lambda s: [s.discard(target) for target in targets])

    def cancel(_e) -> None:
        app.page.pop_dialog()

    def click(_e) -> None:
        text = ("Die Konfliktversion wird entfernt; die Hauptdatei bleibt, wie sie ist. Unter Einstellungen → "
                "Backups lässt sie sich wiederherstellen.") if len(targets) == 1 else \
            f"Alle {len(targets)} Konfliktversionen werden entfernt; unter Einstellungen → Backups bleiben sie erhalten."
        app.page.show_dialog(ft.AlertDialog(title=ft.Text(label), content=ft.Text(text),
                                            actions=[ft.TextButton("Abbrechen", on_click=cancel),
                                                     ft.TextButton("Verwerfen", on_click=run)]))
    return ft.TextButton(label, on_click=click)


def _segments(segments: list[ft.Segment], value: str | None, on_pick) -> ft.SegmentedButton:
    """Einzeilige Umschaltleiste; ``value=None``: nichts vorausgewählt (erneutes Antippen hebt die Wahl auf)."""
    def changed(e) -> None:
        on_pick(e.control.selected[0] if e.control.selected else None)

    return ft.SegmentedButton(segments=segments, selected=[value] if value else [], allow_empty_selection=True,
                              show_selected_icon=False, on_change=changed)


def _pick_segments(options, colored: bool) -> list[ft.Segment]:
    """Segmente einer Wahl: Farbfelder, wenn die Wahl „diese Fassung“ heißt, „✎“ für Bearbeitet, sonst das Wort.

    Der Anzeigetext steht immer im Tooltip.
    """
    def content(pick: Pick, label: str) -> ft.Control:
        if pick is Pick.BEARBEITET:
            return ft.Text("✎", size=12)
        return side_chips(_PICK_SIDES[pick]) if colored else ft.Text(label, size=12)
    return [ft.Segment(value=pick.value, label=content(pick, label), tooltip=label) for pick, label in options]


def _title_row(title: str, problems: list[str]) -> ft.Control:
    """Kopfzeile einer Karte; rot „offen“, solange dort etwas fehlt (Details im Tooltip)."""
    parts: list[ft.Control] = [ft.Text(title, size=12, weight=ft.FontWeight.W_600, expand=True)]
    if problems:
        parts.append(ft.Text("offen", size=11, color=ft.Colors.ERROR, tooltip="; ".join(problems)))
    return ft.Row(parts)


def _head_card(app: "MobileApp", plan: NotePlan, choices: NoteChoices) -> ft.Control:
    """Karte „Kopfbereich (YAML)“: Vergleich, Wahl, bei „Beide“ die Fragen je Eigenschaft."""
    def picked(value: str | None) -> None:
        choices.head = Pick(value) if value else None
        app.render()

    rows = [DiffRow("haupt", line) for line in plan.head.main] + [DiffRow("konflikt", line) for line in plan.head.other]
    controls: list[ft.Control] = [
        _title_row("Kopfbereich (YAML)", head_problems(plan, choices)), diff_box(rows, None, framed=False),
        _segments(_pick_segments(head_labels(plan), sides_meaning(plan, None)),
                  choices.head.value if choices.head else None, picked)]
    if choices.head is Pick.BEIDE:
        controls += frontmatter_controls(plan.head.fm, choices.fm, app.render)
    return card(controls, spacing=4)


def _entry_card(app: "MobileApp", plan: NotePlan, choices: NoteChoices, index: int) -> ft.Control:
    """Karte einer Notiz: Kopfzeile, Vergleich (nicht bei „nur Häkchen“), Wahl, Bearbeiten-Feld, Todos."""
    entry = plan.entries[index]
    first = next((line.strip() for line in entry.a_lines or entry.b_lines if line.strip()), "")
    title = (first if len(first) <= _TITLE_LENGTH else first[:_TITLE_LENGTH - 1] + "…") + " · " + KIND_LABELS[entry.kind]
    if entry.moved:
        title += " · an anderer Stelle"
    controls: list[ft.Control] = [_title_row(title, entry_problems(plan, choices, index))]
    if entry.kind is not Kind.STATUS:
        controls.append(diff_box(entry_diff(entry), None, framed=False))
    pick = choices.picks.get(index)
    if entry.kind is not Kind.STATUS:
        def picked(value: str | None) -> None:
            choices.picks[index] = Pick(value) if value else None
            if choices.picks[index] is Pick.BEARBEITET and index not in choices.texts:
                choices.texts[index] = edit_prefill(entry, choices, index)
            app.render()
        controls.append(_segments(_pick_segments(pick_labels(plan, entry), sides_meaning(plan, entry)),
                                  pick.value if pick else None, picked))
    if pick is Pick.BEARBEITET:
        def edited(e) -> None:
            choices.texts[index] = e.control.value or ""
        controls.append(ft.TextField(value=choices.texts.get(index, ""), multiline=True, min_lines=2, dense=True,
                                     on_change=edited))
    else:
        controls += [_todo_row(app, choices, index, todo) for todo in entry.todos]
    return card(controls, spacing=4)


def _todo_row(app: "MobileApp", choices: NoteChoices, index: int, todo) -> ft.Control:
    """Eine Zeile je Todo: Text, Stand je Fassung als Farbfeld (rot/grün wie im Vergleich), dann ☑ | ☐ ohne Vorauswahl."""
    def picked(value: str | None) -> None:
        if value is None:
            choices.todos.pop((index, todo.row), None)
        else:
            choices.todos[(index, todo.row)] = value == "erledigt"
        app.render()

    state = choices.todos.get((index, todo.row))
    sides = ft.Row([side_chips(("haupt",), _BOX[todo.main_done]), side_chips(("konflikt",), _BOX[not todo.main_done])],
                   spacing=2, tight=True, tooltip="Stand in Hauptdatei (rot) und Konfliktversion (grün)")
    options = [ft.Segment(value=value, label=ft.Text(symbol, size=12), tooltip=tip) for value, symbol, tip in _TODO_OPTIONS]
    return ft.Row([ft.Text(todo.text, size=12, expand=True), sides,
                   _segments(options, None if state is None else ("erledigt" if state else "offen"), picked)],
                  vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _apply_button(app: "MobileApp", plan: NotePlan, choices: NoteChoices, siblings) -> ft.Control:
    """„Übernehmen (n offen)“; erst aktiv, wenn ``missing`` nichts meldet (Liste im Tooltip)."""
    problems = missing(plan, choices)
    manual = tuple(c.conflict.relpath for c in siblings if c is not plan.case) \
        if plan.case.kind is CaseKind.MAIN_DELETED else ()

    async def apply(_e) -> None:
        await app.act(lambda s: s.resolve(plan.case, *note_result(plan, choices), manual))

    label = f"Übernehmen ({len(problems)} offen)" if problems else "Übernehmen"
    button = ft.Button(label, on_click=apply, disabled=bool(problems), tooltip="; ".join(problems) or None)
    on_cards = head_problems(plan, choices) + [p for k in range(len(plan.entries))
                                                for p in entry_problems(plan, choices, k)]
    hint = [p for p in problems if p not in on_cards]  # was an keiner Karte steht (z. B. nichts wiederhergestellt)
    return ft.Column([button] + [ft.Text(p, size=11, color=EXPLANATION) for p in hint], spacing=2)
