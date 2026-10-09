"""Polling-Watcher: meldet Unterschiede zwischen zwei Beobachtungen (kein Event-System).

Semantik (PLAN.md, „Watcher“): ``poll`` vergleicht den aktuellen Zustand mit
dem vorherigen und meldet hinzugekommene, entfernte und geänderte
Markdown-Dateien (inklusive Konfliktdateien). Zwischenstände zwischen zwei
Polls werden **nicht** garantiert gemeldet; maßgeblich ist immer der aktuelle
Plattenstand. Die Korrektheit von Änderungen hängt nie am Watcher, sondern
an Guards bzw. Tausch-Protokoll.

``(mtime_ns, size)`` ist nur ein Änderungshinweis (keine Identität).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

State = dict[str, tuple[int, int]]


@dataclass(frozen=True)
class Changes:
    """Unterschiede zwischen zwei Beobachtungen.

    Attributes:
        added: Neu aufgetauchte Dateien.
        removed: Verschwundene Dateien.
        modified: Dateien mit geändertem ``(mtime_ns, size)``.
    """

    added: frozenset[str]
    removed: frozenset[str]
    modified: frozenset[str]

    @property
    def any(self) -> bool:
        """``True``, wenn sich irgendetwas geändert hat."""
        return bool(self.added or self.removed or self.modified)


def observe(root: Path) -> State:
    """Erfasst den aktuellen Zustand aller sichtbaren Markdown-Dateien.

    Versteckte Ordner und Dateien (``.obsidian``, ``.NAME.mw-*`` …) werden
    übersprungen. Dateien, die während des Scans verschwinden, fehlen einfach.

    Args:
        root: Vault-Ordner.

    Returns:
        Relativer Pfad (mit ``/``) → ``(mtime_ns, size)``.
    """
    state: State = {}
    for folder, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        rel_folder = Path(folder).relative_to(root).as_posix()
        for name in filenames:
            if name.startswith(".") or not name.endswith(".md"):
                continue
            try:
                stat = os.stat(os.path.join(folder, name))
            except FileNotFoundError:
                continue
            state[name if rel_folder == "." else f"{rel_folder}/{name}"] = (stat.st_mtime_ns, stat.st_size)
    return state


def poll(root: Path, previous: State) -> tuple[Changes, State]:
    """Beobachtet erneut und vergleicht mit dem vorherigen Zustand.

    Args:
        root: Vault-Ordner.
        previous: Ergebnis der letzten Beobachtung (leer beim ersten Mal).

    Returns:
        Unterschiede und der neue Zustand.
    """
    current = observe(root)
    changes = Changes(added=frozenset(current.keys() - previous.keys()),
                      removed=frozenset(previous.keys() - current.keys()),
                      modified=frozenset(p for p in current.keys() & previous.keys() if current[p] != previous[p]))
    return changes, current
