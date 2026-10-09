"""Eigene Konfliktdateien und ihre Sidecars (PLAN.md, „Konflikte“).

* Name: ``<stem>.sync-conflict-<YYYYMMDD>-<HHMMSS>-MERKWEISER<8 base32>.md``,
  **exklusiv** angelegt; bei einer Kollision gibt es einen neuen Zufallsteil.
  Eine ältere Konfliktversion kann so nie überschrieben werden.
* Sidecar ``conflicts/<sha1(konflikt-relpath ohne Marker)>.json`` je
  Konfliktdatei (nicht je Hauptdatei): ``{konflikt_relpath, konflikt_sha1,
  haupt_relpath, base_op, base_sha1}``. Gültig nur, solange die Konfliktdatei
  mit ``konflikt_sha1`` existiert.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from pathlib import Path

from ..ports.clock import Clock
from .appdata import VaultData, write_json_atomic
from .fsops import FsOps
from .vault import DECIDED_SUFFIX, OWN_DEVICE_PREFIX, parse_conflict_name


def sha1(data: bytes) -> str:
    """SHA-1 (hex) von Bytes."""
    return hashlib.sha1(data).hexdigest()


def _candidate(main: Path, clock: Clock) -> Path:
    """Bildet einen neuen eigenen Konfliktnamen neben der Hauptdatei."""
    stem = main.name[:-3] if main.name.endswith(".md") else main.name
    stamp = clock.now().strftime("%Y%m%d-%H%M%S")
    suffix = base64.b32encode(secrets.token_bytes(5)).decode()
    return main.with_name(f"{stem}.sync-conflict-{stamp}-{OWN_DEVICE_PREFIX}{suffix}.md")


def create_from_bytes(fs: FsOps, main: Path, data: bytes, clock: Clock) -> Path:
    """Legt eine eigene Konfliktdatei mit ``data`` exklusiv an.

    Args:
        fs: Dateisystem-Primitive.
        main: Pfad der Hauptdatei.
        data: Inhalt.
        clock: Zeitquelle für den Namen.

    Returns:
        Pfad der neuen Konfliktdatei.
    """
    while True:
        path = _candidate(main, clock)
        try:
            fs.create_exclusive(path, data)
            fs.fsync_dir(path.parent)
            return path
        except FileExistsError:
            continue


def move_to_conflict(fs: FsOps, main: Path, source: Path, clock: Clock) -> Path:
    """Benennt eine Datei ohne Überschreiben in eine eigene Konfliktdatei um.

    Der Inhalt bleibt dabei im Vault (Löschinvariante: Rename an einen
    anderen Vault-Pfad).

    Args:
        fs: Dateisystem-Primitive.
        main: Pfad der Hauptdatei (bestimmt den Namen).
        source: Umzubenennende Datei.
        clock: Zeitquelle.

    Returns:
        Pfad der Konfliktdatei.
    """
    while True:
        path = _candidate(main, clock)
        try:
            fs.rename_no_replace(source, path)
            return path
        except FileExistsError:
            continue


def find_with_content(main: Path, data: bytes) -> Path | None:
    """Sucht eine eigene Konfliktdatei zu ``main`` mit genau diesem Inhalt.

    Verhindert Duplikate, wenn die Wiederherstellung einen Schritt wiederholt.

    Args:
        main: Hauptdatei.
        data: Gesuchter Inhalt.

    Returns:
        Pfad oder ``None``.
    """
    if not main.parent.exists():
        return None
    for candidate in main.parent.iterdir():
        parsed = parse_conflict_name(candidate.name)
        if parsed and parsed.main_relpath == main.name and parsed.own and candidate.read_bytes() == data:
            return candidate
    return None


def sidecar_key(conflict_relpath: str) -> str:
    """Schlüssel eines Sidecars: SHA-1 des Konfliktpfads **ohne** Marker.

    Args:
        conflict_relpath: Pfad der Konfliktdatei (mit oder ohne Marker).

    Returns:
        Hex-Schlüssel; bleibt stabil, wenn der Marker gesetzt wird.
    """
    return hashlib.sha1(conflict_relpath.replace(DECIDED_SUFFIX, "").encode("utf-8")).hexdigest()


def write_sidecar(data: VaultData, conflict_relpath: str, conflict_sha1: str, main_relpath: str,
                  base_op: str | None, base_sha1: str | None) -> None:
    """Schreibt das Sidecar einer eigenen Konfliktdatei.

    Args:
        data: App-Daten des Vaults.
        conflict_relpath: Konfliktdatei.
        conflict_sha1: Ihr Inhalts-Hash (Gültigkeitsbedingung).
        main_relpath: Hauptdatei.
        base_op: Op, deren Verzeichnis die Basis-Bytes enthält.
        base_sha1: Hash der Basis (``None``, wenn keine verlässliche Basis bekannt ist).
    """
    payload = {"konflikt_relpath": conflict_relpath, "konflikt_sha1": conflict_sha1,
               "haupt_relpath": main_relpath, "base_op": base_op, "base_sha1": base_sha1}
    write_json_atomic(data.conflicts_dir / f"{sidecar_key(conflict_relpath)}.json", payload)


def read_sidecar(data: VaultData, conflict_relpath: str, current_sha1: str) -> dict | None:
    """Liest ein Sidecar, aber nur, solange es zur aktuellen Konfliktdatei passt.

    Args:
        data: App-Daten.
        conflict_relpath: Konfliktdatei.
        current_sha1: Aktueller Hash ihres Inhalts.

    Returns:
        Das Sidecar oder ``None`` (fehlt oder veraltet).
    """
    path = data.conflicts_dir / f"{sidecar_key(conflict_relpath)}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if payload.get("konflikt_sha1") == current_sha1 else None
