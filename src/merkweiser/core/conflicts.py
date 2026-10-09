"""Konflikte: Erkennung, Auto-Merge und Rückgängig (PLAN.md, „Konflikte“).

Persistente Quelle ungelöster Konflikte sind **allein** die Konfliktdateien im
Vault. Je Hauptdatei wird nur die älteste Konfliktdatei bearbeitet (Kette);
nach einer Änderung der Hauptdatei wird neu bewertet.

Fallarten:

* ``AUTO``: konfliktfreier Merge mit bestandener Verlustprüfung (Union ohne
  Basis; diff3 mit gültigem Sidecar).
* ``MANUAL``: diff3-Hunks, verschachtelte (``nested``) oder schon entschiedene
  (``…MWENTSCHIEDEN``) Konfliktdateien, nicht unterstütztes Encoding.
* ``MAIN_DELETED``: Hauptdatei fehlt (nie automatisch).
* ``BUSY``: eine andere Instanz arbeitet an der Datei.

Auto-Merges laufen als Op ``automerge`` (Backup von Haupt- und Konfliktdatei
sowie Ergebnis) und sind über ``undo_automerge`` rückgängig zu machen.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import conflict_files as cf
from .merge.diff3 import merge3
from .merge.model import MergeResult
from .merge.union import merge2
from .merge.verify import verify
from .ops import OpStore
from .safe_write import ChangedBeforeWriteError, Writer
from .source import SourceText
from .vault import ConflictFile, VaultIndex


class CaseKind(Enum):
    """Art eines Konfliktfalls."""

    AUTO = "auto"
    MANUAL = "manual"
    MAIN_DELETED = "main_deleted"
    BUSY = "busy"


@dataclass(frozen=True)
class ConflictCase:
    """Ein Konfliktfall (eine Konfliktdatei gegen ihre Hauptdatei).

    Attributes:
        kind: Fallart.
        conflict: Die Konfliktdatei.
        main_bytes: Inhalt der Hauptdatei oder ``None`` (fehlt).
        conflict_bytes: Inhalt der Konfliktdatei.
        merge: Merge-Ergebnis (bei ``AUTO`` konfliktfrei) oder ``None``.
        reason: Kurzbegründung für manuelle Fälle.
    """

    kind: CaseKind
    conflict: ConflictFile
    main_bytes: bytes | None
    conflict_bytes: bytes
    merge: MergeResult | None
    reason: str = ""


def classify(root: Path, writer: Writer, index: VaultIndex, busy: set[str],
             manual: set[str] = frozenset()) -> list[ConflictCase]:
    """Bewertet je Hauptdatei die älteste Konfliktdatei.

    Args:
        root: Vault-Ordner.
        writer: Writer (für Sidecars und Basis-Bytes).
        index: Aktueller Scan.
        busy: Pfade, an denen eine andere Instanz arbeitet.
        manual: Konfliktdateien, die nie automatisch gemerged werden
            (``resolve.manual_only_paths``).

    Returns:
        Ein Fall je Hauptdatei mit Konflikten; ``MAIN_DELETED`` ggf. mehrfach
        (alle Versionen werden zur Auswahl angeboten).
    """
    groups: dict[str, list[ConflictFile]] = {}
    for conflict in index.conflicts:
        groups.setdefault(conflict.main_relpath, []).append(conflict)
    cases = []
    for main_rel, conflicts in sorted(groups.items()):
        conflicts.sort(key=lambda c: (c.stamp, c.relpath))
        main = root / main_rel
        if not main.exists():
            cases.extend(_case(CaseKind.MAIN_DELETED, c, None, root, "Hauptdatei fehlt") for c in conflicts)
            continue
        cases.append(_evaluate(root, writer, conflicts[0], main.read_bytes(), busy, manual))
    return cases


def _evaluate(root: Path, writer: Writer, conflict: ConflictFile, main_bytes: bytes, busy: set[str],
              manual: set[str]) -> ConflictCase:
    """Bewertet eine Konfliktdatei gegen die vorhandene Hauptdatei."""
    if conflict.relpath in busy or conflict.main_relpath in busy:
        return _case(CaseKind.BUSY, conflict, main_bytes, root, "in Bearbeitung durch andere Instanz")
    if conflict.nested:
        return _case(CaseKind.MANUAL, conflict, main_bytes, root, "verschachtelte Konfliktdatei")
    if conflict.relpath in manual:
        return _case(CaseKind.MANUAL, conflict, main_bytes, root, "frühere Entscheidung offen – bitte bestätigen")
    if conflict.decided:
        return _case(CaseKind.MANUAL, conflict, main_bytes, root, "Entscheidung unterbrochen – bitte erneut entscheiden")
    conflict_bytes = (root / conflict.relpath).read_bytes()
    main_src, conf_src = SourceText.from_bytes(main_bytes), SourceText.from_bytes(conflict_bytes)
    if not (main_src.writable and conf_src.writable):
        return ConflictCase(CaseKind.MANUAL, conflict, main_bytes, conflict_bytes, None, "Encoding nicht unterstützt")
    a, b = [l.text for l in main_src.lines], [l.text for l in conf_src.lines]
    base = _sidecar_base(writer, conflict, conflict_bytes)
    result = merge3(base, a, b) if base is not None else merge2(a, b)
    if not result.clean or verify(result, a, b, base):
        return ConflictCase(CaseKind.MANUAL, conflict, main_bytes, conflict_bytes, result, "widersprüchliche Änderungen")
    return ConflictCase(CaseKind.AUTO, conflict, main_bytes, conflict_bytes, result)


def _case(kind: CaseKind, conflict: ConflictFile, main_bytes: bytes | None, root: Path, reason: str) -> ConflictCase:
    """Fall ohne Merge-Berechnung."""
    return ConflictCase(kind, conflict, main_bytes, (root / conflict.relpath).read_bytes(), None, reason)


def _sidecar_base(writer: Writer, conflict: ConflictFile, conflict_bytes: bytes) -> list[str] | None:
    """Verlässliche Basis aus einem gültigen Sidecar (nur eigene Konflikte)."""
    if not conflict.own:
        return None
    sidecar = cf.read_sidecar(writer.data, conflict.relpath, cf.sha1(conflict_bytes))
    if not sidecar or not sidecar.get("base_sha1") or not sidecar.get("base_op"):
        return None
    blob = writer.data.ops_dir / sidecar["base_op"] / f"vorher-{sidecar['base_sha1']}"
    return [l.text for l in SourceText.from_bytes(blob.read_bytes()).lines] if blob.exists() else None


def render(lines: tuple[str, ...], like: bytes) -> bytes:
    """Setzt Zeilen mit dem Zeilenende-Stil einer Vorlage zu Bytes zusammen.

    Args:
        lines: Zeilen ohne Zeilenende.
        like: Vorlage (Hauptdatei): dominantes Zeilenende, Schluss-Umbruch, BOM.

    Returns:
        Bytes.
    """
    template = SourceText.from_bytes(like)
    eol = template.dominant_eol()
    final = bool(template.lines) and template.lines[-1].eol != ""
    text = eol.join(lines) + (eol if lines and final else "")
    prefix = b"\xef\xbb\xbf" if template.encoding.value == "utf-8-sig" else b""
    return prefix + text.encode("utf-8")


def auto_merge(writer: Writer, store: OpStore, case: ConflictCase) -> str | None:
    """Führt einen ``AUTO``-Fall aus: Backup-Op, Hauptdatei schreiben, Konfliktdatei entfernen.

    Idempotent: Ein Absturz zwischen den Schritten führt beim nächsten Scan zu
    einem Merge, dessen Ergebnis der Hauptdatei entspricht.

    Args:
        writer: Writer.
        store: Op-Store.
        case: Fall vom Typ ``AUTO``.

    Returns:
        ``op-id`` der Automerge-Op (für „Rückgängig“) oder ``None`` (Datei
        hat sich zwischenzeitlich geändert; nächster Scan bewertet neu).
    """
    assert case.kind is CaseKind.AUTO and case.merge and case.main_bytes is not None
    result = render(case.merge.lines(), case.main_bytes)
    op = store.create("automerge", {"relpath": case.conflict.main_relpath, "konflikt": case.conflict.relpath},
                      {"haupt": case.main_bytes, "konflikt": case.conflict_bytes, "ergebnis": result})
    try:
        if result != case.main_bytes:
            writer.write(case.conflict.main_relpath, case.main_bytes, result, parent=op.id)
        writer.remove(case.conflict.relpath, case.conflict_bytes, parent=op.id)
    except ChangedBeforeWriteError:
        op.set_state("ABORTED", grund="Datei während des Merges geändert")
        op.release()
        return None
    op.set_state("DONE")
    op.release()
    return op.id


def undo_automerge(writer: Writer, store: OpStore, op_id: str) -> None:
    """Macht einen Auto-Merge rückgängig: Hauptdatei zurück, Konfliktdatei wieder anlegen.

    Args:
        writer: Writer.
        store: Op-Store.
        op_id: Die Automerge-Op.

    Raises:
        ChangedBeforeWriteError: Die Hauptdatei wurde seitdem verändert.
    """
    op = store.open_for_recovery(op_id)
    if op is None:
        raise RuntimeError("Op ist gerade gesperrt")
    blobs, manifest = op.manifest["blobs"], op.manifest
    before, conflict = op.blob("haupt", blobs["haupt"]), op.blob("konflikt", blobs["konflikt"])
    result = op.blob("ergebnis", blobs["ergebnis"])
    op.release()
    writer.write(manifest["relpath"], result, before)
    target = writer.root / manifest["konflikt"]
    if target.exists():
        cf.create_from_bytes(writer.fs, writer.root / manifest["relpath"], conflict, writer.clock)
    else:
        writer.write(manifest["konflikt"], None, conflict)
