"""Ports für App-Datenverzeichnis und Ordnerzugriff (plattformneutral).

Die Mobile-Oberfläche hängt nur von diesen Protocols ab; die einzigen Stellen,
die Flet- bzw. Android-APIs benennen, sind ``merkweiser.mobile.platform``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class AppStorage(Protocol):
    """Liefert das private App-Datenverzeichnis (nie im Vault)."""

    @property
    def data_dir(self) -> Path:
        """Verzeichnis für Einstellungen, Op-Verzeichnisse, Historie (wird bei Bedarf angelegt)."""
        ...


class FolderAccess(Protocol):
    """Ordnerwahl und Zugriffsrecht auf den geteilten Speicher."""

    async def pick_folder(self) -> str | None:
        """Lässt den Nutzer einen Ordner wählen.

        Returns:
            Echter Dateipfad oder ``None`` (abgebrochen bzw. nicht als Pfad darstellbar).
        """
        ...

    def has_all_files_access(self) -> bool | None:
        """``True``/``False``, oder ``None``, wenn es sich nicht feststellen lässt."""
        ...

    def request_all_files_access(self) -> bool:
        """Öffnet die Systemseite zum Erteilen des Zugriffs.

        Returns:
            ``True``, wenn die Seite geöffnet werden konnte.
        """
        ...
