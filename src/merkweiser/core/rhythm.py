"""Rhythmus-Grammatik der Routinen (W9, ``docs/FORMAT.md`` „Routinen“): rein, ohne Dateizugriff.

Eine Überschrift in ``Routinen.md`` besteht aus Rhythmus, optional Optionen in
Klammern und optional Tags (die das Modul ``routines`` abtrennt)::

    täglich
    werktags
    wöchentlich Di, Do
    alle 3 Tage ab 17.11.2026
    alle 2 Wochen Mo ab 16.11.2026
    monatlich 1., 15.
    jährlich 15.09.
    … (Frist 3 Tage, auch in Pausen)

Schlüsselwörter und Wochentage werden ohne Groß-/Kleinschreibung gelesen;
``rhythm_text``/``options_text`` liefern die **kanonische** Schreibweise
(Round-Trip: ``parse_rhythm(rhythm_text(r)) == r``). Die kanonische Form ist
auch das Notiz-Thema der Instanzen in den Tagesdateien; daraus lässt sich der
Rhythmus jederzeit wieder lesen (Ablauf ohne Routinen-Datei).

Fälligkeit (``is_due``):

* ``monatlich 31.`` fällt in kürzeren Monaten auf den letzten Tag,
  ``jährlich 29.02.`` in Nicht-Schaltjahren auf den 28.02.
* ``alle n Tage ab S``: ab ``S`` jeden n-ten Tag.
* ``alle n Wochen W ab S``: an den Wochentagen ``W`` jeder n-ten Woche; die
  Phase hängt am **Montag der Startwoche**, Tage vor ``S`` zählen nicht.
* Feiertage gibt es nicht; dafür sind die Pausen da (``routines``).
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
"""Wochentags-Kürzel, Index = ``date.weekday()`` (einzige Quelle; auch für Anzeigen)."""

MAX_INTERVAL = 366
NEXT_DUE_LIMIT = 800
"""Suchgrenze in Tagen für ``next_due`` (deckt jährliche Regeln mit langen Pausen ab)."""

_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_ALLE_RE = re.compile(r"alle\s+(\d+)\s+(tage?|wochen?)(?:\s+(.*?))?\s+ab\s+(\S+)", re.IGNORECASE)
_FRIST_RE = re.compile(r"frist\s+(\d+)\s+tage?", re.IGNORECASE)


class Kind(Enum):
    """Art eines Rhythmus; der Wert ist das Schlüsselwort der kanonischen Schreibweise."""

    TAEGLICH = "täglich"
    WERKTAGS = "werktags"
    WOECHENTLICH = "wöchentlich"
    TAGE = "alle Tage"
    WOCHEN = "alle Wochen"
    MONATLICH = "monatlich"
    JAEHRLICH = "jährlich"


class RhythmError(ValueError):
    """Überschrift bzw. Option nicht lesbar; die Meldung ist deutsch und für die Anzeige gedacht."""


@dataclass(frozen=True)
class Rhythm:
    """Ein gelesener Rhythmus.

    Attributes:
        kind: Art.
        weekdays: Wochentage (0 = Mo) für ``WOECHENTLICH``/``WOCHEN``, sortiert, ohne Dubletten.
        interval: n bei ``TAGE``/``WOCHEN`` (sonst 1).
        start: Startdatum bei ``TAGE``/``WOCHEN``.
        days: Monatstage bei ``MONATLICH`` (sortiert) bzw. ``(tag,)`` bei ``JAEHRLICH``.
        month: Monat bei ``JAEHRLICH``.
    """

    kind: Kind
    weekdays: tuple[int, ...] = ()
    interval: int = 1
    start: date | None = None
    days: tuple[int, ...] = ()
    month: int | None = None


@dataclass(frozen=True)
class Options:
    """Optionen einer Überschrift (Klammerteil).

    Attributes:
        frist: Gültigkeit in Tagen ab dem Fälligkeitstag (1 = nur dieser Tag);
            ``None`` = bis die nächste Instanz derselben Regel fällig wird.
        in_pauses: ``True`` = Pausen gelten für diese Überschrift nicht.
    """

    frist: int | None = None
    in_pauses: bool = False


def last_day(year: int, month: int) -> int:
    """Letzter Tag eines Monats (28–31)."""
    return calendar.monthrange(year, month)[1]


def parse_date_de(text: str) -> date:
    """Liest ``TT.MM.JJJJ`` (ein- oder zweistellig für Tag und Monat).

    Args:
        text: Datumstext.

    Returns:
        Das Datum.

    Raises:
        RhythmError: Kein gültiges Datum.
    """
    match = _DATE_RE.fullmatch(text.strip())
    if match is None:
        raise RhythmError(f"Datum „{text.strip()}“ bitte als TT.MM.JJJJ")
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError as exc:
        raise RhythmError(f"Datum „{text.strip()}“ gibt es nicht") from exc


def format_date_de(day: date) -> str:
    """Kanonische Schreibweise ``TT.MM.JJJJ`` (Gegenstück zu ``parse_date_de``)."""
    return f"{day:%d.%m.%Y}"


def split_heading(text: str) -> tuple[str, str | None]:
    """Trennt Rhythmus und Klammerteil: ``"wöchentlich Mo (Frist 3 Tage)"`` → ``("wöchentlich Mo", "Frist 3 Tage")``.

    Args:
        text: Überschrift ohne ``## `` und ohne Tags.

    Returns:
        ``(rhythmus, optionen_oder_None)``.

    Raises:
        RhythmError: Klammer nicht am Ende bzw. nicht geschlossen.
    """
    text = text.strip()
    if "(" not in text and ")" not in text:
        return text, None
    open_at = text.find("(")
    if open_at < 0 or not text.endswith(")") or text.count("(") != 1 or text.count(")") != 1:
        raise RhythmError("Optionen bitte in genau einer Klammer am Ende, z. B. (Frist 3 Tage)")
    return text[:open_at].strip(), text[open_at + 1:-1].strip()


def parse_rhythm(text: str) -> Rhythm:
    """Liest einen Rhythmus (ohne Klammerteil und Tags).

    Args:
        text: z. B. ``"wöchentlich Di, Do"``.

    Returns:
        Der Rhythmus.

    Raises:
        RhythmError: Unbekannt oder ungültig (Meldung nennt das Problem).
    """
    words = text.strip()
    head, _, rest = words.partition(" ")
    key, rest = head.casefold(), rest.strip()
    if key in (Kind.TAEGLICH.value, Kind.WERKTAGS.value) and not rest:
        return Rhythm(Kind(key))
    if key == Kind.WOECHENTLICH.value:
        return Rhythm(Kind.WOECHENTLICH, weekdays=_weekdays(rest))
    if key == Kind.MONATLICH.value:
        days = tuple(sorted({_day_number(part) for part in _parts(rest)}))
        if not days:
            raise RhythmError("monatlich: Tag fehlt, z. B. „monatlich 1.“")
        return Rhythm(Kind.MONATLICH, days=days)
    if key == Kind.JAEHRLICH.value:
        return _yearly(rest)
    if key == "alle":
        return _every(words)
    raise RhythmError(f"Rhythmus „{words}“ unbekannt (täglich, werktags, wöchentlich …, alle …, monatlich …, jährlich …)")


def parse_options(text: str | None) -> Options:
    """Liest den Klammerteil (``Frist N Tage``, ``auch in Pausen``; getrennt durch Komma oder Semikolon).

    Args:
        text: Inhalt der Klammer oder ``None``.

    Returns:
        Die Optionen (Standard ohne Klammer).

    Raises:
        RhythmError: Unbekannte Option, doppelte Frist oder Frist < 1.
    """
    frist, in_pauses = None, False
    for part in _parts(text or "", ",;"):
        match = _FRIST_RE.fullmatch(part)
        if match and frist is None:
            frist = int(match.group(1))
            if frist < 1:
                raise RhythmError("Frist mindestens 1 Tag")
        elif part.casefold() == "auch in pausen" and not in_pauses:
            in_pauses = True
        else:
            raise RhythmError(f"Option „{part}“ unbekannt (Frist N Tage, auch in Pausen)")
    return Options(frist, in_pauses)


def rhythm_text(rhythm: Rhythm) -> str:
    """Kanonische Schreibweise (auch Notiz-Thema der Instanzen).

    Args:
        rhythm: Rhythmus.

    Returns:
        z. B. ``"alle 2 Wochen Mo ab 16.11.2026"``.
    """
    kind = rhythm.kind
    if kind in (Kind.TAEGLICH, Kind.WERKTAGS):
        return kind.value
    if kind is Kind.WOECHENTLICH:
        return f"wöchentlich {_weekday_text(rhythm.weekdays)}"
    if kind is Kind.MONATLICH:
        return "monatlich " + ", ".join(f"{day}." for day in rhythm.days)
    if kind is Kind.JAEHRLICH:
        return f"jährlich {rhythm.days[0]:02d}.{rhythm.month:02d}."
    unit = ("Tag" if rhythm.interval == 1 else "Tage") if kind is Kind.TAGE \
        else ("Woche" if rhythm.interval == 1 else "Wochen")
    days = f" {_weekday_text(rhythm.weekdays)}" if kind is Kind.WOCHEN else ""
    return f"alle {rhythm.interval} {unit}{days} ab {format_date_de(rhythm.start)}"  # type: ignore[arg-type]


def options_text(options: Options) -> str:
    """Kanonischer Klammerinhalt (leer = keine Optionen)."""
    parts = [] if options.frist is None else [f"Frist {options.frist} {'Tag' if options.frist == 1 else 'Tage'}"]
    return ", ".join(parts + (["auch in Pausen"] if options.in_pauses else []))


def is_due(rhythm: Rhythm, day: date) -> bool:
    """Ist eine Regel mit diesem Rhythmus an ``day`` fällig (Pausen nicht berücksichtigt)?

    Args:
        rhythm: Rhythmus.
        day: Tag.

    Returns:
        ``True`` bei Fälligkeit (siehe Moduldoku für Monatsende und Wochen-Phase).
    """
    kind = rhythm.kind
    if kind is Kind.TAEGLICH:
        return True
    if kind is Kind.WERKTAGS:
        return day.weekday() < 5
    if kind is Kind.WOECHENTLICH:
        return day.weekday() in rhythm.weekdays
    if kind is Kind.MONATLICH:
        return day.day in {min(d, last_day(day.year, day.month)) for d in rhythm.days}
    if kind is Kind.JAEHRLICH:
        return day.month == rhythm.month and day.day == min(rhythm.days[0], last_day(day.year, day.month))
    start = rhythm.start
    assert start is not None
    if day < start:
        return False
    if kind is Kind.TAGE:
        return (day - start).days % rhythm.interval == 0
    weeks = (_monday(day) - _monday(start)).days // 7
    return day.weekday() in rhythm.weekdays and weeks % rhythm.interval == 0


def next_due(rhythm: Rhythm, after: date, skip: Callable[[date], bool] = lambda _d: False,
             limit: int = NEXT_DUE_LIMIT) -> date | None:
    """Nächster fälliger Tag nach ``after`` (ausschließlich), der nicht übersprungen wird.

    Args:
        rhythm: Rhythmus.
        after: Ausgangstag (zählt selbst nicht).
        skip: ``True`` für Tage, an denen keine Instanz entsteht (Pausen).
        limit: Höchstens so viele Tage suchen.

    Returns:
        Der Tag oder ``None`` (innerhalb der Grenze keiner).
    """
    for offset in range(1, limit + 1):
        day = after + timedelta(days=offset)
        if is_due(rhythm, day) and not skip(day):
            return day
    return None


def _parts(text: str, separators: str = ", ") -> list[str]:
    """Zerlegt an den Trennzeichen; leere Teile entfallen."""
    return [part.strip() for part in re.split(f"[{re.escape(separators)}]+", text) if part.strip()]


def _weekdays(text: str) -> tuple[int, ...]:
    """Wochentage aus ``"Di, Do"``/``"di do"`` (mindestens einer)."""
    names = {name.casefold(): index for index, name in enumerate(WEEKDAYS)}
    found = set()
    for part in _parts(text):
        if part.casefold() not in names:
            raise RhythmError(f"Wochentag „{part}“ unbekannt ({', '.join(WEEKDAYS)})")
        found.add(names[part.casefold()])
    if not found:
        raise RhythmError("Wochentag fehlt, z. B. „wöchentlich Mo“")
    return tuple(sorted(found))


def _weekday_text(weekdays: tuple[int, ...]) -> str:
    """``(1, 3)`` → ``"Di, Do"``."""
    return ", ".join(WEEKDAYS[index] for index in weekdays)


def _day_number(part: str) -> int:
    """Monatstag aus ``"15."``/``"15"`` (1–31)."""
    digits = part.rstrip(".")
    if not digits.isdigit() or not 1 <= int(digits) <= 31:
        raise RhythmError(f"Monatstag „{part}“ ungültig (1. bis 31.)")
    return int(digits)


def _yearly(rest: str) -> Rhythm:
    """``jährlich TT.MM.`` (Tag muss im Monat eines Schaltjahrs existieren)."""
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.?", rest)
    if match is None:
        raise RhythmError("jährlich: Datum bitte als TT.MM., z. B. „jährlich 15.09.“")
    day, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12 or not 1 <= day <= last_day(2000, month):
        raise RhythmError(f"jährlich: {day:02d}.{month:02d}. gibt es nicht")
    return Rhythm(Kind.JAEHRLICH, days=(day,), month=month)


def _every(text: str) -> Rhythm:
    """``alle n Tage ab S`` bzw. ``alle n Wochen [W] ab S`` (ohne W: Wochentag des Starts)."""
    match = _ALLE_RE.fullmatch(text)
    if match is None:
        raise RhythmError("„alle …“ bitte als „alle 3 Tage ab TT.MM.JJJJ“ oder „alle 2 Wochen Mo ab TT.MM.JJJJ“")
    interval, unit, days, start = int(match.group(1)), match.group(2).casefold(), match.group(3), match.group(4)
    if not 1 <= interval <= MAX_INTERVAL:
        raise RhythmError(f"Abstand 1 bis {MAX_INTERVAL}")
    begin = parse_date_de(start)
    if unit.startswith("tag"):
        if days:
            raise RhythmError("„alle n Tage“ hat keine Wochentage")
        return Rhythm(Kind.TAGE, interval=interval, start=begin)
    weekdays = _weekdays(days) if days else (begin.weekday(),)
    return Rhythm(Kind.WOCHEN, weekdays=weekdays, interval=interval, start=begin)


def _monday(day: date) -> date:
    """Montag der Woche von ``day``."""
    return day - timedelta(days=day.weekday())
