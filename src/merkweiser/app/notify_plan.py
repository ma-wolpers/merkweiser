"""Benachrichtigungen planen – rein, ohne Plattform (W5, PLAN-SPAETERE-SCHRITTE.md).

Flet 0.86.5 kann kein Python im Hintergrund ausführen. Deshalb wird beim
Verlassen der App alles für die nächsten Tage **vorgeplant**:

* **Termin 1** (nächster Termin zur eingestellten Uhrzeit, nicht im Urlaub):
  **Inhalt** laut ``notify_content`` (🔥 rote, dann die Todos des Auslösetags,
  dann gelbe früherer Tage). Titel mit Anzahl (``· 🔥 n · ⭐ m``, gezählt vor
  dem Kürzen), 🔥/⭐-Zeilen fett, Kanal ``hoch`` bei mindestens einem roten
  Todo, sonst ``normal``. Ohne passende Todos keine Inhaltsbenachrichtigung –
  das sperrt die neutralen Erinnerungen nicht. GRENZE(Banner): Ob ``hoch`` als
  Banner erscheint, entscheiden Android und die Kanal-Einstellungen des Nutzers.
* **Folgetermine**: neutral („Öffne Merkweiser, um deine Todos zu sehen“).
  Mit Eskalation: 2. Termin ``normal``, 3. ``hoch``, ab dem 4. ``maximal``.
  Ohne Eskalation: alle ``normal`` mit gleichem Text, weiterhin täglich.
* **Urlaub** (bis einschließlich ``urlaub_bis``): keine Benachrichtigung;
  Zählung und Eskalation pausieren. Liegt Termin 1 im Urlaub, ist der erste
  Termin danach neutral ``normal`` (der Inhalt wäre veraltet).
* **Horizont**: ``vorplanung_tage`` Termine außerhalb des Urlaubs (Standard 14,
  höchstens 30): Android drosselt Alarme lange nicht geöffneter Apps
  (App-Standby-Buckets), mehr wäre nicht verlässlich.
* GRENZE(Benachrichtigung): Der Inhalt ist der Stand beim Planen; später per
  Sync eingetroffene Todos fehlen. GRENZE(Zustellung): Android garantiert keine
  pünktliche Zustellung (ungenaue Alarme, Akkusparen).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from ..core.inline import Urgency
from .notify_content import SYMBOL, NotifyContent

MAX_HORIZON = 30
MAX_LINES = 8
SCAN_LIMIT_DAYS = 400
NEUTRAL = "Öffne Merkweiser, um deine Todos zu sehen."


@dataclass(frozen=True)
class NotifySettings:
    """Die für das Planen nötigen Einstellungen (aus ``Settings``)."""

    enabled: bool
    at: time
    escalate: bool = True
    vacation_until: date | None = None
    horizon: int = 14


@dataclass(frozen=True)
class Planned:
    """Eine geplante Benachrichtigung.

    Attributes:
        id: Termin-Nummer (1 = Inhalt).
        at: Auslösezeitpunkt.
        title: Titel.
        body: Text (Zeilen mit Zeilenumbruch).
        level: ``normal``, ``hoch`` oder ``maximal`` (Kanal).
        bold: Indizes der fett gezeigten Zeilen von ``body`` (nach dem Kürzen).
    """

    id: int
    at: datetime
    title: str
    body: str
    level: str
    bold: tuple[int, ...] = ()

    def as_item(self) -> dict:
        """Eintrag für ``MerkweiserNotify.schedule`` (Zeit in ms seit 1970, ``bold`` als Liste ganzer Zahlen)."""
        return {"id": self.id, "at": int(self.at.timestamp() * 1000), "title": self.title, "body": self.body,
                "level": self.level, "bold": list(self.bold)}


def _moment(day: date, at: time, tz: tzinfo | None) -> datetime:
    """Lokaler Zeitpunkt (Gerätezeitzone mit Sommerzeit, bzw. ``tz`` in Tests)."""
    if tz is None:
        return datetime.combine(day, at).astimezone()
    return datetime.combine(day, at, tzinfo=tz)


def plan(now: datetime, settings: NotifySettings, content_for: Callable[[date], NotifyContent],
         tz: tzinfo | None = None) -> list[Planned]:
    """Alle Benachrichtigungen ab jetzt (siehe Moduldoku).

    Args:
        now: Jetzt (lokal, mit Offset).
        settings: Einstellungen.
        content_for: Inhalt für einen Auslösetag (``notify_content.content``); ohne Zeilen kein Inhalt.
        tz: Zeitzone für die Termine oder ``None`` (Gerät).

    Returns:
        Geplante Benachrichtigungen, zeitlich sortiert.
    """
    if not settings.enabled:
        return []
    horizon = max(1, min(settings.horizon, MAX_HORIZON))
    first = now.date() if now < _moment(now.date(), settings.at, tz) else now.date() + timedelta(days=1)
    planned: list[Planned] = []
    ordinal = 0  # Termine außerhalb des Urlaubs (1 = Inhalt)
    for offset in range(SCAN_LIMIT_DAYS):
        if ordinal >= horizon:
            break
        day = first + timedelta(days=offset)
        if settings.vacation_until is not None and day <= settings.vacation_until:
            if ordinal == 0:
                ordinal = 1  # Termin 1 fällt in den Urlaub: danach geht es neutral weiter
            continue
        ordinal += 1
        when = _moment(day, settings.at, tz)
        if ordinal == 1:
            found = content_for(day)
            if found.lines:
                body, bold = _body(found)
                planned.append(Planned(ordinal, when, _title(day, found), body, "hoch" if found.red else "normal", bold))
            continue
        planned.append(Planned(ordinal, when, "Merkweiser", _neutral(ordinal, settings.escalate),
                               _level(ordinal, settings.escalate)))
    return planned


def _body(found: NotifyContent) -> tuple[str, tuple[int, ...]]:
    """Inhaltstext und Fett-Indizes: höchstens ``MAX_LINES`` Zeilen, Rest als Anzahl.

    Args:
        found: Inhalt vor dem Kürzen.

    Returns:
        ``(Text, Indizes)``; die Indizes zeigen auf die tatsächlich angezeigten
        Zeilen, die Zeile „… und n weitere“ ist nie fett.
    """
    shown = list(found.lines[:MAX_LINES])
    rest = len(found.lines) - len(shown)
    bold = tuple(i for i in found.bold if i < len(shown))
    return "\n".join(shown + ([f"… und {rest} weitere"] if rest else [])), bold


def _title(day: date, found: NotifyContent) -> str:
    """Titel mit Anzahl roter und gelber Todos (Gesamtzahlen vor dem Kürzen; 0 entfällt).

    Args:
        day: Auslösetag.
        found: Inhalt.

    Returns:
        z. B. ``Deine Todos am 27.10. · 🔥 2 · ⭐ 3``.
    """
    counts = [(SYMBOL[Urgency.ROT], found.red), (SYMBOL[Urgency.GELB], found.yellow)]
    return f"Deine Todos am {day:%d.%m.}" + "".join(f" · {symbol} {n}" for symbol, n in counts if n)


def _level(ordinal: int, escalate: bool) -> str:
    """Dringlichkeit des n-ten Termins."""
    if not escalate or ordinal <= 2:
        return "normal"
    return "hoch" if ordinal == 3 else "maximal"


def _neutral(ordinal: int, escalate: bool) -> str:
    """Text einer neutralen Erinnerung."""
    if not escalate or ordinal <= 2:
        return NEUTRAL
    return f"Seit {ordinal - 1} Tagen nicht geöffnet – {NEUTRAL[0].lower()}{NEUTRAL[1:]}"
