"""Flet-/Android-Adapter für ``AppStorage`` und ``FolderAccess`` (Flet 0.86.5).

Geprüft gegen die gepinnte Version:

* ``ft.StoragePaths().get_application_support_directory()`` liefert das private
  App-Verzeichnis (``Path.home()`` ist auf Android nicht beschreibbar; Befund
  aus namenfit-mobile). Davon nutzt Merkweiser den Unterordner ``data``.
* ``ft.FilePicker()`` ist ein Service: nur konstruieren, nicht ins Overlay;
  ``get_directory_path`` ist eine Koroutine.

BAUSTELLE(S1): Berechtigungsabfrage und Einstellungsseite über ``pyjnius``
(``Environment.isExternalStorageManager``, Intent
``ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION``) sind auf dem Gerät noch
nicht bestätigt. Fehlt ``jnius`` (Desktop-Test) oder schlägt der Aufruf fehl,
melden die Methoden ``None`` bzw. ``False``; die Oberfläche erklärt dann den
manuellen Weg in den Android-Einstellungen.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import flet as ft


@dataclass(frozen=True)
class ResolvedAppStorage:
    """``AppStorage`` mit einem vorab aufgelösten Pfad.

    Attributes:
        path: Privates Datenverzeichnis.
    """

    path: Path

    @property
    def data_dir(self) -> Path:
        """Das Datenverzeichnis (wird bei Bedarf angelegt)."""
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path


async def resolve_app_storage() -> ResolvedAppStorage:
    """Ermittelt das private App-Verzeichnis (innerhalb eines laufenden Page-Kontexts aufrufen).

    Returns:
        ``AppStorage`` für ``<support-dir>/data``.
    """
    support = await ft.StoragePaths().get_application_support_directory()
    return ResolvedAppStorage(Path(support) / "data")


class FletFolderAccess:
    """``FolderAccess`` über Flets FilePicker und ``pyjnius``."""

    def __init__(self) -> None:
        self._picker = ft.FilePicker()

    async def pick_folder(self) -> str | None:
        """Ordnerauswahl des Systems.

        Returns:
            Pfad oder ``None`` (abgebrochen, oder Android liefert keinen echten
            Pfad, z. B. eine ``content://``-URI).
        """
        path = await self._picker.get_directory_path(dialog_title="Notizordner wählen")
        if not path or path.startswith("content://"):
            return None
        return path

    def has_all_files_access(self) -> bool | None:
        """Fragt „Zugriff auf alle Dateien“ ab.

        Returns:
            Status oder ``None``, wenn er sich nicht ermitteln lässt.
        """
        try:
            from jnius import autoclass  # nur auf Android vorhanden

            return bool(autoclass("android.os.Environment").isExternalStorageManager())
        except Exception:
            return None

    def request_all_files_access(self) -> bool:
        """Öffnet die Android-Einstellungsseite „Zugriff auf alle Dateien“ dieser App.

        Returns:
            ``True``, wenn die Seite geöffnet werden konnte.
        """
        try:
            from jnius import autoclass

            intent_cls = autoclass("android.content.Intent")
            settings = autoclass("android.provider.Settings")
            uri = autoclass("android.net.Uri")
            context = autoclass("android.app.ActivityThread").currentApplication()
            intent = intent_cls(settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
            intent.setData(uri.parse("package:" + context.getPackageName()))
            intent.addFlags(intent_cls.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            return True
        except Exception:
            return False
