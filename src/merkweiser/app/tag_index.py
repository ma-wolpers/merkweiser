"""Verwendete Tags für den Tag-Picker im Editor (W7, UI-neutral).

Gezählt wird wie im Tag-Dialog beim Verschieben (``views.tag_check``: „#x gibt es
schon (n Einträge)“): Anzahl der Einträge (Knoten wie in ``query.search``, ohne
implizite) mit diesem **wirksamen** Tag, also auch geerbt. Angezeigt wird die
häufigste **explizite** Schreibweise (bei Gleichstand alphabetisch).

Zwischenspeicher wie bei ``duplicate_service``: gültig, solange der
``DocumentCache`` dieselben Dokumentobjekte liefert. Eigene Schreibvorgänge
(``forget``), Verschieben und Löschen (Index ändert sich) und externe Änderungen
(``mtime``/Größe) erzeugen neue Objekte und damit eine neue Zählung.
GRENZE(Tag-Picker): wie beim ``DocumentCache``; Dateien, die erst nach dem
letzten ``rescan`` auftauchen, zählen ab dem nächsten Prüfintervall.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .notes_service import NotesService

INVALID_PATTERN = "Kein gültiger regulärer Ausdruck – gesucht wird nach dem Text."


def used_tags(service: "NotesService") -> list[tuple[str, int]]:
    """Alle verwendeten Tags mit Anzahl, häufigste zuerst.

    Args:
        service: Geöffneter Service.

    Returns:
        ``[(name, anzahl), …]`` absteigend nach Anzahl, dann alphabetisch (ohne Groß-/Kleinschreibung).
    """
    documents = [(p, service.cache.get(p)) for _day, paths in sorted(service.index.day_files.items()) for p in paths]
    cached = getattr(service, "_tag_memo", None)
    if cached is not None and len(cached[0]) == len(documents) \
            and all(a[0] == b[0] and a[1] is b[1] for a, b in zip(cached[0], documents)):
        return cached[1]
    counts: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = {}
    for _path, doc in documents:
        for note in doc.notes:
            for node in note.outline.nodes:
                if node.implicit or not node.lines:
                    continue
                counts.update(note.tags[node.index].effective)
                for tag in node.tags:
                    spellings.setdefault(tag.key, Counter())[tag.name] += 1
    result = []
    for key, count in counts.items():
        names = spellings.get(key)
        result.append((min(names.items(), key=lambda kv: (-kv[1], kv[0]))[0] if names else key, count))
    result.sort(key=lambda item: (-item[1], item[0].casefold()))
    service._tag_memo = (documents, result)  # hält die Dokumente fest: Identitätsvergleich bleibt gültig
    return result


def filter_tags(tags: list[tuple[str, int]], pattern: str) -> tuple[list[tuple[str, int]], str]:
    """Filtert Tags nach der Sucheingabe (regulärer Ausdruck, ohne Groß-/Kleinschreibung).

    Args:
        tags: Ergebnis von ``used_tags``.
        pattern: Eingabe; ein führendes ``#`` wird ignoriert, leer = alle.

    Returns:
        ``(Treffer, Hinweis)``; bei ungültigem Ausdruck Teilstringsuche und ``INVALID_PATTERN``.
    """
    pattern = pattern.strip().removeprefix("#")
    if not pattern:
        return list(tags), ""
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        needle = pattern.casefold()
        return [tag for tag in tags if needle in tag[0].casefold()], INVALID_PATTERN
    return [tag for tag in tags if regex.search(tag[0])], ""
