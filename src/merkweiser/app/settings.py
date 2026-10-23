"""Einstellungen als JSON in den App-Daten (nie im Vault).

Felder laut PLAN.md: Notizordner, Dateinamensmuster, Projekt-Präfix,
Poll-Intervall und Aufbewahrung (Backups und Historie, Standard 30 Tage);
dazu die Einrückbreite des Editors (2 oder 4 Leerzeichen) und die
Morgen-Benachrichtigung (W5: an/aus, Uhrzeit, Eskalation, Urlaub, Vorplanung).
Einstellungen, die nur die Oberfläche betreffen, verändern nie den Vault.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from datetime import date, time
from pathlib import Path

from ..core.appdata import write_json_atomic
from ..core.vault import DEFAULT_PATTERN, DayPattern
from .list_editing import INDENT_WIDTHS


@dataclass(frozen=True)
class Settings:
    """Einstellungen eines Geräts.

    Attributes:
        vault: Notizordner (absoluter Pfad auf diesem Gerät) oder ``None``.
        pattern: Dateinamensmuster der Tagesdateien.
        project_prefix: Präfix für Projekt-Tags.
        poll_seconds: Abstand der Änderungsprüfung.
        retention_days: Aufbewahrung von Backups und veralteten Historienständen.
        report_dir: Ordner für Diagnoseberichte (z. B. ein per Syncthing geteilter
            Ordner außerhalb des Vaults) oder ``None``.
        indent_width: Leerzeichen je Einrückungsebene im Editor (2 oder 4;
            Standard 4 = ein Tab in Obsidian).
        notify_enabled: Morgen-Benachrichtigung an (Standard aus; das erste
            Einschalten fragt die Android-Berechtigung an).
        notify_time: Uhrzeit ``HH:MM`` (Standard 07:00).
        notify_escalate: Neutrale Erinnerungen eskalieren (Standard an).
        vacation_until: Urlaub bis einschließlich ``JJJJ-MM-TT`` oder ``None``.
        notify_horizon: Vorgeplante Termine (1–30, Standard 14).
    """

    vault: str | None = None
    pattern: str = DEFAULT_PATTERN
    project_prefix: str = "projekt"
    poll_seconds: float = 5.0
    retention_days: int = 30
    report_dir: str | None = None
    indent_width: int = 4
    notify_enabled: bool = False
    notify_time: str = "07:00"
    notify_escalate: bool = True
    vacation_until: str | None = None
    notify_horizon: int = 14

    def notify_at(self) -> time:
        """Uhrzeit der Benachrichtigung als ``time``."""
        return time.fromisoformat(self.notify_time)

    def vacation_date(self) -> date | None:
        """Urlaubsende als ``date`` oder ``None``."""
        return date.fromisoformat(self.vacation_until) if self.vacation_until else None

    def validated(self) -> "Settings":
        """Prüft die Werte.

        Returns:
            ``self``.

        Raises:
            ValueError: ungültiges Muster, Präfix oder Zahlenwert.
        """
        DayPattern(self.pattern)
        if not self.project_prefix or any(c.isspace() or c == "#" for c in self.project_prefix):
            raise ValueError("Projekt-Präfix ohne Leerzeichen und ohne #")
        if self.poll_seconds <= 0 or self.retention_days < 1:
            raise ValueError("Poll-Intervall > 0 und Aufbewahrung ≥ 1 Tag")
        if self.indent_width not in INDENT_WIDTHS:
            raise ValueError("Einrückung: 2 oder 4 Leerzeichen")
        try:
            self.notify_at()
            self.vacation_date()
        except ValueError as exc:
            raise ValueError("Uhrzeit als HH:MM, Urlaub als JJJJ-MM-TT") from exc
        if not 1 <= self.notify_horizon <= 30:
            raise ValueError("Vorplanung: 1 bis 30 Tage")
        return self


def load_settings(app_data: Path) -> Settings:
    """Lädt die Einstellungen; unbekannte Felder werden ignoriert.

    Args:
        app_data: App-Datenverzeichnis.

    Returns:
        Gespeicherte oder Standard-Einstellungen.
    """
    path = app_data / "settings.json"
    if not path.exists():
        return Settings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known}).validated()


def save_settings(app_data: Path, settings: Settings) -> None:
    """Speichert die Einstellungen atomar.

    Args:
        app_data: App-Datenverzeichnis.
        settings: Zu speichernde Werte (werden geprüft).
    """
    app_data.mkdir(parents=True, exist_ok=True)
    write_json_atomic(app_data / "settings.json", asdict(settings.validated()))
