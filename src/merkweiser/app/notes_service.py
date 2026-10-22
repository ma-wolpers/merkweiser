"""NotesService: die einzige Fassade für Desktop und Mobile (PLAN.md, „App-Schicht“).

Bündelt Lesen (Tagesansicht, Todos, Suche, Konflikte) und alle Aktionen. Jede
Aktion folgt demselben Muster: Datei frisch lesen → Operation planen →
``Writer.write`` → bei ``ChangedBeforeWriteError`` bis zu 3-mal neu planen,
danach ``StaleTargetError`` (die UI lädt neu und meldet es).

``start()`` führt die feste Startreihenfolge aus: Tausch-Wiederherstellung →
Resolve-Ops → Moves → Aufbewahrung → leere Tagesdateien entfernen → Scan →
Auto-Merge.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from ..core import conflict_files as cf
from ..core.appdata import open_vault_data
from ..core.cleanup import empty_day_files
from ..core.automerge_log import AutoMergeEntry, automerge_log, hide_automerges, undone_manual_paths
from ..core.automerge_log import undo_automerge as _undo_automerge
from ..core.conflicts import CaseKind, ConflictCase, auto_merge, classify
from ..core.doc_cache import DocumentCache
from ..core.document import Document, parse_document
from ..core.edits import add_todo, set_done, set_project, set_urgent
from ..core.fs_probe import GUARANTEE, VaultNotWritableError, probe_install_mode
from ..core.fsops import FsOps
from ..core.history import History
from ..core.move_exec import MoveResult, move_todo, recover_moves
from ..core.note_ops import NoteNotFoundError, append_note, delete_note, replace_note_text
from ..core.ops import OpStore
from ..core.patch import StaleTargetError, Target
from ..core.query import Filter, Hit, search
from ..core.recovery import RecoveryReport, recover
from ..core.resolve import ResolveOutcome, manual_only_paths, recover_resolves, resolve
from ..core.retention import prune_ops, prune_sidecars
from ..core.safe_write import ChangedBeforeWriteError, WriteResult, Writer
from ..core.vault import DayPattern, VaultIndex, scan, write_target
from ..core.watch import Changes, State, observe, poll
from ..ports.clock import Clock
from .settings import Settings

MAX_REPLANS = 3
READ_ONLY_GUARANTEE = "keine (schreibgeschützt)"


class ReadOnlyVaultError(PermissionError):
    """Aktion abgelehnt: Der Notizordner ist schreibgeschützt geöffnet."""


class SameDayMoveError(ValueError):
    """Verschieben abgelehnt: Das Zieldatum ist das Datum der Quelldatei (nichts geändert)."""


def _writes(method):
    """Markiert eine schreibende Service-Methode; im Schreibschutz wird sie abgelehnt.

    Args:
        method: Methode von ``NotesService``.

    Returns:
        Die umhüllte Methode, die bei ``read_only`` ``ReadOnlyVaultError`` wirft,
        bevor irgendetwas geplant oder geschrieben wird.
    """
    @functools.wraps(method)
    def guarded(self, *args, **kwargs):
        if self.read_only:
            raise ReadOnlyVaultError("Der Notizordner ist schreibgeschützt geöffnet; Änderungen sind nicht möglich.")
        return method(self, *args, **kwargs)
    return guarded


@dataclass
class StartReport:
    """Was beim Start passiert ist (für Hinweise in der Oberfläche)."""

    recovery: RecoveryReport
    resolves: list[ResolveOutcome] = field(default_factory=list)
    moves: list[MoveResult] = field(default_factory=list)
    automerges: list[str] = field(default_factory=list)
    removed_empty: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DayFile:
    """Eine Tagesdatei in der Tagesansicht."""

    relpath: str
    document: Document
    duplicate: bool
    has_conflict: bool


class NotesService:
    """Fassade über einem Vault.

    Args:
        root: Vault-Ordner.
        app_data: App-Datenverzeichnis des Geräts.
        settings: Einstellungen.
        clock: Zeitquelle.
        fs: Dateisystem-Primitive (Tests: mit Fault-Injection). ``None``: die
            Install-Variante per Selbsttest im Vault ermitteln (``probe_install_mode``).

    Attributes:
        read_only: ``True``, wenn der Selbsttest keine Variante findet, mit der
            sich im Vault ohne Überschreiben schreiben lässt (PLAN.md, „No-Go“):
            Der Vault ist dann nur lesbar, der Start überspringt alle
            schreibenden Schritte, und schreibende Methoden werfen
            ``ReadOnlyVaultError``.
    """

    def __init__(self, root: Path, app_data: Path, settings: Settings, clock: Clock, fs: FsOps | None = None) -> None:
        self.root, self.settings, self.clock = root, settings.validated(), clock
        self.pattern = DayPattern(settings.pattern)
        self.read_only = False
        if fs is None:
            try:
                fs = FsOps(probe_install_mode(root))
            except VaultNotWritableError:
                self.read_only, fs = True, FsOps("excl")  # wird nie zum Schreiben benutzt (_writes)
        self.fs = fs
        self.data = open_vault_data(app_data, root)
        self.store = OpStore(self.data, clock, self.fs)
        self.history = History(self.data, clock)
        self.writer = Writer(root, self.data, self.store, self.fs, clock, self.history)
        self.cache = DocumentCache(root, settings.project_prefix)
        self.index: VaultIndex = scan(root, self.pattern)
        self.busy: set[str] = set()
        self._watch: State = {}

    # --- Start und Beobachtung ----------------------------------------------------

    def start(self) -> StartReport:
        """Feste Startreihenfolge; danach sind alle Ops in einem definierten Zustand.

        Im Schreibschutz nur Scan und Beobachtung: Unvollständige Ops bleiben
        unangetastet, bis der Ordner wieder beschreibbar ist.

        Returns:
            Startbericht für Hinweise in der Oberfläche.
        """
        if self.read_only:
            self.rescan()
            self._watch = observe(self.root)
            return StartReport(RecoveryReport())
        report = StartReport(recover(self.writer))
        self.busy = report.recovery.busy_paths
        report.resolves = recover_resolves(self.writer, self.store)
        report.moves = recover_moves(self.writer, self.store, self.settings.project_prefix)
        prune_sidecars(self.root, self.data)
        prune_ops(self.root, self.data, self.store, self.clock, self.settings.retention_days)
        self.rescan()
        report.removed_empty = self._remove_empty_day_files()
        report.automerges = self.auto_merge_all()
        self._watch = observe(self.root)
        return report

    @property
    def write_guarantee(self) -> str:
        """Schreibgarantie für die Anzeige („voll“, „eingeschränkt (A1–A3)“ oder „keine (schreibgeschützt)“)."""
        return READ_ONLY_GUARANTEE if self.read_only else GUARANTEE[self.fs.install_mode]

    def rescan(self) -> VaultIndex:
        """Liest die Dateiliste neu."""
        self.index = scan(self.root, self.pattern)
        return self.index

    def poll(self) -> Changes:
        """Prüft auf Änderungen und schließt fällige Quarantänen ab (nicht im Schreibschutz)."""
        if not self.read_only:
            self.writer.finish_due()
        changes, self._watch = poll(self.root, self._watch)
        if changes.any:
            self.rescan()
        return changes

    # --- Ansichten ------------------------------------------------------------------

    def day(self, day: date) -> list[DayFile]:
        """Alle Tagesdateien eines Datums (Dubletten markiert)."""
        paths = self.index.day_files.get(day, ())
        open_conflicts = {c.main_relpath for c in self.index.conflicts}
        return [DayFile(p, self.cache.get(p), len(paths) > 1, p in open_conflicts) for p in paths]

    def day_of(self, relpath: str) -> date | None:
        """Datum einer Tagesdatei laut Index.

        Args:
            relpath: Datei relativ zum Vault.

        Returns:
            Das Datum oder ``None``, wenn die Datei keine bekannte Tagesdatei ist.
        """
        return next((d for d, paths in self.index.day_files.items() if relpath in paths), None)

    def search(self, criteria: Filter) -> list[Hit]:
        """Suche über alle Tagesdateien (Semantik im Core, für alle UIs gleich)."""
        docs = [(p, d, self.cache.get(p)) for d, paths in self.index.day_files.items() for p in paths]
        return search(docs, criteria)

    def conflicts(self) -> list[ConflictCase]:
        """Aktuelle Konfliktfälle."""
        manual = manual_only_paths(self.store) | undone_manual_paths(self.store)
        return classify(self.root, self.writer, self.index, self.busy, manual)

    @_writes
    def auto_merge_all(self) -> list[str]:
        """Führt alle automatisch zusammenführbaren Fälle aus (Kette je Hauptdatei)."""
        done = []
        for _round in range(len(self.index.conflicts) + 1):
            cases = [c for c in self.conflicts() if c.kind is CaseKind.AUTO]
            if not cases:
                break
            for case in cases:
                op_id = auto_merge(self.writer, self.store, case)
                if op_id:
                    done.append(op_id)
            self.rescan()
        return done

    def automerges(self, limit: int = 20) -> list[AutoMergeEntry]:
        """Liste „Automatisch zusammengeführt“, neueste zuerst.

        Args:
            limit: Höchstzahl der Einträge.

        Returns:
            Einträge mit Bytes vorher/nachher und Rückgängig-Zustand.
        """
        return automerge_log(self.store, limit)

    def hide_automerges(self, op_ids: list[str]) -> list[str]:
        """Blendet Einträge der Auto-Merge-Liste aus (nur Anzeige; Backup und Rückgängig-Wirkung bleiben).

        Schreibt nur in die App-Daten, nie in den Vault; daher auch im Schreibschutz erlaubt.

        Args:
            op_ids: Automerge-Ops.

        Returns:
            Tatsächlich ausgeblendete ``op-id``s.
        """
        return hide_automerges(self.store, op_ids)

    @_writes
    def undo_automerge(self, op_id: str) -> str:
        """Macht einen Auto-Merge rückgängig; die Konfliktdatei bleibt danach „nur manuell“.

        Args:
            op_id: Die Automerge-Op.

        Returns:
            Pfad der wiederhergestellten Konfliktdatei.
        """
        restored = _undo_automerge(self.writer, self.store, op_id)
        self.rescan()
        return restored

    @_writes
    def resolve(self, case: ConflictCase, result: bytes, decision: str,
                manual_only: tuple[str, ...] = ()) -> ResolveOutcome:
        """Wendet eine explizite Konfliktentscheidung an (Resolve-Op mit Marker)."""
        outcome = resolve(self.writer, self.store, case.conflict.main_relpath, case.main_bytes,
                          case.conflict.relpath, case.conflict_bytes, result, decision, manual_only)
        self.rescan()
        return outcome

    # --- Aktionen ---------------------------------------------------------------------

    @_writes
    def set_done(self, target: Target, done: bool) -> WriteResult:
        """Todo erledigt bzw. offen setzen."""
        return self._edit(target.relpath, lambda doc: set_done(doc, target, done))

    @_writes
    def set_urgent(self, target: Target, urgent: bool) -> WriteResult:
        """Todo als dringend markieren bzw. die Markierung entfernen."""
        return self._edit(target.relpath, lambda doc: set_urgent(doc, target, urgent))

    @_writes
    def set_project(self, target: Target, name: str | None) -> WriteResult:
        """Explizites Projekt eines Todos setzen bzw. entfernen."""
        prefix = self.settings.project_prefix
        return self._edit(target.relpath, lambda doc: set_project(doc, target, name, prefix))

    @_writes
    def add_todo(self, relpath: str, note_index: int, text: str, parent: Target | None = None) -> WriteResult:
        """Neues Todo in eine Notiz einfügen."""
        return self._edit(relpath, lambda doc: add_todo(doc, note_index, text, parent))

    @_writes
    def append_note(self, text: str) -> WriteResult:
        """Neue Notiz in der Tagesdatei von heute (Datei wird bei Bedarf angelegt)."""
        relpath = write_target(self.index, self.pattern, self.clock.today())
        result = self._edit(relpath, lambda doc: append_note(doc, text), allow_missing=True)
        self.rescan()
        return result

    @_writes
    def delete_note(self, relpath: str, original: tuple[str, ...]) -> WriteResult:
        """Notiz samt einem angrenzenden Trenner löschen."""
        return self._edit(relpath, lambda doc: delete_note(doc, original))

    @_writes
    def replace_note_text(self, relpath: str, planned_raw: bytes, original: tuple[str, ...],
                          text: str) -> WriteResult:
        """Rohtext einer Notiz ersetzen; ist sie nicht mehr eindeutig auffindbar → eigene Konfliktdatei.

        Args:
            relpath: Datei.
            planned_raw: Dateiinhalt beim Öffnen des Editors (Planungsstand, Basis).
            original: Inhaltszeilen der Notiz beim Öffnen.
            text: Neuer Notiztext.
        """
        try:
            return self._edit(relpath, lambda doc: replace_note_text(doc, original, text))
        except NoteNotFoundError:
            ours = replace_note_text(self._parse(planned_raw), original, text)
            base = self.store.create("konfliktbasis", {"relpath": relpath}, {"vorher": planned_raw})
            base.set_state("DONE")
            base.release()
            path = cf.create_from_bytes(self.fs, self.root / relpath, ours, self.clock)
            rel = self.writer.rel(path)
            cf.write_sidecar(self.data, rel, cf.sha1(ours), relpath, base.id, cf.sha1(planned_raw))
            self.rescan()
            return WriteResult(base.id, "CONFLICTED", [rel])

    @_writes
    def move_todo(self, target: Target, day: date) -> MoveResult:
        """Todo samt Teilbaum (bzw. die ganze Notiz, wenn es ihr alleiniges Todo ist) verschieben.

        Args:
            target: Zeile des Todos.
            day: Zieldatum.

        Returns:
            Ergebnis des Move-Protokolls.

        Raises:
            SameDayMoveError: ``day`` ist das Datum der Quelldatei; geprüft vor
                jedem Lesen und Schreiben, es bleibt nichts verändert.
            StaleTargetError: Todo nicht eindeutig auffindbar.
        """
        if self.day_of(target.relpath) == day:
            raise SameDayMoveError(f"Das Todo steht schon am {day:%d.%m.%Y}.")
        dst = write_target(self.index, self.pattern, day)
        result = move_todo(self.writer, self.store, target.relpath, target, dst, self.settings.project_prefix)
        for path in (target.relpath, dst):
            self.cache.forget(path)
        self.rescan()
        return result

    # --- intern -----------------------------------------------------------------------

    def _remove_empty_day_files(self) -> list[str]:
        """Entfernt leere Tagesdateien (nur Leerraum und ``---``) über das sichere Löschprotokoll.

        Ändert sich eine Datei zwischen Prüfung und Löschen, bleibt sie stehen.

        Returns:
            Entfernte Pfade (relativ zum Vault).
        """
        removed = []
        for relpath, raw in empty_day_files(self.root, self.index, self.busy):
            try:
                self.writer.remove(relpath, raw)
            except ChangedBeforeWriteError:
                continue
            removed.append(relpath)
        if removed:
            self.rescan()
        return removed

    def _parse(self, raw: bytes) -> Document:
        """Liest Bytes mit dem eingestellten Projekt-Präfix ein."""
        return parse_document(raw, self.settings.project_prefix)

    def _edit(self, relpath: str, build: Callable[[Document], bytes], allow_missing: bool = False) -> WriteResult:
        """Lesen → planen → schreiben, bei externer Änderung bis zu 3-mal neu planen."""
        path = self.root / relpath
        for _attempt in range(MAX_REPLANS):
            before = path.read_bytes() if path.exists() else None
            if before is None and not allow_missing:
                raise StaleTargetError(f"{relpath} existiert nicht mehr")
            after = build(self._parse(before or b""))
            if after == before:
                return WriteResult("", "DONE")
            try:
                result = self.writer.write(relpath, before, after)
            except ChangedBeforeWriteError:
                continue
            self.cache.forget(relpath)
            return result
        raise StaleTargetError(f"{relpath} wurde wiederholt extern geändert")
