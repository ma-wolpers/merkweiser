"""Move-Protokoll: Todo bzw. ganze Notiz auf ein anderes Datum verschieben (PLAN.md, „Move-Protokoll“).

Ein Move ist eine Eltern-Op ``move`` (Manifest: Quelle, Ziel, exakter
Quellblock ``B``, einzufügende Zeilen ``B'``). Reihenfolge: **erst Ziel, dann
Quelle**; die Quelle wird nur bei exaktem, eindeutigem Blocknachweis verändert.

Idempotenz ohne Todo-IDs: Ob ein Schritt erledigt ist, entscheidet allein der
Zustand der zugehörigen Unter-Op (``eltern_op`` = Move-Op), nie ein
Textvergleich. Eine Wiederholung hängt das Ziel deshalb nie ein zweites Mal an.

Determinismus: Die Zielnotiz (``ziel``, siehe ``move_plan.plan_target``) wird
**einmal** beim Anlegen der Op gewählt und im Manifest gespeichert. Neuplanen
und Wiederaufnahme finden sie nur exakt wieder und suchen nie neu; ist sie
verändert, bleibt der Move ``INCOMPLETE`` und die Quelle unberührt.

Alt-Ops (vor dem 2026-10-22, ohne ``mode``) laufen ohne Kopfzeile zu Ende:
``B'`` wird als eigene Notiz angehängt.
"""

from __future__ import annotations

from dataclasses import dataclass

from .document import parse_document
from .move_plan import (NEW, MovePlan, insert_moved, moved_chunks, plan_move, plan_note_move, plan_target,
                        remove_moved_source)
from .ops import Op, OpStore
from .patch import BlockTarget, StaleTargetError, Target, resolve_block
from .safe_write import Writer
from .step_ops import DONE_LIKE, child_state, run_step


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
    return _start(writer, store, src_rel, plan_move(source, target), dst_rel, prefix)


def move_note(writer: Writer, store: OpStore, src_rel: str, original: tuple[str, ...], dst_rel: str,
              prefix: str) -> MoveResult:
    """Verschiebt eine ganze Notiz in eine andere Tagesdatei (W7, „Notiz verschieben“).

    Gleiches Protokoll und gleiches Manifest wie ``move_todo`` im Modus ``notiz``:
    am Zieltag Zusammenführen mit genau einer gleichen Themennotiz, sonst neue
    Notiz; erst Ziel, dann Quelle; Wiederaufnahme über ``resume_move``.

    Args:
        writer: Writer.
        store: Op-Store.
        src_rel: Quelldatei.
        original: Inhaltszeilen der Notiz beim Öffnen.
        dst_rel: Zieldatei (aus ``vault.write_target``).
        prefix: Projekt-Präfix.

    Returns:
        Ergebnis; ``INCOMPLETE`` mit Hinweis, wenn die Quelle nicht nachweisbar ist.

    Raises:
        NoteNotFoundError: Notiz nicht eindeutig auffindbar (nichts verändert).
    """
    source = parse_document((writer.root / src_rel).read_bytes(), prefix)
    return _start(writer, store, src_rel, plan_note_move(source, src_rel, original), dst_rel, prefix)


def _start(writer: Writer, store: OpStore, src_rel: str, plan: MovePlan, dst_rel: str, prefix: str) -> MoveResult:
    """Wählt das Ziel einmalig, legt die Move-Op mit Manifest an und führt sie aus.

    Args:
        writer: Writer.
        store: Op-Store.
        src_rel: Quelldatei.
        plan: Geplanter Move (Todo oder ganze Notiz).
        dst_rel: Zieldatei.
        prefix: Projekt-Präfix.

    Returns:
        Ergebnis des Protokolls.
    """
    dst_path = writer.root / dst_rel
    ziel = plan_target(parse_document(dst_path.read_bytes() if dst_path.exists() else b"", prefix), plan)
    op = store.create("move", {"src": src_rel, "dst": dst_rel, "block": list(plan.source_block.expected_lines),
                               "block_first": plan.source_block.first_line, "moved": list(plan.moved_lines),
                               "mode": plan.mode, "topic": plan.topic, "key": plan.key, "ziel": ziel}, {})
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
    plan = _manifest_plan(m)
    same_file = m["src"] == m["dst"]
    target_state = child_state(store, op.id, m["dst"])
    if target_state == "CONFLICTED":
        return _incomplete(op, f"Zieldatei war gleichzeitig in Bearbeitung – {_what(plan)} steht in einer Konfliktdatei")
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
    if child_state(store, op.id, m["src"]) in DONE_LIKE:
        return _done(op)
    if force_source and not _moved_once_in_target(writer, m, plan, prefix):
        return _incomplete(op, "Zielblock nicht eindeutig nachweisbar – Quelle bleibt unverändert")
    try:
        _apply(writer, op, m["src"], prefix, "quelle", lambda doc: remove_moved_source(doc, plan))
    except StaleTargetError:
        return _incomplete(op, f"{_what(plan, capital=True)} steht jetzt in beiden Dateien "
                               "(Quelle wurde inzwischen verändert)")
    return _done(op)


def _what(plan: MovePlan, capital: bool = False) -> str:
    """Bezeichnung des verschobenen Inhalts für Hinweise.

    Args:
        plan: Der Plan.
        capital: Satzanfang.

    Returns:
        „verschobene Notiz“/„Notiz“ im Modus ``notiz``, sonst „verschobenes Todo“/„Todo“.
    """
    if plan.mode == "notiz":
        return "Notiz" if capital else "verschobene Notiz"
    return "Todo" if capital else "verschobenes Todo"


def _manifest_plan(manifest: dict) -> MovePlan:
    """Plan aus dem Manifest; Alt-Ops ohne ``mode`` gelten als „Todo, ohne Thema“.

    Args:
        manifest: Manifest der Move-Op.

    Returns:
        Der gespeicherte Plan.
    """
    block = BlockTarget(manifest["src"], manifest["block_first"], tuple(manifest["block"]))
    return MovePlan(block, tuple(manifest["moved"]), manifest.get("mode", "todo"), manifest.get("topic"),
                    manifest.get("key"))


def _insert(doc, plan: MovePlan, manifest: dict, same_file: bool) -> bytes:
    """Ziel-Bytes mit der gespeicherten Zielwahl; gleiche Datei (nur Alt-Ops): ein Patch.

    Args:
        doc: Frisch gelesenes Zieldokument.
        plan: Gespeicherter Plan.
        manifest: Manifest (``ziel`` fehlt bei Alt-Ops → neue Notiz).
        same_file: Quelle und Ziel sind dieselbe Datei.

    Returns:
        Neue Bytes der Zieldatei.

    Raises:
        StaleTargetError: Zielnotiz oder Quellblock nicht mehr exakt vorhanden.
    """
    if same_file:
        doc = parse_document(remove_moved_source(doc, plan), "")
    return insert_moved(doc, plan, manifest.get("ziel", NEW))


def _apply(writer: Writer, op: Op, relpath: str, prefix: str, role: str, build) -> None:
    """Plant auf frischem Stand und schreibt (``step_ops.run_step``, bis zu 3 Neuversuche).

    Args:
        writer: Writer.
        op: Die Move-Op.
        relpath: Ziel- bzw. Quelldatei.
        prefix: Projekt-Präfix.
        role: ``ziel`` oder ``quelle`` (Fortschrittsfeld ``<rolle>_geschrieben``).
        build: ``dokument → neue Bytes``.

    Raises:
        StaleTargetError: nach 3 Versuchen oder wenn die Planung scheitert.
    """
    run_step(writer, op, relpath, prefix, lambda doc, _raw: build(doc))
    op.set_state(op.state().get("zustand", "PREPARED"), **{f"{role}_geschrieben": True})


def _moved_once_in_target(writer: Writer, manifest: dict, plan: MovePlan, prefix: str) -> bool:
    """Zielnachweis für „Quelle trotzdem entfernen“: jedes eingefügte Teilstück genau einmal exakt im Ziel."""
    path = writer.root / manifest["dst"]
    if not path.exists():
        return False
    doc = parse_document(path.read_bytes(), prefix)
    try:
        for chunk in moved_chunks(plan, manifest.get("ziel", NEW)):
            resolve_block(doc.source, BlockTarget(manifest["dst"], 0, chunk), unique=True)
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
