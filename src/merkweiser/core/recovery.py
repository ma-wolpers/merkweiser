"""Wiederherstellung der Tausch-Ebene nach einem Absturz (PLAN.md, Tabelle Zeilen 1–11).

Läuft beim Start **vor** dem Scan, der Rekonstruktion der Konflikte und jedem
Auto-Merge. Entscheidet ausschließlich aus dem unveränderlichen Manifest und
dem aktuellen Plattenzustand (``P``, ``T``, ``D``); ``state.json`` ist nur ein
Hinweis. Jede Aktion unterliegt selbst den Invarianten L und I, deshalb ist die
Wiederherstellung idempotent: Ein Abbruch währenddessen wird beim nächsten
Start einfach fortgesetzt (Zeile 9).

Ops, deren Lock eine andere (auch suspendierte) Instanz hält, werden nicht
übernommen; ihre Pfade gelten als „in Bearbeitung“ (Zeile 10). Verwaiste
Hilfsdateien ohne bekannte Op werden nie gelöscht, sondern als eigene
Konfliktdateien sichtbar gemacht (Zeile 11).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import conflict_files as cf
from .ops import Op
from .safe_write import WriteResult, Writer, side_paths

_SIDE_FILE_RE = re.compile(r"^\.(?P<name>.+)\.mw-(?P<op>[0-9]{8}-[0-9]{6}-[A-Z2-7]{8})\.(?:tmp|old|partial)$")


@dataclass
class RecoveryReport:
    """Ergebnis eines Wiederherstellungslaufs.

    Attributes:
        results: Ergebnis je übernommener Op.
        busy_paths: Pfade, deren Op eine andere Instanz hält (keine Merges dafür).
        not_applied: Ops, deren Änderung nicht ausgeführt wurde (Hinweis „Wiederholen“).
        orphans: Verwaiste Hilfsdateien, die zu Konfliktdateien wurden.
    """

    results: list[WriteResult] = field(default_factory=list)
    busy_paths: set[str] = field(default_factory=set)
    not_applied: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)


def recover(writer: Writer) -> RecoveryReport:
    """Bringt alle unvollständigen Schreib- und Entfern-Ops in einen definierten Zustand.

    Ops in Quarantäne bekommen eine **neue** volle Quarantäne (monoton, ab jetzt).

    Args:
        writer: Writer des Vaults (liefert Store, Dateisystem und Protokollschritte).

    Returns:
        Bericht für die Oberfläche.
    """
    report = RecoveryReport()
    known: set[str] = set()
    for op_id in writer.store.all_ids():
        known.add(op_id)
        if writer.store.is_final(op_id):
            continue
        op = writer.store.open_for_recovery(op_id)
        if op is None:
            relpath = _manifest_relpath(writer, op_id)
            if relpath:
                report.busy_paths.add(relpath)
            continue
        if op.manifest.get("art") not in ("write", "remove"):
            op.release()  # übergeordnete Ops (resolve, move) behandelt ihre eigene Wiederherstellung
            continue
        result = _recover_op(writer, op, report)
        if result is not None:
            report.results.append(result)
    report.orphans = _rescue_orphans(writer, known)
    return report


def _recover_op(writer: Writer, op: Op, report: RecoveryReport) -> WriteResult | None:
    """Wendet die Zustandstabelle auf eine Op an.

    Args:
        writer: Writer.
        op: Übernommene Op.
        report: Bericht (wird ergänzt).

    Returns:
        Ergebnis oder ``None`` (Op hat noch keinen Zustand und wurde abgebrochen).
    """
    manifest = op.manifest
    main = writer.root / manifest["relpath"]
    tmp, old = side_paths(main, op.id)
    blobs = manifest["blobs"]
    expected = op.blob("vorher", blobs["vorher"]) if "vorher" in blobs else None
    if not op.state():  # Zeile 1: nie vorbereitet → Vault garantiert unberührt
        return _abort(op, tmp, writer, report)
    if manifest["art"] == "remove":
        return _recover_remove(writer, op, main, old, expected)
    new = op.blob("neu", blobs["neu"])
    if writer.fs.exists(old):
        return _recover_displaced(writer, op, main, tmp, old, expected, new)
    if manifest.get("create_only"):
        return _recover_create(writer, op, main, tmp, new, report)
    if op.state().get("zustand") in ("PREPARED", "TMP_READY"):  # Zeile 2: nie verdrängt
        return _abort(op, tmp, writer, report)
    _drop_tmp(writer, tmp, new)
    return _restart_quarantine(writer, op)  # D schon behandelt: Abschluss prüft P erneut


def _recover_displaced(writer: Writer, op: Op, main: Path, tmp: Path, old: Path,
                       expected: bytes | None, new: bytes) -> WriteResult:
    """Zeilen 3–6: ``D`` existiert noch."""
    if not writer.fs.exists(main):
        if old.read_bytes() == expected:  # Zeile 3: Absturz zwischen Wegbenennen und Installieren
            _install(writer, tmp, main, new)
            op.set_state("INSTALLED")
        else:  # fremder Stand gewinnt, N wird sichtbar
            writer.fs.rename_no_replace(old, main)
            return _conflicted(writer, op, main, tmp, new)
    elif main.read_bytes() != new:  # Zeile 4: P extern belegt
        result = _conflicted(writer, op, main, tmp, new, finish=False)
        if old.read_bytes() == expected:
            writer.fs.remove(old)  # L: E ist als „vorher“ persistiert und gerade geprüft
        else:
            result.conflicts.append(writer.rel(cf.move_to_conflict(writer.fs, main, old, writer.clock)))
        op.set_state("CONFLICTED", konflikte=result.conflicts)
        op.release()
        return result
    _drop_tmp(writer, tmp, new)
    return writer.save_displaced(op, main, old, expected or b"", restore_to_main=False)  # Zeilen 5/6


def _recover_create(writer: Writer, op: Op, main: Path, tmp: Path, new: bytes,
                    report: RecoveryReport) -> WriteResult | None:
    """Zeile 7a: Create-only."""
    if writer.fs.exists(main):
        if main.read_bytes() == new:
            _drop_tmp(writer, tmp, new)
            return _restart_quarantine(writer, op)
        if writer.fs.exists(tmp) and tmp.read_bytes() == new:
            return _conflicted(writer, op, main, tmp, new)
        return _abort(op, tmp, writer, report)
    if not writer.fs.exists(tmp):
        return _abort(op, tmp, writer, report)
    _install(writer, tmp, main, new)
    return _restart_quarantine(writer, op)


def _recover_remove(writer: Writer, op: Op, main: Path, old: Path, expected: bytes | None) -> WriteResult:
    """Zeile 8: ``safe_remove``."""
    if writer.fs.exists(old):
        return writer.save_displaced(op, main, old, expected or b"", restore_to_main=True)
    if writer.fs.exists(main) and main.read_bytes() == expected and op.state().get("zustand") == "PREPARED":
        op.set_state("ABORTED", grund="nicht ausgeführt")
        op.release()
        return WriteResult(op.id, "ABORTED")
    op.set_state("DONE")  # D wurde bereits geprüft und entfernt
    op.release()
    return WriteResult(op.id, "DONE")


def _install(writer: Writer, tmp: Path, main: Path, new: bytes) -> None:
    """Installiert ``N`` ohne Überschreiben (aus ``T`` oder neu aus dem Op-Verzeichnis)."""
    if not (writer.fs.exists(tmp) and tmp.read_bytes() == new):
        if writer.fs.exists(tmp):
            writer.fs.remove(tmp)  # unvollständige eigene Temp-Datei (Ausnahme in L)
        writer.fs.create_exclusive(tmp, new)
    writer.fs.rename_no_replace(tmp, main)


def _conflicted(writer: Writer, op: Op, main: Path, tmp: Path, new: bytes, finish: bool = True) -> WriteResult:
    """Macht ``N`` sichtbar (aus ``T``, vorhandener Konfliktdatei oder neu)."""
    result = WriteResult(op.id, "CONFLICTED")
    if writer.fs.exists(tmp) and tmp.read_bytes() == new and cf.find_with_content(main, new) is None:
        result.conflicts.append(writer.own_conflict(op, main, cf.move_to_conflict(writer.fs, main, tmp, writer.clock)))
    else:
        _drop_tmp(writer, tmp, new)
        writer.ensure_visible(op, main, new, result)
    if finish:
        op.set_state("CONFLICTED", konflikte=result.conflicts)
        op.release()
    return result


def _drop_tmp(writer: Writer, tmp: Path, new: bytes) -> None:
    """Entfernt die eigene Temp-Datei, deren Ziel-Bytes ``N`` persistiert sind."""
    if writer.fs.exists(tmp):
        writer.fs.remove(tmp)


def _restart_quarantine(writer: Writer, op: Op) -> WriteResult:
    """Beginnt die Quarantäne neu (nie Wanduhr-Vergleiche über Neustarts)."""
    op.set_state("QUARANTINE", **{k: v for k, v in op.state().items() if k == "d_sha1"})
    return writer.quarantine(op)


def _abort(op: Op, tmp: Path, writer: Writer, report: RecoveryReport) -> WriteResult:
    """Zeilen 1/2: Änderung nicht ausgeführt; ``N`` bleibt im Op-Verzeichnis (Wiederholen)."""
    if writer.fs.exists(tmp):
        writer.fs.remove(tmp)
    report.not_applied.append(op.id)
    op.set_state("ABORTED", grund="nicht ausgeführt")
    op.release()
    return WriteResult(op.id, "ABORTED")


def _manifest_relpath(writer: Writer, op_id: str) -> str | None:
    """Liest den Pfad einer fremd gesperrten Op aus ihrem Manifest (ohne Lock)."""
    import json

    path = writer.data.ops_dir / op_id / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")).get("relpath") if path.exists() else None


def _rescue_orphans(writer: Writer, known: set[str]) -> list[str]:
    """Zeile 11: verwaiste Hilfsdateien werden zu Konfliktdateien (nie gelöscht).

    Args:
        writer: Writer.
        known: Alle bekannten ``op-id``s.

    Returns:
        Neue Konfliktdateien (relativ zum Vault).
    """
    rescued = []
    for side in sorted(writer.root.rglob(".*.mw-*")):
        match = _SIDE_FILE_RE.match(side.name)
        hidden_folder = any(part.startswith(".") for part in side.relative_to(writer.root).parts[:-1])
        if not match or hidden_folder or (match["op"] in known and not writer.store.is_final(match["op"])):
            continue
        main = side.with_name(match["name"])
        rescued.append(writer.rel(cf.move_to_conflict(writer.fs, main, side, writer.clock)))
    return rescued
