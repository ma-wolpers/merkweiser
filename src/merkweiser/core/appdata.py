"""App-Daten-Layout je Vault (immer außerhalb des Vaults, je Gerät).

Layout (PLAN.md, „App-Daten-Layout“)::

    <app-daten>/vaults/<vault-id>/meta.json
    <app-daten>/vaults/<vault-id>/history/…
    <app-daten>/vaults/<vault-id>/ops/<op-id>/…
    <app-daten>/vaults/<vault-id>/conflicts/<sha1>.json
    <app-daten>/vaults/<vault-id>/instances/<instanz-id>

``vault-id`` = SHA-1 des normalisierten, aufgelösten Vault-Pfads. Zwei Vaults
mit gleichem relativen Dateipfad teilen dadurch nie Historie, Backups,
Sidecars oder Journale.

GRENZE: Wird der Vault-Ordner umbenannt oder verschoben, entsteht eine neue
ID. Die Historie beginnt leer (nur schwächere Vorschläge); alte Backups
bleiben unter der alten ID erhalten und sind über ``meta.json`` zuordenbar.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path


def vault_id(root: Path) -> str:
    """Berechnet die stabile ID eines Vault-Ordners auf diesem Gerät.

    Args:
        root: Vault-Ordner.

    Returns:
        SHA-1 (hex) von ``normcase(realpath(root))``.
    """
    normalized = os.path.normcase(os.path.realpath(root))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VaultData:
    """Verzeichnisse der technischen Zustände eines Vaults.

    Attributes:
        base: ``<app-daten>/vaults/<vault-id>``.
    """

    base: Path

    @property
    def history_dir(self) -> Path:
        """Beobachtungs-Historie."""
        return self.base / "history"

    @property
    def ops_dir(self) -> Path:
        """Op-Verzeichnisse (Transaktionen und Backups)."""
        return self.base / "ops"

    @property
    def conflicts_dir(self) -> Path:
        """Sidecars eigener Konflikte."""
        return self.base / "conflicts"

    @property
    def instances_dir(self) -> Path:
        """Heartbeats laufender Instanzen (nur Anzeige)."""
        return self.base / "instances"


def open_vault_data(app_data: Path, root: Path) -> VaultData:
    """Legt das Layout für einen Vault an (idempotent) und schreibt ``meta.json``.

    Args:
        app_data: App-Datenverzeichnis des Geräts (nie im Vault).
        root: Vault-Ordner.

    Returns:
        Die Verzeichnisse dieses Vaults.

    Raises:
        ValueError: wenn ``app_data`` im Vault liegt.
    """
    real_root, real_data = Path(os.path.realpath(root)), Path(os.path.realpath(app_data))
    if real_data == real_root or real_root in real_data.parents:
        raise ValueError("App-Daten dürfen nicht im Vault liegen")
    data = VaultData(app_data / "vaults" / vault_id(root))
    for folder in (data.history_dir, data.ops_dir, data.conflicts_dir, data.instances_dir):
        folder.mkdir(parents=True, exist_ok=True)
    meta = data.base / "meta.json"
    if not meta.exists():
        write_json_atomic(meta, {"vault_path": str(real_root)})
    return data


def write_json_atomic(path: Path, payload: object) -> None:
    """Schreibt JSON atomar (Temp-Datei + ``os.replace``) in den App-Daten.

    Nur für Merkweisers eigene Dateien außerhalb des Vaults; dort gibt es
    keine fremden Schreiber, ein einfacher atomarer Ersatz genügt.

    Args:
        path: Zieldatei.
        payload: JSON-serialisierbare Daten.
    """
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
