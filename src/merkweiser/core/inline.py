"""Zeilensemantik: Listenmarker, Einrückung, Checkbox, Dringlichkeit, Tags, Projekte.

Arbeitet auf einzelnen Zeilen und stützt sich für Code- und Link-Bereiche
ausschließlich auf ``lexer`` (keine eigenen Regeln dafür). Struktur
(Thema, Eltern, Vererbung) entscheidet ``outline`` bzw. ``tags``.

Regeln (``docs/FORMAT.md``):

* Listenpunkt: ``-``, ``*``, ``+``, ``1.``, ``1)`` nach optionaler Einrückung.
* Einrückung in Spalten mit Tabstopps bei Vielfachen von 4.
* Checkbox direkt nach dem Marker: ``[ ]`` offen, ``[x]``/``[X]`` erledigt,
  anderes Zeichen → ``OTHER`` (GRENZE: gilt als normaler Punkt).
* Dringend: Der Inhalt (nach der Checkbox) beginnt mit ``==…==``.
* Tag: ``#name`` am Wortanfang, nur in ``TEXT``-Tokens, nicht rein numerisch.
* Projekt: Tag mit Präfix ``<prefix>/``, Vergleich ohne Groß-/Kleinschreibung.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .lexer import text_spans

TAB_STOP = 4

_LIST_RE = re.compile(r"^([ \t]*)([-*+]|\d{1,9}[.)])(?:[ \t]+|$)")
_CHECKBOX_RE = re.compile(r"\[(.)\](?:[ \t]+|$)")
_TAG_RE = re.compile(r"(?<!\S)#([\w/\-]+)")


class TodoStatus(Enum):
    """Status eines Listenpunkts."""

    NONE = "none"    # keine Checkbox
    OPEN = "open"    # [ ]
    DONE = "done"    # [x] oder [X]
    OTHER = "other"  # [-], [/] … (GRENZE: wie normaler Punkt behandelt)


@dataclass(frozen=True)
class ListItem:
    """Analyse einer Listenpunkt-Zeile.

    Attributes:
        indent: Einrückung des Markers in Spalten (Tabstopps beachtet).
        marker: Der Marker (``-``, ``*``, ``+``, ``1.`` …).
        status: Todo-Status.
        status_col: Zeichenindex des Statuszeichens innerhalb ``[ ]`` oder ``None``.
        body_start: Zeichenindex, an dem der eigentliche Inhalt beginnt.
        urgent: ``True``, wenn der Inhalt mit ``==…==`` beginnt.
    """

    indent: int
    marker: str
    status: TodoStatus
    status_col: int | None
    body_start: int
    urgent: bool

    @property
    def is_todo(self) -> bool:
        """``True`` für offene oder erledigte Todos (nicht für ``OTHER``)."""
        return self.status in (TodoStatus.OPEN, TodoStatus.DONE)


@dataclass(frozen=True)
class Tag:
    """Ein Tag-Vorkommen in einer Zeile.

    Attributes:
        name: Tag ohne ``#`` in Originalschreibweise.
        start: Spalte des ``#``.
        end: Spalte hinter dem Tag.
    """

    name: str
    start: int
    end: int

    @property
    def key(self) -> str:
        """Vergleichsschlüssel ohne Groß-/Kleinschreibung (wie in Obsidian)."""
        return self.name.casefold()


def indent_columns(prefix: str) -> int:
    """Rechnet führenden Leerraum in Spalten um (Tabstopps bei Vielfachen von 4).

    Args:
        prefix: Leerraum am Zeilenanfang (Leerzeichen und Tabs).

    Returns:
        Spalte, in der der Inhalt beginnt.
    """
    column = 0
    for char in prefix:
        column = (column // TAB_STOP + 1) * TAB_STOP if char == "\t" else column + 1
    return column


def leading_whitespace(text: str) -> str:
    """Liefert den führenden Leerraum einer Zeile (Leerzeichen und Tabs)."""
    return text[: len(text) - len(text.lstrip(" \t"))]


def parse_list_item(text: str) -> ListItem | None:
    """Analysiert eine Zeile als Listenpunkt.

    Args:
        text: Zeileninhalt.

    Returns:
        Die Analyse oder ``None``, wenn die Zeile kein Listenpunkt ist.
    """
    match = _LIST_RE.match(text)
    if match is None:
        return None
    content_start = match.end()
    status, status_col, body_start = TodoStatus.NONE, None, content_start
    checkbox = _CHECKBOX_RE.match(text, content_start)
    if checkbox:
        char = checkbox.group(1)
        status = {" ": TodoStatus.OPEN, "x": TodoStatus.DONE, "X": TodoStatus.DONE}.get(char, TodoStatus.OTHER)
        status_col, body_start = content_start + 1, checkbox.end()
    return ListItem(indent=indent_columns(match.group(1)), marker=match.group(2), status=status,
                    status_col=status_col, body_start=body_start, urgent=is_urgent(text[body_start:]))


def is_urgent(body: str) -> bool:
    """Prüft, ob ein Inhalt mit einer ``==…==``-Hervorhebung beginnt.

    Args:
        body: Inhalt nach Marker und Checkbox.

    Returns:
        ``True``, wenn der Inhalt mit ``==`` beginnt und später ein schließendes
        ``==`` mit mindestens einem Zeichen dazwischen folgt.
    """
    stripped = body.lstrip()
    return stripped.startswith("==") and stripped.find("==", 3) != -1


def find_tags(text: str) -> tuple[Tag, ...]:
    """Findet alle Tags einer Zeile außerhalb von Code und Link-Zielen.

    Ein Tag beginnt am Wortanfang (davor Zeilenanfang oder Leerraum) und darf
    nicht nur aus Ziffern bestehen. ``# Überschrift`` ist kein Tag, weil nach
    ``#`` ein Leerzeichen steht.

    Args:
        text: Zeileninhalt.

    Returns:
        Die Tags in Spaltenreihenfolge.
    """
    spans = text_spans(text)
    tags = []
    for match in _TAG_RE.finditer(text):
        name = match.group(1).rstrip("/")
        if not name or name.isdigit():  # Obsidian: mindestens ein Nicht-Ziffer-Zeichen
            continue
        start, end = match.start(), match.start() + 1 + len(name)
        if any(s <= start and end <= e for s, e in spans):
            tags.append(Tag(name=name, start=start, end=end))
    return tuple(tags)


def project_name(tag: Tag, prefix: str) -> str | None:
    """Liefert den Projektnamen, falls ``tag`` ein Projekt-Tag ist.

    Args:
        tag: Ein gefundener Tag.
        prefix: Einstellbares Projekt-Präfix (Standard ``projekt``).

    Returns:
        Der Teil nach ``<prefix>/`` in Originalschreibweise, sonst ``None``.
    """
    head = prefix.casefold() + "/"
    if tag.key.startswith(head) and len(tag.name) > len(head):
        return tag.name[len(head):]
    return None
