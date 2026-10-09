"""Aufbewahrung der Op-Verzeichnisse (Backups) – PLAN.md, „Backups“.

Eine Op wird beim Start nur gelöscht, wenn sie

* abgeschlossen ist (``DONE``, ``ABORTED``, ``CONFLICTED`` oder bestätigt ``INTERRUPTED``),
* älter als die Aufbewahrung ist (Zeitpunkt aus dem Manifest),
* von keiner existierenden Konfliktdatei referenziert wird (``konflikt``,
  ``marker`` im Manifest oder ``base_op`` eines gültigen Sidecars),
* keinen unbestätigten Hinweis trägt.

Unvollständige Ops werden nie gelöscht, egal wie alt sie sind. Gelöscht wird
nur in den App-Daten, nie im Vault.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..ports.clock import Clock
from .appdata import VaultData
from .ops import FINAL_STATES, OpStore


def prune_ops(root: Path, data: VaultData, store: OpStore, clock: Clock, days: int) -> list[str]:
    """Löscht veraltete, nicht mehr benötigte Op-Verzeichnisse.

    Args:
        root: Vault-Ordner (für die Prüfung, ob Konfliktdateien existieren).
        data: App-Daten.
        store: Op-Store.
        clock: Zeitquelle.
        days: Aufbewahrung in Tagen.

    Returns:
        Gelöschte ``op-id``s.
    """
    limit = clock.now().astimezone(timezone.utc) - timedelta(days=days)
    protected = _sidecar_base_ops(data)
    removed = []
    for op_id in store.all_ids():
        manifest, state = store.read(op_id)
        if state.get("zustand") not in FINAL_STATES or (state.get("hinweis") and not state.get("bestaetigt")):
            continue
        created = manifest.get("erstellt")
        if not created or datetime.fromisoformat(created) > limit or op_id in protected:
            continue
        if any((root / manifest[key]).exists() for key in ("konflikt", "marker") if manifest.get(key)):
            continue
        shutil.rmtree(data.ops_dir / op_id)
        removed.append(op_id)
    return removed


def _sidecar_base_ops(data: VaultData) -> set[str]:
    """Ops, deren Bytes ein Sidecar einer noch existierenden Konfliktdatei als Basis nutzt."""
    protected = set()
    if not data.conflicts_dir.exists():
        return protected
    for path in data.conflicts_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("base_op"):
            protected.add(payload["base_op"])
    return protected


def prune_sidecars(root: Path, data: VaultData) -> int:
    """Entfernt Sidecars, deren Konfliktdatei (mit oder ohne Marker) nicht mehr existiert.

    Args:
        root: Vault-Ordner.
        data: App-Daten.

    Returns:
        Anzahl entfernter Sidecars.
    """
    if not data.conflicts_dir.exists():
        return 0
    removed = 0
    for path in data.conflicts_dir.glob("*.json"):
        conflict = json.loads(path.read_text(encoding="utf-8")).get("konflikt_relpath", "")
        marked = conflict[: -len(".md")] + "MWENTSCHIEDEN.md" if conflict.endswith(".md") else conflict
        if not ((root / conflict).exists() or (root / marked).exists()):
            path.unlink()
            removed += 1
    return removed
