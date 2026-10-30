"""Tab „Zeit“: Arbeitszeit messen und ansehen (W6, PLAN-SPAETERE-SCHRITTE.md).

Aufbau von oben: laufende Messung („Orga läuft seit 08:15 (1:23)“),
Tätigkeit (Dropdown, sortiert nach 7-Tage-Summe), ohne Messung „Start“, sonst
„Messung beenden“ (Endzeit wählen oder keine Zeit eintragen) mit Schnellknopf
„Sofort stoppen“ (nur Symbol) und „Wechseln zu …“ (wenn eine andere Tätigkeit
gewählt ist; öffnet immer die Uhrzeit-Wahl, vorbelegt mit jetzt) mit Schnellknopf
„Sofort wechseln“ (W6a);
darunter Hinweise (veraltet verworfen, beschädigt, nicht lesbar, Umbenennung
unklar, mehrere laufende Messungen), dann die Übersicht (7/14/30 Tage, je Tag
eine Zeile, Summen) und „Tätigkeiten verwalten“ (Unterseite ``taetigkeiten``).

Die Laufzeit wird beim Öffnen und etwa minütlich neu berechnet (``Ticker``,
gestartet in ``MobileApp.render`` nur für die sichtbare Zeit-Ansicht).
Gespeichert wird dabei nichts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import flet as ft

from ...app import time_service as ts
from ...app.nav import PageRef
from ...app.time_scan import ScanResult, refresh
from ...app.views import WEEKDAYS
from ...core.activities import DEFAULT_ACTIVITY, is_valid
from ...core.frontmatter import Stamp
from ...core.time_ops import pending_booking
from ...core.timetrack import hm, totals
from .time_dialogs import show_abort_dialog, show_rename_dialog, show_switch_dialog

if TYPE_CHECKING:
    from .app import MobileApp

RANGES = (7, 14, 30)


def running_text(stamp: Stamp, now: datetime) -> str:
    """„„Orga“ läuft seit 08:15 (1:23)“ – Dauer aus dem Stempel, nur zur Anzeige."""
    elapsed = now.astimezone(timezone.utc) - stamp.start.astimezone(timezone.utc)
    minutes = max(int(elapsed.total_seconds() // 60), 0)
    return f"„{stamp.activity}“ läuft seit {stamp.start:%H:%M} ({hm(minutes)})"


def time_view(app: "MobileApp") -> list[ft.Control]:
    """Baut den Zeit-Tab (siehe Moduldoku) und meldet den Ticker für die Laufzeit an."""
    state = app.__dict__.setdefault("_time", {"days": 7, "activity": None, "archive_done": False})
    archive = state["days"] > 7 and not state["archive_done"]
    scan = refresh(app.service, state["days"], archive)
    state["archive_done"] = state["archive_done"] or archive
    if scan.hints:
        app.say(" ".join(scan.hints))
    app.time_tick = None
    controls = _measure(app, scan, state) + _notes(app, scan) + _overview(app, scan, state)
    controls.append(ft.TextButton("Tätigkeiten verwalten", icon=ft.Icons.EDIT,
                                  on_click=lambda _e: app.open_page(PageRef("taetigkeiten"))))
    return controls


def _measure(app: "MobileApp", scan: ScanResult, state: dict) -> list[ft.Control]:
    """Laufende Messung, Tätigkeit und Knöpfe."""
    names = ts.activity_names(app.service, scan) or [DEFAULT_ACTIVITY]
    selectable = [n for n in names if is_valid(n)] or [DEFAULT_ACTIVITY]
    run = scan.running[0] if len(scan.running) == 1 else None
    chosen = state["activity"] if state["activity"] in selectable else (run.stamp.activity if run else selectable[0])

    async def select(e) -> None:
        state["activity"] = e.control.value
        app.render()

    controls: list[ft.Control] = []
    if pending_booking(app.service.store):
        return [ft.Text("Eine Buchung wird noch abgeschlossen – siehe Einstellungen → Konflikte.", color=ft.Colors.ERROR)]
    if run:
        label = ft.Text(running_text(run.stamp, app.service.clock.now()), size=18, weight=ft.FontWeight.BOLD)
        controls.append(label)
        app.time_tick = _ticker(app, label, run.stamp)
    dropdown = ft.Dropdown(label="Tätigkeit", value=chosen, on_select=select,
                           options=[ft.DropdownOption(key=n, text=n) for n in selectable])
    controls.append(dropdown)
    if run:
        controls.append(_with_quick(
            ft.Button("Messung beenden", on_click=lambda _e: show_abort_dialog(app, run.stamp.start)),
            ft.Icons.STOP, "Sofort stoppen", _action(app, lambda s: ts.stop(s))))
        if chosen != run.stamp.activity:
            controls.append(_with_quick(
                ft.Button(f"Wechseln zu „{chosen}“", icon=ft.Icons.SWAP_HORIZ,
                          on_click=lambda _e: show_switch_dialog(app, chosen, run.stamp.start)),
                ft.Icons.FAST_FORWARD, "Sofort wechseln", _action(app, lambda s: ts.switch(s, chosen))))
    elif not scan.running:
        controls.append(ft.Button("Start", icon=ft.Icons.PLAY_ARROW, on_click=_action(app, lambda s: ts.start(s, chosen))))
    return controls


def _with_quick(button: ft.Control, icon: str, tooltip: str, on_quick) -> ft.Row:
    """Knopf, der einen Dialog öffnet, mit Schnellknopf (nur Symbol) direkt dahinter.

    Args:
        button: Der beschriftete Knopf (öffnet die Uhrzeit- bzw. Endzeit-Wahl).
        icon: Symbol des Schnellknopfs.
        tooltip: Erklärung des Schnellknopfs.
        on_quick: Aktion des Schnellknopfs (wirkt sofort, ohne Dialog).

    Returns:
        Die Zeile aus beiden Knöpfen.
    """
    return ft.Row([button, ft.IconButton(icon=icon, tooltip=tooltip, on_click=on_quick)], spacing=4)


def _notes(app: "MobileApp", scan: ScanResult) -> list[ft.Control]:
    """Mehrere laufende Messungen, beschädigte Stempel, nicht lesbare Köpfe, unklare Umbenennungen."""
    controls: list[ft.Control] = []
    conflict = ts.running_conflict(scan)
    if conflict:
        choice = ft.RadioGroup(content=ft.Column([ft.Radio(value=c, label=t) for c, t in conflict.options()]))
        controls += [ft.Text("Mehrere Messungen laufen (z. B. auf zwei Geräten). Welche zählt?", color=ft.Colors.ERROR),
                     choice, ft.Button("Entscheiden", on_click=_action(
                         app, lambda s: ts.resolve_running(s, choice.value or "")))]
    for relpath, reason in scan.damaged:
        controls.append(ft.Row([ft.Text(f"{relpath}: {reason}", color=ft.Colors.ERROR, expand=True),
                                ft.TextButton("Verwerfen", on_click=_action(
                                    app, lambda s, r=relpath: ts.discard_damaged(s, r)))]))
    for relpath in scan.unreadable:
        controls.append(ft.Text(f"{relpath}: Kopfbereich nicht sicher lesbar – Zeiten dort werden nicht gezählt "
                                "und nicht geändert.", size=12, color=ft.Colors.ERROR))
    for relpath, _day, old, new in scan.unclear:
        buttons = [ft.TextButton(label, on_click=_action(app, lambda s, m=mode, r=relpath: ts.resolve_unclear(
            s, r, old, new, m))) for mode, label in (("addieren", "Addieren"), ("groesser", "Größeren Wert"),
                                                       ("nichts", "Nichts ändern"))]
        controls += [ft.Text(f"{relpath}: „{old}“ und „{new}“ stehen beide da (nach Umbenennung). Wie zählen?",
                             size=12), ft.Row(buttons, wrap=True)]
    return controls


def _overview(app: "MobileApp", scan: ScanResult, state: dict) -> list[ft.Control]:
    """Zeitraum-Wahl, je Tag eine Zeile, Summen je Tätigkeit und gesamt."""
    async def changed(e) -> None:
        state["days"] = int((e.control.selected or ["7"])[0])
        app.render()

    controls: list[ft.Control] = [ft.Divider(), ft.SegmentedButton(
        segments=[ft.Segment(value=str(d), label=ft.Text(f"{d} Tage")) for d in RANGES],
        selected=[str(state["days"])], on_change=changed)]
    for day in scan.days:
        parts = " · ".join(f"{name} {hm(value)}" for name, value in sorted(day.minutes.items()) if value)
        controls.append(ft.Text(f"{WEEKDAYS[day.day.weekday()]} {day.day:%d.%m.}: {parts or '–'}", size=13))
    sums = totals(scan.days)
    summary = " · ".join(f"{name} {hm(value)}" for name, value in sorted(sums.items()) if value)
    controls.append(ft.Text(f"Summe: {summary + ' · ' if summary else ''}gesamt {hm(sum(sums.values()))}",
                            weight=ft.FontWeight.BOLD))
    return controls


def activities_page(app: "MobileApp", _arg: str) -> list[ft.Control]:
    """Unterseite „Tätigkeiten verwalten“: hinzufügen, umbenennen, löschen."""
    scan = refresh(app.service)
    field = ft.TextField(label="Neue Tätigkeit", expand=True)
    controls: list[ft.Control] = [ft.Row([field, ft.Button("Hinzufügen", on_click=_action(
        app, lambda s: ts.add_activity(s, field.value or "")))]),
        ft.Text("Erlaubt: Buchstaben, Ziffern, Leerzeichen, - und _. Löschen entfernt nur den Eintrag; "
                "eingetragene Zeiten bleiben.", size=12)]
    for name in ts.activity_names(app.service, scan):
        suffix = "" if is_valid(name) else " (nur lesend – bitte umbenennen)"
        controls.append(ft.Row([ft.Text(name + suffix, expand=True),
                                ft.IconButton(icon=ft.Icons.EDIT, tooltip="Umbenennen",
                                              on_click=lambda _e, n=name: show_rename_dialog(app, n)),
                                ft.IconButton(icon=ft.Icons.DELETE, tooltip="Löschen", on_click=_action(
                                    app, lambda s, n=name: ts.delete_activity(s, n)))]))
    return controls


def _action(app: "MobileApp", action):
    """Klick-Handler: Aktion über ``app.act``, Meldung anzeigen."""
    async def click(_e) -> None:
        message = await app.act(action)
        if isinstance(message, str) and message:
            app.say(message)
            app.render()
    return click


def _ticker(app: "MobileApp", label: ft.Text, stamp: Stamp):
    """Coroutine-Funktion für den Ticker: etwa minütlich die Laufzeit neu anzeigen."""
    async def tick() -> None:
        while True:
            now = app.service.clock.now()
            await asyncio.sleep(max(60 - now.second, 1))
            label.value = running_text(stamp, app.service.clock.now())
            app.page.update()
    return tick
