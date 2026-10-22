"""Unterbrochene Vorgänge: Eltern-Ops im Zustand ``INCOMPLETE`` (PLAN-SPAETERE-SCHRITTE.md, S0).

Ein Vorgang wird ``INCOMPLETE``, wenn eine Datei nicht mehr zum gespeicherten
Plan passt; dann schreibt Merkweiser bewusst **nichts** weiter und wartet auf
eine Entscheidung. Diese Liste zeigt solche Vorgänge auf der Konflikte-Seite
und zählt im Einstellungen-Badge mit.

Aktionen je Art:

* ``move``: „Erneut versuchen“ (``resume_move``), „Quelle trotzdem entfernen“
  (``force_source``, nur mit exaktem Zielnachweis), „Beide behalten“
  (Vorgang als erledigt quittieren, keine Dateiänderung).
* andere Arten (ab den Phasen 3, 4, 7): „Erneut prüfen“ bzw. „Verwerfen“ über
  ihre eigenen Module; bis dahin nur „Verwerfen“.

„Verwerfen“/„Beide behalten“ ändert nur App-Daten (Zustand ``DONE`` mit
``verworfen``); danach greift die normale Aufbewahrung.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..core.move_exec import MoveResult, resume_move
from ..core.ops import OpStore

if TYPE_CHECKING:
    from .notes_service import NotesService

ART_LABELS = {"move": "Verschieben", "zeitbuchung": "Zeit eintragen", "umbenennen": "Tätigkeit umbenennen",
              "duplikat": "Doppelte Notiz entfernen", "rueckgaengig": "Rückgängig machen"}
RETRY, FORCE, DISMISS = "retry", "force", "dismiss"
ACTION_LABELS = {RETRY: "Erneut versuchen", FORCE: "Quelle trotzdem entfernen", DISMISS: "Verwerfen"}


@dataclass(frozen=True)
class Interrupted:
    """Ein unterbrochener Vorgang für die Anzeige.

    Attributes:
        op_id: Die Eltern-Op.
        art: Op-Art (``move`` …).
        label: Deutsche Bezeichnung der Art.
        hint: Erklärung aus dem Op-Zustand.
        created: Zeitpunkt (UTC, ISO) aus dem Manifest.
        detail: Kurzbeschreibung (z. B. Quelle → Ziel).
        actions: Mögliche Aktionen (``RETRY``, ``FORCE``, ``DISMISS``) in Anzeigereihenfolge.
    """

    op_id: str
    art: str
    label: str
    hint: str
    created: str
    detail: str
    actions: tuple[str, ...]


def interrupted(store: OpStore) -> list[Interrupted]:
    """Alle unterbrochenen Vorgänge, neueste zuerst.

    Args:
        store: Op-Store.

    Returns:
        Einträge für die Konflikte-Seite.
    """
    found = []
    for op_id in reversed(store.all_ids()):
        manifest, state = store.read(op_id)
        if state.get("zustand") != "INCOMPLETE":
            continue
        art = manifest.get("art", "")
        detail = f"{manifest.get('src', '')} → {manifest.get('dst', '')}" if art == "move" else ""
        actions = (RETRY, FORCE, DISMISS) if art == "move" else (DISMISS,)
        found.append(Interrupted(op_id, art, ART_LABELS.get(art, art), state.get("hinweis", ""),
                                 manifest.get("erstellt", ""), detail, actions))
    return found


def action_label(entry: Interrupted, action: str) -> str:
    """Beschriftung einer Aktion („Verwerfen“ heißt beim Move „Beide behalten“).

    Args:
        entry: Der Vorgang.
        action: ``RETRY``, ``FORCE`` oder ``DISMISS``.

    Returns:
        Text für den Knopf.
    """
    if entry.art == "move" and action == DISMISS:
        return "Beide behalten"
    return ACTION_LABELS[action]


def apply_action(service: "NotesService", op_id: str, action: str) -> str:
    """Führt eine Aktion für einen unterbrochenen Vorgang aus.

    Args:
        service: Geöffneter Service (schreibend, außer bei ``DISMISS``).
        op_id: Die Eltern-Op.
        action: ``RETRY``, ``FORCE`` oder ``DISMISS``.

    Returns:
        Meldung für die Oberfläche (leer = erledigt ohne Hinweis).

    Raises:
        ReadOnlyVaultError: bei ``RETRY``/``FORCE`` im Schreibschutz.
        ValueError: unbekannte Aktion oder Art.
    """
    manifest, _state = service.store.read(op_id)
    if action == DISMISS:
        return _dismiss(service.store, op_id)
    if manifest.get("art") != "move" or action not in (RETRY, FORCE):
        raise ValueError(f"Aktion {action} für {manifest.get('art')} nicht möglich")
    service.check_writable()
    result: MoveResult = resume_move(service.writer, service.store, op_id, service.settings.project_prefix,
                                     force_source=action == FORCE)
    return "" if result.state == "DONE" else result.hint


def _dismiss(store: OpStore, op_id: str) -> str:
    """Quittiert einen Vorgang ohne Dateiänderung (``DONE`` mit ``verworfen``).

    Args:
        store: Op-Store.
        op_id: Die Eltern-Op.

    Returns:
        Meldung (leer bei Erfolg).
    """
    op = store.open_for_recovery(op_id)
    if op is None:
        return "Vorgang wird gerade von einer anderen Instanz bearbeitet."
    op.set_state("DONE", verworfen=True)
    op.release()
    return ""


def open_issue_count(service: "NotesService") -> int:
    """Zahl für das Einstellungen-Badge: offene Konflikte und unterbrochene Vorgänge.

    Args:
        service: Geöffneter Service.

    Returns:
        Anzahl (0 = kein Badge).
    """
    return len(service.conflicts()) + len(interrupted(service.store))
