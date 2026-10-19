"""Mobile-App: Kompositionswurzel, Einrichtung, Navigation und Polling (Flet 0.86.5).

Regel: Alle ``NotesService``-Aufrufe laufen in **async**-Handlern auf dem
Event-Loop von Flet. Damit sind sie untereinander und mit der Polling-Schleife
serialisiert; der Service braucht keine Thread-Sicherheit.

Ablauf: App-Datenverzeichnis auflösen → Einstellungen laden → ist ein
lesbarer Notizordner eingestellt, wird ``NotesService.start()`` ausgeführt
(Wiederherstellung, Scan, Auto-Merge) und die Hauptansicht gezeigt; sonst die
Einrichtung (Zugriff erteilen, Ordner wählen).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from pathlib import Path

import flet as ft

from ...app.notes_service import NotesService, StartReport
from ...app.settings import Settings, load_settings, save_settings
from ...core.clock import SystemClock
from ...ports.storage_access import AppStorage, FolderAccess
from ..platform.flet_access import FletFolderAccess, resolve_app_storage
from . import tabs

TAB_NAMES = ("Heute", "Todos", "Suche", "Konflikte", "Einstellungen")
TAB_ICONS = (ft.Icons.TODAY, ft.Icons.CHECKLIST, ft.Icons.SEARCH, ft.Icons.SYNC_PROBLEM, ft.Icons.SETTINGS)


class MobileApp:
    """Zustand und Navigation der Mobile-App.

    Args:
        page: Flet-Seite.
        storage: Privates App-Datenverzeichnis.
        access: Ordnerwahl und Zugriffsrecht.
    """

    def __init__(self, page: ft.Page, storage: AppStorage, access: FolderAccess) -> None:
        self.page, self.storage, self.access = page, storage, access
        self.settings: Settings = load_settings(storage.data_dir)
        self.service: NotesService | None = None
        self.report: StartReport | None = None
        self.tab = 0
        self.status = ft.Text("", size=12, color=ft.Colors.ERROR)
        self.body = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)
        self.nav = ft.NavigationBar(
            destinations=[ft.NavigationBarDestination(icon=i, label=n) for i, n in zip(TAB_ICONS, TAB_NAMES)],
            selected_index=0, on_change=self._on_tab)

    async def start(self) -> None:
        """Baut die Seite auf und öffnet den Vault oder die Einrichtung."""
        self.page.title = "Merkweiser"
        self.page.on_app_lifecycle_state_change = self._on_lifecycle
        self.page.add(ft.SafeArea(content=ft.Column([self.status, self.body], expand=True), expand=True))
        self.page.navigation_bar = self.nav
        await self.open_vault()
        self.page.run_task(self._poll_loop)

    async def open_vault(self) -> None:
        """Öffnet den eingestellten Vault oder zeigt die Einrichtung."""
        root = Path(self.settings.vault) if self.settings.vault else None
        if root is None or not (root.is_dir() and os.access(root, os.R_OK | os.W_OK)):
            self.service = None
            self.show_setup()
            return
        try:
            self.service = NotesService(root, self.storage.data_dir, self.settings, SystemClock())
            self.report = self.service.start()
        except Exception as exc:  # Start darf die App nicht beenden; Ursache anzeigen
            self.service = None
            self.say(f"Notizordner konnte nicht geöffnet werden: {type(exc).__name__}: {exc}")
            self.show_setup()
            return
        self.nav.visible = True
        self.say(tabs.start_hint(self.report))
        self.render()

    def show_setup(self) -> None:
        """Einrichtung: Zugriff erteilen und Notizordner wählen."""
        self.nav.visible = False
        self.body.controls = tabs.setup_view(self)
        self.page.update()

    async def choose_folder(self, path: str | None = None) -> None:
        """Übernimmt einen Notizordner (gewählt oder eingetippt) und öffnet ihn.

        Args:
            path: Eingetippter Pfad oder ``None`` für die Systemauswahl.
        """
        path = path or await self.access.pick_folder()
        if not path:
            self.say("Kein Ordner gewählt (oder Android hat keinen echten Pfad geliefert – dann bitte eintippen).")
            self.show_setup()
            return
        self.settings = replace(self.settings, vault=path)
        save_settings(self.storage.data_dir, self.settings)
        await self.open_vault()

    async def save_settings(self, settings: Settings) -> None:
        """Speichert geänderte Einstellungen und öffnet den Vault neu."""
        try:
            save_settings(self.storage.data_dir, settings.validated())
        except ValueError as exc:
            self.say(str(exc))
            return
        self.settings = settings
        await self.open_vault()

    async def act(self, action) -> None:
        """Führt eine Service-Aktion aus, meldet Fehler und zeichnet neu.

        Args:
            action: Funktion ``service → beliebig``.
        """
        if self.service is None:
            return
        try:
            action(self.service)
            self.say("")
        except Exception as exc:  # Fehler sichtbar machen, nichts verschlucken
            self.say(f"{type(exc).__name__}: {exc}")
        self.service.rescan()
        self.render()

    def say(self, message: str) -> None:
        """Zeigt eine Statusmeldung (leer = ausblenden)."""
        self.status.value = message
        self.status.visible = bool(message)

    def render(self) -> None:
        """Zeichnet den aktuellen Tab neu."""
        builders = (tabs.today_view, tabs.todos_view, tabs.search_view, tabs.conflicts_view, tabs.settings_view)
        self.body.controls = builders[self.tab](self)
        self.page.update()

    async def _on_tab(self, event) -> None:
        """Tab-Wechsel über die Navigationsleiste."""
        self.tab = int(event.control.selected_index)
        self.render()

    async def _on_lifecycle(self, event) -> None:
        """Beim Zurückkehren in den Vordergrund sofort auf Änderungen prüfen."""
        if "resume" in str(getattr(event, "state", "")).lower():
            await self._poll_once()

    async def _poll_loop(self) -> None:
        """Prüft im Vordergrund regelmäßig auf Änderungen (Watcher ist nur Hinweisgeber)."""
        while True:
            await asyncio.sleep(self.settings.poll_seconds)
            await self._poll_once()

    async def _poll_once(self) -> None:
        """Ein Poll: Quarantänen abschließen, bei Änderungen neu zeichnen."""
        if self.service is None:
            return
        try:
            if self.service.poll().any:
                self.render()
        except Exception as exc:
            self.say(f"Prüfung fehlgeschlagen: {exc}")
            self.page.update()


async def main(page: ft.Page) -> None:
    """Einstiegspunkt für ``ft.run``."""
    storage = await resolve_app_storage()
    await MobileApp(page, storage, FletFolderAccess()).start()
