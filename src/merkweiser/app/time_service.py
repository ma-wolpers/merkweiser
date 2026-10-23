"""Zeit-Tracker: Aktionen für die Oberflächen (W6, PLAN-SPAETERE-SCHRITTE.md).

Alle schreibenden Aktionen prüfen den Schreibschutz und laufen über
``core.time_ops`` (Schrittprotokoll). Laufende Messungen kommen immer frisch
aus ``time_scan.refresh``; solange eine Zeitbuchung offen ist
(``pending_booking``), wird kein zweiter Stopp angeboten.

* ``start``: Stempel in die heutige Tagesdatei (keine zweite Messung).
* ``stop`` / ``abort(end)``: Dauer aus Zeitstempeln, je Tag abgerundet,
  Mitternacht geteilt (``timetrack.segments``), in die Tagesdateien gebucht.
* ``abort(None)``: „Keine Zeit eintragen“ – nur der Stempel wird gelöscht.
* ``switch``: laufende Messung endet jetzt, neue beginnt jetzt.
* ``resolve_running``: mehrere laufende Messungen (z. B. von zwei Geräten in
  verschiedenen Dateien) mit denselben Optionen wie im Konfliktdialog.
* Tätigkeiten: ``add``, ``rename_activity`` (alle Tagesdateien und Stempel,
  Zusammenführen nur nach Bestätigung), ``delete`` (Zeiten bleiben; nicht bei
  aktiver Messung).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ..core.activities import same_name, valid_activity
from ..core.frontmatter import Stamp, minutes, parse_bytes, set_own
from ..core.merge.frontmatter import StampConflict
from ..core.time_ops import (MeasurementError, Part, book, discard_stamp, pending_booking, plan_rename_file, rename,
                             start_measurement)
from ..core.step_ops import run_step
from ..core.timetrack import order_activities, segments, totals
from ..core.vault import write_target
from .time_scan import Running, ScanResult, refresh
from .time_state import load_state, save_state

if TYPE_CHECKING:
    from .notes_service import NotesService


class NeedsConfirmation(ValueError):
    """Die Aktion braucht eine Rückfrage (z. B. Umbenennen auf einen vorhandenen Namen)."""


def _now(service: "NotesService") -> datetime:
    return service.clock.now().replace(microsecond=0)


def _single(service: "NotesService") -> Running:
    """Die eine laufende Messung (sonst ``MeasurementError``)."""
    if pending_booking(service.store):
        raise MeasurementError("Eine Buchung wird noch abgeschlossen – bitte unter Konflikte nachsehen.")
    running = refresh(service).running
    if not running:
        raise MeasurementError("Es läuft keine Messung.")
    if len(running) > 1:
        raise MeasurementError("Mehrere Messungen laufen – bitte zuerst entscheiden, welche zählt.")
    return running[0]


def _parts(service: "NotesService", run: Running, end: datetime) -> list[Part]:
    """Segmente einer Messung mit ihren Tagesdateien (erstes = Datei des Stempels)."""
    parts = []
    for day, value in segments(run.stamp.start, end, run.day):
        relpath = run.relpath if day == run.day else write_target(service.index, service.pattern, day)
        parts.append(Part(relpath, day, value))
    return parts


def start(service: "NotesService", activity: str) -> str:
    """Startet eine Messung jetzt.

    Returns:
        Meldung.

    Raises:
        MeasurementError: Es läuft schon eine Messung bzw. eine Buchung ist offen.
        ValueError: ungültiger Name.
    """
    service.check_writable()
    name = valid_activity(activity)
    if pending_booking(service.store) or refresh(service).running:
        raise MeasurementError("Es läuft schon eine Messung.")
    now = _now(service)
    relpath = write_target(service.index, service.pattern, service.clock.today())
    start_measurement(service.writer, relpath, Stamp(now, name), service.settings.project_prefix)
    _remember(service, name)
    service.rescan()
    return f"„{name}“ läuft seit {now:%H:%M}."


def stop(service: "NotesService", end: datetime | None = None) -> str:
    """Beendet die laufende Messung (jetzt bzw. zur gewählten Endzeit) und bucht die Minuten."""
    service.check_writable()
    run = _single(service)
    end = end or _now(service)
    if end < run.stamp.start or end > _now(service):
        raise MeasurementError("Die Endzeit muss zwischen Beginn und jetzt liegen.")
    parts = _parts(service, run, end)
    hint = book(service.writer, service.store, run.stamp, run.relpath, end, parts,
                prefix=service.settings.project_prefix)
    service.rescan()
    booked = sum(p.minutes for p in parts)
    return hint or f"„{run.stamp.activity}“: {booked // 60}:{booked % 60:02d} eingetragen."


def abort(service: "NotesService", end: datetime | None) -> str:
    """„Messung abbrechen“: mit Endzeit buchen oder (``None``) keine Zeit eintragen."""
    if end is not None:
        return stop(service, end)
    service.check_writable()
    run = _single(service)
    discard_stamp(service.writer, run.relpath, run.stamp, service.settings.project_prefix)
    service.rescan()
    return f"Messung „{run.stamp.activity}“ verworfen, keine Zeit eingetragen."


def switch(service: "NotesService", activity: str) -> str:
    """Laufende Messung endet jetzt, eine neue mit ``activity`` beginnt jetzt."""
    service.check_writable()
    name = valid_activity(activity)
    run = _single(service)
    now = _now(service)
    new_rel = write_target(service.index, service.pattern, service.clock.today())
    hint = book(service.writer, service.store, run.stamp, run.relpath, now, _parts(service, run, now),
                Stamp(now, name), new_rel, service.settings.project_prefix)
    _remember(service, name)
    service.rescan()
    return hint or f"„{run.stamp.activity}“ beendet, „{name}“ läuft seit {now:%H:%M}."


def running_conflict(scan: ScanResult) -> StampConflict | None:
    """Zwei laufende Messungen als Konflikt mit Optionen (``None`` bei höchstens einer)."""
    if len(scan.running) < 2:
        return None
    first, second = sorted(scan.running, key=lambda r: r.stamp.start)[:2]
    return StampConflict(first.stamp, second.stamp)


def resolve_running(service: "NotesService", choice: str) -> str:
    """Entscheidet zwischen zwei laufenden Messungen (Optionen wie ``StampConflict.options``)."""
    service.check_writable()
    earlier, later = sorted(refresh(service).running, key=lambda r: r.stamp.start)[:2]
    prefix = service.settings.project_prefix
    if choice == "spaeter":
        discard_stamp(service.writer, earlier.relpath, earlier.stamp, prefix)
    elif choice == "frueher" and same_name(earlier.stamp.activity, later.stamp.activity):
        discard_stamp(service.writer, later.relpath, later.stamp, prefix)
    elif choice == "frueher_endet":
        book(service.writer, service.store, earlier.stamp, earlier.relpath, later.stamp.start,
             _parts(service, earlier, later.stamp.start), prefix=prefix)
    else:
        raise ValueError(f"Unbekannte Wahl {choice}")
    service.rescan()
    return "Entschieden."


def discard_damaged(service: "NotesService", relpath: str) -> str:
    """Verwirft einen beschädigten Messstempel (nichts wird verbucht)."""
    service.check_writable()
    discard_stamp(service.writer, relpath, None, service.settings.project_prefix)
    service.rescan()
    return "Beschädigter Messstempel verworfen."


def activity_names(service: "NotesService", scan: ScanResult) -> list[str]:
    """Tätigkeiten in Anzeigereihenfolge: Geräteliste und Namen aus den Dateien, nach 7-Tage-Summe."""
    week = totals(scan.days[:7])
    return order_activities(load_state(service.data).activities + sorted(scan.names), week)


def add_activity(service: "NotesService", name: str) -> str:
    """Fügt eine Tätigkeit zur Geräteliste hinzu (Name nach R2)."""
    name = valid_activity(name)
    state = load_state(service.data)
    if any(same_name(name, a) for a in state.activities):
        raise ValueError(f"„{name}“ gibt es schon.")
    dropped = [r for r in state.renames if same_name(r["alt"], name)]
    state.renames = [r for r in state.renames if r not in dropped]
    state.activities.append(name)
    save_state(service.data, state)
    return f"„{name}“ hinzugefügt." + (" (Frühere Umbenennung dieses Namens vergessen.)" if dropped else "")


def delete_activity(service: "NotesService", name: str) -> str:
    """Entfernt eine Tätigkeit aus der Geräteliste; eingetragene Zeiten bleiben."""
    if any(same_name(r.stamp.activity, name) for r in refresh(service).running):
        raise MeasurementError(f"„{name}“ läuft gerade und kann nicht gelöscht werden.")
    state = load_state(service.data)
    state.activities = [a for a in state.activities if not same_name(a, name)]
    save_state(service.data, state)
    return f"„{name}“ aus der Liste entfernt; eingetragene Zeiten bleiben."


def rename_activity(service: "NotesService", old: str, new: str, merge: bool = False) -> str:
    """Benennt eine Tätigkeit in allen Tagesdateien und aktiven Stempeln um (S2).

    Raises:
        NeedsConfirmation: Der neue Name existiert schon und ``merge`` ist nicht gesetzt.
    """
    service.check_writable()
    new = valid_activity(new)
    archive = refresh(service, archive=True)
    state = load_state(service.data)
    if not merge and any(same_name(new, n) and n != old for n in [*state.activities, *archive.names]):
        raise NeedsConfirmation(f"„{new}“ gibt es schon. Zusammenführen (Minuten je Tag addieren)?")
    files = [f for day, paths in sorted(service.index.day_files.items()) for p in paths
             if (f := plan_rename_file(p, service.cache.get(p).source.raw, old, new))]
    state.renames.append({"alt": old, "neu": new, "zeit": _now(service).isoformat(), "ignoriert": []})
    save_state(service.data, state)  # vor dem ersten Schreiben: Sync-Normalisierung kennt die Umbenennung
    hint = rename(service.writer, service.store, old, new, merge, files, service.settings.project_prefix)
    state = load_state(service.data)
    state.activities = list(dict.fromkeys(new if same_name(a, old) else a for a in state.activities))
    if new not in state.activities:
        state.activities.append(new)
    save_state(service.data, state)
    service.rescan()
    return hint or f"„{old}“ heißt jetzt „{new}“ ({len(files)} Datei(en))."


def resolve_unclear(service: "NotesService", relpath: str, old: str, new: str, mode: str) -> str:
    """„Umbenennung unklar“: ``addieren``, ``groesser`` (größerer Wert) oder ``nichts`` (nicht mehr fragen)."""
    if mode == "nichts":
        state = load_state(service.data)
        for entry in state.renames:
            if entry["alt"] == old and entry["neu"] == new:
                entry.setdefault("ignoriert", []).append(relpath)
        save_state(service.data, state)
        return "Unverändert gelassen."
    service.check_writable()

    def build(_doc, raw):
        values, _ = minutes(parse_bytes(raw or b""))
        a, b = values.get(old, 0), values.get(new, 0)
        return set_own(raw or b"", {old: None, new: a + b if mode == "addieren" else max(a, b)})

    run_step(service.writer, None, relpath, service.settings.project_prefix, build)
    service.rescan()
    return "Übernommen."


def _remember(service: "NotesService", name: str) -> None:
    """Neue Namen aus Start/Wechsel in die Geräteliste aufnehmen."""
    state = load_state(service.data)
    if not any(same_name(name, a) for a in state.activities):
        state.activities.append(name)
        save_state(service.data, state)
