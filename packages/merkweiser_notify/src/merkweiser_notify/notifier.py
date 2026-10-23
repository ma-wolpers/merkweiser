"""Flet-Service ``MerkweiserNotify``: Python-Seite der Erweiterung (siehe README).

Jede Methode ruft gleichnamig die Dart-Seite (``notify_service.dart``) auf, die
per ``MethodChannel("merkweiser_notify")`` an das Kotlin-Plugin weitergibt.
Nur auf Android wirksam; auf anderen Plattformen wirft die Dart-Seite einen
Fehler (``MissingPluginException``), den der Aufrufer abfängt.
"""

from __future__ import annotations

from typing import Any, Optional

import flet as ft

PERMISSION_TIMEOUT = 300.0
"""Sekunden, die ``request_permission`` auf die Antwort im Systemdialog wartet."""


@ft.control("MerkweiserNotify")
class MerkweiserNotify(ft.Service):
    """Geplante Benachrichtigungen (ein Service je Seite; meldet sich beim Erzeugen selbst an)."""

    async def permission(self) -> str:
        """``"granted"`` oder ``"denied"``."""
        return await self._invoke_method("permission")

    async def request_permission(self) -> str:
        """Fragt (ab Android 13) nach der Berechtigung und liefert den Zustand danach."""
        return await self._invoke_method("request_permission", timeout=PERMISSION_TIMEOUT)

    async def schedule(self, items: list[dict[str, Any]]) -> int:
        """Ersetzt alle geplanten Benachrichtigungen.

        Args:
            items: Je Eintrag ``id`` (int), ``at`` (Millisekunden seit 1970, UTC),
                ``title``, ``body``, ``level`` (``normal``/``hoch``/``maximal``).

        Returns:
            Anzahl der geplanten (in der Zukunft liegenden) Einträge.
        """
        return await self._invoke_method("schedule", {"items": items})

    async def cancel_all(self) -> None:
        """Storniert alle geplanten Benachrichtigungen."""
        await self._invoke_method("cancel_all")

    async def status(self) -> dict[str, Any]:
        """Zustand für Anzeige und Spike-Bericht: ``permission``, ``pending``, ``exact_allowed``, ``battery_unrestricted``."""
        return await self._invoke_method("status")

    async def launch_payload(self) -> Optional[str]:
        """``"heute"``, wenn die App über eine Benachrichtigung geöffnet wurde (einmalig), sonst ``None``."""
        return await self._invoke_method("launch_payload")
