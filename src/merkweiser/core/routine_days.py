"""Routinen-Instanzen in Tagesdateien planen (W9): rein, ohne Schreibzugriff.

Jede Funktion nimmt das frisch gelesene ``Document`` einer Tagesdatei und
liefert neue Bytes. Sie ist damit ein ``build`` für ``step_ops.run_step``, das
bei fremden Änderungen auf neuem Stand einfach erneut plant.

* ``present``: Steht eine Instanz schon in irgendeiner Notiz ihres Themas
  (egal ob offen, erledigt oder verpasst, auch mit anderen Tags oder anderer
  Ampel)? Das macht das Eintragen idempotent, auch nach vorzeitigem Abhaken
  und nach einem Abbruch zwischen Tagesdatei und Merkpunkt.
* ``plan_day``: fehlende Instanzen unter ihr Thema schreiben (Verschiebe-Regel
  ``move_plan.insert_under_topic``).
* ``expire_lines``: abgelaufene Instanzen auf verpasst setzen (``edits.set_status``).
"""

from __future__ import annotations

from collections.abc import Sequence

from .document import Document, parse_document
from .edits import NotATodoError, set_status
from .inline import TodoStatus
from .move_plan import insert_under_topic
from .patch import StaleTargetError, Target
from .routines import instance_key
from .topics import topic_key, topic_notes


def present(doc: Document, topic: str, body: str) -> bool:
    """Steht ein Todo mit demselben ``instance_key`` in einer Notiz dieses Themas?

    Args:
        doc: Tagesdatei.
        topic: Notiz-Thema der Instanz.
        body: Regeltext.

    Returns:
        ``True``, wenn die Instanz schon eingetragen ist (jeder Todo-Zustand zählt).
    """
    key = instance_key(body)
    for note in topic_notes(doc, topic_key(topic)):
        for node in note.outline.items():
            if node.item is not None and node.item.is_todo and not doc.layout.in_code(node.lines[0]):
                if instance_key(doc.line_text(node.lines[0])[node.item.body_start:]) == key:
                    return True
    return False


def missing(doc: Document, entries: Sequence[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Die Einträge, deren Instanz noch nicht in der Tagesdatei steht.

    Args:
        doc: Tagesdatei.
        entries: ``(thema, regeltext, zeile)`` je Instanz.

    Returns:
        Die fehlenden Einträge in Eingabereihenfolge.
    """
    return [entry for entry in entries if not present(doc, entry[0], entry[1])]


def plan_day(doc: Document, entries: Sequence[tuple[str, str, str]]) -> bytes:
    """Schreibt die fehlenden Instanzen eines Tages, je Thema als ein Block.

    Gibt es genau eine Notiz des Themas, kommen die Zeilen an ihr Ende, sonst
    entsteht eine neue Notiz ``Thema`` + Zeilen am Dateiende. Themen werden
    in der Reihenfolge ihres ersten Eintrags bearbeitet.

    Args:
        doc: Frisch gelesene Tagesdatei (auch leer).
        entries: ``(thema, regeltext, zeile)``; ``zeile`` ist die fertige
            Instanzzeile (``Occurrence.line``).

    Returns:
        Neue Bytes; unverändert, wenn alles schon da ist.
    """
    todo = missing(doc, entries)
    topics = list(dict.fromkeys(topic for topic, _body, _line in todo))
    for topic in topics:
        lines = tuple(line for t, _body, line in todo if t == topic)
        doc = parse_document(insert_under_topic(doc, topic, lines))
    return doc.source.to_bytes()


def expire_lines(doc: Document, targets: Sequence[Target]) -> bytes:
    """Setzt die Zielzeilen auf verpasst; inzwischen veränderte Ziele werden übersprungen.

    Args:
        doc: Frisch gelesene Tagesdatei.
        targets: Offene ``#wdh``-Todos, deren Frist abgelaufen ist.

    Returns:
        Neue Bytes (nur Statuszeichen geändert).
    """
    for target in targets:
        try:
            doc = parse_document(set_status(doc, target, TodoStatus.MISSED))
        except (StaleTargetError, NotATodoError):
            continue
    return doc.source.to_bytes()
