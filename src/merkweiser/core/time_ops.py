"""Zeit-Tracker, schreibender Teil im Schrittprotokoll (W6, PLAN-SPAETERE-SCHRITTE.md S1/S2).

**Zeitbuchung** (``stop``/``switch``/``abort`` mit Endzeit), Eltern-Op
``zeitbuchung``. Das Manifest hält vor dem ersten Schreiben Stempel, Ende, alle
Segmente (Datei, Tag, Minuten) und ggf. den neuen Stempel. Schritte, je Datei
genau ein Schreibvorgang:

1. Dateien nur mit Minuten (Folgetage über Mitternacht), aufsteigend;
2. die Datei des Stempels: eigene Minuten addieren **und** Stempel entfernen
   (bei Wechsel am selben Tag zugleich den neuen Stempel setzen);
3. bei Wechsel in eine andere Datei: dort Minuten bzw. neuen Stempel.

Vor jedem offenen Schritt, solange Schritt 2 offen ist, muss der Stempel in
seiner Datei **genau** dem Manifest entsprechen. Fehlt er, bevor etwas
gebucht ist → ``ABORTED`` („anderswo beendet“), sonst ``INCOMPLETE`` mit den
schon gebuchten Teilen. Ein doppeltes Stoppen ist so ausgeschlossen.

**Umbenennen**, Eltern-Op ``umbenennen``: je Datei ein Schreibvorgang, der
``zeit_alt`` entfernt, ``zeit_neu`` um den geplanten Wert erhöht und einen
Stempel mit dem alten Namen umbenennt. Vor einem offenen Schritt müssen die
aktuellen Werte den geplanten entsprechen; sonst wird die Datei übersprungen
und gemeldet. Weil Entfernen und Addieren atomar zusammen geschehen, kann
nichts doppelt addiert werden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .frontmatter import KEEP, FrontmatterError, Stamp, minutes, parse, set_own, stamp_of
from .ops import Op, OpStore
from .patch import StaleTargetError
from .safe_write import WriteResult, Writer
from .source import SourceText
from .step_ops import STEP_DONE, child_states, finish, incomplete, pending_ops, run_step


class MeasurementError(ValueError):
    """Eine Zeitaktion ist im aktuellen Zustand nicht möglich (deutsche Meldung)."""


@dataclass(frozen=True)
class Part:
    """Ein Segment einer Buchung: Minuten in einer Tagesdatei."""

    relpath: str
    day: date
    minutes: int


def _stamp_dict(stamp: Stamp, relpath: str) -> dict:
    return {"start": stamp.start.isoformat(), "taetigkeit": stamp.activity, "relpath": relpath}


def _stamp(data: dict) -> Stamp:
    return Stamp(datetime.fromisoformat(data["start"]), data["taetigkeit"])


def _head(raw: bytes | None):
    return parse(SourceText.from_bytes(raw or b""))


def start_measurement(writer: Writer, relpath: str, stamp: Stamp, prefix: str = "") -> WriteResult | None:
    """Setzt einen Startstempel (ein Schreibvorgang).

    Raises:
        MeasurementError: In der Datei steht schon ein (auch beschädigter) Stempel.
        FrontmatterError: Kopf nicht sicher lesbar.
    """
    def build(_doc, raw):
        if stamp_of(_head(raw)) is not None:
            raise MeasurementError("In dieser Tagesdatei steht schon ein Messstempel.")
        return set_own(raw or b"", {}, stamp)

    return run_step(writer, None, relpath, prefix, build)


def discard_stamp(writer: Writer, relpath: str, expected: Stamp | None, prefix: str = "") -> WriteResult | None:
    """Entfernt einen Stempel ohne Verbuchung (veraltet, beschädigt, „Keine Zeit eintragen“).

    Args:
        expected: Der erwartete Stempel; ``None`` = beschädigten Stempel verwerfen.

    Raises:
        MeasurementError: Der Stempel ist inzwischen ein anderer.
    """
    def build(_doc, raw):
        current = stamp_of(_head(raw))
        if expected is not None and current != expected:
            raise MeasurementError("Die Messung wurde inzwischen verändert oder beendet.")
        return set_own(raw or b"", {}, None)

    return run_step(writer, None, relpath, prefix, build)


def book(writer: Writer, store: OpStore, stamp: Stamp, stamp_relpath: str, end: datetime, parts: list[Part],
         new_stamp: Stamp | None = None, new_relpath: str | None = None, prefix: str = "") -> str:
    """Beendet eine Messung und verbucht ihre Minuten (S1).

    Returns:
        Leer bei Erfolg, sonst ein Hinweis (``ABORTED`` bzw. ``INCOMPLETE``).
    """
    plan = {"stempel": _stamp_dict(stamp, stamp_relpath), "ende": end.isoformat(),
            "segmente": [{"relpath": p.relpath, "tag": p.day.isoformat(), "minuten": p.minutes} for p in parts],
            "neuer_stempel": _stamp_dict(new_stamp, new_relpath) if new_stamp and new_relpath else None}
    return _continue_booking(writer, store, store.create("zeitbuchung", plan, {}), prefix)


def _steps(m: dict) -> list[tuple[str, int, bool, bool]]:
    """``(relpath, minuten, stempel_entfernen, neuen_stempel_setzen)`` in Ausführungsreihenfolge."""
    stamp_rel = m["stempel"]["relpath"]
    new_rel = m["neuer_stempel"]["relpath"] if m["neuer_stempel"] else None
    minutes_by: dict[str, int] = {}
    for seg in sorted(m["segmente"], key=lambda s: s["tag"]):
        minutes_by[seg["relpath"]] = minutes_by.get(seg["relpath"], 0) + seg["minuten"]
    steps = [(rel, value, False, False) for rel, value in minutes_by.items() if rel not in (stamp_rel, new_rel)]
    steps.append((stamp_rel, minutes_by.get(stamp_rel, 0), True, new_rel == stamp_rel))
    if new_rel and new_rel != stamp_rel:
        steps.append((new_rel, minutes_by.get(new_rel, 0), False, True))
    return steps


def _continue_booking(writer: Writer, store: OpStore, op: Op, prefix: str) -> str:
    """Offene Schritte einer Zeitbuchung (siehe Moduldoku)."""
    m = op.manifest
    stamp, stamp_rel = _stamp(m["stempel"]), m["stempel"]["relpath"]
    new_stamp = _stamp(m["neuer_stempel"]) if m["neuer_stempel"] else None
    activity = stamp.activity
    done = child_states(store, op.id)
    booked = [rel for rel, *_ in _steps(m) if done.get(rel) in STEP_DONE]
    for rel, value, remove, set_new in _steps(m):
        if done.get(rel) in STEP_DONE:
            continue
        if done.get(stamp_rel) not in STEP_DONE and stamp_of(_head(_read(writer, stamp_rel))) != stamp:
            hint = "Die Messung wurde inzwischen anderswo beendet oder verändert."
            if not booked:
                op.set_state("ABORTED", hinweis=hint)
                op.release()
                return hint
            hint += f" Schon eingetragen: {', '.join(booked)} – weitere Teile wurden nicht gebucht."
            incomplete(op, hint)
            return hint

        def build(_doc, raw, value=value, remove=remove, set_new=set_new):
            current, damaged = minutes(_head(raw))
            if value and activity in damaged:
                raise FrontmatterError(f"zeit_{activity} ist beschädigt")
            values = {activity: current.get(activity, 0) + value} if value else {}
            target = new_stamp if set_new else (None if remove else KEEP)
            return set_own(raw or b"", values, target)

        try:
            run_step(writer, op, rel, prefix, build)
        except (FrontmatterError, StaleTargetError) as exc:
            hint = f"{rel}: {exc} – Buchung angehalten."
            incomplete(op, hint)
            return hint
        booked.append(rel)
    finish(op)
    return ""


def rename(writer: Writer, store: OpStore, old: str, new: str, merge: bool, files: list[dict],
           prefix: str = "") -> str:
    """Benennt eine Tätigkeit in den angegebenen Dateien um (S2).

    Args:
        files: ``[{relpath, alt_wert, neu_wert, stempel_alt}]`` aus dem Planungs-Scan.

    Returns:
        Leer bei Erfolg, sonst ein Hinweis (``INCOMPLETE`` mit übersprungenen Dateien).
    """
    op = store.create("umbenennen", {"alt": old, "neu": new, "zusammenfuehren": merge, "dateien": files}, {})
    return _continue_rename(writer, store, op, prefix)


def plan_rename_file(relpath: str, raw: bytes, old: str, new: str) -> dict | None:
    """Planungseintrag einer Datei für ``rename`` (``None``: nichts umzubenennen)."""
    head = _head(raw)
    values, _damaged = minutes(head)
    stamp = stamp_of(head)
    has_stamp = isinstance(stamp, Stamp) and stamp.activity == old
    if old not in values and not has_stamp:
        return None
    return {"relpath": relpath, "alt_wert": values.get(old), "neu_wert": values.get(new), "stempel_alt": has_stamp}


def _continue_rename(writer: Writer, store: OpStore, op: Op, prefix: str) -> str:
    """Offene Schritte einer Umbenennung."""
    m = op.manifest
    old, new = m["alt"], m["neu"]
    done = child_states(store, op.id)
    skipped = []
    for entry in m["dateien"]:
        if done.get(entry["relpath"]) in STEP_DONE:
            continue

        def build(_doc, raw, entry=entry):
            current = plan_rename_file(entry["relpath"], raw or b"", old, new)
            if current != entry:
                raise StaleTargetError("inzwischen geändert")
            values: dict[str, int | None] = {}
            if entry["alt_wert"] is not None:
                values = {old: None, new: (entry["neu_wert"] or 0) + entry["alt_wert"]}
            stamp = stamp_of(_head(raw))
            target = Stamp(stamp.start, new) if entry["stempel_alt"] else KEEP  # type: ignore[union-attr]
            return set_own(raw or b"", values, target)

        try:
            run_step(writer, op, entry["relpath"], prefix, build)
        except (StaleTargetError, FrontmatterError):
            skipped.append(entry["relpath"])
    if skipped:
        hint = f"Umbenennung „{old}“ → „{new}“: {', '.join(skipped)} inzwischen geändert – dort unverändert."
        incomplete(op, hint)
        return hint
    finish(op)
    return ""


def resume(writer: Writer, store: OpStore, op_id: str, prefix: str = "") -> str:
    """Setzt eine Zeitbuchung bzw. Umbenennung fort („Erneut prüfen“ oder Start)."""
    op = store.open_for_recovery(op_id)
    if op is None:
        return "Vorgang wird gerade von einer anderen Instanz bearbeitet."
    if op.manifest["art"] == "zeitbuchung":
        return _continue_booking(writer, store, op, prefix)
    return _continue_rename(writer, store, op, prefix)


def recover_time_ops(writer: Writer, store: OpStore, prefix: str = "") -> list[str]:
    """Setzt unterbrochene Zeitbuchungen und Umbenennungen beim Start fort."""
    ids = pending_ops(store, "zeitbuchung") + pending_ops(store, "umbenennen")
    return [op_id for op_id in sorted(ids) if resume(writer, store, op_id, prefix) == ""]


def pending_booking(store: OpStore) -> str | None:
    """Offene (nicht abgeschlossene) Zeitbuchung – solange es eine gibt, bietet die UI keinen zweiten Stopp an."""
    for op_id in pending_ops(store, "zeitbuchung"):
        return op_id
    return None


def _read(writer: Writer, relpath: str) -> bytes | None:
    path = writer.root / relpath
    return path.read_bytes() if path.exists() else None
