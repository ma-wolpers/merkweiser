"""Mobile-App: Kompositionswurzel, Einrichtung, Navigation und Polling (Flet 0.86.5).

Regel: Alle ``NotesService``-Aufrufe laufen in **async**-Handlern auf dem
Event-Loop von Flet. Damit sind sie untereinander und mit der Polling-Schleife
serialisiert; der Service braucht keine Thread-Sicherheit.

Ablauf: App-Datenverzeichnis auflösen → Einstellungen laden → ist ein
lesbarer Notizordner eingestellt, wird ``NotesService.start()`` ausgeführt
(Wiederherstellung, Scan, Auto-Merge) und die Hauptansicht gezeigt; sonst die
Einrichtung (Zugriff erteilen, Ordner wählen).

Navigation (PLAN-SPAETERE-SCHRITTE.md 1.6): ``self.pages`` (``app.nav.Nav``)
ist die einzige Wahrheit über Tab und Unterseite; jeder Tab hat seinen eigenen
Stapel. Es gibt nur **eine** Flet-View. Android-Zurück: Die Wurzel-View hat
``can_pop=False`` und ``on_confirm_pop``; Flet 0.86.5 fragt dann bei jedem
Zurück nach (``view.dart``: ``PopScope`` → ``confirm_pop``). Merkweiser geht in
``Nav`` zurück und antwortet ``confirm_pop(False)``; nur an der Wurzel des Tabs
„Tag“ antwortet es ``True`` (Flet ruft ``SystemNavigator.pop``). Offene Dialoge
schließt Flutter selbst, bevor die View gefragt wird.
BAUSTELLE(Zurück): Verhalten auf dem Gerät nach Phase 2 prüfen.
"""

from __future__ import annotations

import asyncio
import os
from collections import deque
from datetime import date, datetime
from dataclasses import replace
from pathlib import Path

import flet as ft

from ...app.diagnostics import build_report, write_report
from ...app.interrupted import open_issue_count
from ...app.nav import Nav, PageRef
from ...app.notes_service import NotesService, StartReport
from ...app.settings import Settings, load_settings, save_settings
from ...core.clock import SystemClock
from ...ports.storage_access import AppStorage, FolderAccess
from ..platform.flet_access import FletFolderAccess, resolve_app_storage
from . import pages, tabs

TAB_NAMES = ("Tag", "Todos", "Suche", "Einstellungen")
TAB_ICONS = (ft.Icons.TODAY, ft.Icons.CHECKLIST, ft.Icons.SEARCH, ft.Icons.SETTINGS)
SETTINGS_TAB = TAB_NAMES.index("Einstellungen")


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
        self.pages = Nav(len(TAB_NAMES))
        self.day: date = date.today()  # beim Öffnen des Vaults auf „heute“ laut Service-Uhr gesetzt
        self.messages: deque[tuple[datetime, str]] = deque(maxlen=30)
        self.status = ft.Text("", size=12, color=ft.Colors.ERROR)
        self.status_link = ft.TextButton("Konflikte ansehen", visible=False, on_click=self._open_conflicts)
        self.body = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)
        self.nav = ft.NavigationBar(
            destinations=[ft.NavigationBarDestination(icon=i, label=n) for i, n in zip(TAB_ICONS, TAB_NAMES)],
            selected_index=0, on_change=self._on_tab)

    async def start(self) -> None:
        """Baut die Seite auf und öffnet den Vault oder die Einrichtung."""
        self.page.title = "Merkweiser"
        self.page.on_app_lifecycle_state_change = self._on_lifecycle
        self.page.add(ft.SafeArea(content=ft.Column([self.status, self.status_link, self.body], expand=True),
                                  expand=True))
        self.page.navigation_bar = self.nav
        root_view = self.page.views[0]
        root_view.can_pop = False
        root_view.on_confirm_pop = self._on_confirm_pop
        await self.open_vault()
        self.page.run_task(self._poll_loop)

    async def open_vault(self) -> None:
        """Öffnet den eingestellten Vault oder zeigt die Einrichtung."""
        root = Path(self.settings.vault) if self.settings.vault else None
        # Lesbar genügt: Ohne sichere Schreibweise öffnet NotesService schreibgeschützt.
        if root is None or not (root.is_dir() and os.access(root, os.R_OK)):
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
        self.day = self.service.clock.today()  # beim Öffnen der App ist immer „heute“ gewählt
        issues = open_issue_count(self.service)
        self.say(tabs.start_hint(self.report, self.service.write_guarantee, issues), link=issues > 0)
        self.render()

    @property
    def tab(self) -> int:
        """Index des aktuellen Tabs (aus ``self.pages``)."""
        return self.pages.current

    def show_day(self, day: date) -> None:
        """Wechselt in den Tab „Tag“ (Wurzel) mit genau diesem Datum (z. B. aus der Suche).

        Args:
            day: Anzuzeigender Tag.
        """
        self.day = day
        self.pages.show_root(0)
        self.render()

    def open_page(self, page: PageRef) -> None:
        """Öffnet eine Unterseite im aktuellen Tab.

        Args:
            page: Die Seite.
        """
        self.pages.push(page)
        self.render()

    def open_conflicts(self) -> None:
        """Zeigt Einstellungen → Konflikte (Start-Hinweis, Konflikt beim Schreiben)."""
        self.pages.show_root(SETTINGS_TAB)
        self.pages.push(PageRef("konflikte"))
        self.say("")
        self.render()

    async def _open_conflicts(self, _e) -> None:
        """Klick auf „Konflikte ansehen“."""
        self.open_conflicts()

    def open_tag(self, tag: str) -> None:
        """Öffnet die Tag-Seite im aktuellen Tab (W2).

        Args:
            tag: Tag-Schlüssel ohne ``#``.
        """
        self.pages.push(PageRef("tag", tag))
        self.render()

    def go_back(self) -> bool:
        """Eine Seite zurück im aktuellen Tab (Zurück-Knopf und Android-Zurück).

        Returns:
            ``False`` an der Wurzel des Tabs „Tag“ (nichts mehr zurück).
        """
        moved = self.pages.back()
        if moved:
            self.render()
        return moved

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

    async def act(self, action):
        """Führt eine Service-Aktion aus, meldet Fehler und Konflikte und zeichnet neu.

        Endet ein Schreibvorgang als ``CONFLICTED`` (die Datei wurde
        zwischenzeitlich verändert), wird das sofort gemeldet, statt dass die
        Konfliktdatei erst später unter Einstellungen → Konflikte auffällt.

        Args:
            action: Funktion ``service → beliebig``.

        Returns:
            Rückgabe der Aktion oder ``None`` bei Fehler bzw. ohne geöffneten Vault.
        """
        if self.service is None:
            return None
        result = None
        try:
            result = action(self.service)
            conflicted = getattr(result, "state", None) == "CONFLICTED"
            self.say("Die Datei wurde zwischendurch verändert. Deine Fassung liegt als Konfliktdatei vor "
                     "(Einstellungen → Konflikte)." if conflicted else "", link=conflicted)
        except Exception as exc:  # Fehler sichtbar machen, nichts verschlucken
            self.say(f"{type(exc).__name__}: {exc}")
        self.service.rescan()
        self.render()
        return result

    def say(self, message: str, link: bool = False) -> None:
        """Zeigt eine Statusmeldung (leer = ausblenden).

        Args:
            message: Text der Meldung.
            link: Darunter „Konflikte ansehen“ anbieten (führt zu Einstellungen → Konflikte).
        """
        self.status_link.visible = bool(message) and link
        if message:
            self.messages.append((datetime.now(), message))
        self.status.color = ft.Colors.ERROR
        self.status.value = message
        self.status.visible = bool(message)

    async def save_diagnostics(self, folder: str | None) -> None:
        """Schreibt einen Diagnosebericht (ohne Notizinhalte) und merkt sich den Ordner.

        Args:
            folder: Zielordner (eingetippt) oder ``None`` für die Systemauswahl.
        """
        folder = folder or await self.access.pick_folder()
        if not folder:
            self.say("Kein Ordner für den Diagnosebericht gewählt.")
            self.render()
            return
        now = datetime.now()
        text = build_report(self.settings, self.service, self.report, list(self.messages), now,
                            {"flet": ft.__version__})
        try:
            path = write_report(Path(folder), text, now)
        except OSError as exc:
            hint = (" Android sperrt die privaten Ordner anderer Apps (…/Android/data/…), auch mit „Alle Dateien“. "
                    "Bitte einen Ordner außerhalb davon wählen, z. B. /storage/emulated/0/Download."
                    if "/Android/" in folder else "")
            self.say(f"Diagnosebericht nicht gespeichert: {type(exc).__name__}: {exc}.{hint}")
            self.render()
            return
        if folder != self.settings.report_dir:
            self.settings = replace(self.settings, report_dir=folder)
            save_settings(self.storage.data_dir, self.settings)
        self.status.value, self.status.visible = f"Diagnosebericht gespeichert: {path.name}", True
        self.status.color = ft.Colors.PRIMARY
        self.render()

    def render(self) -> None:
        """Zeichnet die oberste Seite des aktuellen Tabs (Unterseite oder Tab-Wurzel) neu."""
        builders = (tabs.day_view, tabs.todos_view, tabs.search_view, tabs.settings_view)
        top = self.pages.top()
        self.body.controls = pages.build_page(self, top) if top else builders[self.pages.current](self)
        self.nav.selected_index = self.pages.current
        self._update_badge()
        self.page.update()

    def _update_badge(self) -> None:
        """Badge am Einstellungen-Symbol: offene Konflikte und unterbrochene Vorgänge (W4)."""
        count = open_issue_count(self.service) if self.service else 0
        self.nav.destinations[SETTINGS_TAB].icon = ft.Icon(ft.Icons.SETTINGS, badge=str(count) if count else None)

    async def _on_tab(self, event) -> None:
        """Tab gewählt: Stapel der anderen Tabs bleiben, der aktive springt zur Wurzel."""
        self.pages.select(int(event.control.selected_index))
        self.render()

    async def _on_confirm_pop(self, event) -> None:
        """Android-Zurück an der Wurzel-View: erst in ``Nav`` zurück, sonst dem System überlassen."""
        await event.control.confirm_pop(not self.go_back())

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
