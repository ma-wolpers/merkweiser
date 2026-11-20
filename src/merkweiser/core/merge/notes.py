"""Notiz-Zuordnung zweier Fassungen für die notizweise Konfliktauflösung (W8).

Notizen haben keine IDs. Die Zuordnung zwischen Hauptdatei (A) und
Konfliktversion (B) ist deshalb eine **Ausrichtung von Notizfolgen** über
``align`` mit immer gröberen Schlüsseln; sie ist deterministisch und hält
je Seite die Reihenfolge (monoton):

* **L0** – identische Notizen (ganzer Text) sind Anker,
* **L1** – Notizen, die sich nur in Häkchen ``[ ]``/``[-]``/``[x]``/``[X]`` unterscheiden,
* **L2** – Notizen mit gleicher erster Zeile (Thema; Häkchen maskiert),
* **L3** – eine übrig gebliebene 1×1-Lücke, wenn beide Notizen mindestens
  eine gleiche (maskierte, nicht leere) Zeile haben.

Alles andere ist „nur in A“ bzw. „nur in B“ (A zuerst, wie ``merge2``). Die
Zuordnung gruppiert **nur die Anzeige**; angewendet wird ausschließlich, was
der Nutzer je Notiz wählt.

Notizgrenzen kommen allein aus ``blocks.analyze`` (alleinige Instanz). Häkchen
werden außerhalb von Codeblöcken maskiert; ``[-]`` und andere Zeichen bleiben
Inhalt.

GRENZE(Notizwahl): Eine verschobene Notiz erscheint als „nur in A“ plus „nur
in B“ (die Anzeige weist darauf hin).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from ..blocks import analyze
from ..inline import STATUS_OF_CHAR, parse_list_item
from ..source import Line
from .align import align
from .model import Cert, status_rule

#: Platzhalter für ein maskiertes Häkchen (kommt in Notiztext nie vor).
STATUS_MASK = "\0"

Pair = tuple[int | None, int | None]


@dataclass(frozen=True)
class BodyNotes:
    """Rumpf einer Fassung, zerlegt in Notizen und Lücken.

    Attributes:
        lines: Rumpfzeilen ohne Zeilenende (wie ``merge.frontmatter.split`` sie liefert).
        keys: Je Zeile der Vergleichsschlüssel (Häkchen maskiert, Codezeilen unverändert).
        spans: Notizen als ``[start, end)`` in ``lines``, in Dateireihenfolge.
    """

    lines: tuple[str, ...]
    keys: tuple[str, ...]
    spans: tuple[tuple[int, int], ...]

    def note(self, index: int) -> tuple[str, ...]:
        """Zeilen der Notiz ``index``."""
        start, end = self.spans[index]
        return self.lines[start:end]

    def note_keys(self, index: int) -> tuple[str, ...]:
        """Vergleichsschlüssel der Zeilen von Notiz ``index``."""
        start, end = self.spans[index]
        return self.keys[start:end]

    def gap(self, k: int) -> tuple[str, ...]:
        """Zeilen zwischen Notiz ``k-1`` und ``k`` (Leerzeilen, ``---``).

        Args:
            k: ``0`` = vor der ersten Notiz, ``len(spans)`` = nach der letzten.

        Returns:
            Die Zeilen der Lücke (ohne Notizen: der ganze Rumpf).
        """
        start = self.spans[k - 1][1] if k > 0 else 0
        end = self.spans[k][0] if k < len(self.spans) else len(self.lines)
        return self.lines[start:end]


@dataclass(frozen=True)
class Row:
    """Ein Zeilenabschnitt innerhalb einer zugeordneten Notiz.

    Attributes:
        a: Zeilen aus A.
        b: Zeilen aus B.
        cert: ``Cert.R1`` (nur Häkchen offen/verpasst/erledigt verschieden: Todo-Wahl),
            ``Cert.R2`` (nur ``[x]``/``[X]``) oder ``None`` (gleich bzw. Lücke).
    """

    a: tuple[str, ...]
    b: tuple[str, ...]
    cert: Cert | None = None

    @property
    def same(self) -> bool:
        """``True``, wenn der Abschnitt in beiden Fassungen byte-gleich ist."""
        return self.cert is None and self.a == self.b


def status_key(line: str) -> str:
    """Vergleichsschlüssel einer Zeile: Todo-Statuszeichen (``" "``, ``x``, ``X``, ``-``) maskiert.

    Args:
        line: Zeile ohne Zeilenende (außerhalb von Code).

    Returns:
        Die Zeile, bei Todos mit ``STATUS_MASK`` an der Stelle des Statuszeichens.
    """
    item = parse_list_item(line)
    if item is None or item.status_col is None or line[item.status_col] not in STATUS_OF_CHAR:
        return line
    return line[:item.status_col] + STATUS_MASK + line[item.status_col + 1:]


def body_notes(body: Sequence[str]) -> BodyNotes:
    """Zerlegt Rumpfzeilen in Notizen (über ``blocks.analyze``).

    Vorangestellt wird eine Leerzeile, damit ein ``---`` am Rumpfanfang nicht als
    Frontmatter gilt (der Kopf ist schon abgetrennt); sie beendet keine Notiz,
    die es nicht gibt, und wird wieder herausgerechnet.

    Args:
        body: Rumpfzeilen ohne Zeilenende.

    Returns:
        Notizen, Lücken und Vergleichsschlüssel.
    """
    lines = tuple(body)
    layout = analyze(tuple(Line(no, text, "\n") for no, text in enumerate(("",) + lines)))
    keys = tuple(text if layout.in_code(no + 1) else status_key(text) for no, text in enumerate(lines))
    spans = tuple((n.span.start - 1, n.span.end - 1) for n in layout.notes)
    return BodyNotes(lines, keys, spans)


def _whole(notes: BodyNotes, i: int) -> str:
    """L0: ganzer Notiztext."""
    return "\n".join(notes.note(i))


def _masked(notes: BodyNotes, i: int) -> str:
    """L1: Notiztext mit maskierten Häkchen."""
    return "\n".join(notes.note_keys(i))


def _topic(notes: BodyNotes, i: int) -> str:
    """L2: erste Zeile (Thema), Häkchen maskiert."""
    return notes.note_keys(i)[0].strip()


_LEVELS: tuple[Callable[[BodyNotes, int], str], ...] = (_whole, _masked, _topic)


def pair_notes(a: BodyNotes, b: BodyNotes) -> list[Pair]:
    """Ordnet die Notizen von A und B einander zu (L0–L3, siehe Modul-Docstring).

    Args:
        a: Hauptdatei.
        b: Konfliktversion.

    Returns:
        ``(i, j)`` für zugeordnete Notizen, ``(i, None)`` nur in A, ``(None, j)``
        nur in B – in Anzeigereihenfolge, je Seite aufsteigend, jede Notiz genau einmal.
    """
    return _pair(a, b, list(range(len(a.spans))), list(range(len(b.spans))), 0)


def _pair(a: BodyNotes, b: BodyNotes, ai: list[int], bi: list[int], level: int) -> list[Pair]:
    """Rekursive Zuordnung eines Teilbereichs mit Schlüsselstufe ``level``."""
    if not ai or not bi:
        return [(i, None) for i in ai] + [(None, j) for j in bi]
    if level == len(_LEVELS):
        if len(ai) == 1 and len(bi) == 1 and _share_line(a, ai[0], b, bi[0]):
            return [(ai[0], bi[0])]
        return [(i, None) for i in ai] + [(None, j) for j in bi]
    key = _LEVELS[level]
    out: list[Pair] = []
    for region in align([[key(a, i) for i in ai], [key(b, j) for j in bi]]):
        (s1, e1), (s2, e2) = region.ranges
        if region.sync:
            out.append((ai[s1], bi[s2]))
        else:
            out += _pair(a, b, ai[s1:e1], bi[s2:e2], level + 1)
    return out


def _share_line(a: BodyNotes, i: int, b: BodyNotes, j: int) -> bool:
    """L3: mindestens eine gleiche, nicht leere (maskierte) Zeile."""
    return bool({k for k in a.note_keys(i) if k.strip()} & set(b.note_keys(j)))


def note_rows(a_lines: Sequence[str], a_keys: Sequence[str],
              b_lines: Sequence[str], b_keys: Sequence[str]) -> tuple[Row, ...]:
    """Zeilenabschnitte zweier zugeordneter Notizen.

    Ausgerichtet wird über die maskierten Schlüssel; eine Synchronzeile, deren
    Text sich unterscheidet, unterscheidet sich also nur im Häkchen (R1 oder R2).

    Args:
        a_lines: Zeilen der Notiz in A.
        a_keys: Deren Schlüssel.
        b_lines: Zeilen der Notiz in B.
        b_keys: Deren Schlüssel.

    Returns:
        Abschnitte in Reihenfolge; gleiche Zeilen und Häkchen-Paare einzeln, sonst Lücken.
    """
    rows: list[Row] = []
    for region in align([list(a_keys), list(b_keys)]):
        (s1, e1), (s2, e2) = region.ranges
        a_part, b_part = tuple(a_lines[s1:e1]), tuple(b_lines[s2:e2])
        rule = status_rule(a_part[0], b_part[0]) if region.sync and a_part != b_part else None
        rows.append(Row(a_part, b_part, rule[0] if rule else None))
    return tuple(rows)
