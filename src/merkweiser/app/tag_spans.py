"""Anzeigetext in Stücke zerlegen: normaler Text und antippbare Tags (W2).

Die Erkennung ist dieselbe wie beim Parsen (``inline.find_tags``): Tags am
Wortanfang, außerhalb von Code und Link-Zielen, nicht nur aus Ziffern. Damit
ist jeder antippbare Tag auch ein Tag, nach dem die Tag-Seite sucht.
"""

from __future__ import annotations

from ..core.inline import find_tags


def text_parts(text: str) -> list[tuple[str, str | None]]:
    """Zerlegt einen Anzeigetext in Text- und Tag-Stücke.

    Args:
        text: Anzeigetext einer Zeile (z. B. ``Row.text``).

    Returns:
        ``(stück, tag_schlüssel)``; ``tag_schlüssel`` ist ``None`` für normalen
        Text, sonst der Vergleichsschlüssel (``Tag.key``, ohne ``#``). Die Stücke
        ergeben aneinandergehängt wieder genau ``text``.
    """
    parts: list[tuple[str, str | None]] = []
    pos = 0
    for tag in find_tags(text):
        if tag.start > pos:
            parts.append((text[pos:tag.start], None))
        parts.append((text[tag.start:tag.end], tag.key))
        pos = tag.end
    if pos < len(text):
        parts.append((text[pos:], None))
    return parts
