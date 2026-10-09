"""Op-Verzeichnisse: das einzige Transaktionsmodell (Write-Ahead, Backups, Journal).

Layout ``vaults/<vault-id>/ops/<op-id>/`` (PLAN.md, „App-Daten-Layout“):

* ``manifest.json``: **nur** der ursprüngliche Plan und geprüfte Referenzen
  (Art, Pfade, Hashes, Eltern-Op); einmal geschrieben, danach unverändert.
* ``state.json``: **einzige** Quelle des Fortschritts ``{zustand, epoche, …}``.
  Fehlt sie, wurde die Op nie vorbereitet und der Vault ist unberührt.
* ``<rolle>-<sha1>``: persistierte, nach dem Schreiben erneut geprüfte Bytes.
* ``lock``: Betriebssystem-Lock (POSIX ``flock``, Windows ``msvcrt.locking``).
  Er wird nur durch Unlock oder Prozessende frei; ein **suspendierter** Prozess
  behält ihn. Es gibt keine Übernahme nach Zeitablauf.
* Fencing: Wer eine Op übernimmt, erhöht ``epoche``. Vor jedem Zustandswechsel
  prüft der Ausführende Lock und Epoche und bricht sonst ohne Wirkung ab.

Nach Abschluss ist das Op-Verzeichnis zugleich das Backup.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
from datetime import timezone
from pathlib import Path
from typing import BinaryIO

from ..ports.clock import Clock
from .appdata import VaultData, write_json_atomic
from .fsops import FsOps

FINAL_STATES = frozenset({"DONE", "ABORTED", "CONFLICTED", "INTERRUPTED"})


class FencedError(Exception):
    """Die Op wurde inzwischen von einer anderen Instanz übernommen."""


class Op:
    """Eine geöffnete, gesperrte Op.

    Args:
        folder: Op-Verzeichnis.
        lock: Offene Lock-Datei (hält den Betriebssystem-Lock).
        epoch: Epoche, unter der diese Instanz handeln darf.
        fs: Dateisystem-Primitive.
    """

    def __init__(self, folder: Path, lock: BinaryIO, epoch: int, fs: FsOps) -> None:
        self.folder = folder
        self._lock = lock
        self.epoch = epoch
        self._fs = fs
        self.manifest: dict = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    @property
    def id(self) -> str:
        """Die ``op-id``."""
        return self.folder.name

    def state(self) -> dict:
        """Liest den aktuellen Zustand (leer, falls ``state.json`` fehlt)."""
        path = self.folder / "state.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def set_state(self, zustand: str, **extra: object) -> None:
        """Setzt den Zustand atomar, nach Prüfung der Epoche (Fencing).

        Args:
            zustand: Neuer Zustand.
            **extra: Weitere Felder (werden zusammengeführt).

        Raises:
            FencedError: Epoche in ``state.json`` ist nicht mehr die eigene.
        """
        current = self.state()
        if current and current.get("epoche") != self.epoch:
            raise FencedError(self.id)
        current.update(extra, zustand=zustand, epoche=self.epoch)
        write_json_atomic(self.folder / "state.json", current)

    def add_blob(self, role: str, data: bytes) -> str:
        """Persistiert Bytes exklusiv und prüft sie durch erneutes Lesen.

        Args:
            role: Rolle, z. B. ``vorher``, ``neu``, ``verdraengt``.
            data: Inhalt.

        Returns:
            SHA-1 des Inhalts.

        Raises:
            OSError: wenn die Prüfung fehlschlägt (Abbruch vor jeder Vault-Änderung).
        """
        return persist_blob(self.folder, self._fs, role, data)

    def blob(self, role: str, sha: str) -> bytes:
        """Liest persistierte Bytes einer Rolle.

        Args:
            role: Rolle.
            sha: Erwarteter SHA-1.

        Returns:
            Die Bytes.
        """
        return (self.folder / f"{role}-{sha}").read_bytes()

    def release(self) -> None:
        """Gibt den Lock frei (Ende der Ausführung in dieser Instanz)."""
        self._lock.close()


class OpStore:
    """Legt Ops an und öffnet sie für Ausführung oder Wiederherstellung.

    Args:
        data: App-Daten des Vaults.
        clock: Zeitquelle (für ``op-id`` und Zeitstempel).
        fs: Dateisystem-Primitive.
    """

    def __init__(self, data: VaultData, clock: Clock, fs: FsOps) -> None:
        self._dir = data.ops_dir
        self._clock = clock
        self._fs = fs

    def create(self, kind: str, plan: dict, blobs: dict[str, bytes], parent: str | None = None) -> Op:
        """Legt eine Op an: Verzeichnis, Lock, Bytes, Manifest, dann ``PREPARED``.

        Erst danach darf der Vault berührt werden (Write-Ahead).

        Args:
            kind: Art (``write``, ``remove``, ``resolve``, ``move`` …).
            plan: Plan-Felder für das Manifest (nur JSON-Werte).
            blobs: Zu persistierende Bytes je Rolle.
            parent: ``op-id`` der Eltern-Op oder ``None``.

        Returns:
            Die gesperrte Op im Zustand ``PREPARED``.
        """
        folder = self._new_folder()
        lock = _acquire(folder)
        assert lock is not None  # frisch angelegtes, eigenes Verzeichnis
        hashes = {role: persist_blob(folder, self._fs, role, data) for role, data in blobs.items()}
        manifest = {"op_id": folder.name, "art": kind, "eltern_op": parent, "blobs": hashes,
                    "erstellt": self._clock.now().astimezone(timezone.utc).isoformat(), **plan}
        write_json_atomic(folder / "manifest.json", manifest)
        self._fs.point(f"{kind}:before_prepared")
        created = Op(folder, lock, 1, self._fs)
        created.set_state("PREPARED")
        self._fs.point(f"{kind}:prepared")
        return created

    def open_for_recovery(self, op_id: str) -> Op | None:
        """Übernimmt eine unvollständige Op (nicht blockierend).

        Args:
            op_id: Die Op.

        Returns:
            Die Op mit erhöhter Epoche, oder ``None``, wenn eine andere
            (auch suspendierte) Instanz den Lock hält oder kein Manifest existiert.
        """
        folder = self._dir / op_id
        lock = _acquire(folder)
        if lock is None:
            return None
        if not (folder / "manifest.json").exists():
            lock.close()
            return None
        epoch = int(json.loads((folder / "state.json").read_text(encoding="utf-8")).get("epoche", 0)) + 1 \
            if (folder / "state.json").exists() else 1
        op = Op(folder, lock, epoch, self._fs)
        if (folder / "state.json").exists():
            state = op.state()
            state["epoche"] = epoch
            write_json_atomic(folder / "state.json", state)
        return op

    def all_ids(self) -> list[str]:
        """Alle ``op-id``s, chronologisch (die ID beginnt mit dem Zeitstempel)."""
        return sorted(p.name for p in self._dir.iterdir() if p.is_dir()) if self._dir.exists() else []

    def read(self, op_id: str) -> tuple[dict, dict]:
        """Liest Manifest und Zustand ohne Lock (nur zur Anzeige und Auswertung).

        Args:
            op_id: Die Op.

        Returns:
            ``(manifest, state)``; fehlende Dateien ergeben leere Dicts.
        """
        folder = self._dir / op_id
        load = lambda name: json.loads((folder / name).read_text(encoding="utf-8")) if (folder / name).exists() else {}
        return load("manifest.json"), load("state.json")

    def is_final(self, op_id: str) -> bool:
        """``True``, wenn die Op abgeschlossen ist (oder nie vorbereitet wurde: dann ``False``)."""
        path = self._dir / op_id / "state.json"
        return path.exists() and json.loads(path.read_text(encoding="utf-8")).get("zustand") in FINAL_STATES

    def _new_folder(self) -> Path:
        """Legt ein neues Op-Verzeichnis exklusiv an (Kollision → neuer Zufallsteil)."""
        self._dir.mkdir(parents=True, exist_ok=True)
        stamp = self._clock.now().strftime("%Y%m%d-%H%M%S")
        while True:
            suffix = base64.b32encode(secrets.token_bytes(5)).decode()
            folder = self._dir / f"{stamp}-{suffix}"
            try:
                folder.mkdir()
                return folder
            except FileExistsError:
                continue


def persist_blob(folder: Path, fs: FsOps, role: str, data: bytes) -> str:
    """Persistiert Bytes exklusiv in einem Op-Verzeichnis und prüft sie erneut.

    Args:
        folder: Op-Verzeichnis.
        fs: Dateisystem-Primitive.
        role: Rolle, z. B. ``vorher``, ``neu``, ``verdraengt``.
        data: Inhalt.

    Returns:
        SHA-1 des Inhalts.

    Raises:
        OSError: wenn die Prüfung fehlschlägt (dann wird nichts im Vault geändert).
    """
    sha = hashlib.sha1(data).hexdigest()
    path = folder / f"{role}-{sha}"
    if not path.exists():
        fs.create_exclusive(path, data)
    if hashlib.sha1(path.read_bytes()).hexdigest() != sha:
        raise OSError(f"Backup-Prüfung fehlgeschlagen: {path.name}")
    return sha


def _acquire(folder: Path) -> BinaryIO | None:
    """Versucht den Betriebssystem-Lock einer Op nicht blockierend zu erwerben.

    Args:
        folder: Op-Verzeichnis.

    Returns:
        Offene Lock-Datei (hält den Lock) oder ``None``, wenn er vergeben ist.
    """
    handle = open(folder / "lock", "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle
