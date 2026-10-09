"""Zeit-Port: Wanduhr und monotone Zeit getrennt.

* ``now``/``today``: lokale, zeitzonenbewusste Wanduhr (Tagesdatum,
  Konfliktnamen, Zeitpunkte für Historie und Backups).
* ``monotonic``: ausschließlich für verstrichene Dauern innerhalb eines
  Prozesses (Quarantäne). Nie über Neustarts vergleichen.

Tests verwenden immer eine Attrappe (``tests/fakes.py``), nie die echte Uhr.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    """Zeitquelle für Core und App."""

    def now(self) -> datetime:
        """Aktuelle lokale Zeit mit Zeitzone."""
        ...

    def today(self) -> date:
        """Aktuelles lokales Datum (Tageswechsel um Mitternacht, Gerätezeitzone)."""
        ...

    def monotonic(self) -> float:
        """Monotone Sekunden für Dauern innerhalb eines Prozesses."""
        ...
