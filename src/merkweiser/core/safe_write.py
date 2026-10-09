"""Tausch-Protokoll: sicheres Schreiben und Entfernen im Vault (PLAN.md).

``Writer.write`` (Ersetzen bzw. Create-only) und ``Writer.remove`` folgen den
Schritten des Plans; jede Grenze ist mit ``fs.point`` markiert, damit Tests dort
einen Prozessabbruch simulieren können. Invarianten:

* **L (Löschen):** Eine Vault-Datei wird nur entfernt, wenn ihre Bytes zuvor
  im Op-Verzeichnis persistiert und geprüft sind und eine erneute Prüfung
  unmittelbar davor dieselben Bytes zeigt, oder sie wird per Rename an einen
  anderen Vault-Pfad verschoben. Ausnahme: die eigene, nie installierte
  Temp-Datei, deren Ziel-Bytes ``N`` persistiert sind.
* **I (Installieren):** nur ohne Überschreiben (``rename_no_replace``).
* Quarantäne: 2 Minuten ``Clock.monotonic``; danach Prüfung von ``P``
  (ist ``N`` noch da, sonst wird ``N`` als Konfliktdatei sichtbar) und von ``D``
  (unverändert → löschen, sonst → Konfliktdatei). Abweichend vom Plan auf
  allen Plattformen, also auch unter Windows (strenger, nicht schwächer).

Neu planen (z. B. nach einer externen Änderung) ist Sache des Aufrufers: Weicht
die Datei schon vor dem Start von ``expected`` ab, kommt
``ChangedBeforeWriteError`` und nichts wird verändert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..ports.clock import Clock
from . import conflict_files as cf
from .appdata import VaultData
from .fsops import FileBusyError, FsOps
from .history import History
from .ops import Op, OpStore

QUARANTINE_SECONDS = 120.0


class ChangedBeforeWriteError(Exception):
    """Die Datei entspricht schon vor dem Schreiben nicht dem erwarteten Stand."""


@dataclass
class WriteResult:
    """Ergebnis eines Schreib- oder Entfernvorgangs.

    Attributes:
        op_id: Die Op.
        state: ``QUARANTINE`` (installiert, Abschlussprüfung ausstehend),
            ``DONE``, ``CONFLICTED`` oder ``ABORTED``.
        conflicts: Neu angelegte eigene Konfliktdateien (relativ zum Vault).
    """

    op_id: str
    state: str
    conflicts: list[str] = field(default_factory=list)


def side_paths(main: Path, op_id: str) -> tuple[Path, Path]:
    """Pfade der Hilfsdateien ``T`` (Temp) und ``D`` (verdrängt) einer Op."""
    return (main.with_name(f".{main.name}.mw-{op_id}.tmp"), main.with_name(f".{main.name}.mw-{op_id}.old"))


class Writer:
    """Führt das Tausch-Protokoll für einen Vault aus.

    Args:
        root: Vault-Ordner.
        data: App-Daten des Vaults (Sidecars).
        store: Op-Verzeichnisse.
        fs: Dateisystem-Primitive.
        clock: Zeitquelle (Namen und monotone Quarantäne).
        history: Beobachtungs-Historie (Best Effort) oder ``None``.
    """

    def __init__(self, root: Path, data: VaultData, store: OpStore, fs: FsOps, clock: Clock,
                 history: History | None = None) -> None:
        self.root, self.data, self.store, self.fs, self.clock, self.history = root, data, store, fs, clock, history
        self._pending: dict[str, tuple[Op, float]] = {}

    def write(self, relpath: str, expected: bytes | None, new: bytes, parent: str | None = None) -> WriteResult:
        """Ersetzt eine Datei (``expected`` gegeben) oder legt sie neu an (``None``).

        Args:
            relpath: Datei relativ zum Vault.
            expected: Planungsstand oder ``None`` für eine neue Datei.
            new: Neue Bytes.
            parent: Eltern-Op (z. B. Resolve-Op) oder ``None``.

        Returns:
            Ergebnis; bei ``QUARANTINE`` steht ``new`` bereits in der Datei.

        Raises:
            ChangedBeforeWriteError: Datei weicht schon vorher ab (neu planen).
            FileBusyError: Windows: Datei ist von anderer Seite zum Schreiben offen.
        """
        main = self.root / relpath
        current = main.read_bytes() if self.fs.exists(main) else None
        if current != expected:
            raise ChangedBeforeWriteError(relpath)
        blobs = {"neu": new} if expected is None else {"vorher": expected, "neu": new}
        op = self.store.create("write", {"relpath": relpath, "create_only": expected is None}, blobs, parent)
        tmp, old = side_paths(main, op.id)
        self.fs.create_exclusive(tmp, new)
        op.set_state("TMP_READY")
        self.fs.point("write:tmp_ready")
        if expected is None:
            return self._install_new(op, main, tmp)
        try:
            with self.fs.write_lock(main):
                self.fs.rename_no_replace(main, old)
                op.set_state("DISPLACED")
                self.fs.point("write:displaced")
                return self._install_and_check(op, main, tmp, old, expected)
        except FileBusyError:
            self.fs.remove(tmp)  # eigene, nie installierte Temp-Datei (Ausnahme in L)
            op.set_state("ABORTED", grund="Datei gerade in Benutzung")
            op.release()
            raise

    def remove(self, relpath: str, expected: bytes, parent: str | None = None) -> WriteResult:
        """Entfernt eine Datei (z. B. eine aufgelöste Konfliktdatei) nur bei unverändertem Inhalt.

        Args:
            relpath: Datei relativ zum Vault.
            expected: Inhalt zum Planungszeitpunkt.
            parent: Eltern-Op oder ``None``.

        Returns:
            ``QUARANTINE`` (verdrängt, Löschung nach Prüfung) oder ``CONFLICTED``.

        Raises:
            ChangedBeforeWriteError: Datei weicht schon vorher ab.
        """
        main = self.root / relpath
        if not self.fs.exists(main) or main.read_bytes() != expected:
            raise ChangedBeforeWriteError(relpath)
        op = self.store.create("remove", {"relpath": relpath}, {"vorher": expected}, parent)
        _tmp, old = side_paths(main, op.id)
        with self.fs.write_lock(main):
            self.fs.rename_no_replace(main, old)
            op.set_state("DISPLACED")
            self.fs.point("remove:displaced")
            return self.save_displaced(op, main, old, expected, restore_to_main=True)

    def finish_due(self) -> list[WriteResult]:
        """Schließt alle Quarantänen ab, deren monotone Frist abgelaufen ist.

        Returns:
            Ergebnisse der abgeschlossenen Ops.
        """
        now = self.clock.monotonic()
        due = [op_id for op_id, (_op, deadline) in self._pending.items() if deadline <= now]
        return [self.finish(self._pending.pop(op_id)[0]) for op_id in due]

    def finish(self, op: Op) -> WriteResult:
        """Abschlussprüfung einer Op in Quarantäne (auch aus der Wiederherstellung).

        Args:
            op: Die Op (Zustand ``QUARANTINE``).

        Returns:
            ``DONE`` oder ``CONFLICTED``.
        """
        manifest, state = op.manifest, op.state()
        main = self.root / manifest["relpath"]
        _tmp, old = side_paths(main, op.id)
        result = WriteResult(op.id, "DONE")
        if manifest["art"] == "write":
            new = op.blob("neu", manifest["blobs"]["neu"])
            if not (self.fs.exists(main) and main.read_bytes() == new):
                self.ensure_visible(op, main, new, result)
        if self.fs.exists(old):
            if cf.sha1(old.read_bytes()) == state.get("d_sha1"):
                self.fs.remove(old)  # L: Bytes persistiert und gerade erneut geprüft
            else:
                result.conflicts.append(self.rel(cf.move_to_conflict(self.fs, main, old, self.clock)))
        if result.conflicts:
            result.state = "CONFLICTED"
        op.set_state(result.state, konflikte=result.conflicts)
        self.fs.point(f"{manifest['art']}:finished")
        self._record(manifest["relpath"])
        op.release()
        return result

    def _install_new(self, op: Op, main: Path, tmp: Path) -> WriteResult:
        """Create-only: Temp-Datei ohne Überschreiben installieren."""
        try:
            self.fs.rename_no_replace(tmp, main)
        except FileExistsError:  # inzwischen extern angelegt: nie überschreiben
            conflict = cf.move_to_conflict(self.fs, main, tmp, self.clock)
            op.set_state("CONFLICTED", konflikte=[self.rel(conflict)])
            op.release()
            return WriteResult(op.id, "CONFLICTED", [self.rel(conflict)])
        op.set_state("QUARANTINE")
        self.fs.point("write:installed")
        return self.quarantine(op)

    def _install_and_check(self, op: Op, main: Path, tmp: Path, old: Path, expected: bytes) -> WriteResult:
        """Ersetzen-Pfad ab Schritt 4: installieren, dann die verdrängte Fassung prüfen."""
        conflicts: list[str] = []
        try:
            self.fs.rename_no_replace(tmp, main)
            op.set_state("INSTALLED")
        except FileExistsError:  # P inzwischen extern belegt: N wird Konfliktdatei
            conflicts.append(self.own_conflict(op, main, cf.move_to_conflict(self.fs, main, tmp, self.clock)))
            op.set_state("INSTALLED", konflikte=conflicts)
        self.fs.point("write:installed")
        result = self.save_displaced(op, main, old, expected, restore_to_main=False)
        result.conflicts[:0] = conflicts
        return result

    def save_displaced(self, op: Op, main: Path, old: Path, expected: bytes, restore_to_main: bool) -> WriteResult:
        """Schritt 5: Kopie von ``D`` sichern und mit dem erwarteten Stand vergleichen.

        Args:
            op: Die Op.
            main: Hauptpfad.
            old: Verdrängte Datei ``D``.
            expected: Erwarteter Inhalt von ``D``.
            restore_to_main: ``True`` bei ``remove``: bei Abweichung wieder nach ``main``.

        Returns:
            ``QUARANTINE`` oder ``CONFLICTED``.
        """
        displaced = old.read_bytes()
        d_sha = op.add_blob("verdraengt", displaced)
        op.set_state("D_SAVED", d_sha1=d_sha)
        self.fs.point(f"{op.manifest['art']}:d_saved")
        if displaced == expected:
            op.set_state("QUARANTINE", d_sha1=d_sha)
            return self.quarantine(op)
        result = WriteResult(op.id, "CONFLICTED")
        new = op.blob("neu", op.manifest["blobs"]["neu"]) if not restore_to_main else None
        if new is not None and self.fs.exists(main) and main.read_bytes() == new:
            # Nur unsere eigene Version N weicht der fremden; eine fremde Datei in P bleibt.
            result.conflicts.append(self.own_conflict(op, main, cf.move_to_conflict(self.fs, main, main, self.clock)))
        try:
            self.fs.rename_no_replace(old, main)
        except FileExistsError:
            result.conflicts.append(self.rel(cf.move_to_conflict(self.fs, main, old, self.clock)))
        op.set_state("CONFLICTED", konflikte=result.conflicts)
        op.release()
        return result

    def ensure_visible(self, op: Op, main: Path, new: bytes, result: WriteResult) -> None:
        """Macht ``N`` als Konfliktdatei sichtbar, falls sie nirgends im Vault steht."""
        existing = cf.find_with_content(main, new)
        result.conflicts.append(self.own_conflict(op, main, existing or cf.create_from_bytes(
            self.fs, main, new, self.clock)))

    def own_conflict(self, op: Op, main: Path, path: Path) -> str:
        """Registriert eine eigene Konfliktdatei mit Sidecar (Basis ``E`` aus dieser Op).

        Args:
            op: Die Op (enthält ``vorher`` = ``E`` als Basis, sofern vorhanden).
            main: Hauptdatei.
            path: Die Konfliktdatei.

        Returns:
            Ihr Pfad relativ zum Vault.
        """
        rel = self.rel(path)
        cf.write_sidecar(self.data, rel, cf.sha1(path.read_bytes()), op.manifest["relpath"], op.id,
                         op.manifest["blobs"].get("vorher"))
        return rel

    def quarantine(self, op: Op) -> WriteResult:
        """Registriert die Op für den Quarantäne-Abschluss (monotone Frist)."""
        self._pending[op.id] = (op, self.clock.monotonic() + QUARANTINE_SECONDS)
        return WriteResult(op.id, "QUARANTINE")

    def rel(self, path: Path) -> str:
        """Pfad relativ zum Vault mit ``/``."""
        return path.relative_to(self.root).as_posix()

    def _record(self, relpath: str) -> None:
        """Historie ergänzen (Best Effort, Korrektheit hängt nicht davon ab)."""
        if self.history is None:
            return
        main = self.root / relpath
        try:
            self.history.record(relpath, main.read_bytes() if main.exists() else None)
        except OSError:
            pass
