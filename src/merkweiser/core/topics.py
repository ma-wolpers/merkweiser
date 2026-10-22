"""Themen einer Notiz lesen und vergleichen (nur lesend, ``docs/FORMAT.md``, „Thema“).

* ``topic_key``: Vergleichsschlüssel einer Themenzeile (getrimmt, ``…`` → ``...``).
  Gleiche Themen heißt gleicher Schlüssel; es gibt keine weitere Normalisierung.
* **Leeres Thema:** Der Schlüssel enthält außer echten Tags und Leerraum nichts
  oder nur ``...``. Die Notiz *hat* dann ein Thema (Tags gelten und vererben
  sich), angezeigt wird aber „kein Thema“.
* **Tag-Thema:** ein leeres Thema mit mindestens einem Tag (z. B. ``#schule``).
* ``find_topic_note`` sucht die **eine** Notiz mit einem Schlüssel; bei keiner
  oder mehreren gibt es kein Ergebnis (Garantie 8: nie raten). Reines ``...``
  wird nie gefunden, weil themenlose Notizen nicht zusammengeführt werden.
"""

from __future__ import annotations

from .document import Document, ParsedNote
from .inline import find_tags
from .outline import NodeKind

EMPTY_TOPIC = "..."
_ELLIPSIS = "…"


def topic_key(line: str) -> str:
    """Vergleichsschlüssel einer Themenzeile.

    Args:
        line: Themenzeile (ohne Zeilenende).

    Returns:
        Die getrimmte Zeile, ``…`` durch ``...`` ersetzt.
    """
    return line.strip().replace(_ELLIPSIS, EMPTY_TOPIC)


def _without_tags(key: str) -> str:
    """Entfernt alle echten Tags (nicht in Code oder Links) aus einem Schlüssel.

    Args:
        key: Themenschlüssel.

    Returns:
        Der Rest ohne Tags, getrimmt.
    """
    rest, last = [], 0
    for tag in find_tags(key):
        rest.append(key[last:tag.start])
        last = tag.end
    rest.append(key[last:])
    return "".join(rest).strip()


def is_empty_topic(line: str) -> bool:
    """Prüft, ob eine Themenzeile ein leeres Thema ist (``...`` und/oder nur Tags).

    Args:
        line: Themenzeile.

    Returns:
        ``True`` für ``...``, ``…``, ``#a #b``, ``... #a``; ``False`` für Text
        und für ``#`` in Code oder Links.
    """
    return _without_tags(topic_key(line)) in ("", EMPTY_TOPIC)


def is_tag_topic(line: str) -> bool:
    """Prüft, ob eine Themenzeile ein leeres Thema mit mindestens einem Tag ist.

    Args:
        line: Themenzeile.

    Returns:
        ``True`` z. B. für ``#schule`` und ``... #schule``.
    """
    return is_empty_topic(line) and bool(find_tags(topic_key(line)))


def mergeable(line: str | None) -> bool:
    """Ob Notizen mit dieser Themenzeile zusammengeführt werden dürfen.

    Args:
        line: Themenzeile oder ``None`` (Notiz ohne Thema).

    Returns:
        ``True`` für normale Themen und Tag-Themen; ``False`` ohne Thema und
        für reines ``...``.
    """
    return line is not None and (not is_empty_topic(line) or is_tag_topic(line))


def topic_line(doc: Document, note: ParsedNote) -> str | None:
    """Erste Zeile des (nicht impliziten) Themas einer Notiz.

    Args:
        doc: Dokument der Notiz.
        note: Die Notiz.

    Returns:
        Die Themenzeile oder ``None``, wenn die Notiz kein Thema hat.
    """
    roots = note.outline.roots
    if not roots or roots[0].kind is not NodeKind.TOPIC or roots[0].implicit or not roots[0].lines:
        return None
    return doc.line_text(roots[0].lines[0])


def find_topic_note(doc: Document, key: str) -> ParsedNote | None:
    """Die einzige Notiz eines Dokuments mit diesem Themenschlüssel.

    Args:
        doc: Dokument (z. B. die Zieldatei eines Verschiebens).
        key: Gesuchter Schlüssel (aus ``topic_key``).

    Returns:
        Die Notiz bei genau einem Treffer, sonst ``None``. Nicht
        zusammenführbare Schlüssel (reines ``...``) liefern immer ``None``.
    """
    if not mergeable(key):
        return None
    hits = [n for n in doc.notes if (line := topic_line(doc, n)) is not None and topic_key(line) == key]
    return hits[0] if len(hits) == 1 else None
