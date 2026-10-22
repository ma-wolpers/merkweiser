"""Doppelte Notizen über mehrere Tagesdateien (W3, PLAN-SPAETERE-SCHRITTE.md S3).

**Gleich** heißt: gleiche Zeilentexte der Notiz nach Normalisierung der
Zeilenenden (LF = CRLF), sonst keine Normalisierung. Gezählt werden nur
Fundstellen in **verschiedenen** Tagesdateien (je Datei die erste); doppelte
Notizen innerhalb derselben Datei werden nicht gemeldet.

Bereinigung als Schrittprotokoll (``step_ops``), Eltern-Op ``duplikat``:

* Das Manifest hält **vor dem ersten Löschen** die Zeilen, alle Fundstellen
  (Datei, Datum, erste Zeile) und die gewählte Fundstelle (``behalten``). Die
  Auswahl wird nach einem Absturz **nie** neu abgeleitet.
* Vor jedem Schritt (auch nach einem Neustart) muss die behaltene Fundstelle
  die Notiz noch exakt enthalten; sonst ``INCOMPLETE`` („Behaltene Fassung
  fehlt“) und **nichts** wird weiter gelöscht.
* Je andere Fundstelle ein Schritt (``delete_note``), erledigt laut Kinder-Op.
  Ist die Notiz dort nicht mehr genau einmal als ganze Notiz vorhanden
  (verändert, entfernt oder doppelt in derselben Datei), wird diese Fundstelle
  übersprungen und am Ende als ``INCOMPLETE`` mit Hinweis gemeldet.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .document import Document, parse_document
from .note_ops import NoteNotFoundError, delete_note
from .ops import Op, OpStore
from .patch import StaleTargetError
from .safe_write import Writer
from .step_ops import STEP_DONE, child_states, finish, incomplete, pending_ops, run_step


@dataclass(frozen=True)
class Place:
    """Eine Fundstelle.

    Attributes:
        relpath: Tagesdatei.
        day: Datum der Tagesdatei.
        first_line: Erste Inhaltszeile der Notiz (beim Finden).
    """

    relpath: str
    day: date
    first_line: int


@dataclass(frozen=True)
class DuplicateGroup:
    """Eine Notiz, die in mehreren Tagesdateien gleich vorkommt.

    Attributes:
        lines: Zeilentexte der Notiz (ohne Zeilenende).
        places: Fundstellen, älteste zuerst (Datum, dann Pfad).
    """

    lines: tuple[str, ...]
    places: tuple[Place, ...]


def note_lines(doc: Document, note) -> tuple[str, ...] | None:
    """Zeilentexte einer Notiz (ohne Zeilenende) oder ``None`` ohne Inhalt."""
    content = note.note.content
    if content is None:
        return None
    return tuple(line.text for line in doc.source.lines[content.start:content.end])


def find_duplicates(documents: Iterable[tuple[str, date, Document]]) -> list[DuplicateGroup]:
    """Sucht gleiche Notizen in verschiedenen Tagesdateien.

    Args:
        documents: ``(relpath, datum, Dokument)`` je Tagesdatei.

    Returns:
        Gruppen mit mindestens zwei Dateien; die mit der jüngsten Fundstelle zuerst.
    """
    seen: dict[tuple[str, ...], dict[str, Place]] = {}
    for relpath, day, doc in documents:
        for note in doc.notes:
            lines = note_lines(doc, note)
            if lines:
                seen.setdefault(lines, {}).setdefault(relpath, Place(relpath, day, note.note.content.start))
    groups = [DuplicateGroup(lines, tuple(sorted(places.values(), key=lambda p: (p.day, p.relpath))))
              for lines, places in seen.items() if len(places) >= 2]
    return sorted(groups, key=lambda g: (g.places[-1].day, g.places[-1].relpath), reverse=True)


def keep_one(writer: Writer, store: OpStore, group: DuplicateGroup, keep: int, prefix: str = "") -> str:
    """Behält Fundstelle ``keep`` und löscht die Notiz an allen anderen (S3).

    Args:
        writer: Writer.
        store: Op-Store.
        group: Die Gruppe (wie angezeigt).
        keep: Index in ``group.places``.
        prefix: Projekt-Präfix.

    Returns:
        Leer bei Erfolg, sonst ein Hinweis (Vorgang dann ``INCOMPLETE``).
    """
    places = [{"relpath": p.relpath, "tag": p.day.isoformat(), "erste_zeile": p.first_line} for p in group.places]
    op = store.create("duplikat", {"zeilen": list(group.lines), "fundstellen": places, "behalten": keep}, {})
    return _continue(writer, store, op, prefix)


def resume_duplicate(writer: Writer, store: OpStore, op_id: str, prefix: str = "") -> str:
    """Setzt eine Duplikatbereinigung fort („Erneut prüfen“ oder Start).

    Returns:
        Leer bei Erfolg, sonst ein Hinweis.
    """
    op = store.open_for_recovery(op_id)
    if op is None:
        return "Vorgang wird gerade von einer anderen Instanz bearbeitet."
    return _continue(writer, store, op, prefix)


def recover_duplicates(writer: Writer, store: OpStore, prefix: str = "") -> list[str]:
    """Setzt unterbrochene Bereinigungen nach einem Absturz fort (``INCOMPLETE`` wartet auf den Nutzer)."""
    return [op_id for op_id in pending_ops(store, "duplikat") if resume_duplicate(writer, store, op_id, prefix) == ""]


def _continue(writer: Writer, store: OpStore, op: Op, prefix: str) -> str:
    """Führt die offenen Löschschritte aus (siehe Moduldoku)."""
    m = op.manifest
    lines = tuple(m["zeilen"])
    places = m["fundstellen"]
    kept = places[m["behalten"]]
    done = child_states(store, op.id)
    skipped = []
    for index, place in enumerate(places):
        if index == m["behalten"] or done.get(place["relpath"]) in STEP_DONE:
            continue
        if not _contains(writer, kept["relpath"], lines, prefix):
            hint = f"Behaltene Fassung in {kept['relpath']} fehlt oder wurde verändert – nichts weiter gelöscht."
            incomplete(op, hint)
            return hint
        try:
            run_step(writer, op, place["relpath"], prefix, lambda doc, _raw: delete_note(doc, lines))
        except (NoteNotFoundError, StaleTargetError):
            skipped.append(place["relpath"])
    if skipped:
        hint = f"Fundstelle(n) {', '.join(skipped)} inzwischen verändert oder mehrdeutig – dort nicht gelöscht."
        incomplete(op, hint)
        return hint
    finish(op)
    return ""


def _contains(writer: Writer, relpath: str, lines: tuple[str, ...], prefix: str) -> bool:
    """``True``, wenn die Datei die Notiz noch mindestens einmal als ganze Notiz enthält."""
    path = writer.root / relpath
    if not path.exists():
        return False
    doc = parse_document(path.read_bytes(), prefix)
    return any(note_lines(doc, note) == lines for note in doc.notes)
