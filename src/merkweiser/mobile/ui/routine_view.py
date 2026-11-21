"""Routinen in der Mobile-Oberfläche (W9): Routinen-Seite und Vorschauzeilen im Tab „Todos“.

**Seite „Routinen“** (🔁 im Tab „Todos“): je Rhythmus eine Karte mit ihren
Regeln (Antippen öffnet den Dialog ``routine_dialog``), „Neue Routine“,
Pausen mit Hinzufügen und Entfernen, die Vorschau-Länge (Einstellung),
nicht lesbare Zeilen der Datei und der letzte Durchlauf.

Eine Vorschauzeile ist eine kommende Routinen-Instanz, die noch in keiner
Tagesdatei steht (``app.routine_preview``). Sie sieht aus wie ein Todo, ist
aber mit 🔁 markiert. Das Häkchen schreibt sie sofort als erledigt in die
Datei ihres Tages (``routine_service.check_preview``), ein Tipp auf den Text
öffnet die Regel im Dialog. Ampel-Stern, ⊘ und Verschieben gibt es erst, wenn
sie eingetragen ist; der Stern zeigt die Stufe nur an. Das ist die einzige Stelle, an der die Oberfläche Vorschauzeilen
anders behandelt (``tabs._hit``).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import flet as ft


from ...app import routine_service
from ...app.routine_views import find_rule, section_title
from ...app.views import HitRow
from ...core.inline import strip_urgency, urgency
from ...core.patch import Target
from ...core.routines import ROUTINES_FILE, RoutineFile
from .date_pick import open_date_picker
from .note_view import marked, rich_text, urgency_bar
from .routine_dialog import show_rule_dialog
from .style import EXPLANATION, URGENCY_STYLE, card

if TYPE_CHECKING:
    from .app import MobileApp

ROUTINE_MARK = "🔁"
"""Kennzeichen kommender Routinen-Instanzen (Vorschau)."""
PREVIEW_CHOICES = (1, 3, 7, 14, 21, 31)
"""Auswahl für die Vorschau-Länge in Tagen (Einstellung ``routine_preview_days``)."""


def routines_page(app: "MobileApp", _arg: str) -> list[ft.Control]:
    """Seite „Routinen“ (siehe Moduldoku).

    Args:
        app: Die laufende App.
        _arg: unbenutzt.

    Returns:
        Die Controls der Seite (ohne Kopfzeile).
    """
    rf = routine_service.load(app.service)
    controls: list[ft.Control] = [ft.Row([ft.Button("Neue Routine", icon=ft.Icons.ADD,
                                                    on_click=lambda _e: show_rule_dialog(app))], wrap=True)]
    if app.service.routines.summary:
        controls.append(ft.Text(app.service.routines.summary, size=12, color=EXPLANATION))
    if rf is None:
        return controls + [ft.Text("Noch keine Routinen. „Neue Routine“ legt Routinen.md im Notizordner an.")]
    controls += _error_card(rf)
    for section in rf.sections:
        rows = [_rule_row(app, section, item) for item in section.items]
        controls.append(card([ft.Text(section_title(section), weight=ft.FontWeight.BOLD), *rows], spacing=2))
    return controls + [_pauses_card(app, rf), _preview_setting(app)]


def _rule_row(app: "MobileApp", section, item) -> ft.Control:
    """Eine Regel: Ampel-Symbol und Text (pausiert blass), Antippen öffnet den Dialog."""
    icon, color, _tip = URGENCY_STYLE[int(urgency(item.body))]
    text = strip_urgency(item.body) + (" (pausiert)" if item.paused else "")
    label = rich_text(app, text, color=EXPLANATION, italic=True) if item.paused else rich_text(app, text)
    return ft.GestureDetector(content=ft.Row([ft.Icon(icon, color=color, size=18), label], spacing=6),
                              on_tap=lambda _e: show_rule_dialog(app, (section, item)))


def _error_card(rf: RoutineFile) -> list[ft.Control]:
    """Karte mit nicht lesbaren Zeilen (leer, wenn alles lesbar ist)."""
    problems = ([rf.until_error] if rf.until_error else []) + [
        f"Zeile {e.line_no + 1}: {e.line.strip()} – {e.message}" for e in rf.errors]
    if not problems:
        return []
    return [card([ft.Text("Nicht lesbar (wird übersprungen)", color=ft.Colors.ERROR, weight=ft.FontWeight.BOLD),
                  *[ft.Text(p, size=12) for p in problems]], spacing=2)]


def _pauses_card(app: "MobileApp", rf: RoutineFile) -> ft.Control:
    """Pausen mit Entfernen-Knopf; „Pause hinzufügen“ fragt erst den Beginn, dann das Ende."""
    today = app.service.clock.today()

    async def add(_e) -> None:
        async def chose_start(start) -> None:
            async def chose_end(end) -> None:
                message = await app.act(lambda s: routine_service.add_pause_range(s, start, end))
                if message:
                    app.say(message)
            open_date_picker(app, start, "Pause bis einschließlich", chose_end)
        open_date_picker(app, today, "Pause ab", chose_start)

    def remover(pause):
        async def remove(_e) -> None:
            await app.act(lambda s: routine_service.delete_pause(s, Target(ROUTINES_FILE, pause.line_no, pause.line)))
        return remove

    rows = [ft.Row([ft.Text(pause.line.strip()[2:], expand=True),
                    ft.IconButton(icon=ft.Icons.DELETE, tooltip="Pause entfernen", on_click=remover(pause))])
            for pause in rf.pauses]
    return card([ft.Text("Pausen", weight=ft.FontWeight.BOLD), *rows,
                 ft.TextButton("Pause hinzufügen", icon=ft.Icons.ADD, on_click=add)], spacing=2)


def _preview_setting(app: "MobileApp") -> ft.Control:
    """Auswahl der Vorschau-Länge im Tab „Todos“ (Einstellung je Gerät)."""
    async def chosen(e) -> None:
        await app.save_settings(replace(app.settings, routine_preview_days=int(e.control.value)))

    days = app.settings.routine_preview_days
    choices = sorted(set(PREVIEW_CHOICES) | {days})
    options = [ft.DropdownOption(key=str(d), text=f"{d} Tag{'e' if d > 1 else ''}") for d in choices]
    return ft.Dropdown(label="Vorschau im Tab Todos", value=str(days), on_select=chosen, options=options)


def preview_line(app: "MobileApp", row: HitRow) -> ft.Control:
    """Vorschauzeile: Kopf „🔁 Datum · Rhythmus“, Checkbox zum vorzeitigen Abhaken, Text, Ampel nur als Anzeige.

    Args:
        app: Die laufende App.
        row: Trefferzeile mit ``row.preview`` (``row.target`` ist ``None``).

    Returns:
        Spalte aus Kopfzeile und Todo-Zeile.
    """
    occurrence = row.preview

    async def check(e) -> None:
        if e.control.value:
            await app.act(lambda s: routine_service.check_preview(s, occurrence))

    icon, color, _tooltip = URGENCY_STYLE[int(row.urgency)]
    head = ft.Text(f"{ROUTINE_MARK} {row.day} · {row.context}" if row.context else f"{ROUTINE_MARK} {row.day}",
                   size=11)
    checkbox = ft.Checkbox(value=False, on_change=check, visual_density=ft.VisualDensity.COMPACT,
                           tooltip="schon jetzt erledigen")

    def edit(_e) -> None:
        rf = routine_service.load(app.service)
        found = find_rule(rf, occurrence.item_line, occurrence.item_text) if rf else None
        if found is None:
            app.say("Die Regel steht nicht mehr so in Routinen.md.")
            return
        show_rule_dialog(app, found)

    text = ft.GestureDetector(content=rich_text(app, strip_urgency(row.text)), on_tap=edit)
    line = marked(checkbox, text, [
        ft.Icon(icon, color=color or EXPLANATION, tooltip="Routine – Ampel nach dem Eintragen änderbar"),
    ])
    return ft.Column([head, urgency_bar(line, row.urgency, True)], spacing=0)
