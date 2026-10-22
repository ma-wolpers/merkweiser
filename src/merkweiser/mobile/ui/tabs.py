"""Ansichten der Mobile-App: Einrichtung, Tag, Todos, Suche, Einstellungen (mit Unterseiten).

Jede Funktion baut die Controls eines Tabs aus den UI-neutralen
Anzeigemodellen (``merkweiser.app.views``). Aktionen laufen über
``MobileApp.act`` (async, serialisiert mit dem Polling).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import TYPE_CHECKING

import flet as ft

from ...app.interrupted import open_issue_count
from ...app.list_editing import INDENT_WIDTHS
from ...app.nav import PageRef
from ...app.ordering import is_pressing, note_is_pressing, stable_first
from ...app.views import HitRow, day_label, hit_rows
from ...core.query import Filter, StatusFilter, TagMode, TextMode, TextQuery
from .date_pick import open_date_picker
from .note_dialogs import new_note_dialog
from .note_view import note_card, todo_line

if TYPE_CHECKING:
    from .app import MobileApp


def start_hint(report, guarantee: str = "voll", open_issues: int = 0) -> str:
    """Hinweis nach dem Start (nicht ausgeführte Änderungen, unvollständige Vorgänge, offene Konflikte).

    Args:
        report: ``StartReport`` oder ``None``.
        guarantee: Schreibgarantie des Vaults; alles außer „voll“ wird gemeldet.
        open_issues: Offene Konflikte und unterbrochene Vorgänge (Badge-Zahl).
    """
    if report is None:
        return ""
    parts = [] if guarantee == "voll" else [f"Schreibgarantie: {guarantee}."]
    if report.recovery.not_applied:
        parts.append(f"{len(report.recovery.not_applied)} Änderung(en) wurden wegen eines Abbruchs nicht ausgeführt.")
    if any(m.state == "INCOMPLETE" for m in report.moves):
        parts.append("Ein Verschieben ist unvollständig – siehe Einstellungen → Konflikte.")
    if report.removed_empty:
        parts.append(f"{len(report.removed_empty)} leere Datumsdatei(en) entfernt.")
    if report.automerges:
        parts.append(f"{len(report.automerges)} Sync-Konflikt(e) automatisch zusammengeführt.")
    if open_issues:
        parts.append(f"{open_issues} offene(r) Konflikt(e) bzw. Vorgang/Vorgänge – Einstellungen → Konflikte.")
    return " ".join(parts)


def setup_view(app: "MobileApp") -> list[ft.Control]:
    """Einrichtung: Zugriff auf alle Dateien und Notizordner."""
    access = app.access.has_all_files_access()
    state = {True: "erteilt", False: "fehlt", None: "unbekannt"}[access]
    path_field = ft.TextField(label="Notizordner (Pfad)", value=app.settings.vault or "/storage/emulated/0/")

    async def request(_e) -> None:
        if not app.access.request_all_files_access():
            app.say("Bitte manuell: Einstellungen → Apps → Merkweiser → Berechtigungen → Dateien → "
                    "„Verwaltung aller Dateien zulassen“.")
        app.show_setup()

    async def pick(_e) -> None:
        await app.choose_folder()

    async def typed(_e) -> None:
        await app.choose_folder(path_field.value.strip() or None)

    return [
        ft.Text("Merkweiser einrichten", size=22, weight=ft.FontWeight.BOLD),
        ft.Text("Merkweiser arbeitet direkt mit deinem Notizordner (z. B. dem Syncthing-Ordner). "
                "Dafür braucht die App „Zugriff auf alle Dateien“."),
        ft.Text(f"Zugriff auf alle Dateien: {state}"),
        ft.Button("Zugriff erteilen", on_click=request),
        ft.Button("Notizordner wählen", on_click=pick),
        path_field,
        ft.Button("Eingetippten Pfad übernehmen", on_click=typed),
    ]


def day_header(app: "MobileApp") -> ft.Control:
    """Kopfzeile des Tabs „Tag“: ◀, Datum (öffnet den Kalender), ▶ und „Heute“ (nur an anderen Tagen).

    Args:
        app: Die laufende App (``app.day`` ist der gewählte Tag).

    Returns:
        Eine Zeile mit den Navigationsknöpfen.
    """
    today = app.service.clock.today()

    async def go(day: date) -> None:
        app.day = day
        app.render()

    def step(icon, delta: int, tooltip: str) -> ft.IconButton:
        async def click(_e) -> None:
            await go(app.day + timedelta(days=delta))
        return ft.IconButton(icon=icon, tooltip=tooltip, on_click=click)

    async def calendar(_e) -> None:
        open_date_picker(app, app.day, "Tag anzeigen", go)

    async def back_to_today(_e) -> None:
        await go(today)

    controls: list[ft.Control] = [step(ft.Icons.CHEVRON_LEFT, -1, "Vortag"),
                                  ft.TextButton(day_label(app.day, today), icon=ft.Icons.CALENDAR_MONTH,
                                                on_click=calendar),
                                  step(ft.Icons.CHEVRON_RIGHT, 1, "Folgetag")]
    if app.day != today:
        controls.append(ft.TextButton("Heute", on_click=back_to_today))
    return ft.Row(controls, spacing=0, wrap=True)


def day_view(app: "MobileApp") -> list[ft.Control]:
    """Tab „Tag“: Datumswahl, Knopf „Neue Notiz“ (öffnet den gemeinsamen Editor leer) und die Notizen des Tages.

    Angesehen wird nur gelesen; eine Tagesdatei entsteht erst, wenn eine Notiz
    gespeichert wird (``NotesService.append_note``).
    """
    service = app.service
    day = app.day

    async def new_note(_e) -> None:
        app.page.show_dialog(new_note_dialog(app, day))

    controls: list[ft.Control] = [day_header(app), ft.Button("Neue Notiz", icon=ft.Icons.ADD, on_click=new_note)]
    empty = len(controls)
    for day_file in service.day(day):
        if day_file.has_conflict:
            controls.append(ft.Text("Diese Datei hat einen ungelösten Konflikt.", color=ft.Colors.ERROR))
        cards = (note_card(app, day_file.relpath, day_file.document, note) for note in day_file.document.notes)
        controls += [card for card in cards if card is not None]
    if len(controls) == empty:
        controls.append(ft.Text(f"Noch keine Notizen am {day:%d.%m.%Y}."))
    return controls


def todos_view(app: "MobileApp") -> list[ft.Control]:
    """Todos aus allen Tagesdateien mit Status- und Tag-Filter; neueste zuerst, offene dringende vorn (W1)."""
    state = app.__dict__.setdefault("_todo_filter", {"status": "offen", "tags": "", "oder": False})
    status = ft.Dropdown(label="Status", value=state["status"], options=[
        ft.DropdownOption(key="offen", text="offen"), ft.DropdownOption(key="erledigt", text="erledigt"),
        ft.DropdownOption(key="alle", text="alle")])
    tags = ft.TextField(label="Tags (Leerzeichen getrennt)", value=state["tags"])
    either = ft.Switch(label="ODER statt UND", value=state["oder"])

    async def apply(_e) -> None:
        state.update(status=status.value or "offen", tags=tags.value or "", oder=bool(either.value))
        app.render()

    status.on_select = apply
    tags.on_submit = apply
    either.on_change = apply
    criteria = Filter(nur_todos=True, status=StatusFilter(state["status"]),
                      tags=tuple(state["tags"].split()), tag_modus=TagMode.ODER if state["oder"] else TagMode.UND)
    rows = stable_first(list(reversed(hit_rows(app.service.search(criteria)))), is_pressing)
    return [status, tags, either, *[_hit(app, r) for r in rows]] or [ft.Text("Keine Todos.")]


def _hit(app: "MobileApp", row: HitRow) -> ft.Control:
    """Ein Treffer mit Datum und Kontext; Todos sind abhakbar."""
    head = ft.Text(f"{row.day} · {row.context}" if row.context else row.day, size=11)
    body = todo_line(app, row.text, row.done, row.urgent, row.target) if row.done is not None else ft.Text(row.text)
    return ft.Column([head, body], spacing=0)


def search_view(app: "MobileApp") -> list[ft.Control]:
    """Freitextsuche (Teilstring oder Regex, identisch zum Desktop) mit ganzen Notizen als Ergebnis.

    Jede Notiz mit Treffer erscheint einmal als Karte (bearbeitbar, abhakbar,
    verschiebbar wie im Tab „Tag“), neuestes Datum zuerst; Karten mit offenem
    dringendem Todo stehen vorn (W1). Nach jeder Aktion
    zeichnet ``render`` neu und rechnet die Treffer frisch über ``NotesService``.
    """
    state = app.__dict__.setdefault("_search", {"text": "", "regex": False})
    text = ft.TextField(label="Suchen", value=state["text"])
    regex = ft.Switch(label="Regulärer Ausdruck", value=state["regex"])

    async def apply(_e) -> None:
        state.update(text=text.value or "", regex=bool(regex.value))
        app.render()

    text.on_submit = apply
    regex.on_change = apply
    controls: list[ft.Control] = [text, regex, ft.Button("Suchen", on_click=apply)]
    if state["text"]:
        query = TextQuery(state["text"], TextMode.REGEX if state["regex"] else TextMode.TEILSTRING)
        try:
            matches = app.service.search_notes(Filter(text=query))
        except ValueError as exc:
            controls.append(ft.Text(f"Ungültiger Ausdruck: {exc}", color=ft.Colors.ERROR))
            return controls
        ordered = stable_first(list(reversed(matches)), lambda m: note_is_pressing(m.relpath, m.document, m.note))
        cards = (note_card(app, m.relpath, m.document, m.note, date_button(app, m.day)) for m in ordered)
        controls += [card for card in cards if card is not None] or [ft.Text("Nichts gefunden.")]
    return controls


def date_button(app: "MobileApp", day: date) -> ft.Control:
    """Kopf einer Suchkarte: das Datum; ein Tipp öffnet den Tab „Tag“ mit genau diesem Datum.

    Args:
        app: Die laufende App.
        day: Datum der Tagesdatei.

    Returns:
        Ein TextButton mit ``day_label``.
    """
    async def open_day(_e) -> None:
        app.show_day(day)

    return ft.TextButton(day_label(day, app.service.clock.today()), icon=ft.Icons.TODAY, on_click=open_day)


def hub_entries(app: "MobileApp") -> list[ft.Control]:
    """Einträge oben in den Einstellungen, die Unterseiten öffnen (W4).

    Args:
        app: Die laufende App.

    Returns:
        Je Unterseite ein ``ListTile``; „Konflikte“ mit Anzahl.
    """
    count = open_issue_count(app.service)

    async def conflicts(_e) -> None:
        app.open_page(PageRef("konflikte"))

    title = f"Konflikte ({count})" if count else "Konflikte"
    return [ft.ListTile(leading=ft.Icon(ft.Icons.SYNC_PROBLEM, color=ft.Colors.ERROR if count else None),
                        title=ft.Text(title), subtitle=ft.Text("Sync-Konflikte, unterbrochene Vorgänge"),
                        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT), on_click=conflicts),
            ft.Divider()]


def settings_view(app: "MobileApp") -> list[ft.Control]:
    """Einstellungen: Unterseiten (Konflikte …), Ordner, Projekt-Präfix, Prüfintervall, Einrückbreite."""
    prefix = ft.TextField(label="Projekt-Präfix", value=app.settings.project_prefix)
    poll = ft.TextField(label="Prüfintervall (Sekunden)", value=str(app.settings.poll_seconds))
    width = ft.Dropdown(label="Einrückung im Editor", value=str(app.settings.indent_width), options=[
        ft.DropdownOption(key=str(w), text=f"{w} Leerzeichen") for w in INDENT_WIDTHS])

    async def save(_e) -> None:
        try:
            seconds = float((poll.value or "5").replace(",", "."))
        except ValueError:
            app.say("Prüfintervall muss eine Zahl sein.")
            app.render()
            return
        await app.save_settings(replace(app.settings, project_prefix=(prefix.value or "").strip(), poll_seconds=seconds,
                                        indent_width=int(width.value or app.settings.indent_width)))

    async def change_folder(_e) -> None:
        app.show_setup()

    report_dir = ft.TextField(label="Ordner für Diagnoseberichte (Pfad)", value=app.settings.report_dir or "")

    async def save_report(_e) -> None:
        await app.save_diagnostics((report_dir.value or "").strip() or None)

    guarantee = f"Schreibgarantie: {app.service.write_guarantee} ({app.service.fs.install_mode})" if app.service else ""
    return [*hub_entries(app), ft.Text(f"Notizordner: {app.settings.vault}"), ft.Text(guarantee, size=12),
            ft.Button("Ordner wechseln", on_click=change_folder),
            prefix, poll, width, ft.Button("Speichern", on_click=save), ft.Divider(),
            ft.Text("Diagnosebericht: Zustand der App als Textdatei, ohne Notizinhalte. "
                    "Leeres Feld = Ordner auswählen.", size=12),
            report_dir, ft.Button("Diagnosebericht speichern", on_click=save_report),
            ft.Text(f"Heute: {date.today().isoformat()}", size=11)]
