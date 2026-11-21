"""UI-neutrales Formularmodell des Routinen-Editors (W9).

``RuleForm`` hält, was der Dialog anzeigt (als Text bzw. einfache Werte).
Daraus entstehen Rhythmus und Optionen **über dieselbe Grammatik** wie beim
Lesen der Datei: Das Formular baut den kanonischen Überschriftstext und liest
ihn mit ``rhythm.parse_rhythm``/``parse_options``. So gibt es keine zweite
Validierung, und die Fehlermeldungen sind dieselben.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..core.document import parse_document
from ..core.rhythm import (WEEKDAYS, Kind, Options, Rhythm, RhythmError, is_due, next_due, options_text,
                           parse_options, parse_rhythm, rhythm_text)
from ..core.routine_edit import heading_line, rule_line
from ..core.routines import RoutineFile, RuleItem, Section, parse_routines
from .views import tag_list

KIND_LABELS: dict[Kind, str] = {
    Kind.TAEGLICH: "täglich", Kind.WERKTAGS: "werktags (Mo–Fr)", Kind.WOECHENTLICH: "wöchentlich",
    Kind.TAGE: "alle n Tage", Kind.WOCHEN: "alle n Wochen", Kind.MONATLICH: "monatlich", Kind.JAEHRLICH: "jährlich",
}
"""Anzeigenamen der Rhythmus-Arten im Dialog (Reihenfolge = Auswahlliste)."""

UPCOMING_COUNT = 3

FIELDS_BY_KIND: dict[Kind, frozenset[str]] = {
    Kind.WOECHENTLICH: frozenset({"weekdays"}), Kind.WOCHEN: frozenset({"weekdays", "interval", "start"}),
    Kind.TAGE: frozenset({"interval", "start"}), Kind.MONATLICH: frozenset({"month_days"}),
    Kind.JAEHRLICH: frozenset({"yearly"}),
}
"""Welche Formularfelder je Rhythmus-Art gelten (einzige Quelle; Dialog-Sichtbarkeit und ``RuleForm.rhythm``)."""


@dataclass
class RuleForm:
    """Inhalt des Regel-Dialogs.

    Attributes:
        body: Regeltext (mit Ampel-Markierung und eigenen Tags).
        kind: Rhythmus-Art.
        weekdays: Wochentage (0 = Mo) für wöchentlich und alle n Wochen.
        interval: n als Text (alle n Tage/Wochen).
        start: Starttag (alle n Tage/Wochen).
        month_days: Monatstage als Text, z. B. ``"1, 15"``.
        yearly: Tag und Monat für jährlich (das Jahr zählt nicht).
        frist: Frist in Tagen als Text; leer = bis zur nächsten Instanz.
        in_pauses: Pausen gelten nicht.
        tags: Tags der Überschrift als Text (``"schule #privat"``).
        active: ``False`` = pausiert (``- [x]``).
    """

    body: str = ""
    kind: Kind = Kind.TAEGLICH
    weekdays: tuple[int, ...] = ()
    interval: str = "2"
    start: date | None = None
    month_days: str = "1"
    yearly: date | None = None
    frist: str = ""
    in_pauses: bool = False
    tags: str = ""
    active: bool = True

    def rhythm(self) -> Rhythm:
        """Rhythmus aus den Feldern.

        Baut ein ``Rhythm``, schreibt es mit ``rhythm_text`` (einzige
        Schreibweise) und liest es mit ``parse_rhythm`` (einzige Prüfung)
        zurück. Monatstage liest dieselbe Grammatik aus dem Textfeld.

        Raises:
            RhythmError: Felder unvollständig oder ungültig.
        """
        kind, every = self.kind, self.uses("start")
        if every and self.start is None:
            raise RhythmError("Starttag fehlt")
        if every and not self.interval.strip().isdigit():
            raise RhythmError("Abstand bitte als Zahl")
        if self.uses("yearly") and self.yearly is None:
            raise RhythmError("Datum fehlt")
        yearly = self.yearly if self.uses("yearly") else None
        days = parse_rhythm(f"{Kind.MONATLICH.value} {self.month_days}").days if self.uses("month_days") \
            else ((yearly.day,) if yearly else ())
        weekly = self.uses("weekdays")
        candidate = Rhythm(kind, weekdays=tuple(sorted(set(self.weekdays))) if weekly else (),
                           interval=int(self.interval) if every else 1, start=self.start if every else None,
                           days=days, month=yearly.month if yearly else None)
        return parse_rhythm(rhythm_text(candidate))

    def uses(self, name: str) -> bool:
        """Gilt das Feld ``name`` für die gewählte Art (``FIELDS_BY_KIND``)?"""
        return name in FIELDS_BY_KIND.get(self.kind, frozenset())

    def options(self) -> Options:
        """Optionen aus den Feldern (über ``parse_options``).

        Raises:
            RhythmError: Frist ist keine Zahl ≥ 1.
        """
        frist = self.frist.strip()
        if frist and not frist.isdigit():
            raise RhythmError("Frist bitte als Zahl von Tagen (leer = bis zur nächsten Fälligkeit)")
        return parse_options(options_text(Options(int(frist) if frist else None, self.in_pauses)) or None)

    def tag_tuple(self) -> tuple[str, ...]:
        """Tags der Überschrift ohne ``#`` (``views.tag_list``)."""
        return tag_list(self.tags)

    def line(self) -> str:
        """Regelzeile.

        Raises:
            ValueError: Text fehlt.
        """
        if not self.body.strip():
            raise ValueError("Text der Routine fehlt")
        return rule_line(self.body, self.active)


def new_form(today: date) -> RuleForm:
    """Leeres Formular mit sinnvollen Vorbelegungen (heute als Start, Wochentag von heute)."""
    return RuleForm(weekdays=(today.weekday(),), start=today, yearly=today, month_days=str(today.day))


def form_of(section: Section, item: RuleItem) -> RuleForm:
    """Formular für eine vorhandene Regel.

    Args:
        section: Ihr Abschnitt.
        item: Die Regelzeile.

    Returns:
        Das vorbelegte Formular.
    """
    r = section.rhythm
    yearly = date(2000, r.month, r.days[0]) if r.kind is Kind.JAEHRLICH and r.month else None
    return RuleForm(body=item.body, kind=r.kind, weekdays=r.weekdays, interval=str(r.interval), start=r.start,
                    month_days=", ".join(str(d) for d in r.days) if r.kind is Kind.MONATLICH else "1",
                    yearly=yearly, frist="" if section.options.frist is None else str(section.options.frist),
                    in_pauses=section.options.in_pauses, tags=" ".join(f"#{t}" for t in section.tags),
                    active=not item.paused)


def find_rule(rf: RoutineFile, line_no: int, text: str) -> tuple[Section, RuleItem] | None:
    """Abschnitt und Regel zu einer Regelzeile (für den Tipp auf eine Vorschauzeile)."""
    for section in rf.sections:
        for item in section.items:
            if item.line == text and (item.line_no == line_no or sum(i.line == text for s in rf.sections
                                                                     for i in s.items) == 1):
                return section, item
    return None


def section_title(section: Section) -> str:
    """Überschrift eines Abschnitts in kanonischer Form ohne ``## ``."""
    return heading_line(section.rhythm, section.options, section.tags)[3:]


def upcoming(form: RuleForm, rf: RoutineFile | None, today: date) -> str:
    """„Nächste: Mo 19.01., Mo 26.01., …“ oder die Fehlermeldung des Formulars.

    Args:
        form: Formular.
        rf: Routinen-Datei (für Pausen) oder ``None``.
        today: Heute.

    Returns:
        Kurzer Text für den Dialog.
    """
    try:
        rhythm, options = form.rhythm(), form.options()
    except RhythmError as exc:
        return str(exc)
    skip = (lambda d: rf.in_pause(d)) if rf is not None and not options.in_pauses else (lambda _d: False)
    days, after = [], today - timedelta(days=1)
    while len(days) < UPCOMING_COUNT and (after := next_due(rhythm, after, skip)) is not None:
        days.append(f"{WEEKDAYS[after.weekday()]} {after:%d.%m.}")
    return "Nächste: " + ", ".join(days) if days else "In den nächsten zwei Jahren nicht fällig."


def due_today(form: RuleForm, rf: RoutineFile | None, today: date) -> bool:
    """Wäre die Regel heute fällig (aktiv, nicht in einer Pause)? Vorbelegung für „Heute schon eintragen“."""
    try:
        rhythm, options = form.rhythm(), form.options()
    except RhythmError:
        return False
    paused = rf is not None and rf.in_pause(today) and not options.in_pauses
    return form.active and is_due(rhythm, today) and not paused


def text_problems(text: str) -> str | None:
    """Prüft einen Rohtext für ``Routinen.md``; ``None`` = keine Probleme (Rohtext-Editor).

    Args:
        text: Kompletter Dateitext.

    Returns:
        Fehlermeldungen je Zeile (eine pro Zeile) oder ``None``.
    """
    return "\n".join(problem_lines(parse_routines(parse_document(text.encode("utf-8"))))) or None


def problem_lines(rf: RoutineFile) -> list[str]:
    """Meldungen zu nicht lesbaren Teilen (einzige Formulierung; Seite und Rohtext-Editor).

    Args:
        rf: Gelesene Routinen-Datei.

    Returns:
        Merkpunkt-Fehler und je nicht lesbarer Zeile ``Zeile N: Text – Meldung``.
    """
    return ([rf.until_error] if rf.until_error else []) + [
        f"Zeile {e.line_no + 1}: {e.line.strip()} – {e.message}" for e in rf.errors]
