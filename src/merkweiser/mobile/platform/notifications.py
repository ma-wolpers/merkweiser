"""Adapter für geplante Benachrichtigungen (W5): Erweiterung ``merkweiser_notify`` oder No-op.

Plattform-Isolation (Projektregel): Die App spricht nur ``Notifier`` an. Ist das
Erweiterungspaket nicht installiert (Desktop, Tests, APK ohne Erweiterung)
oder antwortet die Plattform nicht (kein Android), ist ``available`` falsch
und alle Aufrufe tun nichts.

BAUSTELLE(S5): Die App-APK enthält die Erweiterung erst, wenn der Gerätetest
des Spikes S5 bestanden ist (dann ``merkweiser-notify`` in
``[tool.flet.android] dependencies`` und ``[tool.flet.dev_packages]``).
"""

from __future__ import annotations

from typing import Any


class NoNotifier:
    """Keine Benachrichtigungen verfügbar."""

    available = False
    reason = "In dieser Version noch nicht verfügbar (Test S5 läuft)."

    async def permission(self) -> str:
        return "nicht verfügbar"

    async def request_permission(self) -> str:
        return "nicht verfügbar"

    async def schedule(self, items: list[dict[str, Any]]) -> int:
        return 0

    async def cancel_all(self) -> None:
        return None

    async def launch_payload(self) -> str | None:
        return None


class PluginNotifier:
    """Über die Flet-Erweiterung (Android); fällt bei Plattformfehlern auf „nicht verfügbar“ zurück."""

    def __init__(self, service) -> None:
        self._service = service
        self.available = True
        self.reason = ""

    async def _call(self, method: str, *args, default=None):
        if not self.available:
            return default
        try:
            return await getattr(self._service, method)(*args)
        except Exception as exc:  # z. B. MissingPluginException außerhalb von Android
            self.available, self.reason = False, f"Benachrichtigungen nicht verfügbar: {type(exc).__name__}"
            return default

    async def permission(self) -> str:
        return await self._call("permission", default="nicht verfügbar")

    async def request_permission(self) -> str:
        return await self._call("request_permission", default="nicht verfügbar")

    async def schedule(self, items: list[dict[str, Any]]) -> int:
        return await self._call("schedule", items, default=0)

    async def cancel_all(self) -> None:
        await self._call("cancel_all")

    async def launch_payload(self) -> str | None:
        return await self._call("launch_payload")


def make_notifier():
    """``PluginNotifier``, falls die Erweiterung installiert ist, sonst ``NoNotifier`` (im Seitenkontext aufrufen)."""
    try:
        from merkweiser_notify import MerkweiserNotify
    except ImportError:
        return NoNotifier()
    return PluginNotifier(MerkweiserNotify())
