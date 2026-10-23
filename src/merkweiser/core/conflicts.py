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
sowie Ergebnis); Liste und „Rückgängig“ stehen in ``automerge_log``.

YAML-Kopf (W6, PLAN-SPAETERE-SCHRITTE.md S5): Hat mindestens eine Seite ein
Frontmatter, werden Kopf (``merge.frontmatter``) und Rumpf getrennt
zusammengeführt; ``ConflictCase.merge`` betrifft dann nur den Rumpf,
``ConflictCase.frontmatter`` den Kopf. ``AUTO`` nur, wenn beides sauber ist.
Ohne Kopf auf beiden Seiten ist alles wie zuvor. Ein Kopf ohne schließendes
``---`` macht den Fall ``MANUAL`` (nur ganze Fassungen wählbar).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import conflict_files as cf
from .merge.diff3 import merge3
from .merge.frontmatter import FmMerge, OPEN, merge_frontmatter, split
from .merge.model import MergeResult, OutLine
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
        merge: Merge-Ergebnis (bei ``AUTO`` konfliktfrei) oder ``None``; bei
            ``frontmatter`` nur für den Rumpf.
        reason: Kurzbegründung für manuelle Fälle.
        frontmatter: Kopf-Merge, falls eine Seite ein Frontmatter hat.
    """

    kind: CaseKind
    conflict: ConflictFile
    main_bytes: bytes | None
    conflict_bytes: bytes
    merge: MergeResult | None
    reason: str = ""
    frontmatter: FmMerge | None = None


def classify(root: Path, writer: Writer, index: VaultIndex, busy: set[str],
             manual: set[str] = frozenset(), renames: tuple[tuple[str, str], ...] = ()) -> list[ConflictCase]:
    """Bewertet je Hauptdatei die älteste Konfliktdatei.

    Args:
        root: Vault-Ordner.
        writer: Writer (für Sidecars und Basis-Bytes).
        index: Aktueller Scan.
        busy: Pfade, an denen eine andere Instanz arbeitet.
        manual: Konfliktdateien, die nie automatisch gemerged werden
            (``resolve.manual_only_paths``).
        renames: Bekannte Tätigkeits-Umbenennungen ``(alt, neu)`` für den Kopf-Merge.

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
        cases.append(_evaluate(root, writer, conflicts[0], main.read_bytes(), busy, manual, renames))
    return cases


def _evaluate(root: Path, writer: Writer, conflict: ConflictFile, main_bytes: bytes, busy: set[str],
              manual: set[str], renames: tuple[tuple[str, str], ...] = ()) -> ConflictCase:
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
    base_raw, origin = _sidecar_base(writer, conflict, conflict_bytes)
    undo = origin == cf.UNDO_ORIGIN
    (head_a, a), (head_b, b) = split(main_bytes), split(conflict_bytes)
    head_base, base = split(base_raw) if base_raw is not None else (None, None)
    fm = None
    if OPEN in (head_a.state, head_b.state):
        return ConflictCase(CaseKind.MANUAL, conflict, main_bytes, conflict_bytes, None,
                            "Kopfbereich ohne schließendes --- – bitte eine ganze Fassung wählen")
    if head_a.lines or head_b.lines:
        fm = merge_frontmatter(head_a, head_b, head_base, () if undo else renames, reverse=undo)
    else:  # kein Kopf auf beiden Seiten: ganze Dateien wie bisher
        a, b = list(head_a.texts), list(head_b.texts)
        base = list(head_base.texts) if head_base is not None else None
    result = merge3(base, a, b) if base is not None else merge2(a, b)
    if not merge_is_safe(result, a, b, base):
        return ConflictCase(CaseKind.MANUAL, conflict, main_bytes, conflict_bytes, result,
                            "widersprüchliche Änderungen", fm)
    if fm is not None and fm.conflicts:
        return ConflictCase(CaseKind.MANUAL, conflict, main_bytes, conflict_bytes, result, fm.reason(), fm)
    if undo:  # Rückgängig war nicht eindeutig: immer eine Entscheidung
        return ConflictCase(CaseKind.MANUAL, conflict, main_bytes, conflict_bytes, result,
                            "Rückgängig nicht eindeutig – bitte entscheiden", fm)
    return ConflictCase(CaseKind.AUTO, conflict, main_bytes, conflict_bytes, result, "", fm)


def merge_is_safe(result: MergeResult, a: list[str], b: list[str], base: list[str] | None) -> bool:
    """Eindeutige Sicherheitsentscheidung (Y9): sauber **und** ``verify`` meldet keine Verstöße.

    ``verify`` liefert die Liste der Verstöße; eine leere Liste heißt bestanden.
    """
    return result.clean and verify(result, a, b, base) == []


def merged_lines(case: ConflictCase, decisions: dict[int, str] | None = None,
                 body: tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Ergebniszeilen eines Falls: Kopf (mit Entscheidungen) + Rumpf.

    Args:
        case: Fall mit Merge.
        decisions: Entscheidungen je Kopf-Konflikt (``FmMerge.resolve``).
        body: Rumpfzeilen (Standard: ``case.merge.lines()``).

    Returns:
        Zeilen ohne Zeilenende.
    """
    body = case.merge.lines() if body is None else body
    fm = getattr(case, "frontmatter", None)
    head = fm.resolve(decisions) if fm is not None else ()
    return tuple(head) + tuple(body)


def _case(kind: CaseKind, conflict: ConflictFile, main_bytes: bytes | None, root: Path, reason: str) -> ConflictCase:
    """Fall ohne Merge-Berechnung."""
    return ConflictCase(kind, conflict, main_bytes, (root / conflict.relpath).read_bytes(), None, reason)


def _sidecar_base(writer: Writer, conflict: ConflictFile, conflict_bytes: bytes) -> tuple[bytes | None, str]:
    """Verlässliche Basis (Bytes) und Herkunft aus einem gültigen Sidecar (nur eigene Konflikte).

    Returns:
        ``(basis_oder_None, herkunft)``; Herkunft leer, wenn nicht angegeben.
    """
    if not conflict.own:
        return None, ""
    sidecar = cf.read_sidecar(writer.data, conflict.relpath, cf.sha1(conflict_bytes))
    if not sidecar:
        return None, ""
    origin = sidecar.get("herkunft", "")
    if not sidecar.get("base_sha1") or not sidecar.get("base_op"):
        return None, origin
    blob = writer.data.ops_dir / sidecar["base_op"] / f"vorher-{sidecar['base_sha1']}"
    return (blob.read_bytes() if blob.exists() else None), origin


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
    result = render(merged_lines(case), case.main_bytes)
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


class HunkPick(Enum):
    """Wahl für einen Konflikt-Hunk (PLAN.md, „Hunk-Optionen“)."""

    HAUPT = "haupt"
    KONFLIKT = "konflikt"
    BEIDE = "beide"
    BEARBEITET = "bearbeitet"


def apply_hunk_picks(merge: MergeResult, picks: list[tuple[HunkPick, str]]) -> tuple[str, ...]:
    """Setzt ein Merge-Ergebnis mit einer Wahl je Hunk zu Zeilen zusammen.

    Aufgelöste Zeilen bleiben, wie der Merge sie liefert. Je Hunk gilt:
    ``HAUPT`` → Zeilen aus A, ``KONFLIKT`` → Zeilen aus B, ``BEIDE`` → A, dann B
    (nur wenn ``Hunk.offers_both``), ``BEARBEITET`` → der mitgegebene Text
    (Zeilen durch ``\n`` getrennt; leerer Text entfernt den Bereich).

    Args:
        merge: Merge-Ergebnis mit Hunks.
        picks: Je Hunk in Reihenfolge ``(Wahl, Text)``; der Text zählt nur bei ``BEARBEITET``.

    Returns:
        Zeilen ohne Zeilenende (für ``render``).

    Raises:
        ValueError: Anzahl passt nicht zu den Hunks, oder ``BEIDE`` ist für
            einen Hunk nicht definiert.
    """
    if len(picks) != len(merge.hunks):
        raise ValueError(f"{len(picks)} Wahlen für {len(merge.hunks)} Abschnitte")
    lines: list[str] = []
    remaining = iter(picks)
    for segment in merge.segments:
        if isinstance(segment, OutLine):
            lines.append(segment.text)
            continue
        pick, text = next(remaining)
        if pick is HunkPick.HAUPT:
            lines += segment.a_lines
        elif pick is HunkPick.KONFLIKT:
            lines += segment.b_lines
        elif pick is HunkPick.BEIDE:
            if not segment.offers_both:
                raise ValueError("„Beide“ ist für diesen Abschnitt nicht definiert")
            lines += segment.a_lines + segment.b_lines
        else:
            lines += text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if text else []
    return tuple(lines)
