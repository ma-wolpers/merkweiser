"""Auto-Merge-Protokoll und „Rückgängig“ (PLAN.md, „Konflikte“, Liste „Automatisch zusammengeführt“).

Jeder Auto-Merge ist eine Op ``automerge`` mit den Blobs ``haupt`` (vorher),
``konflikt`` und ``ergebnis``. Dieses Modul

* listet sie für die Oberfläche (``automerge_log``),
* macht einen Auto-Merge rückgängig (``undo_automerge``) und
* liefert die Konfliktdateien, die danach **nie wieder automatisch**
  zusammengeführt werden dürfen (``undone_manual_paths``) und
* blendet Einträge auf Wunsch aus (``hide_automerges``; Nutzerwunsch vom
  2026-10-21). Ausblenden ändert nur die Anzeige: Die Op samt Backup bleibt bis
  zum Ende der Aufbewahrung, ``rueckgaengig`` und ``nur_manuell`` bleiben gültig.

Garantie 4 (PLAN.md): Ein „Rückgängig“ ist eine ausdrückliche Entscheidung.
Ohne Markierung würde der nächste Start dieselbe Konfliktdatei wieder
automatisch zusammenführen und das Rückgängig still aufheben. Deshalb steht die
Absicht **vor** dem ersten Schreibzugriff in ``state.json``
(``rueckgaengig = "geplant"``, ``nur_manuell`` = ursprünglicher Pfad) und wird
nach dem Wiederherstellen auf den tatsächlichen Pfad gesetzt
(``rueckgaengig = "erledigt"``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import conflict_files as cf
from .ops import OpStore
from .safe_write import Writer


@dataclass(frozen=True)
class AutoMergeEntry:
    """Ein Eintrag der Liste „Automatisch zusammengeführt“.

    Attributes:
        op_id: Die Automerge-Op (für „Rückgängig“).
        relpath: Hauptdatei.
        conflict_relpath: Ursprünglicher Pfad der zusammengeführten Konfliktdatei.
        created: Zeitpunkt des Merges (aus dem Manifest, mit Zeitzone).
        before: Hauptdatei vor dem Merge.
        after: Ergebnis des Merges.
        undone: ``None``, ``"geplant"`` (unterbrochen, erneut auslösbar) oder ``"erledigt"``.
    """

    op_id: str
    relpath: str
    conflict_relpath: str
    created: datetime
    before: bytes
    after: bytes
    undone: str | None


def automerge_log(store: OpStore, limit: int = 20) -> list[AutoMergeEntry]:
    """Abgeschlossene, nicht ausgeblendete Auto-Merges, neueste zuerst (solange die Op aufbewahrt wird).

    Args:
        store: Op-Store.
        limit: Höchstzahl der Einträge.

    Returns:
        Einträge mit den Bytes vorher/nachher für die Anzeige.
    """
    entries: list[AutoMergeEntry] = []
    for op_id in reversed(store.all_ids()):
        manifest, state = store.read(op_id)
        if manifest.get("art") != "automerge" or state.get("zustand") != "DONE" or state.get("ausgeblendet"):
            continue
        blobs = manifest["blobs"]
        entries.append(AutoMergeEntry(
            op_id, manifest["relpath"], manifest["konflikt"], datetime.fromisoformat(manifest["erstellt"]),
            store.read_blob(op_id, "haupt", blobs["haupt"]), store.read_blob(op_id, "ergebnis", blobs["ergebnis"]),
            state.get("rueckgaengig")))
        if len(entries) >= limit:
            break
    return entries


def undo_automerge(writer: Writer, store: OpStore, op_id: str) -> str:
    """Macht einen Auto-Merge rückgängig: Hauptdatei zurück, Konfliktdatei wieder anlegen.

    Idempotent: Ein zweiter Aufruf (z. B. nach Abbruch) überspringt bereits
    erledigte Teile. Die wiederhergestellte Konfliktdatei wird dauerhaft als
    „nur manuell“ markiert.

    Args:
        writer: Writer.
        store: Op-Store.
        op_id: Die Automerge-Op.

    Returns:
        Pfad der wiederhergestellten Konfliktdatei (relativ zum Vault).

    Raises:
        RuntimeError: Op gerade gesperrt.
        ChangedBeforeWriteError: Die Hauptdatei wurde seit dem Merge verändert;
            dann bleibt alles unverändert und die Markierung wird zurückgenommen.
    """
    op = store.open_for_recovery(op_id)
    if op is None:
        raise RuntimeError("Op ist gerade gesperrt")
    try:
        manifest, blobs = op.manifest, op.manifest["blobs"]
        before, conflict = op.blob("haupt", blobs["haupt"]), op.blob("konflikt", blobs["konflikt"])
        result = op.blob("ergebnis", blobs["ergebnis"])
        main = writer.root / manifest["relpath"]
        op.set_state("DONE", rueckgaengig="geplant", nur_manuell=[manifest["konflikt"]])
        try:
            if not (main.exists() and main.read_bytes() == before):
                writer.write(manifest["relpath"], result, before)
        except Exception:
            op.set_state("DONE", rueckgaengig=None, nur_manuell=[])
            raise
        restored = _restore_conflict(writer, manifest["relpath"], manifest["konflikt"], conflict)
        op.set_state("DONE", rueckgaengig="erledigt", nur_manuell=[restored])
        return restored
    finally:
        op.release()


def hide_automerges(store: OpStore, op_ids: list[str]) -> list[str]:
    """Blendet Einträge der Liste „Automatisch zusammengeführt“ aus.

    Setzt ``ausgeblendet`` im Zustand der Op (mit Lock und Fencing wie jede
    Zustandsänderung). Eine gerade von einer anderen Instanz gesperrte Op wird
    übersprungen und bleibt sichtbar.

    Args:
        store: Op-Store.
        op_ids: Die auszublendenden Automerge-Ops.

    Returns:
        Tatsächlich ausgeblendete ``op-id``s.
    """
    hidden = []
    for op_id in op_ids:
        op = store.open_for_recovery(op_id)
        if op is None:
            continue
        try:
            if op.manifest.get("art") == "automerge":
                op.set_state(op.state().get("zustand", "DONE"), ausgeblendet=True)
                hidden.append(op_id)
        finally:
            op.release()
    return hidden


def undone_manual_paths(store: OpStore) -> set[str]:
    """Konfliktdateien, die nie wieder automatisch zusammengeführt werden.

    Quellen: rückgängig gemachte Auto-Merges und Rückgängig im Backup-Browser,
    das eine Sync-Konfliktdatei wieder angelegt hat (``core.backups``).

    Args:
        store: Op-Store.

    Returns:
        Relative Pfade aus ``nur_manuell`` aller Automerge- und Rückgängig-Ops.
    """
    paths: set[str] = set()
    for op_id in store.all_ids():
        manifest, state = store.read(op_id)
        if manifest.get("art") in ("automerge", "rueckgaengig"):
            paths.update(state.get("nur_manuell") or ())
    return paths


def _restore_conflict(writer: Writer, relpath: str, conflict_relpath: str, conflict: bytes) -> str:
    """Legt die Konfliktversion wieder an (ursprünglicher Pfad, sonst eigener Name).

    GRENZE: Ist der ursprüngliche Pfad belegt und bricht der Prozess genau
    zwischen dem Anlegen unter eigenem Namen und dem Festhalten dieses Namens
    ab, ist die neue Datei nicht als „nur manuell“ markiert; der nächste Start
    führt sie dann wieder automatisch zusammen. Das Rückgängig ist damit
    verloren, aber sichtbar: Der neue Merge erscheint wieder in der Liste und
    kann erneut rückgängig gemacht werden.

    Args:
        writer: Writer.
        relpath: Hauptdatei.
        conflict_relpath: Ursprünglicher Pfad der Konfliktdatei.
        conflict: Ihr Inhalt.

    Returns:
        Pfad der Konfliktdatei (relativ zum Vault).
    """
    target = writer.root / conflict_relpath
    if target.exists():
        if target.read_bytes() == conflict:
            return conflict_relpath
        main = writer.root / relpath
        found = cf.find_with_content(main, conflict)
        return writer.rel(found or cf.create_from_bytes(writer.fs, main, conflict, writer.clock))
    writer.write(conflict_relpath, None, conflict)
    return conflict_relpath
