"""Frontmatter-bewusster Merge (W6, PLAN-SPAETERE-SCHRITTE.md S5/S2/Y5/Y7).

Der Rumpf wird wie bisher zeilenweise zusammengeführt; der YAML-Kopf hier,
**strukturiert**, damit nie doppelte Schlüssel entstehen:

* **Fremde Schlüssel** (Obsidian-Eigenschaften): gleich → einmal; nur auf einer
  Seite → übernehmen; mit Basis gilt die diff3-Regel je Schlüssel (auch für
  Löschungen); sonst unterschiedlich → ``PropertyConflict``.
* **``zeit_*``**: Sync-Merge = **Maximum** je Tätigkeit, nachdem bekannte
  Umbenennungen (``renames``, S2) auf **beide** Seiten angewandt wurden.
  Rückgängig (``reverse=True``) = diff3 je Schlüssel **ohne** Maximum (Undo
  darf Werte senken); beide geändert → Konflikt. Beschädigte Werte → Konflikt.
* **Stempel** (``messung_start`` + ``messung_taetigkeit``) nur **als Datensatz**:
  gleich → übernehmen; mit Basis diff3 auf dem Datensatz; sonst
  ``StampConflict`` (einseitig, zwei verschiedene oder beschädigt) mit den
  erlaubten Optionen (``StampConflict.options``).
* **Undurchsichtiger** Kopf auf einer Seite: als Block, gleich oder (mit Basis
  eindeutig) übernehmen, sonst ``BlockConflict`` (Wahl A oder B).

``FmMerge.resolve(decisions)`` setzt die Kopfzeilen zusammen; ohne Konflikte
ohne Entscheidungen. Option „frühere Messung endet beim Beginn der späteren“
bucht die Minuten (abgerundet) in derselben Datei – beide Stempel stehen im
Kopf dieser Tagesdatei, also am selben Tag.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timezone

from ..activities import same_name
from ..frontmatter import (ACTIVITY, NONE, OK, OPAQUE, OPEN, START, ZEIT, Damaged, Frontmatter, Stamp, minutes,
                           parse, stamp_of)
from ..source import SourceText

STAMP_SLOT = "\0messung"


@dataclass(frozen=True)
class Head:
    """Der Kopf einer Fassung: gelesenes Frontmatter und seine Zeilen (inkl. Begrenzer)."""

    fm: Frontmatter
    lines: tuple[str, ...]
    texts: tuple[str, ...]

    @property
    def state(self) -> str:
        return self.fm.state

    def entry_lines(self, key: str) -> tuple[str, ...] | None:
        """Zeilen des (einzigen) Eintrags ``key`` oder ``None``."""
        entries = self.fm.by_key(key)
        return tuple(self.texts[entries[0].start:entries[0].end]) if entries else None


def split(raw: bytes) -> tuple[Head, list[str]]:
    """Trennt eine Fassung in Kopf und Rumpfzeilen (ohne Zeilenende).

    Bei ``offen`` (kein schließendes ``---``) gibt es keinen Kopf; der Aufrufer
    behandelt das konservativ (``state == OPEN``).
    """
    source = SourceText.from_bytes(raw)
    texts = tuple(line.text for line in source.lines)
    fm = parse(source)
    if fm.state in (OK, OPAQUE):
        return Head(fm, texts[fm.start:fm.end], texts), list(texts[fm.end:])
    return Head(fm, (), texts), list(texts)


@dataclass(frozen=True)
class PropertyConflict:
    """Ein Schlüssel hat auf beiden Seiten verschiedene Werte (``None`` = fehlt)."""

    key: str
    a: tuple[str, ...] | None
    b: tuple[str, ...] | None


@dataclass(frozen=True)
class BlockConflict:
    """Der ganze (undurchsichtige) Kopf unterscheidet sich."""

    a: tuple[str, ...]
    b: tuple[str, ...]


@dataclass(frozen=True)
class StampConflict:
    """Zwei verschiedene, ein einseitiger oder ein beschädigter Messstempel."""

    a: Stamp | Damaged | None
    b: Stamp | Damaged | None

    def options(self) -> list[tuple[str, str]]:
        """Erlaubte Entscheidungen ``(code, Beschriftung)`` laut Anforderung (W6)."""
        if isinstance(self.a, Damaged) or isinstance(self.b, Damaged):
            keep = [(side, f"Messung „{s.activity}“ seit {_when(s)} weiterlaufen lassen")
                    for side, s in (("a", self.a), ("b", self.b)) if isinstance(s, Stamp)]
            return [*keep, ("verwerfen", "Messung verwerfen (nichts eintragen)")]
        if self.a is None or self.b is None:
            s = self.a or self.b
            return [("weiter", f"Messung „{s.activity}“ seit {_when(s)} weiterlaufen lassen"),
                    ("verwerfen", "Messung verwerfen (nichts eintragen)")]
        earlier, later = sorted((self.a, self.b), key=lambda s: s.start)
        options = [("spaeter", f"Nur die spätere zählt („{later.activity}“ seit {_when(later)})")]
        if same_name(earlier.activity, later.activity):
            options.append(("frueher", f"Die frühere zählt („{earlier.activity}“ seit {_when(earlier)}), "
                                       "die zweite wird verworfen"))
        else:
            options.append(("frueher_endet", f"„{earlier.activity}“ endet um {_when(later)} (Zeit wird eingetragen), "
                                             f"„{later.activity}“ läuft weiter"))
        return options


@dataclass
class FmMerge:
    """Ergebnis des Kopf-Merges.

    Attributes:
        order: Ausgabereihenfolge der Schlüssel (``STAMP_SLOT`` für den Stempel).
        values: Aufgelöste Zeilen je fremdem Schlüssel (``None`` = entfällt) bzw. Konfliktindex.
        zeit: Aufgelöste Minuten je Tätigkeit (``None`` = Konflikt, siehe ``values``).
        stamp: Aufgelöster Stempel, ``None`` oder Konfliktindex.
        block: Bei undurchsichtigem Kopf: aufgelöste Zeilen bzw. Konfliktindex.
        closing: Schließender Begrenzer.
        conflicts: Alle Konflikte (Index = Schlüssel in ``decisions``).
    """

    order: list[str] = field(default_factory=list)
    values: dict[str, tuple[str, ...] | None | int] = field(default_factory=dict)
    zeit: dict[str, int] = field(default_factory=dict)
    stamp: Stamp | None | int = None
    block: tuple[str, ...] | int | None = None
    closing: str = "---"
    conflicts: list[PropertyConflict | StampConflict | BlockConflict] = field(default_factory=list)

    def reason(self) -> str:
        """Kurzbegründung für den Konfliktfall (leer ohne Konflikte)."""
        kinds = {type(c) for c in self.conflicts}
        if StampConflict in kinds:
            return "laufende Messungen"
        if BlockConflict in kinds:
            return "Kopfbereich unterschiedlich"
        return "unterschiedliche Eigenschaften" if kinds else ""

    def resolve(self, decisions: Mapping[int, str] | None = None) -> tuple[str, ...]:
        """Kopfzeilen (inkl. Begrenzer; leer ohne Kopf) mit Entscheidungen je Konflikt.

        Raises:
            ValueError: Entscheidung fehlt oder ist für den Konflikt nicht erlaubt.
        """
        decisions = decisions or {}
        if self.block is not None:
            return self.block if not isinstance(self.block, int) else self._side(self.block, decisions)
        zeit = dict(self.zeit)
        stamp = self.stamp if not isinstance(self.stamp, int) else self._stamp(self.stamp, decisions, zeit)
        lines: list[str] = []
        for key in self.order:
            if key == STAMP_SLOT:
                if stamp is not None:
                    lines += [f"{START}: {stamp.start.isoformat(timespec='seconds')}", f"{ACTIVITY}: {stamp.activity}"]
                continue
            value = self.values.get(key)
            if isinstance(value, int):
                value = self._side(value, decisions)
            elif key.startswith(ZEIT) and key[len(ZEIT):] in zeit:
                value = (f"{key}: {zeit.pop(key[len(ZEIT):])}",)
            lines += value or ()
        lines += [f"{ZEIT}{name}: {value}" for name, value in zeit.items()]  # z. B. Buchung aus Option 3
        return ("---", *lines, self.closing) if lines else ()

    def _side(self, index: int, decisions: Mapping[int, str]) -> tuple[str, ...]:
        conflict = self.conflicts[index]
        choice = decisions.get(index)
        if choice not in ("a", "b"):
            raise ValueError("Für den Kopfbereich fehlt eine Entscheidung")
        return (getattr(conflict, choice) or ()) if not isinstance(conflict, StampConflict) else ()

    def _stamp(self, index: int, decisions: Mapping[int, str], zeit: dict[str, int]) -> Stamp | None:
        conflict = self.conflicts[index]
        assert isinstance(conflict, StampConflict)
        choice = decisions.get(index)
        if choice not in dict(conflict.options()):
            raise ValueError("Für die laufenden Messungen fehlt eine Entscheidung")
        stamps = [s for s in (conflict.a, conflict.b) if isinstance(s, Stamp)]
        if choice in ("a", "b"):
            return getattr(conflict, choice)
        if choice == "weiter":
            return stamps[0]
        if choice == "verwerfen":
            return None
        earlier, later = sorted(stamps, key=lambda s: s.start)
        if choice == "frueher":
            return earlier
        if choice == "frueher_endet":
            span = later.start.astimezone(timezone.utc) - earlier.start.astimezone(timezone.utc)  # echte Dauer
            booked = int(span.total_seconds() // 60)
            zeit[earlier.activity] = zeit.get(earlier.activity, 0) + max(booked, 0)
        return later


def merge_frontmatter(a: Head, b: Head, base: Head | None = None, renames: Sequence[tuple[str, str]] = (),
                      reverse: bool = False) -> FmMerge:
    """Führt zwei Köpfe zusammen (siehe Moduldoku).

    Args:
        a: Hauptdatei (bzw. beim Rückgängig: aktueller Stand).
        b: Konfliktversion (bzw. beim Rückgängig: Stand vorher).
        base: Gemeinsame Basis oder ``None``.
        renames: Bekannte Umbenennungen ``(alt, neu)`` (nur Sync-Merge).
        reverse: Rückgängig-Modus (diff3 ohne Maximum).

    Returns:
        Das Ergebnis; ``conflicts`` leer heißt automatisch auflösbar.

    Raises:
        ValueError: Ein Kopf ist ``offen`` (Aufrufer prüft das vorher).
    """
    if OPEN in (a.state, b.state):
        raise ValueError("Kopfbereich ohne schließendes ---")
    result = FmMerge(closing=(a.lines or b.lines or ("---",))[-1])
    usable_base = base if base is not None and base.state in (OK, NONE, OPAQUE) else None
    if OPAQUE in (a.state, b.state) or (usable_base and usable_base.state == OPAQUE):
        result.block = _pick(a.lines, b.lines, usable_base.lines if usable_base else None, result,
                             lambda x, y: BlockConflict(x, y))
        return result
    _merge_keys(a, b, usable_base, result, renames, reverse)
    return result


def _merge_keys(a: Head, b: Head, base: Head | None, result: FmMerge, renames, reverse: bool) -> None:
    """Fremde Schlüssel, ``zeit_*`` und Stempel in ``result`` eintragen."""
    keys = [e.key for e in a.fm.entries] + [e.key for e in b.fm.entries]
    seen: list[str] = []
    for key in keys:
        slot = STAMP_SLOT if key in (START, ACTIVITY) else key
        if slot not in seen:
            seen.append(slot)
    if STAMP_SLOT not in seen:
        seen.append(STAMP_SLOT)
    result.order = seen
    ma, da = minutes(a.fm)
    mb, db = minutes(b.fm)
    mbase, dbase = minutes(base.fm) if base else ({}, [])
    if not reverse:
        for old, new in renames:
            for side in (ma, mb):
                if old in side:
                    side[new] = side.get(new, 0) + side.pop(old)
                    if ZEIT + new not in result.order:
                        result.order.append(ZEIT + new)
    for key in [k for k in seen if k != STAMP_SLOT]:
        if not key.startswith(ZEIT):
            values = (a.entry_lines(key), b.entry_lines(key), base.entry_lines(key) if base else None)
            result.values[key] = _pick(*values[:2], values[2] if base else None, result,
                                       lambda x, y, k=key: PropertyConflict(k, x, y), base is not None)
        elif key in da + db + dbase:
            values = (a.entry_lines(key), b.entry_lines(key), base.entry_lines(key) if base else None)
            result.values[key] = _pick(*values[:2], values[2] if base else None, result,
                                       lambda x, y, k=key: PropertyConflict(k, x, y), base is not None)
        else:
            name = key[len(ZEIT):]
            _merge_minutes(name, ma.get(name), mb.get(name), mbase.get(name) if base else None, base is not None,
                           reverse, result, a, b)
    sa, sb = stamp_of(a.fm), stamp_of(b.fm)
    sbase = stamp_of(base.fm) if base else None
    if sa == sb:
        result.stamp = sa if not isinstance(sa, Damaged) else _conflict(result, StampConflict(sa, sb))
    elif base is not None and sa == sbase and not isinstance(sb, Damaged):
        result.stamp = sb
    elif base is not None and sb == sbase and not isinstance(sa, Damaged):
        result.stamp = sa
    else:
        result.stamp = _conflict(result, StampConflict(sa, sb))


def _merge_minutes(name: str, a: int | None, b: int | None, base: int | None, has_base: bool, reverse: bool,
                   result: FmMerge, head_a: Head, head_b: Head) -> None:
    """``zeit_<name>``: Maximum (Sync) bzw. diff3 ohne Maximum (Rückgängig)."""
    if not reverse:
        if a is not None or b is not None:
            result.zeit[name] = max(a or 0, b or 0)
        return
    if a == b or (has_base and b == base):
        value = a
    elif has_base and a == base:
        value = b
    else:
        key = ZEIT + name
        result.values[key] = _conflict(result, PropertyConflict(key, head_a.entry_lines(key), head_b.entry_lines(key)))
        return
    if value is not None:
        result.zeit[name] = value


def _pick(a, b, base, result: FmMerge, make, has_base: bool | None = None):
    """Gleich → a; mit Basis die unveränderte Seite übernehmen; einseitig (ohne Basis) → die vorhandene; sonst Konflikt."""
    has_base = base is not None if has_base is None else has_base
    if a == b:
        return a
    if has_base:
        if a == base:
            return b
        if b == base:
            return a
    elif a is None or b is None:
        return a if a is not None else b
    return _conflict(result, make(a, b))


def _conflict(result: FmMerge, conflict) -> int:
    result.conflicts.append(conflict)
    return len(result.conflicts) - 1


def _when(stamp: Stamp) -> str:
    """Startzeit eines Stempels für Beschriftungen (mit dem gespeicherten Offset)."""
    return stamp.start.strftime("%d.%m. %H:%M")
