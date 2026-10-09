"""Test-Attrappen (keine echten Uhren, keine echten Nutzerdaten)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


class FakeClock:
    """Steuerbare Uhr: Wanduhr und monotone Zeit getrennt verstellbar.

    Args:
        start: Anfangszeitpunkt der Wanduhr (Standard: 2026-01-15 10:00 UTC+1).
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 15, 10, 0, tzinfo=timezone(timedelta(hours=1)))
        self._mono = 1000.0

    def now(self) -> datetime:
        """Aktuelle (vorgegebene) Wanduhrzeit."""
        return self._now

    def today(self) -> date:
        """Datum der vorgegebenen Wanduhrzeit."""
        return self._now.date()

    def monotonic(self) -> float:
        """Vorgegebene monotone Zeit."""
        return self._mono

    def advance(self, seconds: float) -> None:
        """Lässt Wanduhr und monotone Zeit gemeinsam vorlaufen.

        Args:
            seconds: Dauer in Sekunden.
        """
        self._now += timedelta(seconds=seconds)
        self._mono += seconds

    def jump_wall(self, seconds: float) -> None:
        """Verstellt nur die Wanduhr (Zeitsprung); die monotone Zeit bleibt.

        Args:
            seconds: Sprung in Sekunden (auch negativ).
        """
        self._now += timedelta(seconds=seconds)
