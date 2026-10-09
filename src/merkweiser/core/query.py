"""Suche und Filter über gelesene Dokumente (Schritt 4, nur lesend).

Semantik (``docs/PLAN.md``, „Suche“), für Desktop und Mobile identisch:

* Verschiedene Filterarten werden UND-verknüpft; ein leeres Feld schränkt nicht ein.
* ``tags`` prüft die **effektiven** Tags (inklusive Vererbung); mehrere Tags
  standardmäßig UND, umschaltbar auf ODER.
* ``projekt`` prüft die effektiven Projekte.
* ``status`` (offen/erledigt) und ``dringend`` (ja/nein) beziehen sich auf
  Todos: Ist einer davon gesetzt, kommen nur Todos in Frage. ``[-]`` u. a.
  gelten nicht als Todo.
* ``text``: ``TextQuery`` mit Modus ``TEILSTRING`` (Standard, per ``casefold``)
  oder ``REGEX`` (``re.IGNORECASE``). Ungültiger Regex → ``InvalidQuery``.
* ``von``/``bis``: Datum der Tagesdatei, inklusiv.

Treffer sind Knoten (Thema, Überschrift, Listenpunkt, Sonstiges) mit Kontext.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Callable, Iterable

from .document import Document, ParsedNote
from .inline import TodoStatus
from .outline import Node, NodeKind


class InvalidQuery(ValueError):
    """Der Suchtext ist im Regex-Modus kein gültiger regulärer Ausdruck."""


class TextMode(Enum):
    """Modus der Freitextsuche."""

    TEILSTRING = "teilstring"
    REGEX = "regex"


class TagMode(Enum):
    """Verknüpfung mehrerer Tags."""

    UND = "und"
    ODER = "oder"


class StatusFilter(Enum):
    """Filter nach Erledigungsstatus."""

    ALLE = "alle"
    OFFEN = "offen"
    ERLEDIGT = "erledigt"


class UrgentFilter(Enum):
    """Filter nach Dringlichkeit."""

    EGAL = "egal"
    JA = "ja"
    NEIN = "nein"


@dataclass(frozen=True)
class TextQuery:
    """Freitext mit explizitem Modus.

    Attributes:
        muster: Suchtext bzw. regulärer Ausdruck.
        modus: Teilstring (Standard) oder Regex.
    """

    muster: str
    modus: TextMode = TextMode.TEILSTRING

    def matcher(self) -> Callable[[str], bool]:
        """Erzeugt die Prüffunktion.

        Returns:
            Funktion, die für einen Text ``True`` liefert, wenn er passt.

        Raises:
            InvalidQuery: bei ungültigem regulärem Ausdruck.
        """
        if self.modus is TextMode.REGEX:
            try:
                regex = re.compile(self.muster, re.IGNORECASE)
            except re.error as exc:
                raise InvalidQuery(str(exc)) from exc
            return lambda text: regex.search(text) is not None
        needle = self.muster.casefold()
        return lambda text: needle in text.casefold()


@dataclass(frozen=True)
class Filter:
    """Alle Suchkriterien; Standardwerte schränken nicht ein."""

    text: TextQuery | None = None
    von: date | None = None
    bis: date | None = None
    tags: tuple[str, ...] = ()
    tag_modus: TagMode = TagMode.UND
    projekt: str | None = None
    status: StatusFilter = StatusFilter.ALLE
    dringend: UrgentFilter = UrgentFilter.EGAL
    nur_todos: bool = False


@dataclass(frozen=True)
class Hit:
    """Ein Treffer auf Knotenebene.

    Attributes:
        relpath: Datei relativ zum Vault.
        day: Datum der Tagesdatei.
        note_index: Index der Notiz in der Datei.
        node_index: Index des Knotens im Notizbaum.
        line_no: Erste Zeile des Knotens.
        kind: Knotenart.
        text: Text der ersten Zeile.
        status: Todo-Status (``NONE`` für Nicht-Punkte).
        urgent: Dringlichkeit.
        tags: Effektive Tag-Schlüssel (sortiert).
        projects: Effektive Projekte.
        inherited_projects: Davon nur geerbte Projekte.
        context: Erste Zeilen der Vorfahren (Überschriften, Thema, Eltern-Punkte).
    """

    relpath: str
    day: date
    note_index: int
    node_index: int
    line_no: int
    kind: NodeKind
    text: str
    status: TodoStatus
    urgent: bool
    tags: tuple[str, ...]
    projects: tuple[str, ...]
    inherited_projects: tuple[str, ...]
    context: tuple[str, ...]


def search(documents: Iterable[tuple[str, date, Document]], criteria: Filter) -> list[Hit]:
    """Durchsucht Dokumente nach Knoten, die alle Kriterien erfüllen.

    Args:
        documents: ``(relpath, datum, Dokument)`` je Tagesdatei.
        criteria: Suchkriterien.

    Returns:
        Treffer in Reihenfolge (Datum, Pfad, Dateiposition).

    Raises:
        InvalidQuery: bei ungültigem regulärem Ausdruck.
    """
    text_ok = criteria.text.matcher() if criteria.text and criteria.text.muster else None
    wanted_tags = {t.lstrip("#").casefold() for t in criteria.tags if t.strip("# ")}
    hits: list[Hit] = []
    for relpath, day, doc in sorted(documents, key=lambda entry: (entry[1], entry[0])):
        if (criteria.von and day < criteria.von) or (criteria.bis and day > criteria.bis):
            continue
        for note in doc.notes:
            for node in note.outline.nodes:
                if node.implicit or not node.lines:
                    continue
                if _matches(doc, note, node, criteria, text_ok, wanted_tags):
                    hits.append(_hit(relpath, day, doc, note, node))
    return hits


def _matches(doc: Document, note: ParsedNote, node: Node, criteria: Filter,
             text_ok: Callable[[str], bool] | None, wanted_tags: set[str]) -> bool:
    """Prüft einen Knoten gegen alle Kriterien außer dem Datum.

    Args:
        doc: Das Dokument.
        note: Die Notiz des Knotens.
        node: Der Knoten.
        criteria: Suchkriterien.
        text_ok: Vorbereitete Textprüfung oder ``None``.
        wanted_tags: Gewünschte Tag-Schlüssel.

    Returns:
        ``True``, wenn der Knoten alle Kriterien erfüllt.
    """
    is_todo = bool(node.item and node.item.is_todo)
    todo_only = criteria.nur_todos or criteria.status is not StatusFilter.ALLE \
        or criteria.dringend is not UrgentFilter.EGAL
    if todo_only and not is_todo:
        return False
    if criteria.status is StatusFilter.OFFEN and node.item.status is not TodoStatus.OPEN:  # type: ignore[union-attr]
        return False
    if criteria.status is StatusFilter.ERLEDIGT and node.item.status is not TodoStatus.DONE:  # type: ignore[union-attr]
        return False
    if criteria.dringend is not UrgentFilter.EGAL and node.item.urgent != (criteria.dringend is UrgentFilter.JA):  # type: ignore[union-attr]
        return False
    tags = note.tags[node.index]
    if wanted_tags:
        present = wanted_tags & tags.effective
        if (criteria.tag_modus is TagMode.UND and present != wanted_tags) or not present:
            return False
    if criteria.projekt and criteria.projekt.casefold() not in {p.casefold() for p in tags.effective_projects}:
        return False
    return text_ok is None or text_ok("\n".join(doc.line_text(no) for no in node.lines))


def _hit(relpath: str, day: date, doc: Document, note: ParsedNote, node: Node) -> Hit:
    """Baut einen Treffer mit Kontextpfad.

    Args:
        relpath: Dateipfad.
        day: Datum der Datei.
        doc: Das Dokument.
        note: Die Notiz.
        node: Der Knoten.

    Returns:
        Der Treffer.
    """
    context: list[str] = []
    parent = node.parent
    while parent is not None:
        ancestor = note.outline.nodes[parent]
        if ancestor.lines:
            context.append(doc.line_text(ancestor.lines[0]).strip())
        parent = ancestor.parent
    tags = note.tags[node.index]
    item = node.item
    return Hit(relpath=relpath, day=day, note_index=note.index, node_index=node.index, line_no=node.lines[0],
               kind=node.kind, text=doc.line_text(node.lines[0]),
               status=item.status if item else TodoStatus.NONE, urgent=bool(item and item.urgent),
               tags=tuple(sorted(tags.effective)), projects=tags.effective_projects,
               inherited_projects=tags.inherited_projects, context=tuple(reversed(context)))
