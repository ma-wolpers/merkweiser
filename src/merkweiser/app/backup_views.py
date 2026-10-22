"""Backup-Browser für die Oberflächen (W4, PLAN-SPAETERE-SCHRITTE.md 1.4, S4).

UI-neutral: Dateiliste, Änderungsliste mit Vergleich, Zusammenhang
(Gruppe) und Folgenwarnung, Rückgängig einer einzelnen Änderung bzw. der
bisherigen Gesamtaktionen „Zusammenführung rückgängig“ (Auto-Merge) und
„Entscheidung rückgängig“ (Konfliktentscheidung).

Das Modell bleibt die **Einzeländerung**. Gehört eine Änderung zu einem
Vorgang mit mehreren Dateien, nennt ``ChangeView.group_note`` den Zusammenhang
und die Folgen, und ``siblings`` die anderen Änderungen desselben Vorgangs.
Eine Garantie, dass jede Einzeländerung isoliert gefahrlos ist, gibt es nicht.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from ..core.backups import Change, change_key, changes, changes_by_file, load, undo_change, undone_ops
from .conflict_views import DiffRow, line_diff

if TYPE_CHECKING:
    from .notes_service import NotesService

GROUP_NOTES = {
    "move": "Gehört zu einem Verschieben (zwei Dateien). Nimmst du nur das Ziel zurück, steht das Todo in keiner "
            "Datei mehr (es bleibt im Backup); nimmst du nur die Quelle zurück, steht es doppelt.",
    "automerge": "Gehört zu einer automatischen Zusammenführung. „Zusammenführung rückgängig“ stellt Hauptdatei "
                 "und Konfliktdatei gemeinsam wieder her.",
    "resolve": "Gehört zu einer Konfliktentscheidung. „Entscheidung rückgängig“ setzt Hauptdatei und Konfliktdatei "
               "gemeinsam zurück.",
    "zeitbuchung": "Gehört zu einer Zeitbuchung, die mehrere Tage betreffen kann; die anderen Tage bleiben verbucht.",
    "duplikat": "Gehört zu einer Duplikat-Bereinigung; die Notiz wird danach wieder als Duplikat gemeldet.",
    "umbenennen": "Gehört zu einer Tätigkeits-Umbenennung; nur diese Datei wird zurückgesetzt.",
    "rueckgaengig": "Ist selbst ein Rückgängig; erneutes Rückgängig stellt den Stand davor wieder her.",
}
GROUP_ACTIONS = {"automerge": "Zusammenführung rückgängig", "resolve": "Entscheidung rückgängig"}


@dataclass(frozen=True)
class FileEntry:
    """Eine Datei in der Backup-Liste.

    Attributes:
        relpath: Datei relativ zum Vault.
        count: Anzahl Änderungen.
        newest: Zeitpunkt der jüngsten Änderung (lokal, ``TT.MM.JJJJ HH:MM``).
    """

    relpath: str
    count: int
    newest: str


@dataclass(frozen=True)
class ChangeView:
    """Eine Änderung zur Anzeige.

    Attributes:
        change: Die Änderung.
        when: Zeitpunkt lokal (``TT.MM.JJJJ HH:MM``).
        diff: Vergleich vorher (``haupt``) / nachher (``konflikt``).
        undone: Bereits rückgängig gemacht.
        group_note: Zusammenhang und Folgen (leer ohne Gruppe).
        group_action: Beschriftung der Gesamtaktion oder leer.
        siblings: Andere Änderungen desselben Vorgangs.
    """

    change: Change
    when: str
    diff: list[DiffRow]
    undone: bool
    group_note: str
    group_action: str
    siblings: list[Change]


def local_time(iso: str) -> str:
    """UTC-ISO-Zeitpunkt als lokale Uhrzeit ``TT.MM.JJJJ HH:MM`` (leer bei fehlender Angabe)."""
    return datetime.fromisoformat(iso).astimezone().strftime("%d.%m.%Y %H:%M") if iso else ""


def file_entries(service: "NotesService") -> list[FileEntry]:
    """Dateien mit Änderungen, jüngste Änderung zuerst."""
    return [FileEntry(rel, len(items), local_time(items[0].created)) for rel, items in changes_by_file(service.store)]


def file_changes(service: "NotesService", relpath: str) -> list[ChangeView]:
    """Änderungen einer Datei mit Vergleich und Zusammenhang, neueste zuerst.

    Args:
        service: Geöffneter Service.
        relpath: Datei.

    Returns:
        Anzeigemodelle; Änderungen mit fehlendem Backup erscheinen ohne Vergleich.
    """
    every = changes(service.store)
    undone = undone_ops(service.store)
    views = []
    for change in (c for c in every if c.relpath == relpath):
        siblings = [c for c in every if change.group and c.group == change.group and c is not change]
        views.append(ChangeView(change, local_time(change.created), _diff(service, change),
                                change_key(change) in undone,
                                GROUP_NOTES.get(change.group_art or "", "") if siblings else "",
                                GROUP_ACTIONS.get(change.group_art or "", ""), siblings))
    return views


def _diff(service: "NotesService", change: Change) -> list[DiffRow]:
    """Vergleich vorher/nachher; ein verdrängter Stand wird allein gezeigt."""
    try:
        before, after = load(service.store, change.before), load(service.store, change.after)
    except OSError:
        return [DiffRow("ausgelassen", "Backup fehlt oder ist beschädigt.")]
    if change.kind == "verdrängt":
        return line_diff(None, before or b"")
    return line_diff(before, after or b"")


def undo(service: "NotesService", change: Change) -> str:
    """Nimmt eine einzelne Änderung zurück.

    Args:
        service: Geöffneter, beschreibbarer Service.
        change: Die Änderung.

    Returns:
        Meldung für die Oberfläche.

    Raises:
        ReadOnlyVaultError: im Schreibschutz.
    """
    service.check_writable()
    plan = undo_change(service.writer, service.store, change, service.settings.project_prefix)
    service.rescan()
    return {"schreiben": "Änderung rückgängig gemacht.", "entfernen": "Datei entfernt (Änderung rückgängig gemacht).",
            "nichts": "Nichts zu tun – der frühere Stand ist schon da.",
            "konflikt": "Nicht eindeutig: Der frühere Stand liegt jetzt als Konfliktdatei vor "
                        "(Einstellungen → Konflikte)."}[plan.action]


def undo_group(service: "NotesService", change: Change) -> str:
    """Gesamtaktion für Auto-Merge („Zusammenführung rückgängig“) bzw. Konfliktentscheidung.

    Auto-Merge: das bisherige ``undo_automerge`` (Hauptdatei zurück, Konfliktdatei
    wieder da, nur manuell). Entscheidung: erst die Hauptdatei, dann die
    entfernte Konfliktdatei je einzeln zurück (beide über ``undo``).

    Args:
        service: Geöffneter, beschreibbarer Service.
        change: Eine Änderung der Gruppe.

    Returns:
        Meldung für die Oberfläche.
    """
    if change.group_art == "automerge" and change.group:
        restored = service.undo_automerge(change.group)
        return f"Zusammenführung rückgängig gemacht; Konfliktdatei wieder da: {restored}"
    members = [c for c in changes(service.store) if c.group == change.group and c.kind != "verdrängt"]
    members.sort(key=lambda c: c.kind == "gelöscht")  # erst Hauptdatei, dann Konfliktdatei
    undone = undone_ops(service.store)
    return " ".join(undo(service, c) for c in members if change_key(c) not in undone) or "Schon rückgängig gemacht."
