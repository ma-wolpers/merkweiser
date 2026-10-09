"""Systemuhr als Implementierung des ``Clock``-Ports (nur Standardbibliothek)."""

from __future__ import annotations

import time
from datetime import date, datetime


class SystemClock:
    """Echte Uhr: lokale Gerätezeitzone und ``time.monotonic``."""

    def now(self) -> datetime:
        """Aktuelle lokale Zeit mit Zeitzone des Geräts.

        Returns:
            Zeitzonenbewusster Zeitpunkt.
        """
        return datetime.now().astimezone()

    def today(self) -> date:
        """Aktuelles lokales Datum.

        Returns:
            Datum in der Gerätezeitzone (Tageswechsel um Mitternacht).
        """
        return self.now().date()

    def monotonic(self) -> float:
        """Monotone Zeit in Sekunden.

        Returns:
            Wert von ``time.monotonic()``; nur Differenzen sind sinnvoll.
        """
        return time.monotonic()
