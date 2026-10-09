"""Dateizugriff: lesender Snapshot einer Datei.

``FileSnapshot`` hält die Rohbytes und einen schnellen Änderungshinweis
``(mtime_ns, size)``. Der Hinweis ist **keine** Identität und kein Beweis für
Gleichheit (PLAN.md, „Signatur“): Maßgeblich für jede Schreibentscheidung ist
der Inhalt; ``(mtime_ns, size)`` dient nur dem Polling.

Die Primitive des Tausch-Protokolls (exklusiv anlegen, umbenennen ohne
Überschreiben, Schreibsperre, ``fsync``) liegen in ``fsops.py``.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileSnapshot:
    """Inhalt einer Datei zu einem Lesezeitpunkt.

    Attributes:
        raw: Die exakten Bytes.
        mtime_ns: Änderungszeit laut Dateisystem (nur Hinweis).
        size: Größe laut Dateisystem (nur Hinweis).
    """

    raw: bytes
    mtime_ns: int
    size: int

    @property
    def sha1(self) -> str:
        """SHA-1 des Inhalts (Schlüssel für Historie und Backups, nicht für Guards)."""
        return hashlib.sha1(self.raw).hexdigest()

    def same_content(self, other: "FileSnapshot | bytes") -> bool:
        """Vergleicht den Inhalt byte-genau.

        Args:
            other: Ein anderer Snapshot oder Rohbytes.

        Returns:
            ``True`` bei identischen Bytes. Zeitstempel spielen keine Rolle.
        """
        return self.raw == (other.raw if isinstance(other, FileSnapshot) else other)


def read_snapshot(path: Path) -> FileSnapshot:
    """Liest eine Datei vollständig.

    Der Stat-Wert wird über den geöffneten Dateideskriptor ermittelt, damit er
    zur gelesenen Datei gehört, auch wenn der Pfad gleichzeitig ersetzt wird.

    Args:
        path: Dateipfad.

    Returns:
        Der Snapshot.

    Raises:
        FileNotFoundError: wenn die Datei nicht existiert.
    """
    with open(path, "rb") as handle:
        stat = os.fstat(handle.fileno())
        raw = handle.read()
    return FileSnapshot(raw=raw, mtime_ns=stat.st_mtime_ns, size=stat.st_size)
