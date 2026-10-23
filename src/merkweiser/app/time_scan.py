"""Zeit-Tracker: Stempel suchen, veraltete bereinigen, Übersicht, Migration nach Umbenennung (1.7, R1, S2/Y8).

``refresh(service, days, archive)`` liest die Tagesdateien des Zeitraums
(Standard 7 Tage bis heute) bzw. mit ``archive=True`` **alle**. Nur in den
tatsächlich gelesenen Dateien gilt:

* Stempel älter als 24 h werden **gelöscht**, ohne Verbuchung, mit Hinweis.
* Gültige, frische Stempel gelten als laufende Messungen; beschädigte werden
  gemeldet (verwerfen in der Oberfläche).
* Bekannte Umbenennungen: steht ``zeit_alt`` **ohne** ``zeit_neu`` in einer
  Datei (z. B. per Sync wieder aufgetaucht), wird sie automatisch migriert;
  stehen **beide** darin, wird nicht gerechnet, sondern „Umbenennung unklar“
  gemeldet.

Schreibend nur, wenn der Vault beschreibbar ist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING

from ..core.frontmatter import OK, OPAQUE, OPEN, Damaged, Stamp, minutes, parse, stamp_of
from ..core.time_ops import discard_stamp, plan_rename_file, rename
from ..core.timetrack import DayTotals, stale
from .time_state import load_state
from .views import WEEKDAYS

if TYPE_CHECKING:
    from .notes_service import NotesService


@dataclass(frozen=True)
class Running:
    """Eine laufende Messung: Stempel und seine Datei."""

    relpath: str
    day: date
    stamp: Stamp


@dataclass
class ScanResult:
    """Ergebnis von ``refresh``.

    Attributes:
        days: Tagessummen im Anzeigezeitraum, neueste zuerst (auch leere Tage).
        running: Laufende Messungen (gültig, jünger als 24 h).
        damaged: ``(relpath, grund)`` beschädigter Stempel.
        unreadable: Dateien mit Zeit-Schlüsseln in nicht sicher lesbarem Kopf.
        hints: Meldungen (verworfene veraltete Stempel, Migrationen).
        unclear: ``(relpath, tag, alt, neu)`` mit ``zeit_alt`` und ``zeit_neu`` nach einer Umbenennung.
        names: Tätigkeitsnamen, die in den gelesenen Dateien vorkommen.
    """

    days: list[DayTotals] = field(default_factory=list)
    running: list[Running] = field(default_factory=list)
    damaged: list[tuple[str, str]] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    unclear: list[tuple[str, date, str, str]] = field(default_factory=list)
    names: set[str] = field(default_factory=set)


def refresh(service: "NotesService", days: int = 7, archive: bool = False) -> ScanResult:
    """Liest den Zeitraum (bzw. das Archiv), bereinigt und migriert (siehe Moduldoku)."""
    today = service.clock.today()
    since = today - timedelta(days=days - 1)
    result = ScanResult()
    per_day: dict[date, dict[str, int]] = {since + timedelta(days=i): {} for i in range(days)}
    state = load_state(service.data)
    migrate: dict[tuple[str, str], list[dict]] = {}
    for day, paths in sorted(service.index.day_files.items()):
        if not archive and not since <= day <= today:
            continue
        for relpath in paths:
            raw = service.cache.get(relpath).source.raw
            head = parse(service.cache.get(relpath).source)
            if head.state in (OPAQUE, OPEN):
                if b"zeit_" in raw or b"messung_" in raw:
                    result.unreadable.append(relpath)
                continue
            if head.state != OK:
                continue
            values, _damaged = minutes(head)
            result.names.update(values)
            if day in per_day:
                for name, value in values.items():
                    per_day[day][name] = per_day[day].get(name, 0) + value
            _stamp(service, relpath, day, stamp_of(head), result)
            for entry in state.renames:
                _rename_check(relpath, day, raw, values, entry, migrate, result)
    _migrate(service, migrate, result)
    result.days = [DayTotals(day, per_day[day]) for day in sorted(per_day, reverse=True)]
    return result


def _stamp(service: "NotesService", relpath: str, day: date, stamp, result: ScanResult) -> None:
    """Stempel einordnen; veraltete sofort verwerfen (nur in beschreibbarem Vault)."""
    if isinstance(stamp, Damaged):
        result.damaged.append((relpath, stamp.reason))
    elif isinstance(stamp, Stamp):
        result.names.add(stamp.activity)
        if not stale(stamp.start, service.clock.now()):
            result.running.append(Running(relpath, day, stamp))
        elif not service.read_only:
            discard_stamp(service.writer, relpath, stamp, service.settings.project_prefix)
            when = f"{WEEKDAYS[stamp.start.weekday()]} {stamp.start:%d.%m. %H:%M}"
            result.hints.append(f"Messung „{stamp.activity}“ seit {when} war älter als 24 h und wurde verworfen.")


def _rename_check(relpath: str, day: date, raw: bytes, values: dict[str, int], entry: dict,
                  migrate: dict, result: ScanResult) -> None:
    """Y8: alter Schlüssel nach Umbenennung – allein migrieren, mit neuem zusammen „unklar“."""
    old, new = entry["alt"], entry["neu"]
    if old not in values:
        return
    if new in values:
        if relpath not in entry.get("ignoriert", []):
            result.unclear.append((relpath, day, old, new))
        return
    planned = plan_rename_file(relpath, raw, old, new)
    if planned:
        migrate.setdefault((old, new), []).append(planned)


def _migrate(service: "NotesService", migrate: dict, result: ScanResult) -> None:
    """Führt automatische Migrationen als Umbenennungs-Vorgang aus."""
    if service.read_only:
        return
    for (old, new), files in migrate.items():
        hint = rename(service.writer, service.store, old, new, False, files, service.settings.project_prefix)
        result.hints.append(hint or f"„{old}“ (nach Umbenennung wieder aufgetaucht) in „{new}“ übernommen: "
                                    f"{len(files)} Datei(en).")
        service.rescan()
