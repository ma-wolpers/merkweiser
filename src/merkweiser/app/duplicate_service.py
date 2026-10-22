"""Doppelte Notizen für die Oberflächen (W3, PLAN-SPAETERE-SCHRITTE.md S3).

``duplicates`` sucht über alle Tagesdateien (``core.duplicates``); das Ergebnis
wird zwischengespeichert, solange sich keine Datei geändert hat (die
Dokumente aus ``DocumentCache`` sind dann dieselben Objekte). ``keep`` führt die
Bereinigung als Schrittprotokoll aus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.duplicates import DuplicateGroup, find_duplicates, keep_one

if TYPE_CHECKING:
    from .notes_service import NotesService


def duplicates(service: "NotesService") -> list[DuplicateGroup]:
    """Alle Gruppen doppelter Notizen (jüngste zuerst).

    Args:
        service: Geöffneter Service.

    Returns:
        Gruppen mit Fundstellen in mindestens zwei Tagesdateien.
    """
    documents = [(p, day, service.cache.get(p)) for day, paths in service.index.day_files.items() for p in paths]
    cached = getattr(service, "_duplicate_memo", None)
    if cached is not None and len(cached[0]) == len(documents) \
            and all(a[0] == b[0] and a[2] is b[2] for a, b in zip(cached[0], documents)):
        return cached[1]
    groups = find_duplicates(documents)
    service._duplicate_memo = (documents, groups)  # hält die Dokumente fest: Identitätsvergleich bleibt gültig
    return groups


def keep(service: "NotesService", group: DuplicateGroup, index: int) -> str:
    """Behält Fundstelle ``index`` und löscht die anderen.

    Args:
        service: Geöffneter, beschreibbarer Service.
        group: Die angezeigte Gruppe.
        index: Index in ``group.places``.

    Returns:
        Meldung für die Oberfläche.

    Raises:
        ReadOnlyVaultError: im Schreibschutz.
    """
    service.check_writable()
    hint = keep_one(service.writer, service.store, group, index, service.settings.project_prefix)
    service.rescan()
    others = len(group.places) - 1
    return hint or f"Doppelte Notiz bereinigt: {others} Fundstelle(n) gelöscht (Backup bleibt)."
