"""Benachrichtigungen in der Mobile-App (W5): neu planen, Start über eine Benachrichtigung, Einstellungsseite.

* ``NotifyController.reschedule`` plant beim Verlassen der App (Lifecycle
  HIDE/PAUSE/DETACH), beim Start und nach Einstellungsänderungen alles neu
  (vorher ``cancel_all``) – mit ``app.notify_plan`` und ``app.notify_content``.
* ``NotifyController.check_launch`` öffnet den Tab „Tag“ mit heute, wenn die App
  über eine Benachrichtigung gestartet bzw. zurückgeholt wurde.
* ``notify_page``: an/aus (das erste Einschalten fragt die Berechtigung an),
  Uhrzeit, Eskalation, Urlaub bis (einschließlich), Vorplanung, Zustand.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import time
from typing import TYPE_CHECKING

import flet as ft

from ...app.notify_content import content_lines
from ...app.notify_plan import NotifySettings, plan
from ..platform.notifications import NoNotifier, make_notifier
from .date_pick import open_date_picker

if TYPE_CHECKING:
    from .app import MobileApp

HORIZONS = (7, 14, 30)


class NotifyController:
    """Verbindet App, Planer und Plattform-Adapter."""

    def __init__(self, app: "MobileApp") -> None:
        self.app = app
        self.notifier = NoNotifier()

    def attach(self) -> None:
        """Erzeugt den Adapter (im Seitenkontext, damit sich der Flet-Service anmeldet)."""
        self.notifier = make_notifier()

    def settings(self) -> NotifySettings:
        """Planer-Einstellungen aus den App-Einstellungen."""
        s = self.app.settings
        return NotifySettings(s.notify_enabled, s.notify_at(), s.notify_escalate, s.vacation_date(), s.notify_horizon)

    async def reschedule(self) -> int:
        """Storniert alles und plant neu; liefert die Zahl geplanter Benachrichtigungen."""
        service = self.app.service
        if service is None or not self.notifier.available:
            return 0
        planned = plan(service.clock.now(), self.settings(), lambda day: content_lines(service, day))
        await self.notifier.cancel_all()
        return await self.notifier.schedule([p.as_item() for p in planned]) if planned else 0

    async def check_launch(self) -> None:
        """Über eine Benachrichtigung geöffnet → Tab „Tag“ mit heute."""
        if self.app.service is not None and await self.notifier.launch_payload() == "heute":
            self.app.show_day(self.app.service.clock.today())


def notify_page(app: "MobileApp", _arg: str) -> list[ft.Control]:
    """Einstellungsseite „Benachrichtigungen“ (ohne Kopfzeile)."""
    control = app.notify
    s = app.settings
    if not control.notifier.available:
        return [ft.Text(control.notifier.reason, color=ft.Colors.ERROR)]

    async def save(**changes) -> None:
        await app.save_settings(replace(app.settings, **changes))
        count = await control.reschedule()
        app.say(f"Gespeichert; {count} Benachrichtigung(en) geplant.")
        app.render()

    async def toggle(e) -> None:
        if e.control.value:
            state = await control.notifier.request_permission()
            if state != "granted":
                app.say("Ohne Erlaubnis kann Merkweiser keine Benachrichtigungen zeigen. Bitte in den "
                        "Android-Einstellungen für Merkweiser erlauben.")
        await save(notify_enabled=bool(e.control.value))

    async def picked_time(e) -> None:
        if isinstance(e.control.value, time):
            await save(notify_time=e.control.value.strftime("%H:%M"))

    async def choose_time(_e) -> None:
        app.page.show_dialog(ft.TimePicker(value=s.notify_at(), help_text="Uhrzeit der Benachrichtigung",
                                           on_change=picked_time))

    async def vacation(day) -> None:
        await save(vacation_until=day.isoformat())

    async def end_vacation(_e) -> None:
        await save(vacation_until=None)

    async def horizon(e) -> None:
        await save(notify_horizon=int(e.control.value or 14))

    async def escalate(e) -> None:
        await save(notify_escalate=bool(e.control.value))

    today = app.service.clock.today()
    vacation_text = f"Urlaub bis einschließlich {s.vacation_date():%d.%m.%Y}" if s.vacation_until else "Kein Urlaub"
    controls: list[ft.Control] = [
        ft.Switch(label="Morgen-Benachrichtigung", value=s.notify_enabled, on_change=toggle),
        ft.TextButton(f"Uhrzeit: {s.notify_time}", icon=ft.Icons.SCHEDULE, on_click=choose_time),
        ft.Switch(label="Erinnerungen eskalieren, wenn die App länger nicht geöffnet wurde",
                  value=s.notify_escalate, on_change=escalate),
        ft.Row([ft.Text(vacation_text, expand=True),
                ft.TextButton("Urlaub wählen", on_click=lambda _e: open_date_picker(
                    app, s.vacation_date() or today, "Urlaub bis einschließlich", vacation)),
                *([ft.TextButton("Urlaub beenden", on_click=end_vacation)] if s.vacation_until else [])], wrap=True),
        ft.Dropdown(label="Vorplanen für", value=str(s.notify_horizon), on_select=horizon,
                    options=[ft.DropdownOption(key=str(d), text=f"{d} Tage") for d in HORIZONS]),
        ft.Text(f"Gegen {s.notify_time} kommt eine Liste deiner offenen Todos von heute und aller dringenden. "
                "Öffnest du die App danach nicht, erinnert Merkweiser an den Folgetagen neutral, auf Wunsch "
                "zunehmend dringlich. Android kann die Zustellung bei Akkusparen verzögern; was nach dem Schließen "
                "der App per Sync dazukommt, steht noch nicht in der Benachrichtigung.", size=12),
    ]
    return controls

