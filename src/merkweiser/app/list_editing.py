"""Strukturbewusstes Bearbeiten von Listen im Editor (UI-neutral, für Desktop und Mobile).

Arbeitet wie ``text_tools`` auf ``(text, start, end)`` mit Python-Indizes;
unbekannte Position (``None``) → nichts.

**Einrücken/Ausrücken** (``shift_item``, Nutzerwunsch 2026-10-22):

* Wirkt nur auf Listenpunkte und Todos (bzw. deren Fortsetzungszeilen) und
  verschiebt immer die **erste Zeile** des Punkts. Fortsetzungen bleiben, wie
  sie sind; die Ansicht rückt sie ohnehin unter ihren Punkt.
* Der Punkt nimmt seinen Teilbaum mit (alle folgenden Punkte mit größerer
  Einrückung bis zur nächsten Leerzeile bzw. zum nächsten Punkt mit gleicher
  oder kleinerer Einrückung), in beide Richtungen.
* Eine Ebene sind ``width`` Leerzeichen (Einstellung, 2 oder 4). Eingefügt
  bzw. entfernt wird am Ende des führenden Leerraums; Ausrücken entfernt einen
  Tab oder bis zu ``width`` Leerzeichen.
* Einrücken höchstens bis zur Einrückung des vorigen Punkts derselben Notiz
  plus eine Ebene; gibt es darüber keinen Punkt, wird nicht eingerückt.
  Ausrücken auf Ebene 0 tut nichts (der Punkt bleibt ein Punkt).
* Bei einer Auswahl werden alle berührten Punkte verschoben; Punkte im
  Teilbaum eines anderen berührten Punkts wandern nur einmal (mit ihm).

**Enter** (``continue_list``): Ein in einen Punkt mit Inhalt getippter
Zeilenumbruch beginnt darunter einen neuen leeren Punkt gleicher Art und
Einrückung (Todos immer offen, nummerierte Punkte zählen weiter). In einem
leeren Punkt verschwindet stattdessen der Marker, die Zeile wird leerer Text.

GRENZE(Editor): Codeblöcke werden hier nicht erkannt; ``- x`` in einem
Codeblock gilt im Editor als Listenpunkt.
"""

from __future__ import annotations

from ..core.inline import TodoStatus, indent_columns, leading_whitespace, parse_list_item
from .text_tools import Edit, affected_lines, apply_text_edits, line_spans

INDENT_WIDTHS = (2, 4)


def _cols(line: str) -> int:
    """Einrückung einer Zeile in Spalten (Tabstopps wie im Parser)."""
    return indent_columns(leading_whitespace(line))


def _head_of(lines: list[str], index: int) -> int | None:
    """Erste Zeile des Punkts, zu dem Zeile ``index`` gehört (Punkt selbst oder Fortsetzung).

    Args:
        lines: Zeilen des Editortexts.
        index: Zeilenindex.

    Returns:
        Index der Punktzeile oder ``None`` (Leerzeile, Thema, Text vor dem ersten Punkt).
    """
    for j in range(index, -1, -1):
        if not lines[j].strip():
            return None
        if parse_list_item(lines[j]) is not None:
            return j
    return None


def _previous_item(lines: list[str], head: int) -> int | None:
    """Der nächste Punkt oberhalb in derselben Notiz (bis zur Leerzeile) oder ``None``."""
    for j in range(head - 1, -1, -1):
        if not lines[j].strip():
            return None
        if parse_list_item(lines[j]) is not None:
            return j
    return None


def _subtree(lines: list[str], head: int) -> list[int]:
    """Punktzeilen im Teilbaum von ``head`` (ohne ``head``, ohne Fortsetzungen).

    Args:
        lines: Zeilen des Editortexts.
        head: Zeile des Punkts.

    Returns:
        Indizes der Nachfahren in Reihenfolge.
    """
    level, found = _cols(lines[head]), []
    for j in range(head + 1, len(lines)):
        if not lines[j].strip():
            break
        if parse_list_item(lines[j]) is not None:
            if _cols(lines[j]) <= level:
                break
            found.append(j)
    return found


def _shift_edit(offset: int, line: str, delta: int, width: int) -> Edit | None:
    """Edit für eine Ebene mehr (``+1``) oder weniger (``-1``) am Ende des führenden Leerraums.

    Args:
        offset: Anfang der Zeile im Text.
        line: Die Zeile.
        delta: ``+1`` oder ``-1``.
        width: Leerzeichen je Ebene.

    Returns:
        Der Edit oder ``None`` (Ausrücken ohne Einrückung).
    """
    ws = leading_whitespace(line)
    if delta > 0:
        return offset + len(ws), 0, " " * width
    if not ws:
        return None
    if ws.endswith("\t"):
        return offset + len(ws) - 1, 1, ""
    count = min(width, len(ws) - len(ws.rstrip(" ")))
    return offset + len(ws) - count, count, ""


def _allowed(lines: list[str], head: int, delta: int, width: int) -> bool:
    """Ob der Punkt an ``head`` in diese Richtung verschoben werden darf (siehe Moduldokumentation)."""
    if delta < 0:
        return _cols(lines[head]) > 0
    previous = _previous_item(lines, head)
    if previous is None:
        return False
    return indent_columns(leading_whitespace(lines[head]) + " " * width) <= _cols(lines[previous]) + width


def shift_item(text: str, start: int | None, end: int | None, delta: int,
               width: int = 4) -> tuple[str, int | None, int | None]:
    """Rückt die berührten Punkte samt Teilbaum um eine Ebene ein (``+1``) oder aus (``-1``).

    Args:
        text: Editortext.
        start: Auswahlanfang oder ``None``.
        end: Auswahlende oder ``None``.
        delta: ``+1`` oder ``-1``.
        width: Leerzeichen je Ebene (2 oder 4).

    Returns:
        ``(text, start, end)``; unverändert bei unbekannter Position, ohne
        berührten Punkt oder wenn die Grenze es verbietet.
    """
    if start is None or end is None:
        return text, start, end
    lines, spans = text.split("\n"), line_spans(text)
    heads: list[int] = []
    for index in affected_lines(text, start, end):
        head = _head_of(lines, index)
        if head is not None and head not in heads:
            heads.append(head)
    edits: list[Edit] = []
    covered: set[int] = set()
    for head in heads:
        if head in covered:
            continue
        tree = [head, *_subtree(lines, head)]
        covered.update(tree)
        if not _allowed(lines, head, delta, width):
            continue
        for row in tree:
            edit = _shift_edit(spans[row][0], lines[row], delta, width)
            if edit is not None:
                edits.append(edit)
    return apply_text_edits(text, start, end, edits)


def _inserted_newline(old: str, new: str, caret: int | None) -> int | None:
    """Position, an der genau ein ``\\n`` eingefügt wurde, sonst ``None``.

    Steht der Zeilenumbruch neben einem vorhandenen, ist die Position
    mehrdeutig; dann entscheidet der vorige Caret, sonst die früheste Position.

    Args:
        old: Text vor der Eingabe.
        new: Text nach der Eingabe.
        caret: Caret vor der Eingabe (Python-Index) oder ``None``.

    Returns:
        Index im alten Text oder ``None``.
    """
    if len(new) != len(old) + 1:
        return None
    prefix = 0
    while prefix < len(old) and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while suffix < len(old) and old[-1 - suffix] == new[-1 - suffix]:
        suffix += 1
    candidates = [i for i in range(len(old) - suffix, prefix + 1) if new[i] == "\n"]
    if not candidates:
        return None
    return caret if caret in candidates else candidates[0]


def continue_list(old: str, new: str, caret: int | None = None) -> tuple[str, int] | None:
    """Reagiert auf ein getipptes Enter in einem Listenpunkt oder Todo.

    Args:
        old: Text vor der Eingabe.
        new: Text nach der Eingabe.
        caret: Caret vor der Eingabe (Python-Index) oder ``None``.

    Returns:
        ``(neuer Text, Caret)`` oder ``None``, wenn nichts zu tun ist (kein
        einzelnes Enter, keine Punktzeile, Enter vor dem Inhalt des Punkts,
        ``[-]``-Punkte).
    """
    at = _inserted_newline(old, new, caret)
    if at is None:
        return None
    line_start = old.rfind("\n", 0, at) + 1
    line_end = old.find("\n", at)
    line_end = len(old) if line_end < 0 else line_end
    line = old[line_start:line_end]
    item = parse_list_item(line)
    if item is None or item.status is TodoStatus.OTHER or at - line_start < item.body_start:
        return None
    if not line[item.body_start:].strip():  # leerer Punkt → Marker weg, Zeile wird Text
        return old[:line_start] + old[line_end:], line_start
    marker = item.marker
    if marker[:-1].isdigit():
        marker = f"{int(marker[:-1]) + 1}{marker[-1]}"
    prefix = leading_whitespace(line) + marker + " " + ("[ ] " if item.is_todo else "")
    return new[:at + 1] + prefix + new[at + 1:], at + 1 + len(prefix)
