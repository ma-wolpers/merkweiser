"""Speicher-Cache für gelesene Dokumente (nur Geschwindigkeit, nie Wahrheit).

Ein persistenter Index ist bewusst nicht vorgesehen (``BAUSTELLE`` laut PLAN.md).
Dieser Cache lebt nur im Speicher und wird über ``(mtime_ns, size)``
invalidiert.

GRENZE: Ändert sich eine Datei, ohne dass sich ``mtime_ns`` oder ``size``
ändern (z. B. bei grober mtime-Auflösung mancher Dateisysteme), kann die
Suche kurz einen veralteten Stand zeigen. Korrektheit von Änderungen hängt
davon nicht ab: Jede Schreiboperation liest die Datei neu und prüft sie per
Guard bzw. Tausch-Protokoll.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .document import Document, parse_document
from .tags import DEFAULT_PROJECT_PREFIX
from .textfile import read_snapshot


@dataclass(frozen=True)
class _Entry:
    """Zwischengespeichertes Dokument mit Änderungshinweis."""

    mtime_ns: int
    size: int
    document: Document


class DocumentCache:
    """Liefert geparste Dokumente und liest nur geänderte Dateien neu.

    Args:
        root: Vault-Ordner.
        project_prefix: Projekt-Präfix für die Tag-Auswertung.
    """

    def __init__(self, root: Path, project_prefix: str = DEFAULT_PROJECT_PREFIX) -> None:
        self._root = root
        self._prefix = project_prefix
        self._entries: dict[str, _Entry] = {}

    def get(self, relpath: str) -> Document:
        """Liefert das Dokument zu einem relativen Pfad.

        Args:
            relpath: Pfad relativ zum Vault (mit ``/``).

        Returns:
            Das (ggf. neu gelesene) Dokument.

        Raises:
            FileNotFoundError: wenn die Datei nicht mehr existiert (Eintrag wird verworfen).
        """
        path = self._root / relpath
        try:
            stat = os.stat(path)
        except FileNotFoundError:
            self._entries.pop(relpath, None)
            raise
        entry = self._entries.get(relpath)
        if entry and (entry.mtime_ns, entry.size) == (stat.st_mtime_ns, stat.st_size):
            return entry.document
        snapshot = read_snapshot(path)
        document = parse_document(snapshot.raw, self._prefix)
        self._entries[relpath] = _Entry(snapshot.mtime_ns, snapshot.size, document)
        return document

    def forget(self, relpath: str) -> None:
        """Verwirft den Eintrag einer Datei (z. B. nach eigenem Schreiben).

        Args:
            relpath: Pfad relativ zum Vault.
        """
        self._entries.pop(relpath, None)

    def retain(self, relpaths: set[str]) -> None:
        """Entfernt Einträge für Dateien, die nicht mehr im Vault sind.

        Args:
            relpaths: Alle aktuell bekannten Pfade.
        """
        for stale in set(self._entries) - relpaths:
            del self._entries[stale]
