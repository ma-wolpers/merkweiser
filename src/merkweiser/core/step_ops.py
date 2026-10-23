"""Schrittprotokoll: mehrteilige Vorgänge als Eltern-Op mit Kinder-Schreibvorgängen (PLAN-SPAETERE-SCHRITTE.md, S0).

Verallgemeinert das Move-Muster (``move_exec``) für alle Vorgänge, die mehrere
Dateien ändern (Zeitbuchung, Umbenennen, Duplikatbereinigung, Rückgängig):

* Die **Eltern-Op** hält im Manifest **vor dem ersten Schreiben** den
  vollständigen Plan (Dateien, beim Planen gesehene Werte, Nutzerentscheidung).
* **Ein Schritt = genau ein atomarer** ``Writer.write`` bzw. ``Writer.remove``
  je Datei, als Kinder-Op (``eltern_op``). Alles, was eine Datei betrifft,
  steckt in einem Schreibvorgang; halbe Zustände innerhalb einer Datei gibt es
  nicht.
* Ob ein Schritt **erledigt** ist, entscheidet allein der Zustand der jüngsten
  Kinder-Op für diese Datei (``STEP_DONE``), **nie** ein Text- oder
  Wertvergleich. ``CONFLICTED`` zählt als erledigt: Merkweisers Fassung steht
  dann in einer eigenen Konfliktdatei mit Sidecar-Basis, und der Merge bringt
  sie ein.
* Die Wiederaufnahme läuft nach der Tausch-Wiederherstellung (``recover``);
  danach ist jede Kinder-Op eindeutig installiert oder nicht.
* ``retention.prune_ops`` schützt Kinder und referenzierte Ops nicht
  abgeschlossener Eltern (S6), damit „erledigt“ nie durch Aufräumen verloren geht.
"""

from __future__ import annotations

from collections.abc import Callable

from .document import Document, parse_document
from .ops import FINAL_STATES, Op, OpStore
from .patch import StaleTargetError
from .safe_write import ChangedBeforeWriteError, WriteResult, Writer

MAX_REPLANS = 3
DONE_LIKE = ("DONE", "QUARANTINE", "INSTALLED", "D_SAVED")
STEP_DONE = DONE_LIKE + ("CONFLICTED",)
REMOVE = object()
"""Rückgabe eines ``build``: Datei entfernen statt schreiben."""


def child_states(store: OpStore, parent_id: str) -> dict[str, str | None]:
    """Zustand der jüngsten Kinder-Op je Datei.

    Args:
        store: Op-Store.
        parent_id: Die Eltern-Op.

    Returns:
        ``relpath → zustand`` (jüngste Kinder-Op gewinnt, IDs sind chronologisch).
    """
    states: dict[str, str | None] = {}
    for child in store.all_ids():
        manifest, state = store.read(child)
        if manifest.get("eltern_op") == parent_id and manifest.get("relpath"):
            states[manifest["relpath"]] = state.get("zustand")
    return states


def child_state(store: OpStore, parent_id: str, relpath: str) -> str | None:
    """Zustand der jüngsten Kinder-Op einer Eltern-Op für eine Datei (oder ``None``).

    Args:
        store: Op-Store.
        parent_id: Die Eltern-Op.
        relpath: Datei relativ zum Vault.

    Returns:
        Zustand oder ``None``, wenn es für diese Datei keine Kinder-Op gibt.
    """
    return child_states(store, parent_id).get(relpath)


def run_step(writer: Writer, op: Op | None, relpath: str, prefix: str,
             build: Callable[[Document, bytes | None], bytes | object | None]) -> WriteResult | None:
    """Plant einen Schritt auf frischem Stand und schreibt ihn als Kinder-Op.

    Bei externer Änderung zwischen Lesen und Schreiben wird bis zu
    ``MAX_REPLANS``-mal neu geplant (wie beim Move).

    Args:
        writer: Writer.
        op: Die Eltern-Op (gesperrt) oder ``None`` für einen einzelnen Schreibvorgang ohne Vorgang.
        relpath: Datei relativ zum Vault.
        prefix: Projekt-Präfix (zum Parsen).
        build: ``(dokument, bytes_oder_None) → neue Bytes``; ``REMOVE`` entfernt
            die Datei, ``None`` bzw. unveränderte Bytes heißen „nichts zu tun“.
            Darf ``StaleTargetError`` werfen (Plan passt nicht mehr).

    Returns:
        Ergebnis des Schreibvorgangs oder ``None``, wenn nichts zu tun war.

    Raises:
        StaleTargetError: Planung gescheitert oder nach ``MAX_REPLANS`` Versuchen.
    """
    path = writer.root / relpath
    parent = op.id if op is not None else None
    for _attempt in range(MAX_REPLANS):
        before = path.read_bytes() if path.exists() else None
        after = build(parse_document(before or b"", prefix), before)
        try:
            if after is REMOVE:
                return None if before is None else writer.remove(relpath, before, parent=parent)
            if after is None or after == before:
                return None
            return writer.write(relpath, before, after, parent=parent)  # type: ignore[arg-type]
        except ChangedBeforeWriteError:
            continue
    raise StaleTargetError(f"{relpath}: wiederholt extern geändert")


def pending_ops(store: OpStore, kind: str) -> list[str]:
    """Eltern-Ops einer Art, die fortgesetzt werden müssen (Wiederaufnahme beim Start).

    Übersprungen werden abgeschlossene Ops, ``INCOMPLETE`` (wartet auf eine
    Nutzerentscheidung) und nie vorbereitete Ops (ohne ``state.json``: nichts
    geschrieben).

    Args:
        store: Op-Store.
        kind: Op-Art, z. B. ``zeitbuchung``.

    Returns:
        ``op-id``s, chronologisch.
    """
    result = []
    for op_id in store.all_ids():
        manifest, state = store.read(op_id)
        if manifest.get("art") == kind and state and state.get("zustand") not in FINAL_STATES | {"INCOMPLETE"}:
            result.append(op_id)
    return result


def finish(op: Op, **extra: object) -> None:
    """Schließt eine Eltern-Op ab (``DONE``) und gibt den Lock frei.

    Args:
        op: Die Eltern-Op.
        **extra: Zusätzliche Zustandsfelder (z. B. Hinweise).
    """
    op.set_state("DONE", **extra)
    op.release()


def incomplete(op: Op, hint: str, **extra: object) -> None:
    """Hält eine Eltern-Op sichtbar unvollständig fest (``INCOMPLETE``), ohne weiter zu schreiben.

    Args:
        op: Die Eltern-Op.
        hint: Erklärung für die Oberfläche („Unterbrochene Vorgänge“).
        **extra: Zusätzliche Zustandsfelder.
    """
    op.set_state("INCOMPLETE", hinweis=hint, **extra)
    op.release()
