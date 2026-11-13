"""Notizweise Konfliktauflösung (Mobile, W8): eine Wahl je Notiz, Todos direkt erledigt/offen.

Ersetzt die abschnittsweise Auswahl. Aufbau je Fall:

* **Schnellwahl** („Hauptdatei behalten“, „Konfliktversion übernehmen“,
  „Zusammenführen“): setzt nur alle Wahlen; bei fehlender Hauptdatei
  „Alle Notizen wiederherstellen“ und „Version verwerfen“ (mit Bestätigung),
* ggf. **Kopfbereich (YAML)**,
* je Notiz Vergleich, Wahl und – bei verschiedenem Häkchen – „Erledigt/Offen“
  ohne Vorauswahl,
* **„Noch offen: …“** und „Auswahl übernehmen“ (erst aktiv, wenn nichts mehr fehlt).

Die Wahl liegt je Fall (Pfad und Inhalt beider Fassungen) in der App; jede
Wahl zeichnet die Seite neu (``app.render``), ein bearbeiteter Text nicht.
Ändert sich eine Fassung, gilt eine frische Wahl.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.conflict_views import Choice, DiffRow, conflict_diff
from ...app.note_conflicts import NoteChoices, edit_prefill, entry_diff, initial_choices, missing, note_result, \
    quick_select
from ...app.note_plan import KIND_LABELS, Kind, NotePlan, Pick, head_labels, note_plan, pick_labels
from ...core import conflict_files as cf
from ...core.conflicts import CaseKind
from .diff_box import diff_box
from .frontmatter_choices import frontmatter_controls

if TYPE_CHECKING:
    from .app import MobileApp

#: Schnellwahl-Knöpfe: (Wahl, Beschriftung).
QUICK = ((Choice.HAUPTDATEI, "Hauptdatei behalten"), (Choice.KONFLIKTVERSION, "Konfliktversion übernehmen"),
         (Choice.BEIDE, "Zusammenführen"))
_TODO_OPTIONS = (("erledigt", "Erledigt"), ("offen", "Offen"))


def note_choice_controls(app: "MobileApp", case, cases) -> list[ft.Control]:
    """Schnellwahl, Kopf, Notizen und Übernehmen-Knopf eines Falls (nicht ``BUSY``).

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
    controls = _quick_controls(app, plan, choices, siblings)
    if plan.whole_only:
        controls += [ft.Text(plan.whole_only, size=12), diff_box(conflict_diff(case))]
    controls += _head_controls(app, plan, choices)
    same = sum(1 for entry in plan.entries if entry.kind is Kind.GLEICH)
    if same:
        controls.append(ft.Text(f"{same} Notiz(en) in beiden Fassungen gleich.", size=12, italic=True))
    for index, entry in enumerate(plan.entries):
        if entry.kind is not Kind.GLEICH:
            controls += _entry_controls(app, plan, choices, index)
    return controls + _footer(app, plan, choices, siblings)


def _choices(app: "MobileApp", plan: NotePlan) -> NoteChoices:
    """Gemerkte Wahl dieses Falls (neu, wenn sich eine Fassung geändert hat)."""
    case = plan.case
    key = (case.conflict.relpath, cf.sha1(case.main_bytes or b""), cf.sha1(case.conflict_bytes))
    store = app.__dict__.setdefault("_note_choices", {})
    if key not in store:
        store[key] = initial_choices(plan)
    return store[key]


def _quick_controls(app: "MobileApp", plan: NotePlan, choices: NoteChoices, siblings) -> list[ft.Control]:
    """Schnellwahl bzw. Wiederherstellen/Verwerfen bei fehlender Hauptdatei."""
    def quick(choice: Choice):
        def click(_e) -> None:
            quick_select(plan, choices, choice)
            app.render()
        return click

    if plan.main_missing:
        buttons: list[ft.Control] = []
        if plan.entries or plan.head or plan.whole_only:
            buttons.append(ft.Button("Alle Notizen wiederherstellen", on_click=quick(Choice.KONFLIKTVERSION)))
        buttons.append(_discard_button(app, "Version verwerfen", [plan.case]))
        if len(siblings) > 1:
            buttons.append(_discard_button(app, f"Alle {len(siblings)} Versionen verwerfen", siblings))
        return [ft.Row(buttons, wrap=True)]
    offered = [(c, label) for c, label in QUICK if not (plan.whole_only and c is Choice.BEIDE)]
    return [ft.Row([ft.OutlinedButton(label, on_click=quick(c)) for c, label in offered], wrap=True),
            ft.Text("Setzt alle Notizen auf einmal; angewendet wird erst mit „Auswahl übernehmen“.", size=11)]


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


def _radio(options, value: str | None, on_change) -> ft.RadioGroup:
    """Auswahl als Zeile von Optionen (``value=None``: nichts vorausgewählt)."""
    return ft.RadioGroup(content=ft.Row([ft.Radio(value=v, label=label) for v, label in options], wrap=True),
                         value=value, on_change=on_change)


def _head_controls(app: "MobileApp", plan: NotePlan, choices: NoteChoices) -> list[ft.Control]:
    """Kopfbereich (YAML): Wahl der Fassung, bei „Beide“ die Fragen je Eigenschaft."""
    if plan.head is None:
        return []

    def picked(e) -> None:
        choices.head = Pick(e.control.value)
        app.render()

    controls: list[ft.Control] = [
        ft.Text("Kopfbereich (YAML)", weight=ft.FontWeight.BOLD),
        diff_box([*_lines("haupt", plan.head.main), *_lines("konflikt", plan.head.other)], None),
        _radio([(p.value, label) for p, label in head_labels(plan)],
               choices.head.value if choices.head else None, picked)]
    if choices.head is Pick.BEIDE:
        controls += frontmatter_controls(plan.head.fm, choices.fm, app.render)
    return controls


def _lines(side: str, lines) -> list[DiffRow]:
    """Vergleichszeilen einer Seite."""
    return [DiffRow(side, line) for line in lines]


def _entry_controls(app: "MobileApp", plan: NotePlan, choices: NoteChoices, index: int) -> list[ft.Control]:
    """Kopfzeile, Vergleich, Wahl, Bearbeiten-Feld und Todo-Wahlen einer Notiz."""
    entry = plan.entries[index]
    title = f"Notiz {entry.number} – {KIND_LABELS[entry.kind]}"
    if entry.moved:
        title += " (steht in der anderen Fassung an anderer Stelle)"
    controls: list[ft.Control] = [ft.Text(title, size=12, weight=ft.FontWeight.W_600),
                                  diff_box(entry_diff(entry), None)]
    pick = choices.picks.get(index)
    if entry.kind is not Kind.STATUS:
        def picked(e) -> None:
            choices.picks[index] = Pick(e.control.value)
            if choices.picks[index] is Pick.BEARBEITET and index not in choices.texts:
                choices.texts[index] = edit_prefill(entry, choices, index)
            app.render()
        controls.append(_radio([(p.value, label) for p, label in pick_labels(plan, entry)],
                               pick.value if pick else None, picked))
    if pick is Pick.BEARBEITET:
        def edited(e) -> None:
            choices.texts[index] = e.control.value or ""
        controls.append(ft.TextField(value=choices.texts.get(index, ""), multiline=True, min_lines=2,
                                     label="Bearbeiteter Text", on_change=edited))
        return controls
    for todo in entry.todos:
        def toggled(e, row=todo.row) -> None:
            choices.todos[(index, row)] = e.control.value == "erledigt"
            app.render()
        state = choices.todos.get((index, todo.row))
        sides = f"Hauptdatei: {'erledigt' if todo.main_done else 'offen'} · " \
                f"Konfliktversion: {'offen' if todo.main_done else 'erledigt'}"
        controls += [ft.Text(f"Todo „{todo.open_line.strip()}“ – {sides}", size=12),
                     _radio(_TODO_OPTIONS, None if state is None else ("erledigt" if state else "offen"), toggled)]
    return controls


def _footer(app: "MobileApp", plan: NotePlan, choices: NoteChoices, siblings) -> list[ft.Control]:
    """„Noch offen: …“ und „Auswahl übernehmen“ (erst aktiv, wenn nichts fehlt)."""
    problems = missing(plan, choices)
    manual = tuple(c.conflict.relpath for c in siblings if c is not plan.case) \
        if plan.case.kind is CaseKind.MAIN_DELETED else ()

    async def apply(_e) -> None:
        await app.act(lambda s: s.resolve(plan.case, *note_result(plan, choices), manual))

    hint = ft.Text("Noch offen: " + "; ".join(problems), size=12) if problems else \
        ft.Text("Alles entschieden.", size=12)
    return [hint, ft.Button("Auswahl übernehmen", on_click=apply, disabled=bool(problems))]
