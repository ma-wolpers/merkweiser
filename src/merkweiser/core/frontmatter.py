"""YAML-Frontmatter: lesen und gezielt eigene Schlüssel ändern, ohne Fremdpakete (S5, PLAN-SPAETERE-SCHRITTE.md).

Merkweiser ändert im Frontmatter **nur** ``zeit_<Tätigkeit>``, ``messung_start``
und ``messung_taetigkeit``. Alles andere bleibt byte-genau (``patch.apply_edits``).

Unterstützte Struktur (alles andere gilt als **undurchsichtig**):

* Begrenzer wie ``blocks.find_frontmatter``: Zeile 0 ``---``, Ende ``---``/``...``.
* Ein Eintrag beginnt mit einer **Schlüsselzeile ohne Einrückung**
  ``schlüssel: wert`` (unquotierter Schlüssel; nach dem ersten ``:`` + Leerraum
  beginnt der Wert, Doppelpunkte im Wert sind erlaubt).
* Folgezeilen gehören zum Eintrag: eingerückte Zeilen und ``- ``-Listenzeilen.
  Damit sind Listen, Block-Skalare (``|``, ``>``) und verschachtelte Strukturen
  als **undurchsichtige Einträge** abgedeckt; fremde Werte werden nie
  interpretiert, nur als ganze Zeilen verglichen.
* Leerzeilen sind erlaubt.

**Undurchsichtig** (``OPAQUE``) machen: Kommentare ``#`` und jede andere Zeile
ohne Einrückung (quotierte Schlüssel, ``? ``, Flow-Fortsetzungen,
Dokumentmarker), Tabulator am Zeilenanfang, Folgezeile ohne Eintrag davor und
doppelte **fremde** Schlüssel. Dann wird das Schreiben eigener Schlüssel
verweigert; der Merge behandelt das Frontmatter als Block (gleich oder Konflikt).

**Offen** (Zeile 0 ``---`` ohne Ende): nie ein neues Frontmatter davorsetzen;
Schreiben wird verweigert.

Eigene Werte werden streng geprüft: ``zeit_*`` = ``^\\d{1,5}$`` (eine Zeile),
``messung_start`` = ISO-8601 mit Offset, ``messung_taetigkeit`` = gültiger Name
(``activities.valid_activity``). Ungültig heißt **beschädigt**: kein stilles
Überschreiben. Doppelte eigene ``zeit_*`` werden als Maximum gelesen und beim
nächsten Schreiben zu einer Zeile.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from .activities import valid_activity
from .blocks import find_frontmatter
from .patch import LineEdit, apply_edits
from .source import SourceText

ZEIT = "zeit_"
START = "messung_start"
ACTIVITY = "messung_taetigkeit"
KEEP = object()
"""``set_own(stamp=KEEP)``: Stempel unverändert lassen."""

NONE, OK, OPAQUE, OPEN = "keine", "ok", "undurchsichtig", "offen"
_KEY_RE = re.compile(r"([A-Za-z_À-\U0010FFFF][^:#\"'\t]*?):(?:[ \t]|$)")
_MINUTES_RE = re.compile(r"\d{1,5}")


class FrontmatterError(ValueError):
    """Eigene Schlüssel können nicht sicher geschrieben werden (undurchsichtig, offen, beschädigt, Encoding)."""


@dataclass(frozen=True)
class Entry:
    """Ein Eintrag: Schlüsselzeile und Folgezeilen (absolute Zeilennummern ``[start, end)``)."""

    key: str
    start: int
    end: int
    value: str

    @property
    def single(self) -> bool:
        """``True`` für einen einzeiligen Eintrag."""
        return self.end - self.start == 1


@dataclass(frozen=True)
class Stamp:
    """Startstempel einer laufenden Messung (immer als Datensatz, Y5)."""

    start: datetime
    activity: str


@dataclass(frozen=True)
class Damaged:
    """Beschädigter bzw. unvollständiger Stempel (läuft nie als Messung weiter)."""

    reason: str


@dataclass(frozen=True)
class Frontmatter:
    """Gelesenes Frontmatter.

    Attributes:
        state: ``keine``, ``ok``, ``undurchsichtig`` oder ``offen``.
        start: Zeile des öffnenden Begrenzers (bei ``ok``/``undurchsichtig``).
        end: Zeile hinter dem schließenden Begrenzer.
        entries: Einträge (nur bei ``ok``).
        reason: Begründung bei ``undurchsichtig``/``offen``.
        loose: Zeilen außerhalb von Einträgen, die nicht leer sind (nur ``ok``: keine).
    """

    state: str
    start: int = 0
    end: int = 0
    entries: tuple[Entry, ...] = ()
    reason: str = ""
    loose: tuple[int, ...] = field(default=())

    def by_key(self, key: str) -> list[Entry]:
        """Alle Einträge mit diesem Schlüssel (Dateireihenfolge)."""
        return [e for e in self.entries if e.key == key]


def parse(source: SourceText) -> Frontmatter:
    """Liest das Frontmatter einer Datei (siehe Moduldoku).

    Args:
        source: Dateiinhalt.

    Returns:
        Das Frontmatter mit Zustand.
    """
    lines = source.lines
    span = find_frontmatter(lines)
    if span is None:
        if lines and lines[0].text.rstrip() == "---":
            return Frontmatter(OPEN, reason="Kopfbereich ohne schließendes ---")
        return Frontmatter(NONE)
    entries: list[Entry] = []
    current: Entry | None = None
    for line in lines[span.start + 1:span.end - 1]:
        text = line.text
        if not text.strip():
            continue
        if text[0] == "\t":
            return Frontmatter(OPAQUE, span.start, span.end, reason="Tabulator am Zeilenanfang")
        if text[0] == " " or text == "-" or text.startswith("- "):
            if current is None:
                return Frontmatter(OPAQUE, span.start, span.end, reason="Folgezeile ohne Schlüssel")
            current = Entry(current.key, current.start, line.no + 1, current.value)
            entries[-1] = current
            continue
        match = _KEY_RE.match(text)
        if not match:
            return Frontmatter(OPAQUE, span.start, span.end, reason=f"nicht lesbare Zeile: {text[:30]}")
        current = Entry(match.group(1), line.no, line.no + 1, text[match.end():].strip())
        entries.append(current)
    foreign = [e.key for e in entries if not is_own(e.key)]
    if len(foreign) != len(set(foreign)):
        return Frontmatter(OPAQUE, span.start, span.end, reason="doppelter Schlüssel")
    return Frontmatter(OK, span.start, span.end, tuple(entries))


def parse_bytes(raw: bytes) -> Frontmatter:
    """``parse`` für Bytes."""
    return parse(SourceText.from_bytes(raw))


def is_own(key: str) -> bool:
    """``True`` für Merkweisers eigene Schlüssel."""
    return key.startswith(ZEIT) or key in (START, ACTIVITY)


def minutes(fm: Frontmatter) -> tuple[dict[str, int], list[str]]:
    """Minuten je Tätigkeit und beschädigte ``zeit_*``-Schlüssel.

    Doppelte gültige Schlüssel ergeben das Maximum (wie die Konfliktregel).

    Returns:
        ``({tätigkeit: minuten}, [beschädigte schlüssel])``.
    """
    result: dict[str, int] = {}
    damaged: list[str] = []
    for entry in fm.entries:
        if not entry.key.startswith(ZEIT):
            continue
        if entry.single and _MINUTES_RE.fullmatch(entry.value):
            name = entry.key[len(ZEIT):]
            result[name] = max(result.get(name, 0), int(entry.value))
        else:
            damaged.append(entry.key)
    return result, damaged


def stamp_of(fm: Frontmatter) -> Stamp | Damaged | None:
    """Der Startstempel als Datensatz (Y5): beide Schlüssel gültig, keiner oder beschädigt.

    Returns:
        ``Stamp``, ``None`` (keine Messung) oder ``Damaged`` (nur ein Schlüssel,
        doppelt, mehrzeilig oder ungültig).
    """
    starts, activities = fm.by_key(START), fm.by_key(ACTIVITY)
    if not starts and not activities:
        return None
    if len(starts) != 1 or len(activities) != 1 or not (starts[0].single and activities[0].single):
        return Damaged("Messstempel unvollständig oder doppelt")
    try:
        start = datetime.fromisoformat(starts[0].value)
        name = valid_activity(activities[0].value)
    except ValueError as exc:
        return Damaged(f"Messstempel ungültig: {exc}")
    if start.tzinfo is None:
        return Damaged("Messstempel ohne Zeitzonen-Offset")
    return Stamp(start, name)


def set_own(raw: bytes, values: Mapping[str, int | None] | None = None, stamp: object = KEEP) -> bytes:
    """Setzt bzw. entfernt eigene Schlüssel; alles andere bleibt byte-genau.

    Args:
        raw: Dateiinhalt (``b""`` für eine neue Datei).
        values: ``{tätigkeit: minuten}``; ``None`` entfernt ``zeit_<tätigkeit>``.
        stamp: ``Stamp`` setzt den Stempel, ``None`` entfernt ihn, ``KEEP`` lässt ihn.

    Returns:
        Neue Bytes (unverändert, wenn nichts zu tun ist).

    Raises:
        FrontmatterError: undurchsichtig, offen, Encoding oder ein zu
            überschreibender eigener Wert ist beschädigt.
    """
    source = SourceText.from_bytes(raw)
    if not source.writable:
        raise FrontmatterError("Encoding nicht unterstützt")
    fm = parse(source)
    if fm.state in (OPAQUE, OPEN):
        raise FrontmatterError(f"Kopfbereich nicht sicher lesbar ({fm.reason}) – nichts geändert")
    desired = _desired(fm, values or {}, stamp)
    if fm.state == NONE:
        lines = tuple(line for line in desired.values() if line)
        return raw if not lines else apply_edits(source, [LineEdit(0, 0, ("---", *lines, "---"))])
    return apply_edits(source, _edits(fm, desired)) if desired else raw


def _desired(fm: Frontmatter, values: Mapping[str, int | None], stamp: object) -> dict[str, str | None]:
    """Gewünschte Zeile je eigenem Schlüssel (``None`` = entfernen); prüft Überschreiben beschädigter Werte."""
    desired: dict[str, str | None] = {}
    _, damaged = minutes(fm)
    for name, value in values.items():
        key = ZEIT + (name if value is None else valid_activity(name))  # Entfernen geht auch für Altnamen
        if value is not None and key in damaged:
            raise FrontmatterError(f"{key} ist beschädigt – bitte zuerst prüfen")
        desired[key] = None if value is None else f"{key}: {int(value)}"
    if stamp is not KEEP:
        if isinstance(stamp, Stamp):
            if isinstance(stamp_of(fm), Damaged):
                raise FrontmatterError("Messstempel beschädigt – bitte zuerst verwerfen")
            desired[START] = f"{START}: {stamp.start.isoformat(timespec='seconds')}"
            desired[ACTIVITY] = f"{ACTIVITY}: {valid_activity(stamp.activity)}"
        else:
            desired[START] = desired[ACTIVITY] = None
    return desired


def _edits(fm: Frontmatter, desired: dict[str, str | None]) -> list[LineEdit]:
    """Zeilen-Edits für ein vorhandenes Frontmatter; leer werdendes Frontmatter wird ganz entfernt."""
    edits: list[LineEdit] = []
    appended: list[str] = []
    for key, line in desired.items():
        existing = fm.by_key(key)
        if existing:
            first, *rest = existing
            edits.append(LineEdit(first.start, first.end, (line,) if line else ()))
            edits += [LineEdit(e.start, e.end, ()) for e in rest]
        elif line:
            appended.append(line)
    remaining = [e for e in fm.entries if e.key not in desired] + [k for k, v in desired.items() if v]
    if not remaining:
        return [LineEdit(fm.start, fm.end, ())]
    if appended:
        edits.append(LineEdit(fm.end - 1, fm.end - 1, tuple(appended)))
    return edits
