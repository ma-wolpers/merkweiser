"""Move-Protokoll: Todo auf ein anderes Datum verschieben (PLAN.md, „Move-Protokoll“).

Ein Move ist eine Eltern-Op ``move`` (Manifest: Quelle, Ziel, exakter
Quellblock ``B``, einzufügende Zeilen ``B'``). Reihenfolge: **erst Ziel, dann
Quelle**; die Quelle wird nur bei exaktem, eindeutigem Blocknachweis verändert.

Idempotenz ohne Todo-IDs: Ob ein Schritt erledigt ist, entscheidet allein der
Zustand der zugehörigen Unter-Op (``eltern_op`` = Move-Op), nie ein
Textvergleich. Eine Wiederholung hängt das Ziel deshalb nie ein zweites Mal an.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .document import parse_document
from .move_plan import MovePlan, insert_moved, plan_move, remove_moved_source
from .ops import Op, OpStore
from .patch import BlockTarget, StaleTargetError, Target, resolve_block
from .safe_write import ChangedBeforeWriteError, Writer

MAX_REPLANS = 3
DONE_LIKE = ("DONE", "QUARANTINE", "INSTALLED", "D_SAVED")


@dataclass(frozen=True)
class MoveResult:
    """Ergebnis eines Moves.

    Attributes:
        op_id: Die Move-Op.
        state: ``DONE`` oder ``INCOMPLETE`` (Todo steht ggf. in beiden Dateien).
        hint: Erklärung für die Oberfläche.
    """

    op_id: str
    state: str
    hint: str = ""


def move_todo(writer: Writer, store: OpStore, src_rel: str, target: Target, dst_rel: str,
              prefix: str) -> MoveResult:
    """Verschiebt ein Todo samt Teilbaum in eine andere Tagesdatei.

    Args:
        writer: Writer.
        store: Op-Store.
        src_rel: Quelldatei.
        target: Zeile des Todos.
        dst_rel: Zieldatei (aus ``vault.write_target``).
        prefix: Projekt-Präfix.

    Returns:
        Ergebnis; ``INCOMPLETE`` mit Hinweis, wenn die Quelle nicht nachweisbar ist.

    Raises:
        StaleTargetError: Todo nicht eindeutig auffindbar (nichts verändert).
    """
    source = parse_document((writer.root / src_rel).read_bytes(), prefix)
    plan = plan_move(source, target)
    op = store.create("move", {"src": src_rel, "dst": dst_rel, "block": list(plan.source_block.expected_lines),
                               "block_first": plan.source_block.first_line, "moved": list(plan.moved_lines),
                               "source_stem": Path(src_rel).stem}, {})
    return _continue(writer, store, op, prefix, force_source=False)


def resume_move(writer: Writer, store: OpStore, op_id: str, prefix: str, force_source: bool = False) -> MoveResult:
    """Setzt eine unvollständige Move-Op fort (Wiederherstellung oder „Erneut versuchen“).

    Args:
        writer: Writer.
        store: Op-Store.
        op_id: Die Move-Op.
        prefix: Projekt-Präfix.
        force_source: „Quelle trotzdem entfernen“: nur zulässig, wenn ``B'`` im
            Ziel genau einmal exakt vorkommt.

    Returns:
        Ergebnis.
    """
    op = store.open_for_recovery(op_id)
    if op is None:
        return MoveResult(op_id, "INCOMPLETE", "Vorgang wird gerade von einer anderen Instanz bearbeitet")
    return _continue(writer, store, op, prefix, force_source)


def find_pending_move(store: OpStore, src_rel: str, block: tuple[str, ...]) -> str | None:
    """Sucht eine unvollständige Move-Op für denselben Quellblock („vorhandenen Vorgang fortsetzen“).

    Args:
        store: Op-Store.
        src_rel: Quelldatei.
        block: Exakte Zeilen des Quellblocks.

    Returns:
        ``op-id`` oder ``None``.
    """
    for op_id in reversed(store.all_ids()):
        manifest, state = store.read(op_id)
        if manifest.get("art") == "move" and state.get("zustand") != "DONE" \
                and manifest["src"] == src_rel and tuple(manifest["block"]) == block:
            return op_id
    return None


def _continue(writer: Writer, store: OpStore, op: Op, prefix: str, force_source: bool) -> MoveResult:
    """Führt die noch offenen Schritte einer Move-Op aus."""
    m = op.manifest
    plan = MovePlan(BlockTarget(m["src"], m["block_first"], tuple(m["block"])), tuple(m["moved"]))
    same_file = m["src"] == m["dst"]
    target_state = _child_state(store, op.id, m["dst"])
    if target_state == "CONFLICTED":
        return _incomplete(op, "Zieldatei war gleichzeitig in Bearbeitung – verschobenes Todo steht in einer Konfliktdatei")
    if target_state not in DONE_LIKE:
        try:
            _apply(writer, op, m["dst"], prefix, "ziel", lambda doc: _insert(doc, plan, m, same_file))
        except StaleTargetError as exc:
            return _incomplete(op, f"Ziel nicht planbar: {exc}")
        if same_file:
            return _done(op)
    elif same_file:
        return _done(op)
    op.set_state("ZIEL_GESCHRIEBEN")
    if _child_state(store, op.id, m["src"]) in DONE_LIKE:
        return _done(op)
    if force_source and not _moved_once_in_target(writer, m, plan, prefix):
        return _incomplete(op, "Zielblock nicht eindeutig nachweisbar – Quelle bleibt unverändert")
    try:
        _apply(writer, op, m["src"], prefix, "quelle", lambda doc: remove_moved_source(doc, plan))
    except StaleTargetError:
        return _incomplete(op, "Todo steht jetzt in beiden Dateien (Quelle wurde inzwischen verändert)")
    return _done(op)


def _insert(doc, plan: MovePlan, manifest: dict, same_file: bool) -> bytes:
    """Ziel-Bytes: bei gleicher Datei erst entfernen, dann einfügen (ein einziger Patch)."""
    if same_file:
        doc = parse_document(remove_moved_source(doc, plan), "")
    return insert_moved(doc, plan, manifest["source_stem"])


def _apply(writer: Writer, op: Op, relpath: str, prefix: str, role: str, build) -> None:
    """Plant auf frischem Stand und schreibt; bei externer Änderung bis zu 3-mal neu planen.

    Raises:
        StaleTargetError: nach 3 Versuchen oder wenn die Planung scheitert.
    """
    path = writer.root / relpath
    for _attempt in range(MAX_REPLANS):
        before = path.read_bytes() if path.exists() else None
        after = build(parse_document(before or b"", prefix))
        try:
            writer.write(relpath, before, after, parent=op.id)
            op.set_state(op.state().get("zustand", "PREPARED"), **{f"{role}_geschrieben": True})
            return
        except ChangedBeforeWriteError:
            continue
    raise StaleTargetError(f"{relpath}: wiederholt extern geändert")


def _child_state(store: OpStore, op_id: str, relpath: str) -> str | None:
    """Zustand der jüngsten Unter-Op (``write``) dieser Move-Op für eine Datei."""
    state = None
    for child in store.all_ids():
        manifest, child_state = store.read(child)
        if manifest.get("eltern_op") == op_id and manifest.get("relpath") == relpath:
            state = child_state.get("zustand")
    return state


def _moved_once_in_target(writer: Writer, manifest: dict, plan: MovePlan, prefix: str) -> bool:
    """Zielnachweis für „Quelle trotzdem entfernen“: ``B'`` genau einmal exakt im Ziel."""
    path = writer.root / manifest["dst"]
    if not path.exists():
        return False
    doc = parse_document(path.read_bytes(), prefix)
    try:
        resolve_block(doc.source, BlockTarget(manifest["dst"], 0, plan.moved_lines), unique=True)
        return True
    except StaleTargetError:
        return False


def _done(op: Op) -> MoveResult:
    """Move abgeschlossen."""
    op.set_state("DONE")
    op.release()
    return MoveResult(op.id, "DONE")


def _incomplete(op: Op, hint: str) -> MoveResult:
    """Move unvollständig: sichtbar lassen, nichts automatisch bereinigen."""
    op.set_state("INCOMPLETE", hinweis=hint)
    op.release()
    return MoveResult(op.id, "INCOMPLETE", hint)


def recover_moves(writer: Writer, store: OpStore, prefix: str) -> list[MoveResult]:
    """Setzt nach einem Absturz unterbrochene Moves fort (nach der Tausch-Wiederherstellung).

    ``INCOMPLETE`` wartet bewusst auf eine Nutzerentscheidung und wird **nicht**
    automatisch fortgesetzt; abgeschlossene Moves werden übersprungen.

    Args:
        writer: Writer.
        store: Op-Store.
        prefix: Projekt-Präfix.

    Returns:
        Ergebnisse der fortgesetzten Moves.
    """
    results = []
    for op_id in store.all_ids():
        manifest, state = store.read(op_id)
        if manifest.get("art") != "move" or state.get("zustand") in ("DONE", "INCOMPLETE"):
            continue
        if not state:  # nie vorbereitet: nichts geschrieben
            continue
        results.append(resume_move(writer, store, op_id, prefix))
    return results
