"""Gerätelokaler Zustand des Zeit-Trackers: Tätigkeitsliste und Umbenennungs-Log (W6, S2).

Liegt je Vault in den App-Daten (``<app-daten>/vaults/<id>/zeit.json``), **nie**
im Vault. Die Minuten und Stempel selbst stehen in den Tagesdateien.

* ``activities``: die Liste dieses Geräts (Standard „Orga“).
* ``renames``: bekannte Umbenennungen ``{alt, neu, zeit, ignoriert}``. Sie
  normalisieren Sync-Konflikte (``merge.frontmatter``) und migrieren später
  per Sync wieder auftauchende alte Schlüssel (``app.time_scan``);
  ``ignoriert`` sind Dateien, bei denen die Nutzerin bzw. der Nutzer „nichts
  ändern“ gewählt hat.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..core.activities import DEFAULT_ACTIVITY
from ..core.appdata import VaultData, write_json_atomic


@dataclass
class TimeState:
    """Zustand des Trackers auf diesem Gerät."""

    activities: list[str] = field(default_factory=lambda: [DEFAULT_ACTIVITY])
    renames: list[dict] = field(default_factory=list)

    def rename_pairs(self) -> tuple[tuple[str, str], ...]:
        """``(alt, neu)`` aller bekannten Umbenennungen, älteste zuerst."""
        return tuple((r["alt"], r["neu"]) for r in self.renames)


def _path(data: VaultData) -> Path:
    return data.base / "zeit.json"


def load_state(data: VaultData) -> TimeState:
    """Lädt den Zustand (Standard, falls noch keiner gespeichert ist)."""
    path = _path(data)
    if not path.exists():
        return TimeState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    activities = raw["taetigkeiten"] if "taetigkeiten" in raw else [DEFAULT_ACTIVITY]  # leer bleibt leer
    return TimeState(list(activities), list(raw.get("umbenennungen") or []))


def save_state(data: VaultData, state: TimeState) -> None:
    """Speichert den Zustand atomar."""
    data.base.mkdir(parents=True, exist_ok=True)
    write_json_atomic(_path(data), {"taetigkeiten": state.activities, "umbenennungen": state.renames})
