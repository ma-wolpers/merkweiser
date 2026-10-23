"""Zeit-Tracker, reiner Rechenteil (W6, PLAN-SPAETERE-SCHRITTE.md S7, 1.7).

* **Dauer** aus absoluten Zeitpunkten (UTC-Differenz): Sommer- und Winterzeit
  ändern die Summe nie.
* **Tagesgrenzen**: lokale Mitternachten in der **aktuellen** Zeitzone des
  Geräts (``tz=None``: Systemregeln über ``datetime.astimezone()``, inklusive
  Sommerzeit; Tests geben eine ``ZoneInfo`` mit).
* **Starttag**: Das erste Segment gehört immer zur Datei des Stempels.
* **Abrunden** je Segment auf ganze Minuten.
* GRENZE(Zeitzone): Wechselt die Zeitzone des Geräts während einer Messung,
  stimmt die Summe; der Teilungspunkt über Mitternacht kann sich um den
  Zeitzonenunterschied verschieben.
* **Veraltet**: Ein Stempel älter als 24 h wird verworfen, ohne Verbuchung.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo

STALE_AFTER = timedelta(hours=24)


def _midnight(day: date, tz: tzinfo | None) -> datetime:
    """Lokale Mitternacht zu Beginn von ``day`` als zeitzonenbewusster Zeitpunkt."""
    if tz is None:
        return datetime.combine(day, time()).astimezone()
    return datetime.combine(day, time(), tzinfo=tz)


def local_date(moment: datetime, tz: tzinfo | None) -> date:
    """Lokales Datum eines Zeitpunkts in der Gerätezeitzone (bzw. ``tz``)."""
    return (moment.astimezone() if tz is None else moment.astimezone(tz)).date()


def segments(start: datetime, end: datetime, start_day: date, tz: tzinfo | None = None) -> list[tuple[date, int]]:
    """Teilt eine Messung an lokalen Mitternachten und rundet je Teil ab.

    Args:
        start: Beginn (mit Offset).
        end: Ende (mit Offset); vor ``start`` → keine Minuten.
        start_day: Tag der Datei mit dem Stempel (erstes Segment).
        tz: Zeitzone für Tagesgrenzen oder ``None`` (Gerät).

    Returns:
        ``(tag, minuten)`` je Tag mit Anteil, aufsteigend; Tage mit 0 Minuten entfallen.
    """
    # Alles in UTC: Python rechnet bei gleicher ``tzinfo`` (z. B. derselben ZoneInfo)
    # nach Wanduhr; in der Umstellungsnacht wäre die Dauer sonst um eine Stunde falsch.
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if end <= start:
        return []
    result: list[tuple[date, int]] = []
    day, cursor = start_day, start
    while cursor < end:
        boundary = max(_midnight(day + timedelta(days=1), tz).astimezone(timezone.utc), cursor)
        part_end = min(boundary, end)
        minutes = int((part_end - cursor).total_seconds() // 60)
        if minutes:
            result.append((day, minutes))
        cursor, day = part_end, day + timedelta(days=1)
    return result


def stale(start: datetime, now: datetime) -> bool:
    """``True``, wenn ein Stempel älter als 24 Stunden ist (echte Dauer, in UTC gerechnet)."""
    return now.astimezone(timezone.utc) - start.astimezone(timezone.utc) > STALE_AFTER


def hm(minutes: int) -> str:
    """Minuten als ``h:mm`` (z. B. ``1:05``)."""
    return f"{minutes // 60}:{minutes % 60:02d}"


def order_activities(names: Iterable[str], last_week: Mapping[str, int]) -> list[str]:
    """Reihenfolge der Tätigkeiten: Minutensumme der letzten 7 Tage absteigend, sonst alphabetisch.

    Args:
        names: Alle Tätigkeiten (Geräteliste und Namen aus den Dateien).
        last_week: Minuten je Tätigkeit in den letzten 7 Tagen.

    Returns:
        Sortierte, eindeutige Namen.
    """
    unique = list(dict.fromkeys(names))
    return sorted(unique, key=lambda n: (-last_week.get(n, 0), n.casefold()))


@dataclass(frozen=True)
class DayTotals:
    """Minuten eines Tages je Tätigkeit."""

    day: date
    minutes: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.minutes.values())


def totals(days: Iterable[DayTotals]) -> dict[str, int]:
    """Summen je Tätigkeit über mehrere Tage."""
    result: dict[str, int] = {}
    for day in days:
        for name, value in day.minutes.items():
            result[name] = result.get(name, 0) + value
    return result
