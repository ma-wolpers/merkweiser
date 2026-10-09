"""Manuelle Konfliktauflösung als Resolve-Op mit Vault-Marker (PLAN.md, Garantien 4/5).

Ablauf: PREPARED (Entscheidung und Bytes ``M0``, ``C0``, ``R`` persistiert) →
MARKED (Konfliktdatei bekommt ``…MWENTSCHIEDEN``, Inhalt bleibt im Vault) →
MAIN_WRITTEN (``safe_write`` der Hauptdatei) → DONE (``safe_remove`` der
markierten Datei, nur bei unverändertem Inhalt).

Eine einmal getroffene Entscheidung wird nie still rückgängig gemacht: Mit
App-Daten setzt ``recover_resolves`` sie fort (Tabelle a–j); ohne App-Daten
verhindert der Marker jeden Auto-Merge und es wird erneut gefragt (Fall k).
Resolve-Ops verfallen nicht wegen eines abweichenden Hashes; sie bleiben
``INTERRUPTED`` mit Hinweis, bis der Konflikt gelöst oder der Hinweis
bestätigt ist.
"""

from __future__ import annotations

from dataclasses import dataclass
from .ops import Op, OpStore
from .safe_write import ChangedBeforeWriteError, Writer
from .vault import DECIDED_SUFFIX, parse_conflict_name


@dataclass(frozen=True)
class ResolveOutcome:
    """Ergebnis einer Auflösung.

    Attributes:
        op_id: Die Resolve-Op.
        state: ``DONE`` oder ``INTERRUPTED``.
        hint: Hinweis für die Oberfläche (leer bei ``DONE``).
    """

    op_id: str
    state: str
    hint: str = ""


def marked_name(conflict_relpath: str) -> str:
    """Pfad der Konfliktdatei mit Marker ``…MWENTSCHIEDEN`` an der Gerätekennung.

    Args:
        conflict_relpath: Konfliktdatei ohne Marker.

    Returns:
        Pfad mit Marker (Hauptdatei-Zuordnung bleibt gleich).
    """
    parsed = parse_conflict_name(conflict_relpath)
    assert parsed is not None and not parsed.decided
    head = conflict_relpath[: -len(".md")]
    return f"{head}{DECIDED_SUFFIX}.md"


def resolve(writer: Writer, store: OpStore, main_rel: str, main_before: bytes | None,
            conflict_rel: str, conflict_before: bytes, result: bytes, decision: str,
            manual_only: tuple[str, ...] = ()) -> ResolveOutcome:
    """Wendet eine explizite Konfliktentscheidung an.

    Args:
        writer: Writer.
        store: Op-Store.
        main_rel: Hauptdatei.
        main_before: Angezeigter Stand der Hauptdatei (``None`` bei ``MAIN_DELETED``).
        conflict_rel: Konfliktdatei (ohne Marker).
        conflict_before: Angezeigter Stand der Konfliktdatei.
        result: Ergebnis ``R`` der Entscheidung.
        decision: Lesbare Beschreibung der Wahl (für Hinweise nach Unterbrechung).
        manual_only: Weitere Konfliktdateien, die danach nur manuell aufgelöst
            werden dürfen (übrige Versionen bei ``MAIN_DELETED``).

    Returns:
        Ergebnis; ``INTERRUPTED`` bedeutet: neu anzeigen, nichts verloren.
    """
    blobs = {"konflikt": conflict_before, "ergebnis": result}
    if main_before is not None:
        blobs["haupt"] = main_before
    op = store.create("resolve", {"relpath": main_rel, "konflikt": conflict_rel, "marker": marked_name(conflict_rel),
                                  "entscheidung": decision, "nur_manuell": list(manual_only)}, blobs)
    return _from_mark(writer, op)


def _from_mark(writer: Writer, op: Op) -> ResolveOutcome:
    """Schritt 3: Marker setzen und prüfen, dann weiter mit Schritt 4."""
    m = op.manifest
    conflict, marked = writer.root / m["konflikt"], writer.root / m["marker"]
    c0 = op.blob("konflikt", m["blobs"]["konflikt"])
    if not (conflict.exists() and conflict.read_bytes() == c0):
        return _interrupt(op, "Konfliktdatei hat sich geändert oder fehlt")
    writer.fs.rename_no_replace(conflict, marked)
    if marked.read_bytes() != c0:
        writer.fs.rename_no_replace(marked, conflict)
        return _interrupt(op, "Konfliktdatei hat sich während der Markierung geändert")
    op.set_state("MARKED")
    writer.fs.point("resolve:marked")
    return _from_write(writer, op)


def _from_write(writer: Writer, op: Op) -> ResolveOutcome:
    """Schritt 4: Hauptdatei schreiben (``M0`` → ``R``)."""
    m = op.manifest
    before = op.blob("haupt", m["blobs"]["haupt"]) if "haupt" in m["blobs"] else None
    result = op.blob("ergebnis", m["blobs"]["ergebnis"])
    try:
        written = writer.write(m["relpath"], before, result, parent=op.id)
    except ChangedBeforeWriteError:
        _unmark(writer, op)
        return _interrupt(op, "Hauptdatei wurde inzwischen geändert – bitte erneut entscheiden")
    if written.state == "CONFLICTED":
        return _interrupt(op, "Gleichzeitige Änderung beim Schreiben – deine Wahl ist als Vorschlag vorausgewählt")
    op.set_state("MAIN_WRITTEN", unter_ops={"haupt": written.op_id})
    writer.fs.point("resolve:main_written")
    return _from_remove(writer, op)


def _from_remove(writer: Writer, op: Op) -> ResolveOutcome:
    """Schritt 5: markierte Konfliktdatei nur bei unverändertem Inhalt entfernen."""
    m = op.manifest
    c0 = op.blob("konflikt", m["blobs"]["konflikt"])
    marked = writer.root / m["marker"]
    if marked.exists():
        try:
            removed = writer.remove(m["marker"], c0, parent=op.id)
        except ChangedBeforeWriteError:
            return _done(op, "Konfliktdatei wurde nach deiner Entscheidung geändert – bleibt als Konflikt")
        if removed.state == "CONFLICTED":
            return _done(op, "Konfliktdatei wurde nach deiner Entscheidung geändert – bleibt als Konflikt")
    return _done(op, "")


def recover_resolves(writer: Writer, store: OpStore) -> list[ResolveOutcome]:
    """Setzt unvollständige Resolve-Ops fort und räumt Automerge-Ops auf (Tabelle a–j).

    Muss **nach** ``recovery.recover`` (Tausch-Ebene) und **vor** Scan bzw.
    Auto-Merge laufen.

    Args:
        writer: Writer.
        store: Op-Store.

    Returns:
        Ergebnisse der fortgesetzten Auflösungen.
    """
    outcomes = []
    for op_id in store.all_ids():
        if store.is_final(op_id):
            continue
        op = store.open_for_recovery(op_id)
        if op is None:
            continue
        art = op.manifest.get("art")
        if art == "automerge":
            gone = not (writer.root / op.manifest["konflikt"]).exists()
            op.set_state("DONE" if gone else "ABORTED")
            op.release()
        elif art == "resolve":
            outcomes.append(_recover_one(writer, op))
        else:
            op.release()
    return outcomes


def _recover_one(writer: Writer, op: Op) -> ResolveOutcome:
    """Fälle a–j einer Resolve-Op aus Plattenzustand und Manifest."""
    m = op.manifest
    main = writer.root / m["relpath"]
    p = main.read_bytes() if main.exists() else None
    m0 = op.blob("haupt", m["blobs"]["haupt"]) if "haupt" in m["blobs"] else None
    c0, r = op.blob("konflikt", m["blobs"]["konflikt"]), op.blob("ergebnis", m["blobs"]["ergebnis"])
    plain, marked = writer.root / m["konflikt"], writer.root / m["marker"]
    c = plain.read_bytes() if plain.exists() else None
    cm = marked.read_bytes() if marked.exists() else None
    if not op.state():
        op.set_state("ABORTED", grund="nie vorbereitet")
        op.release()
        return ResolveOutcome(op.id, "ABORTED")
    if p == r:
        if cm == c0:
            return _from_remove(writer, op)                                        # d
        if c is None and cm is None:
            return _done(op, "")                                                   # e
        return _done(op, "Konfliktdatei wurde geändert – bleibt als Konflikt")     # f
    if p == m0:
        if c == c0 and cm is None:
            return _from_mark(writer, op)                                          # a
        if cm == c0:
            return _from_write(writer, op)                                         # b
        if c is None and cm is None:
            return _interrupt(op, "Konfliktdatei wurde extern entfernt – deine Entscheidung ist nicht angewendet")  # i
        return _interrupt(op, "Konfliktdatei wurde geändert – deine frühere Wahl ist vorausgewählt")  # g
    return _interrupt(op, "Hauptdatei wurde extern geändert – deine frühere Wahl ist vorausgewählt")    # h/j


def _unmark(writer: Writer, op: Op) -> None:
    """Nimmt den Marker zurück, wenn die Auflösung vor dem Haupt-Write scheitert."""
    m = op.manifest
    marked, plain = writer.root / m["marker"], writer.root / m["konflikt"]
    if marked.exists() and not plain.exists():
        writer.fs.rename_no_replace(marked, plain)


def _interrupt(op: Op, hint: str) -> ResolveOutcome:
    """Unterbrochen: Entscheidung bleibt im Op-Verzeichnis, Konflikt wird erneut gezeigt."""
    op.set_state("INTERRUPTED", hinweis=hint, bestaetigt=False)
    op.release()
    return ResolveOutcome(op.id, "INTERRUPTED", hint)


def _done(op: Op, hint: str) -> ResolveOutcome:
    """Abgeschlossen (ggf. mit Hinweis auf eine danach geänderte Konfliktdatei)."""
    op.set_state("DONE", hinweis=hint, bestaetigt=not hint)
    op.release()
    return ResolveOutcome(op.id, "DONE", hint)


def acknowledge(store: OpStore, op_id: str) -> None:
    """Bestätigt den Hinweis einer unterbrochenen Auflösung (danach normale Aufbewahrung).

    Args:
        store: Op-Store.
        op_id: Resolve-Op.
    """
    op = store.open_for_recovery(op_id)
    if op is not None:
        op.set_state(op.state().get("zustand", "INTERRUPTED"), bestaetigt=True)
        op.release()


def manual_only_paths(store: OpStore) -> set[str]:
    """Konfliktdateien, für die nie ein Auto-Merge laufen darf.

    Rekonstruierbar aus den Op-Manifesten und -Zuständen:

    * Konfliktdatei (mit und ohne Marker) einer unterbrochenen oder mit Hinweis
      abgeschlossenen, noch nicht bestätigten Resolve-Op,
    * alle in ``nur_manuell`` genannten Versionen (übrige Versionen nach einer
      ``MAIN_DELETED``-Wiederherstellung).

    Args:
        store: Op-Store.

    Returns:
        Relative Pfade.
    """
    paths: set[str] = set()
    for op_id in store.all_ids():
        manifest, state = store.read(op_id)
        if manifest.get("art") != "resolve":
            continue
        paths.update(manifest.get("nur_manuell", ()))
        if state.get("hinweis") and not state.get("bestaetigt"):  # INTERRUPTED oder DONE mit Hinweis (f)
            paths.update({manifest["konflikt"], manifest["marker"]})
    return paths
