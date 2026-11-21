"""Routinen: Durchlauf beim Start und Poll (W9, ``PLAN-SPAETERE-SCHRITTE.md`` W9).

``run_due`` trägt fällige Instanzen ein und lässt abgelaufene ablaufen:

1. **Eintragen** Tag für Tag von ``eingetragen_bis + 1`` bis heute (ohne
   Merkpunkt nur heute; höchstens ``MAX_CATCHUP_DAYS`` je Durchlauf, der Rest
   folgt beim nächsten Poll). Instanzen, deren Frist beim Nachholen schon
   abgelaufen ist, werden direkt als ``[-]`` geschrieben (lückenlos).
2. **Ablauf**: offene ``#wdh``-Todos früherer Tage, deren Frist vorbei ist
   (``routines.expiry_for``), werden ``[-]``.
3. **Merkpunkt** ``eingetragen_bis`` vorwärts schreiben, aber nur wenn sich die
   Regeln seit dem Lesen nicht geändert haben (``RoutineFile.same_rules``).

Sicherheit: Jeder Schreibvorgang läuft über ``step_ops.run_step`` (frisch
planen, Backup, Konfliktdatei statt Überschreiben); ``present`` macht das
Eintragen idempotent. Übersprungen wird bei Schreibschutz; nur das Eintragen
zusätzlich bei offenem Konflikt auf ``Routinen.md``, ungültigem Merkpunkt,
nicht beschreibbarem Kopf oder wenn die Datei „in Bearbeitung“ ist. Eine
mehrdeutige Tagesdatei stoppt das Eintragen vor diesem Tag (gemeldet).
Fehler brechen weder Start noch Poll ab, sie landen in ``RoutineReport.problems``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING

from ..core.document import Document
from ..core.frontmatter import set_keys
from ..core.inline import TodoStatus, parse_list_item
from ..core.patch import StaleTargetError, Target
from ..core.query import Filter, StatusFilter
from ..core.routine_days import expire_lines, missing, plan_day
from ..core.routines import ROUTINES_FILE, UNTIL_KEY, WDH_TAG, RoutineFile, expiry_for, occurrences, parse_routines
from ..core.step_ops import run_step
from ..core.topics import topic_line
from ..core.vault import AmbiguousDayFile, write_target
from ..core.watch import Changes

if TYPE_CHECKING:
    from .notes_service import NotesService

MAX_CATCHUP_DAYS = 31


@dataclass
class RoutineReport:
    """Ergebnis eines Durchlaufs (für Hinweise).

    Attributes:
        written: Offen eingetragene Instanzen.
        missed: Beim Nachholen direkt als verpasst eingetragene Instanzen.
        expired: Abgelaufene, auf verpasst gesetzte Todos.
        problems: Meldungen (Durchlauf ganz oder teilweise übersprungen).
    """

    written: int = 0
    missed: int = 0
    expired: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Kurzer deutscher Hinweis; leer, wenn nichts passiert ist."""
        parts = [f"{n} {label}" for n, label in ((self.written, "eingetragen"), (self.missed, "nachgetragen als verpasst"),
                                                 (self.expired, "abgelaufen")) if n]
        text = f"Routinen: {', '.join(parts)}." if parts else ""
        return " ".join(([text] if text else []) + self.problems)


def load(service: "NotesService") -> RoutineFile | None:
    """Liest ``Routinen.md`` (zwischengespeichert, solange sich die Datei nicht ändert).

    Args:
        service: Geöffneter Service.

    Returns:
        Die gelesene Datei oder ``None``, wenn es sie nicht gibt.
    """
    try:
        doc = service.cache.get(ROUTINES_FILE)
    except FileNotFoundError:
        return None
    memo = getattr(service, "_routine_memo", None)
    if memo is not None and memo[0] is doc:
        return memo[1]
    parsed = parse_routines(doc)
    service._routine_memo = (doc, parsed)  # Identität des Cache-Dokuments = unveränderte Datei
    return parsed


def run_due(service: "NotesService") -> RoutineReport:
    """Ein vollständiger Durchlauf (siehe Moduldoku). Wirft nie.

    Args:
        service: Geöffneter Service.

    Returns:
        Bericht; im Schreibschutz leer.
    """
    report = RoutineReport()
    today = service.clock.today()
    service._routine_day = today
    if service.read_only:
        return report
    try:
        rf = load(service)
        done = _materialize(service, rf, today, report) if rf is not None and rf.sections else None
        _expire(service, rf, today, report)
        if done is not None:
            _advance(service, rf, done)  # type: ignore[arg-type]
    except Exception as exc:  # GRENZE(W9): ein Fehler im Durchlauf darf Start und Poll nie abbrechen
        report.problems.append(f"Routinen übersprungen: {exc}")
    return report


def on_poll(service: "NotesService", changes: Changes) -> RoutineReport | None:
    """Durchlauf nach einem Poll, wenn sich etwas geändert hat oder ein neuer Tag begonnen hat.

    Eigene Schreibvorgänge eines Durchlaufs lösen genau einen weiteren aus, der
    nichts mehr zu tun hat.

    Args:
        service: Geöffneter Service.
        changes: Ergebnis des Polls.

    Returns:
        Bericht oder ``None``, wenn kein Durchlauf nötig war.
    """
    if service.read_only or (not changes.any and service.clock.today() == getattr(service, "_routine_day", None)):
        return None
    return run_due(service)


def _materialize(service: "NotesService", rf: RoutineFile, today: date, report: RoutineReport) -> date | None:
    """Trägt die Instanzen ab dem Merkpunkt ein; liefert den letzten vollständig bearbeiteten Tag."""
    blocked = _blocked(service, rf)
    if blocked:
        report.problems.append(blocked)
        return None
    first = rf.until + timedelta(days=1) if rf.until else today
    last = min(today, first + timedelta(days=MAX_CATCHUP_DAYS - 1))
    done, day, wrote = None, first, False
    while day <= last:
        occs = occurrences(rf, day)
        if occs:
            try:
                relpath = write_target(service.index, service.pattern, day)
            except AmbiguousDayFile as exc:
                report.problems.append(f"Routinen ab {day:%d.%m.%Y} nicht eingetragen: {exc}")
                break
            entries = [(o.topic, o.body, o.line(TodoStatus.MISSED if o.expires and o.expires <= today
                                                 else TodoStatus.OPEN)) for o in occs]
            new: list[tuple[str, str, str]] = []

            def build(doc: Document, _raw: bytes | None, entries=entries, new=new) -> bytes:
                new[:] = missing(doc, entries)
                return plan_day(doc, entries)

            run_step(service.writer, None, relpath, service.settings.project_prefix, build)
            service.cache.forget(relpath)
            report.missed += sum(1 for _t, _b, line in new if line.startswith("- [-]"))
            report.written += sum(1 for _t, _b, line in new if not line.startswith("- [-]"))
            wrote = wrote or bool(new)
        done, day = day, day + timedelta(days=1)
    if wrote:
        service.rescan()
    return done


def _blocked(service: "NotesService", rf: RoutineFile) -> str | None:
    """Grund, warum gerade nicht eingetragen werden darf (``None`` = alles gut)."""
    if ROUTINES_FILE in service.busy:
        return "Routinen.md ist in Bearbeitung – Routinen werden später eingetragen."
    if any(c.main_relpath == ROUTINES_FILE for c in service.index.conflicts):
        return "Routinen.md hat einen offenen Konflikt – Routinen werden erst danach eingetragen."
    if rf.until_error:
        return f"Routinen.md: {rf.until_error} – nichts eingetragen."
    if not rf.head_writable:
        return "Routinen.md: Kopfbereich nicht sicher lesbar – nichts eingetragen."
    return None


def _expire(service: "NotesService", rf: RoutineFile | None, today: date, report: RoutineReport) -> None:
    """Setzt offene ``#wdh``-Todos früherer Tage mit abgelaufener Frist auf verpasst."""
    due: dict[str, list[Target]] = defaultdict(list)
    for hit in service.search(Filter(tags=(WDH_TAG,), status=StatusFilter.OFFEN, bis=today - timedelta(days=1))):
        doc = service.cache.get(hit.relpath)
        topic, item = topic_line(doc, doc.notes[hit.note_index]), parse_list_item(hit.text)
        if topic is None or item is None or hit.relpath in service.busy:
            continue
        expires = expiry_for(rf, topic, hit.text[item.body_start:], hit.day)
        if expires is not None and expires <= today:
            due[hit.relpath].append(Target(hit.relpath, hit.line_no, hit.text))
    for relpath, targets in due.items():
        run_step(service.writer, None, relpath, service.settings.project_prefix,
                 lambda doc, _raw, targets=targets: expire_lines(doc, targets))
        service.cache.forget(relpath)
        report.expired += len(targets)
    if due:
        service.rescan()


def _advance(service: "NotesService", rf: RoutineFile, done: date) -> None:
    """Schreibt ``eingetragen_bis`` vorwärts, nur bei unveränderten Regeln (sonst beim nächsten Durchlauf)."""
    def build(doc: Document, raw: bytes | None) -> bytes | None:
        fresh = parse_routines(doc)
        if not fresh.same_rules(rf):
            raise StaleTargetError("Routinen.md wurde während des Eintragens geändert")
        if fresh.until is not None and fresh.until >= done:
            return None
        return set_keys(raw or b"", {UNTIL_KEY: done.isoformat()})

    try:
        run_step(service.writer, None, ROUTINES_FILE, service.settings.project_prefix, build)
    except StaleTargetError:
        return  # der nächste Poll bemerkt die Änderung und trägt idempotent erneut ein
    service.cache.forget(ROUTINES_FILE)
