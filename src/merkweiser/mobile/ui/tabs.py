"""Ansichten der Mobile-App: Einrichtung, Heute, Todos, Suche, Konflikte, Einstellungen.

Jede Funktion baut die Controls eines Tabs aus den UI-neutralen
Anzeigemodellen (``merkweiser.app.views``). Aktionen laufen über
``MobileApp.act`` (async, serialisiert mit dem Polling).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

import flet as ft

from ...app.views import HitRow, hit_rows, note_ref, note_rows
from ...core.query import Filter, StatusFilter, TagMode, TextMode, TextQuery
from .note_dialogs import note_actions
from .note_view import note_row, todo_line

if TYPE_CHECKING:
    from .app import MobileApp


def start_hint(report, guarantee: str = "voll") -> str:
    """Hinweis nach dem Start (nicht ausgeführte Änderungen, unvollständige Vorgänge).

    Args:
        report: ``StartReport`` oder ``None``.
        guarantee: Schreibgarantie des Vaults; alles außer „voll“ wird gemeldet.
    """
    if report is None:
        return ""
    parts = [] if guarantee == "voll" else [f"Schreibgarantie: {guarantee}."]
    if report.recovery.not_applied:
        parts.append(f"{len(report.recovery.not_applied)} Änderung(en) wurden wegen eines Abbruchs nicht ausgeführt.")
    if any(m.state == "INCOMPLETE" for m in report.moves):
        parts.append("Ein Verschieben ist unvollständig – siehe Konflikte.")
    if report.removed_empty:
        parts.append(f"{len(report.removed_empty)} leere Datumsdatei(en) entfernt.")
    if report.automerges:
        parts.append(f"{len(report.automerges)} Sync-Konflikt(e) automatisch zusammengeführt.")
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


def today_view(app: "MobileApp") -> list[ft.Control]:
    """Heute: neue Notiz und die Notizen des heutigen Tages."""
    service = app.service
    editor = ft.TextField(label="Neue Notiz", multiline=True, min_lines=3)

    async def save(_e) -> None:
        text = editor.value or ""
        if text.strip():
            await app.act(lambda s: s.append_note(text))

    controls: list[ft.Control] = [editor, ft.Button("Notiz speichern", on_click=save)]
    today = service.clock.today()
    for day_file in service.day(today):
        if day_file.has_conflict:
            controls.append(ft.Text("Diese Datei hat einen ungelösten Konflikt.", color=ft.Colors.ERROR))
        for note in day_file.document.notes:
            rows = note_rows(day_file.relpath, day_file.document, note)
            ref = note_ref(day_file.relpath, day_file.document, note)
            if rows and ref is not None:
                column = [note_row(app, r) for r in rows] + [note_actions(app, ref)]
                controls.append(ft.Container(content=ft.Column(column), padding=8, border_radius=8,
                                             bgcolor=ft.Colors.SURFACE_CONTAINER))
    if len(controls) == 2:
        controls.append(ft.Text(f"Noch keine Notizen am {today.isoformat()}."))
    return controls


def todos_view(app: "MobileApp") -> list[ft.Control]:
    """Todos aus allen Tagesdateien mit Status- und Tag-Filter."""
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
    rows = hit_rows(app.service.search(criteria))
    return [status, tags, either, *[_hit(app, r) for r in reversed(rows)]] or [ft.Text("Keine Todos.")]


def _hit(app: "MobileApp", row: HitRow) -> ft.Control:
    """Ein Treffer mit Datum und Kontext; Todos sind abhakbar."""
    head = ft.Text(f"{row.day} · {row.context}" if row.context else row.day, size=11)
    body = todo_line(app, row.text, row.done, row.urgent, row.target) if row.done is not None else ft.Text(row.text)
    return ft.Column([head, body], spacing=0)


def search_view(app: "MobileApp") -> list[ft.Control]:
    """Freitextsuche (Teilstring oder Regex, identisch zum Desktop)."""
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
            controls += [_hit(app, r) for r in reversed(hit_rows(app.service.search(Filter(text=query))))]
        except ValueError as exc:
            controls.append(ft.Text(f"Ungültiger Ausdruck: {exc}", color=ft.Colors.ERROR))
    return controls


def settings_view(app: "MobileApp") -> list[ft.Control]:
    """Einstellungen: Ordner, Projekt-Präfix, Prüfintervall."""
    prefix = ft.TextField(label="Projekt-Präfix", value=app.settings.project_prefix)
    poll = ft.TextField(label="Prüfintervall (Sekunden)", value=str(app.settings.poll_seconds))

    async def save(_e) -> None:
        try:
            seconds = float((poll.value or "5").replace(",", "."))
        except ValueError:
            app.say("Prüfintervall muss eine Zahl sein.")
            app.render()
            return
        await app.save_settings(replace(app.settings, project_prefix=(prefix.value or "").strip(), poll_seconds=seconds))

    async def change_folder(_e) -> None:
        app.show_setup()

    report_dir = ft.TextField(label="Ordner für Diagnoseberichte (Pfad)", value=app.settings.report_dir or "")

    async def save_report(_e) -> None:
        await app.save_diagnostics((report_dir.value or "").strip() or None)

    guarantee = f"Schreibgarantie: {app.service.write_guarantee} ({app.service.fs.install_mode})" if app.service else ""
    return [ft.Text(f"Notizordner: {app.settings.vault}"), ft.Text(guarantee, size=12),
            ft.Button("Ordner wechseln", on_click=change_folder),
            prefix, poll, ft.Button("Speichern", on_click=save), ft.Divider(),
            ft.Text("Diagnosebericht: Zustand der App als Textdatei, ohne Notizinhalte. "
                    "Leeres Feld = Ordner auswählen.", size=12),
            report_dir, ft.Button("Diagnosebericht speichern", on_click=save_report),
            ft.Text(f"Heute: {date.today().isoformat()}", size=11)]
