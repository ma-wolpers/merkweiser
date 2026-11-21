"""Routinen-Datei ``Routinen.md``: Modell, Parser und fällige Instanzen (W9, ``docs/FORMAT.md`` „Routinen“).

Aufbau der Datei (alles vor der ersten ``## ``-Überschrift ist freier
Doku-Text und wird ignoriert, ebenso Codeblöcke)::

    ---
    eingetragen_bis: 2026-11-17
    ---
    # Routinen
    (Erklärung …)

    ## werktags #schule (Frist 2 Tage)
    - [ ] Vertretungsplan prüfen
    - [x] pausierte Regel

    ## Pausen
    - 21.12.2026 bis 04.01.2027

* Überschrift = Rhythmus (``core.rhythm``), optional Optionen in Klammern und
  Tags, die an jede Instanz vererbt werden.
* Regelzeile = ``- [ ] Text`` auf Ebene 0 (Todo-Grammatik mit Ampel und Tags);
  ``- [x]`` heißt **pausiert**. Alles andere in einem Abschnitt ist ein
  ``ParseError`` (wird angezeigt, nie ein Absturz; der Abschnitt bleibt sonst gültig).
* ``## Pausen``: ``- TT.MM.JJJJ bis TT.MM.JJJJ`` oder ein einzelner Tag.
* ``eingetragen_bis`` (Frontmatter, ISO-Datum) ist der Merkpunkt: Bis zu diesem
  Tag sind die Instanzen eingetragen (``app.routine_service``).

Eine Instanz in der Tagesdatei ist ``- [ ] Text #<geerbte Tags> #wdh`` in einer
Notiz, deren Thema die kanonische Rhythmus-Schreibweise ist
(``rhythm.rhythm_text``). ``occurrences`` ist die **einzige** Quelle dafür,
welche Instanzen an einem Tag entstehen (Eintragen, Vorschau, Benachrichtigung).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from . import frontmatter as fmx
from .document import Document
from .edits import tagged_line
from .inline import STATUS_CHAR, TodoStatus, find_tags, parse_list_item, strip_urgency
from .rhythm import (Options, Rhythm, RhythmError, format_date_de, is_due, next_due, parse_date_de, parse_options,
                     parse_rhythm, rhythm_text, split_heading)
from .topics import without_tags

ROUTINES_FILE = "Routinen.md"
"""Fester Name der Routinen-Datei im Vault-Root."""
WDH_TAG = "wdh"
"""Tag, der eine Zeile als Routinen-Instanz kennzeichnet (nur solche laufen automatisch ab)."""
UNTIL_KEY = fmx.UNTIL
"""Frontmatter-Schlüssel des Merkpunkts (Quelle: ``frontmatter.UNTIL``)."""
PAUSES_HEADING = "Pausen"
HEADING = "## "

DEFAULT_TEXT = """# Routinen

Wiederkehrende Todos für Merkweiser. Gelesen werden nur die Abschnitte ab der
ersten Überschrift mit zwei Rauten; dieser Text wird ignoriert.

Jede Überschrift ist ein Rhythmus, darunter stehen die Todos als `- [ ] Text`
(mit Ampel `==…==` bzw. `==🔴…==` und Tags). Ein Haken `- [x]` pausiert eine Regel.

Rhythmen: `täglich`, `werktags`, `wöchentlich Di, Do`, `alle 3 Tage ab 17.11.2026`,
`alle 2 Wochen Mo ab 16.11.2026`, `monatlich 1., 15.`, `jährlich 15.09.`.
Optionen in Klammern dahinter: `(Frist 3 Tage)`, `(auch in Pausen)`.
Tags in der Überschrift gelten für alle Todos darunter.

Unter der Überschrift `Pausen` stehen Zeiträume wie `- 21.12.2026 bis 04.01.2027`.

Merkweiser trägt fällige Todos mit `#wdh` in die Tagesdatei ein und setzt sie
nach Ablauf der Frist auf verpasst `[-]`. Ohne Frist gilt ein Todo, bis das
nächste derselben Regel fällig wird.
"""

_PAUSE_RE = re.compile(r"-\s+(\S+)(?:\s+bis\s+(\S+))?")


@dataclass(frozen=True)
class RuleItem:
    """Eine Regelzeile: ``line_no``/``line`` adressieren sie, ``body`` ist der Text hinter der Checkbox."""

    line_no: int
    line: str
    body: str
    paused: bool


@dataclass(frozen=True)
class Section:
    """Ein gültiger Rhythmus-Abschnitt.

    Attributes:
        line_no: Zeile der Überschrift.
        heading: Überschriftzeile wörtlich.
        rhythm: Rhythmus.
        options: Optionen.
        tags: Tags der Überschrift (werden vererbt), Originalschreibweise.
        items: Regelzeilen.
    """

    line_no: int
    heading: str
    rhythm: Rhythm
    options: Options
    tags: tuple[str, ...]
    items: tuple[RuleItem, ...]

    @property
    def topic(self) -> str:
        """Notiz-Thema der Instanzen: kanonischer Rhythmus ohne Optionen und Tags."""
        return rhythm_text(self.rhythm)


@dataclass(frozen=True)
class Pause:
    """Ein Pausenzeitraum (beide Tage einschließlich)."""

    line_no: int
    line: str
    start: date
    end: date


@dataclass(frozen=True)
class ParseError:
    """Nicht lesbare Zeile mit deutscher Meldung."""

    line_no: int
    line: str
    message: str


@dataclass(frozen=True)
class RoutineFile:
    """Gelesene Routinen-Datei.

    Attributes:
        until: Merkpunkt oder ``None``.
        until_error: Meldung bei ungültigem Merkpunkt (dann wird nichts eingetragen).
        head_writable: Kopfbereich kann sicher geschrieben werden (``frontmatter``-Regeln, Encoding).
        sections: Gültige Rhythmus-Abschnitte in Dateireihenfolge.
        pauses: Pausen.
        errors: Nicht lesbare Zeilen.
        pauses_line: Zeile der Überschrift ``## Pausen`` oder ``None``.
    """

    until: date | None = None
    until_error: str | None = None
    head_writable: bool = True
    sections: tuple[Section, ...] = ()
    pauses: tuple[Pause, ...] = ()
    errors: tuple[ParseError, ...] = ()
    pauses_line: int | None = None

    def in_pause(self, day: date) -> bool:
        """``True``, wenn ``day`` in einer Pause liegt."""
        return any(p.start <= day <= p.end for p in self.pauses)

    def same_rules(self, other: RoutineFile) -> bool:
        """Gleiche Regeln, Pausen und Fehler (Zeilennummern und Merkpunkt egal).

        Damit prüft der Durchlauf, ob sich die Regeln während des Eintragens
        geändert haben, bevor er den Merkpunkt fortschreibt.
        """
        return _rules_key(self) == _rules_key(other)


@dataclass(frozen=True)
class Occurrence:
    """Eine fällige Instanz.

    Attributes:
        day: Fälligkeitstag.
        topic: Notiz-Thema in der Tagesdatei.
        body: Regeltext (mit Ampel und eigenen Tags).
        tags: Geerbte Tags der Überschrift.
        expires: Erster Tag, an dem die Instanz als verpasst gilt, oder ``None`` (nie).
        item_line: Zeile der Regel in ``Routinen.md``.
        item_text: Regelzeile wörtlich (Adresse für den Editor).
    """

    day: date
    topic: str
    body: str
    tags: tuple[str, ...]
    expires: date | None
    item_line: int
    item_text: str

    def line(self, status: TodoStatus) -> str:
        """Instanzzeile für die Tagesdatei (``instance_line``)."""
        return instance_line(self.body, self.tags, status)


def pause_text(start: date, end: date) -> str:
    """Anzeige- und Schreibform einer Pause: ``TT.MM.JJJJ`` bzw. ``TT.MM.JJJJ bis TT.MM.JJJJ`` (einzige Quelle)."""
    return format_date_de(start) + ("" if end == start else f" bis {format_date_de(end)}")


def parse_routines(doc: Document) -> RoutineFile:
    """Liest ``Routinen.md``; wirft nie (Probleme stehen in ``errors``/``until_error``).

    Args:
        doc: Geparstes Dokument der Datei (``parse_document``).

    Returns:
        Die gelesene Datei.
    """
    head = fmx.parse(doc.source)
    until, until_error = _until(head)
    reader = _Reader(doc)
    for line in doc.source.lines[head.end if head.state in (fmx.OK, fmx.OPAQUE) else 0:]:
        if not doc.layout.in_code(line.no):
            reader.feed(line.no, line.text)
    reader.finish()
    return RoutineFile(until, until_error, doc.source.writable and head.state in (fmx.NONE, fmx.OK),
                       tuple(reader.sections), tuple(reader.pauses), tuple(reader.errors), reader.pauses_line)


def occurrences(rf: RoutineFile, day: date) -> list[Occurrence]:
    """Alle Instanzen, die an ``day`` entstehen (einzige Quelle für Eintragen, Vorschau, Benachrichtigung).

    Pausierte Regeln (``[x]``) und Tage in Pausen (außer ``auch in Pausen``)
    erzeugen nichts.

    Args:
        rf: Gelesene Routinen-Datei.
        day: Tag.

    Returns:
        Instanzen in Dateireihenfolge, ``expires`` schon berechnet.
    """
    result = []
    for section in rf.sections:
        if not is_due(section.rhythm, day) or (rf.in_pause(day) and not section.options.in_pauses):
            continue
        expires = expires_on(section.rhythm, section.options, rf.in_pause, day)
        result += [Occurrence(day, section.topic, item.body, section.tags, expires, item.line_no, item.line)
                   for item in section.items if not item.paused]
    return result


def expires_on(rhythm: Rhythm, options: Options, in_pause: Callable[[date], bool], day: date) -> date | None:
    """Erster Tag, an dem eine Instanz vom ``day`` als verpasst gilt.

    Mit Frist: ``day + frist`` (``Frist 1 Tag`` = nur der Fälligkeitstag). Ohne
    Frist: der nächste Tag, an dem dieselbe Regel wieder eine Instanz erzeugt
    (Pausen übersprungen, außer ``auch in Pausen``). Ein tägliches Todo vom
    letzten Tag vor den Ferien bleibt also bis zum ersten Tag danach offen.

    Args:
        rhythm: Rhythmus.
        options: Optionen.
        in_pause: Pausenprüfung der Datei.
        day: Fälligkeitstag.

    Returns:
        Der Tag oder ``None`` (keine nächste Instanz in Sicht: läuft nie ab).
    """
    if options.frist is not None:
        return day + timedelta(days=options.frist)
    return next_due(rhythm, day, skip=lambda d: not options.in_pauses and in_pause(d))


def expiry_for(rf: RoutineFile | None, topic: str, body: str, day: date) -> date | None:
    """Ablauf eines vorhandenen ``#wdh``-Todos aus seinem Notiz-Thema.

    Das Thema muss sich als Rhythmus lesen lassen, sonst läuft das Todo nie
    automatisch ab. Optionen und Pausen kommen aus dem passenden Abschnitt
    der Routinen-Datei (bevorzugt der mit derselben Regel), sonst gelten die
    Standardoptionen.

    Args:
        rf: Routinen-Datei oder ``None`` (fehlt).
        topic: Themenzeile der Notiz des Todos.
        body: Text des Todos hinter der Checkbox.
        day: Datum der Tagesdatei.

    Returns:
        Erster verpasster Tag oder ``None``.
    """
    try:
        rhythm = parse_rhythm(without_tags(topic))
    except RhythmError:
        return None
    candidates = [s for s in rf.sections if s.rhythm == rhythm] if rf else []
    key = instance_key(body)
    exact = [s for s in candidates if any(instance_key(i.body) == key for i in s.items)]
    chosen = exact or candidates
    options = chosen[0].options if chosen and len({s.options for s in chosen}) == 1 else Options()
    return expires_on(rhythm, options, rf.in_pause if rf else (lambda _d: False), day)


def instance_line(body: str, tags: tuple[str, ...], status: TodoStatus) -> str:
    """Zeile einer Instanz: ``- [ ] body #geerbt #wdh`` (Tags nur, wenn sie noch fehlen).

    Args:
        body: Regeltext.
        tags: Geerbte Tags der Überschrift.
        status: Zustand (``OPEN``; ``MISSED`` beim Nachholen, ``DONE`` beim vorzeitigen Abhaken).

    Returns:
        Die Zeile ohne Zeilenende.
    """
    line = f"- [{STATUS_CHAR[status]}] {body}"
    for tag in (*tags, WDH_TAG):
        line = tagged_line(line, tag)
    return line


def instance_key(body: str) -> str:
    """Vergleichsschlüssel Regel ↔ Instanz: ohne Ampel, ohne Tags, Leerraum zusammengefasst, ``casefold``.

    So bleibt eine Instanz erkennbar, auch wenn ihr in der Tagesdatei Tags oder
    eine andere Ampel-Stufe gegeben wurden.
    """
    return " ".join(without_tags(strip_urgency(body)).split()).casefold()


def _until(head: fmx.Frontmatter) -> tuple[date | None, str | None]:
    """Merkpunkt aus dem Frontmatter (nur bei lesbarem Kopf)."""
    entries = head.by_key(UNTIL_KEY) if head.state == fmx.OK else []
    if not entries:
        return None, None
    try:
        return date.fromisoformat(entries[0].value), None
    except ValueError:
        return None, f"{UNTIL_KEY}: „{entries[0].value}“ ist kein Datum (JJJJ-MM-TT)"


def _rules_key(rf: RoutineFile) -> tuple:
    """Inhalt, der die Regeln bestimmt (ohne Zeilennummern und Merkpunkt)."""
    return (tuple((s.heading, tuple(i.line for i in s.items)) for s in rf.sections),
            tuple(p.line for p in rf.pauses), tuple(e.line for e in rf.errors))


class _Reader:
    """Zeilenweiser Leser der Abschnitte (Zustand: kein Abschnitt, Rhythmus, Pausen, ungültig)."""

    def __init__(self, doc: Document) -> None:
        self.doc = doc
        self.sections: list[Section] = []
        self.pauses: list[Pause] = []
        self.errors: list[ParseError] = []
        self.pauses_line: int | None = None
        self.mode = "doku"
        self.head: tuple | None = None
        self.items: list[RuleItem] = []

    def feed(self, no: int, text: str) -> None:
        """Verarbeitet eine Zeile außerhalb von Code."""
        if text.startswith(HEADING):
            self.finish()
            self._heading(no, text)
        elif self.mode in ("doku", "ungueltig") or not text.strip():
            return
        elif self.mode == "pausen":
            self._pause(no, text)
        else:
            self._item(no, text)

    def finish(self) -> None:
        """Schließt den laufenden Rhythmus-Abschnitt ab."""
        if self.mode == "rhythmus" and self.head is not None:
            self.sections.append(Section(*self.head, tuple(self.items)))
        self.head, self.items = None, []

    def _heading(self, no: int, text: str) -> None:
        title = text[len(HEADING):].strip()
        if title.casefold() == PAUSES_HEADING.casefold():
            if self.pauses_line is not None:
                self._error(no, text, "zweite Überschrift „Pausen“ – bitte zusammenlegen")
                self.mode = "ungueltig"
                return
            self.pauses_line, self.mode = no, "pausen"
            return
        try:
            rhythm_part, option_part = split_heading(without_tags(title))
            head = (no, text, parse_rhythm(rhythm_part), parse_options(option_part),
                    tuple(tag.name for tag in find_tags(title)))
        except RhythmError as exc:
            self._error(no, text, str(exc))
            self.mode = "ungueltig"
            return
        self.head, self.mode = head, "rhythmus"

    def _item(self, no: int, text: str) -> None:
        item = parse_list_item(text)
        if item is None or item.status is TodoStatus.NONE:
            self._error(no, text, "gehört zu keiner Regel – Regeln als „- [ ] Text“")
        elif item.indent > 0:
            self._error(no, text, "eingerückte Zeilen werden in Routinen nicht unterstützt")
        elif item.status not in (TodoStatus.OPEN, TodoStatus.DONE):
            self._error(no, text, "Regeln nur mit [ ] (aktiv) oder [x] (pausiert)")
        elif not text[item.body_start:].strip():
            self._error(no, text, "Regel ohne Text")
        else:
            body = text[item.body_start:].strip()
            self.items.append(RuleItem(no, text, body, item.status is TodoStatus.DONE))

    def _pause(self, no: int, text: str) -> None:
        match = _PAUSE_RE.fullmatch(text.strip())
        try:
            if match is None:
                raise RhythmError("Pause bitte als „- TT.MM.JJJJ bis TT.MM.JJJJ“")
            start = parse_date_de(match.group(1))
            end = parse_date_de(match.group(2)) if match.group(2) else start
            if end < start:
                raise RhythmError("Pause endet vor ihrem Beginn")
        except RhythmError as exc:
            self._error(no, text, str(exc))
            return
        self.pauses.append(Pause(no, text, start, end))

    def _error(self, no: int, text: str, message: str) -> None:
        self.errors.append(ParseError(no, text, message))
