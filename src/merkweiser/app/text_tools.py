"""Einfüge-Werkzeuge für die Notiz-Editoren (UI-neutral, für Desktop und Mobile).

Jede Funktion nimmt ``(text, start, end)`` und liefert ein Tripel gleicher
Form. ``start``/``end`` sind Python-Indizes (Codepoints) der Auswahl; ist die
Position unbekannt (``None``), passiert **nichts**.

Bereich (``toggle_todo``, ``indent``): bei einem Caret die Zeile des Carets,
bei einer Auswahl alle Zeilen, in denen mindestens ein Zeichen ausgewählt ist
(endet die Auswahl genau am Zeilenanfang, zählt diese Zeile nicht). Leerzeilen
dazwischen gehören zum Bereich, werden aber **nicht verändert**: Eine Leerzeile
ist eine Notizgrenze (``docs/FORMAT.md``), und ``- [ ] `` würde sie aufheben.

Die Auswahl wird so umgerechnet, dass sie danach dieselben Zeichen umfasst
(Einfügungen an oder vor einer Position verschieben sie).

Flutter (und damit Flet) zählt Positionen in UTF-16-Einheiten; dafür gibt es
``utf16_to_index``/``index_to_utf16``. Die Oberfläche rechnet um.
"""

from __future__ import annotations

from ..core.inline import TodoStatus, leading_whitespace, parse_list_item

TAB = "\t"
_CHECKBOX = "[ ] "

# (Position im alten Text, Anzahl entfernter Zeichen, eingefügter Text)
Edit = tuple[int, int, str]


def utf16_to_index(text: str, offset: int) -> int:
    """Rechnet eine UTF-16-Position (Flutter) in einen Python-Index um.

    Args:
        text: Der Text.
        offset: Position in UTF-16-Einheiten (Zeichen außerhalb der BMP zählen 2).

    Returns:
        Der Index in ``text`` (höchstens ``len(text)``).
    """
    units = 0
    for index, char in enumerate(text):
        if units >= offset:
            return index
        units += 2 if ord(char) > 0xFFFF else 1
    return len(text)


def index_to_utf16(text: str, index: int) -> int:
    """Rechnet einen Python-Index in eine UTF-16-Position (Flutter) um.

    Args:
        text: Der Text.
        index: Index in ``text``.

    Returns:
        Die Position in UTF-16-Einheiten.
    """
    return sum(2 if ord(char) > 0xFFFF else 1 for char in text[:index])


def _lines(text: str) -> list[tuple[int, int]]:
    """``(anfang, ende)`` jeder Zeile (ohne ``\\n``)."""
    spans, start = [], 0
    for line in text.split("\n"):
        spans.append((start, start + len(line)))
        start += len(line) + 1
    return spans


def _affected(text: str, start: int, end: int) -> list[int]:
    """Indizes der betroffenen Zeilen (siehe Moduldokumentation)."""
    spans = _lines(text)
    if start == end:
        return [next(i for i, (a, b) in enumerate(spans) if a <= start <= b)]
    hits = [i for i, (a, b) in enumerate(spans) if start < b + 1 and end > a]
    return list(range(hits[0], hits[-1] + 1)) if hits else []


def _apply(text: str, start: int, end: int, edits: list[Edit]) -> tuple[str, int, int]:
    """Wendet Edits an und rechnet die Auswahl um.

    Args:
        text: Alter Text.
        start: Auswahlanfang.
        end: Auswahlende.
        edits: Nicht überlappende Edits.

    Returns:
        ``(neuer Text, neuer Anfang, neues Ende)``.
    """
    def moved(position: int) -> int:
        shift = 0
        for at, removed, inserted in edits:
            if at + removed <= position:
                shift += len(inserted) - removed
            elif at < position:  # Position lag im entfernten Bereich
                shift += at - position + len(inserted)
        return position + shift

    out, last = [], 0
    for at, removed, inserted in sorted(edits):
        out += [text[last:at], inserted]
        last = at + removed
    out.append(text[last:])
    return "".join(out), moved(start), moved(end)


def toggle_todo(text: str, start: int | None, end: int | None) -> tuple[str, int | None, int | None]:
    """Macht die Zeilen zu Todos bzw. wieder zu Text.

    Sind alle nicht leeren Zeilen des Bereichs Todos (offen oder abgehakt),
    wird zurückgeschaltet: ``- [ ] x``/``- [x] x`` → ``x`` (der Marker kommt
    nicht zurück). Sonst wird jede Zeile ohne Todo eines: ``x`` → ``- [ ] x``,
    ``- x``/``1. x`` → Checkbox hinter dem Marker. ``[-]`` und andere
    Statuszeichen bleiben unverändert (GRENZE laut FORMAT.md). Die Einrückung
    bleibt immer erhalten.

    Args:
        text: Editortext.
        start: Auswahlanfang oder ``None``.
        end: Auswahlende oder ``None``.

    Returns:
        ``(text, start, end)``; unverändert bei unbekannter Position.
    """
    if start is None or end is None:
        return text, start, end
    spans = _lines(text)
    rows = [(spans[i][0], text[spans[i][0]:spans[i][1]]) for i in _affected(text, start, end)]
    rows = [(offset, line) for offset, line in rows if line.strip()]
    items = [(offset, line, parse_list_item(line)) for offset, line in rows]
    edits: list[Edit] = []
    if items and all(item and item.is_todo for _o, _l, item in items):
        for offset, line, item in items:
            indent = len(leading_whitespace(line))
            edits.append((offset + indent, item.body_start - indent, ""))  # type: ignore[union-attr]
    else:
        for offset, line, item in items:
            if item is None:
                edits.append((offset + len(leading_whitespace(line)), 0, "- " + _CHECKBOX))
            elif item.status is TodoStatus.NONE:
                gap = "" if line[item.body_start - 1:item.body_start].isspace() else " "
                edits.append((offset + item.body_start, 0, gap + _CHECKBOX))
    return _apply(text, start, end, edits)


def indent(text: str, start: int | None, end: int | None, delta: int) -> tuple[str, int | None, int | None]:
    """Rückt die Zeilen des Bereichs um eine Ebene ein (``+1``) oder aus (``-1``).

    Eine Ebene ist ein Tab. Ausrücken entfernt einen führenden Tab oder bis zu
    vier führende Leerzeichen; Zeilen ohne Einrückung bleiben unverändert.

    Args:
        text: Editortext.
        start: Auswahlanfang oder ``None``.
        end: Auswahlende oder ``None``.
        delta: ``+1`` oder ``-1``.

    Returns:
        ``(text, start, end)``; unverändert bei unbekannter Position.
    """
    if start is None or end is None:
        return text, start, end
    spans = _lines(text)
    edits: list[Edit] = []
    for index in _affected(text, start, end):
        offset, stop = spans[index]
        line = text[offset:stop]
        if not line.strip():
            continue
        if delta > 0:
            edits.append((offset, 0, TAB))
        elif line.startswith(TAB):
            edits.append((offset, 1, ""))
        elif line.startswith(" "):
            edits.append((offset, min(4, len(line) - len(line.lstrip(" "))), ""))
    return _apply(text, start, end, edits)


def insert_tag(text: str, start: int | None, end: int | None) -> tuple[str, int | None, int | None]:
    """Fügt ``#`` ein: am Anfang des ausgewählten Wortes bzw. am Zeilenende.

    Bei einer Auswahl kommt ``#`` vor das Wort, in dem die Auswahl beginnt (die
    Auswahl wird nicht ersetzt, sie verschiebt sich um 1). Ohne Auswahl kommt
    ``#`` ans Ende der Caret-Zeile, mit Leerzeichen davor, falls nötig; der
    Caret steht danach hinter ``#``.

    Args:
        text: Editortext.
        start: Auswahlanfang oder ``None``.
        end: Auswahlende oder ``None``.

    Returns:
        ``(text, start, end)``; unverändert bei unbekannter Position oder wenn
        das Wort schon mit ``#`` beginnt.
    """
    if start is None or end is None:
        return text, start, end
    if start != end:
        word = start
        while word > 0 and not text[word - 1].isspace():
            word -= 1
        if text[word:word + 1] == "#":
            return text, start, end
        return _apply(text, start, end, [(word, 0, "#")])
    line_start, line_end = _lines(text)[_affected(text, start, end)[0]]
    line = text[line_start:line_end]
    insert = "#" if not line or line[-1].isspace() else " #"
    new_text, _s, _e = _apply(text, start, end, [(line_end, 0, insert)])
    return new_text, line_end + len(insert), line_end + len(insert)
