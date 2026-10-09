"""Vault: Discovery und Adressierung von Tages- und Konfliktdateien (kein Schreiben).

Verantwortung laut ``docs/PLAN.md``: Dateinamensmuster ↔ Datum, rekursiver
Scan, Dubletten, getrennte Liste der Konfliktdateien und die Regel, in welche
Datei für ein Datum geschrieben wird. Geschrieben wird hier nie; das ist
Sache von ``safe_write``.

Alle Pfade sind relativ zum Vault-Ordner und verwenden ``/`` als Trenner.
Versteckte Ordner (``.obsidian``, ``.git``, ``.stfolder`` …) und versteckte
Dateien (z. B. die Hilfsdateien ``.NAME.mw-*``) werden nicht gescannt.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_PATTERN = "%Y-%m-%d.md"
OWN_DEVICE_PREFIX = "MERKWEISER"
DECIDED_SUFFIX = "MWENTSCHIEDEN"

_PLACEHOLDERS = {"%Y": r"(?P<Y>\d{4})", "%m": r"(?P<m>\d{2})", "%d": r"(?P<d>\d{2})"}
_CONFLICT_SEGMENT_RE = re.compile(r"\.sync-conflict-(\d{8})-(\d{6})-([A-Z0-9]+)")


class PatternError(ValueError):
    """Ungültiges Dateinamensmuster."""


class AmbiguousDayFile(Exception):
    """Für ein Datum gibt es mehrere Dateien und keine am kanonischen Ort."""


@dataclass(frozen=True)
class DayPattern:
    """Dateinamensmuster für Tagesdateien, z. B. ``%Y-%m-%d.md``.

    Attributes:
        pattern: Das Muster; ``%Y``, ``%m`` und ``%d`` müssen genau einmal vorkommen.
    """

    pattern: str = DEFAULT_PATTERN

    def __post_init__(self) -> None:
        """Prüft das Muster.

        Raises:
            PatternError: wenn ein Platzhalter fehlt oder doppelt ist, andere
                ``%``-Platzhalter vorkommen oder ein Pfadtrenner enthalten ist.
        """
        for placeholder in _PLACEHOLDERS:
            if self.pattern.count(placeholder) != 1:
                raise PatternError(f"{placeholder} muss genau einmal vorkommen: {self.pattern!r}")
        if re.sub("%[Ymd]", "", self.pattern).count("%"):
            raise PatternError(f"nur %Y, %m und %d sind erlaubt: {self.pattern!r}")
        if "/" in self.pattern or "\\" in self.pattern:
            raise PatternError(f"das Muster beschreibt nur den Dateinamen: {self.pattern!r}")

    @property
    def regex(self) -> re.Pattern[str]:
        """Regulärer Ausdruck, der einen **ganzen** Dateinamen prüft."""
        parts = re.split(r"(%[Ymd])", self.pattern)
        return re.compile("".join(_PLACEHOLDERS.get(p, re.escape(p)) for p in parts))

    def parse(self, filename: str) -> date | None:
        """Leitet das Datum aus einem Dateinamen ab.

        Args:
            filename: Dateiname ohne Ordner.

        Returns:
            Das Datum oder ``None``, wenn der ganze Name nicht passt oder das
            Datum ungültig ist (z. B. 2026-02-30).
        """
        match = self.regex.fullmatch(filename)
        if match is None:
            return None
        try:
            return date(int(match["Y"]), int(match["m"]), int(match["d"]))
        except ValueError:
            return None

    def format(self, day: date) -> str:
        """Bildet den Dateinamen für ein Datum.

        Args:
            day: Das Datum.

        Returns:
            Der Dateiname nach Muster.
        """
        return (self.pattern.replace("%Y", f"{day.year:04d}")
                .replace("%m", f"{day.month:02d}").replace("%d", f"{day.day:02d}"))


@dataclass(frozen=True)
class ConflictFile:
    """Eine Konfliktdatei im Vault (``….sync-conflict-YYYYMMDD-HHMMSS-GERÄT….md``).

    Attributes:
        relpath: Pfad der Konfliktdatei.
        main_relpath: Pfad der zugehörigen Hauptdatei (Name ohne **alle** Segmente).
        stamp: Zeitstempel des äußersten (letzten) Segments, ``YYYYMMDD-HHMMSS``.
        device: Gerätekennung des äußersten Segments.
        nested: ``True`` bei mehr als einem Segment (nur manuell auflösbar).
    """

    relpath: str
    main_relpath: str
    stamp: str
    device: str
    nested: bool

    @property
    def own(self) -> bool:
        """``True`` für Konfliktdateien, die Merkweiser selbst angelegt hat."""
        return self.device.startswith(OWN_DEVICE_PREFIX)

    @property
    def decided(self) -> bool:
        """``True``, wenn die Kennung den Marker ``MWENTSCHIEDEN`` trägt."""
        return self.device.endswith(DECIDED_SUFFIX)


def parse_conflict_name(relpath: str) -> ConflictFile | None:
    """Erkennt eine Markdown-Konfliktdatei und bestimmt ihre Hauptdatei.

    Die Hauptdatei ist der Name ohne **alle** ``.sync-conflict-…``-Segmente.
    Dadurch kann eine Konfliktdatei nie selbst als Hauptdatei gelten.

    Args:
        relpath: Relativer Pfad mit ``/``.

    Returns:
        Die Beschreibung oder ``None`` (kein Konfliktname oder keine ``.md``-Datei).
    """
    folder, _, name = relpath.rpartition("/")
    segments = list(_CONFLICT_SEGMENT_RE.finditer(name))
    if not segments or not name.endswith(".md"):
        return None
    main_name = _CONFLICT_SEGMENT_RE.sub("", name)
    last = segments[-1]
    return ConflictFile(relpath=relpath, main_relpath=f"{folder}/{main_name}" if folder else main_name,
                        stamp=f"{last.group(1)}-{last.group(2)}", device=last.group(3),
                        nested=len(segments) > 1)


@dataclass(frozen=True)
class VaultIndex:
    """Ergebnis eines Scans.

    Attributes:
        day_files: Datum → Pfade aller Tagesdateien dieses Datums (sortiert).
        conflicts: Alle Markdown-Konfliktdateien (sortiert nach Pfad).
    """

    day_files: dict[date, tuple[str, ...]]
    conflicts: tuple[ConflictFile, ...]

    def duplicates(self) -> dict[date, tuple[str, ...]]:
        """Daten mit mehr als einer Tagesdatei."""
        return {day: paths for day, paths in self.day_files.items() if len(paths) > 1}


def scan(root: Path, pattern: DayPattern) -> VaultIndex:
    """Durchsucht den Vault rekursiv nach Tages- und Konfliktdateien.

    Args:
        root: Vault-Ordner.
        pattern: Dateinamensmuster.

    Returns:
        Der Index. Dateien, die weder Tages- noch Konfliktdatei sind, werden ignoriert.
    """
    days: dict[date, list[str]] = defaultdict(list)
    conflicts: list[ConflictFile] = []
    for folder, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        rel_folder = Path(folder).relative_to(root).as_posix()
        for name in filenames:
            if name.startswith("."):
                continue
            relpath = name if rel_folder == "." else f"{rel_folder}/{name}"
            conflict = parse_conflict_name(relpath)
            if conflict is not None:
                conflicts.append(conflict)
                continue
            day = pattern.parse(name)
            if day is not None:
                days[day].append(relpath)
    return VaultIndex(day_files={d: tuple(sorted(p)) for d, p in days.items()},
                      conflicts=tuple(sorted(conflicts, key=lambda c: c.relpath)))


def write_target(index: VaultIndex, pattern: DayPattern, day: date) -> str:
    """Bestimmt, in welche Datei Merkweiser für ein Datum schreibt.

    Regel (PLAN.md): genau eine vorhandene Datei → diese; keine → kanonischer
    Pfad im Vault-Wurzelordner; mehrere → die am kanonischen Ort, sonst Abbruch.

    Args:
        index: Aktueller Scan.
        pattern: Dateinamensmuster.
        day: Datum.

    Returns:
        Relativer Pfad der Zieldatei.

    Raises:
        AmbiguousDayFile: mehrere Dateien und keine am kanonischen Ort (die UI fragt).
    """
    canonical = pattern.format(day)
    existing = index.day_files.get(day, ())
    if len(existing) == 1:
        return existing[0]
    if not existing or canonical in existing:
        return canonical
    raise AmbiguousDayFile(f"{day.isoformat()}: {', '.join(existing)}")
