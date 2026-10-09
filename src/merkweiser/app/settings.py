"""Einstellungen als JSON in den App-Daten (nie im Vault).

Felder laut PLAN.md: Notizordner, Dateinamensmuster, Projekt-Präfix,
Poll-Intervall und Aufbewahrung (Backups und Historie, Standard 30 Tage).
Einstellungen, die nur die Oberfläche betreffen, verändern nie den Vault.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ..core.appdata import write_json_atomic
from ..core.vault import DEFAULT_PATTERN, DayPattern


@dataclass(frozen=True)
class Settings:
    """Einstellungen eines Geräts.

    Attributes:
        vault: Notizordner (absoluter Pfad auf diesem Gerät) oder ``None``.
        pattern: Dateinamensmuster der Tagesdateien.
        project_prefix: Präfix für Projekt-Tags.
        poll_seconds: Abstand der Änderungsprüfung.
        retention_days: Aufbewahrung von Backups und veralteten Historienständen.
    """

    vault: str | None = None
    pattern: str = DEFAULT_PATTERN
    project_prefix: str = "projekt"
    poll_seconds: float = 5.0
    retention_days: int = 30

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
