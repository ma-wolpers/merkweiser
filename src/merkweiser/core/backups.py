"""Backup-Browser und Rückgängig einzelner Änderungen (W4, PLAN-SPAETERE-SCHRITTE.md S4).

**Änderungen** sind die Blatt-Ops ``write``/``remove`` (jede ändert genau eine
Datei). Ihre Bedeutung kommt von der Eltern-Op (Auto-Merge, Konflikt
entschieden, Verschieben …). Dazu kommen **verdrängte Stände**: Bytes, die beim
Tausch in der Datei standen, aber nicht dem erwarteten Stand entsprachen.

**Rückgängig** nimmt nur diese eine Änderung zurück und erhält spätere:

* Inhalt: ``merge3(base=after, a=aktuell, b=before)``; eine fehlende Datei zählt
  dabei nur **intern** als leer.
* Existenz (diff3 auf einem Wahrheitswert): ``ex = exists(before)``, falls
  ``exists(aktuell) == exists(after)``, sonst ``exists(aktuell)``. Soll die Datei
  nicht existieren, das Ergebnis hat aber Inhalt → Konfliktdatei (nie Inhalt
  durch Löschen verlieren). Eine echt leere Datei bleibt eine leere Datei.
* Sicherheitsentscheidung ``merge_is_safe``: nur ein sauberes Ergebnis, das
  ``verify`` ohne Verstöße besteht, wird direkt geschrieben. Sonst wird
  ``before`` eine **eigene Konfliktdatei** mit Sidecar-Basis ``after`` (eigene
  ``konfliktbasis``-Op); der Konfliktdialog zeigt dann denselben diff3.
* Verdrängte Stände werden immer als Konfliktdatei wiederhergestellt.

Ablauf als Schrittprotokoll (``step_ops``): Eltern-Op ``rueckgaengig`` mit
``ziel_op`` im Manifest; die Dateiänderung ist eine Kinder-Op. „Bereits
rückgängig gemacht“ wird aus abgeschlossenen ``rueckgaengig``-Ops abgeleitet,
die Ziel-Op wird nicht verändert. Wird dabei eine Sync-Konfliktdatei wieder
angelegt, steht sie in ``nur_manuell`` (kein erneuter Auto-Merge).

GRENZE(Rückgängig): Bis Phase 6 wird zeilenweise über die ganze Datei
zusammengeführt, auch im YAML-Kopf. diff3 ist dabei konservativ: Haben beide
Seiten dieselbe Zeile geändert, entsteht ein Hunk und damit eine Konfliktdatei.
Das gilt auch für **benachbarte** Änderungen (z. B. Haken zurücknehmen, wenn
direkt darunter inzwischen ein Todo ergänzt wurde) – wie beim Sync-Merge
(``test_adjacent_changes_on_both_sides_are_manual_grenze``). Die Entscheidung
fällt dann im Konfliktdialog.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import conflict_files as cf
from .ops import OpStore
from .safe_write import Writer
from .step_ops import REMOVE, STEP_DONE, child_state, finish, pending_ops, run_step
from .undo_merge import UndoPlan, plan_undo
from .vault import parse_conflict_name

PARENT_LABELS = {"automerge": "automatisch zusammengeführt", "resolve": "Konflikt entschieden",
                 "move": "verschoben", "rueckgaengig": "rückgängig gemacht", "duplikat": "Duplikat entfernt",
                 "zeitbuchung": "Zeit eingetragen", "umbenennen": "Tätigkeit umbenannt"}
OWN_KINDS = {"angelegt": "angelegt", "bearbeitet": "bearbeitet", "gelöscht": "gelöscht",
             "verdrängt": "von außen überschriebener Stand"}


@dataclass(frozen=True)
class BlobRef:
    """Verweis auf persistierte Bytes einer Op."""

    op_id: str
    role: str
    sha: str


@dataclass(frozen=True)
class Change:
    """Eine einzelne Änderung an einer Datei (bzw. ein verdrängter Stand).

    Attributes:
        op_id: Die Blatt-Op.
        relpath: Datei relativ zum Vault.
        created: Zeitpunkt (UTC, ISO).
        kind: ``angelegt``, ``bearbeitet``, ``gelöscht`` oder ``verdrängt``.
        label: Anzeige der Art (Eltern-Art hat Vorrang).
        before: Stand vorher (``None``: Datei existierte nicht).
        after: Stand nachher (``None``: Datei wurde gelöscht).
        group: Eltern-Op (zusammengehörige Änderungen) oder ``None``.
        group_art: Art der Eltern-Op.
    """

    op_id: str
    relpath: str
    created: str
    kind: str
    label: str
    before: BlobRef | None
    after: BlobRef | None
    group: str | None
    group_art: str | None


class UndoConflict(Exception):
    """Die Änderung lässt sich nicht eindeutig zurücknehmen."""


def changes(store: OpStore) -> list[Change]:
    """Alle Änderungen, neueste zuerst.

    Args:
        store: Op-Store.

    Returns:
        Änderungen abgeschlossener bzw. installierter Blatt-Ops und verdrängte Stände.
    """
    ops = {op_id: store.read(op_id) for op_id in store.all_ids()}
    # Eigener erster Durchlauf: IDs derselben Sekunde sortieren nach Zufallsteil,
    # ein Kind kann also vor seiner Eltern-Op stehen.
    arts = {op_id: manifest.get("art", "") for op_id, (manifest, _state) in ops.items()}
    found: list[Change] = []
    for op_id, (manifest, state) in ops.items():
        if manifest.get("art") in ("write", "remove") and state.get("zustand") in STEP_DONE:
            found += _changes_of(op_id, manifest, state, arts)
    found.sort(key=lambda change: change.created)
    return list(reversed(found))


def _changes_of(op_id: str, manifest: dict, state: dict, arts: dict[str, str]) -> list[Change]:
    """Änderung(en) einer Blatt-Op: die Änderung selbst und ggf. ein verdrängter Stand."""
    blobs = manifest.get("blobs", {})
    ref = lambda role: BlobRef(op_id, role, blobs[role]) if role in blobs else None  # noqa: E731
    parent = manifest.get("eltern_op")
    group_art = arts.get(parent) if parent else None
    if manifest["art"] == "remove":
        kind, before, after = "gelöscht", ref("vorher"), None
    else:
        kind = "angelegt" if manifest.get("create_only") else "bearbeitet"
        before, after = ref("vorher"), ref("neu")
    label = PARENT_LABELS.get(group_art or "", OWN_KINDS[kind])
    common = dict(relpath=manifest["relpath"], created=manifest.get("erstellt", ""), group=parent, group_art=group_art)
    result = [Change(op_id, kind=kind, label=label, before=before, after=after, **common)]
    displaced = state.get("d_sha1")
    if displaced and displaced != blobs.get("vorher"):
        result.append(Change(op_id, kind="verdrängt", label=OWN_KINDS["verdrängt"],
                             before=BlobRef(op_id, "verdraengt", displaced), after=None, **common))
    return result


def changes_by_file(store: OpStore) -> list[tuple[str, list[Change]]]:
    """Änderungen nach Datei gruppiert; Dateien mit der jüngsten Änderung zuerst.

    Args:
        store: Op-Store.

    Returns:
        ``(relpath, änderungen_neueste_zuerst)``.
    """
    groups: dict[str, list[Change]] = {}
    for change in changes(store):
        groups.setdefault(change.relpath, []).append(change)
    return list(groups.items())


def load(store: OpStore, ref: BlobRef | None) -> bytes | None:
    """Liest die Bytes eines Verweises (``None`` bleibt ``None``).

    Raises:
        OSError: Blob fehlt oder ist beschädigt.
    """
    return None if ref is None else store.read_blob(ref.op_id, ref.role, ref.sha)


def undone_ops(store: OpStore) -> set[str]:
    """Ziel-Ops, die bereits rückgängig gemacht wurden (abgeleitet, ohne die Ziel-Op zu ändern)."""
    done = set()
    for op_id in store.all_ids():
        manifest, state = store.read(op_id)
        if manifest.get("art") == "rueckgaengig" and state.get("zustand") == "DONE":
            done.add(f"{manifest['ziel_op']}:{manifest.get('ziel_art', '')}")
    return done


def change_key(change: Change) -> str:
    """Schlüssel einer Änderung in ``undone_ops`` (Op und Art, wegen verdrängter Stände)."""
    return f"{change.op_id}:{change.kind}"


def undo_change(writer: Writer, store: OpStore, change: Change, prefix: str = "") -> UndoPlan:
    """Nimmt eine Änderung zurück (Schrittprotokoll, Eltern-Op ``rueckgaengig``).

    Args:
        writer: Writer.
        store: Op-Store.
        change: Die Änderung.
        prefix: Projekt-Präfix (zum Parsen).

    Returns:
        Was geschehen ist (``konflikt`` heißt: Konfliktdatei angelegt).
    """
    plan = {"ziel_op": change.op_id, "ziel_art": change.kind, "relpath": restore_path(store, change),
            "vorher_ref": _ref_dict(change.before), "nachher_ref": _ref_dict(change.after)}
    op = store.create("rueckgaengig", plan, {})
    return _continue(writer, store, op, prefix)


def restore_path(store: OpStore, change: Change) -> str:
    """Datei, auf die Rückgängig wirkt.

    Beim Entscheiden eines Konflikts (``resolve``) wird die Konfliktdatei erst zum
    Marker ``…MWENTSCHIEDEN`` umbenannt und dann entfernt. Rückgängig legt sie
    unter ihrem **ursprünglichen** Namen wieder an; ein wiederhergestellter
    Marker würde sonst als offene Entscheidung gelten.

    Args:
        store: Op-Store.
        change: Die Änderung.

    Returns:
        Relativer Pfad.
    """
    if change.group_art == "resolve" and change.group:
        parent, _state = store.read(change.group)
        if change.relpath == parent.get("marker"):
            return parent["konflikt"]
    return change.relpath


def recover_undos(writer: Writer, store: OpStore, prefix: str = "") -> list[str]:
    """Setzt unterbrochene Rückgängig-Vorgänge fort (Start, nach der Tausch-Wiederherstellung).

    Returns:
        ``op-id``s der fortgesetzten Vorgänge.
    """
    resumed = []
    for op_id in pending_ops(store, "rueckgaengig"):
        op = store.open_for_recovery(op_id)
        if op is not None:
            _continue(writer, store, op, prefix)
            resumed.append(op_id)
    return resumed


def _continue(writer: Writer, store: OpStore, op, prefix: str) -> UndoPlan:
    """Führt den einzigen Schritt aus, falls er nicht schon erledigt ist."""
    m = op.manifest
    rel = m["relpath"]
    before, after = load(store, _ref(m["vorher_ref"])), load(store, _ref(m["nachher_ref"]))
    if child_state(store, op.id, rel) in STEP_DONE:
        finish(op, ergebnis="geschrieben")
        return UndoPlan("schreiben")
    base = None if m["ziel_art"] == "verdrängt" else (after or b"")
    if base is None or op.state().get("konfliktdatei"):
        return _as_conflict(writer, store, op, before or b"", base)
    outcome: dict[str, UndoPlan] = {}

    def build(_doc, raw: bytes | None):
        outcome["plan"] = planned = plan_undo(before, after, raw)
        if planned.action == "konflikt":
            raise UndoConflict(rel)
        return {"schreiben": planned.data, "entfernen": REMOVE, "nichts": None}[planned.action]

    try:
        run_step(writer, op, rel, prefix, build)
    except UndoConflict:
        return _as_conflict(writer, store, op, before or b"", base)
    result = outcome["plan"]
    restored = rel if result.action == "schreiben" and parse_conflict_name(rel) else None
    finish(op, ergebnis=result.action, nur_manuell=[restored] if restored else [])
    return result


def _as_conflict(writer: Writer, store: OpStore, op, content: bytes, base: bytes | None) -> UndoPlan:
    """Legt ``content`` als eigene Konfliktdatei an (mit Sidecar-Basis, falls ``base`` gegeben).

    Idempotent: Existiert schon eine Konfliktdatei mit genau diesem Inhalt, wird
    keine zweite angelegt.
    """
    rel = op.manifest["relpath"]
    main = writer.root / rel
    op.set_state(op.state().get("zustand", "PREPARED"), konfliktdatei=True)
    path = cf.find_with_content(main, content) or cf.create_from_bytes(writer.fs, main, content, writer.clock)
    conflict_rel = writer.rel(path)
    if base is not None:
        basis = store.create("konfliktbasis", {"relpath": rel}, {"vorher": base})
        basis.set_state("DONE")
        basis.release()
        cf.write_sidecar(writer.data, conflict_rel, cf.sha1(content), rel, basis.id, cf.sha1(base), cf.UNDO_ORIGIN)
    finish(op, ergebnis="konflikt", konflikte=[conflict_rel])
    return UndoPlan("konflikt")


def _ref_dict(ref: BlobRef | None) -> dict | None:
    return None if ref is None else {"op_id": ref.op_id, "role": ref.role, "sha": ref.sha}


def _ref(data: dict | None) -> BlobRef | None:
    return None if data is None else BlobRef(data["op_id"], data["role"], data["sha"])

