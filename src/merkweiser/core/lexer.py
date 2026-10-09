"""Gemeinsame Inline-Tokenisierung einer Zeile.

Damit Tag-, Checkbox- und Dringlichkeitserkennung nicht jeweils eigene Regeln
für Inline-Code, Links und URLs haben, liefert dieser Lexer **eine** Zerlegung
in Spalten-Spans:

* ``CODE``: Inline-Code (Backtick-Folge bis zur nächsten Folge gleicher Länge).
* ``WIKILINK``: ``[[…]]`` und ``![[…]]``.
* ``LINK_URL``: Ziel eines Markdown-Links ``](…)``, Autolinks ``<…>`` und
  nackte URLs (``https://…``, ``obsidian://…``, ``mailto:…`` …).
* ``TEXT``: alles andere (inklusive Link-Beschriftungen).

Tags werden später nur in ``TEXT`` gesucht. ``==…==``-Hervorhebungen sind
normaler Text; die Dringlichkeit prüft ``inline`` am Inhaltsanfang.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_MD_LINK_RE = re.compile(r"!?\[([^\[\]\n]*)\]\(([^()\s]*(?:\([^()\s]*\)[^()\s]*)*)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\)")
_AUTOLINK_RE = re.compile(r"<[A-Za-z][A-Za-z0-9+.\-]{1,31}:[^\s<>]*>")
_BARE_URL_RE = re.compile(r"(?:https?|ftp|file|obsidian)://[^\s<>]+|mailto:[^\s<>]+")


class TokenKind(Enum):
    """Art eines Inline-Tokens."""

    TEXT = "text"
    CODE = "code"
    WIKILINK = "wikilink"
    LINK_URL = "link_url"


@dataclass(frozen=True)
class Token:
    """Ein Inline-Token als Spaltenbereich ``[start, end)`` einer Zeile.

    Attributes:
        kind: Art des Tokens.
        start: Erste Spalte (Zeichenindex).
        end: Spalte hinter dem letzten Zeichen.
    """

    kind: TokenKind
    start: int
    end: int


def tokenize(text: str) -> tuple[Token, ...]:
    """Zerlegt eine Zeile in Inline-Tokens.

    Aufeinanderfolgender Text wird zu einem ``TEXT``-Token zusammengefasst.

    Args:
        text: Zeileninhalt ohne Zeilenende.

    Returns:
        Lückenlose, nicht überlappende Tokens in Spaltenreihenfolge.
    """
    tokens: list[Token] = []
    pos = text_start = 0
    while pos < len(text):
        found = _special_at(text, pos)
        if found is None:
            pos += _literal_backticks(text, pos) or 1
            continue
        _flush_text(tokens, text_start, pos)
        for token in found:
            if token.kind is TokenKind.TEXT:
                _flush_text(tokens, token.start, token.end)
            else:
                tokens.append(token)
        pos = text_start = found[-1].end
    _flush_text(tokens, text_start, len(text))
    return tuple(tokens)


def text_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Liefert nur die ``TEXT``-Bereiche einer Zeile.

    Args:
        text: Zeileninhalt.

    Returns:
        ``(start, end)``-Paare der Textbereiche.
    """
    return tuple((t.start, t.end) for t in tokenize(text) if t.kind is TokenKind.TEXT)


def _special_at(text: str, pos: int) -> list[Token] | None:
    """Erkennt ein besonderes Token, das an ``pos`` beginnt.

    Args:
        text: Zeileninhalt.
        pos: Aktuelle Spalte.

    Returns:
        Ein oder mehrere Tokens (Link: Beschriftung + URL) oder ``None``.
    """
    char = text[pos]
    if char == "`":
        return _code_span(text, pos)
    if text.startswith("[[", pos) or text.startswith("![[", pos):
        close = text.find("]]", pos)
        return [Token(TokenKind.WIKILINK, pos, close + 2)] if close != -1 else None
    if char in "![":
        match = _MD_LINK_RE.match(text, pos)
        if match:
            # Beschriftung inklusive der eckigen Klammern ist Text, ab „](“ URL.
            label_end = match.end(1)
            return [Token(TokenKind.TEXT, pos, label_end + 1),
                    Token(TokenKind.LINK_URL, label_end + 1, match.end())]
    if char == "<":
        match = _AUTOLINK_RE.match(text, pos)
        if match:
            return [Token(TokenKind.LINK_URL, pos, match.end())]
    if pos == 0 or not (text[pos - 1].isalnum() or text[pos - 1] == "_"):
        match = _BARE_URL_RE.match(text, pos)
        if match:
            return [Token(TokenKind.LINK_URL, pos, match.end())]
    return None


def _code_span(text: str, pos: int) -> list[Token] | None:
    """Sucht zu einer Backtick-Folge die schließende Folge gleicher Länge.

    Args:
        text: Zeileninhalt.
        pos: Beginn der Backtick-Folge.

    Returns:
        Das ``CODE``-Token oder ``None``, wenn keine passende Folge existiert.
    """
    run = _literal_backticks(text, pos)
    search = pos + run
    while True:
        close = text.find("`" * run, search)
        if close == -1:
            return None
        close_run = _literal_backticks(text, close)
        if close_run == run:
            return [Token(TokenKind.CODE, pos, close + run)]
        search = close + close_run


def _literal_backticks(text: str, pos: int) -> int:
    """Länge der Backtick-Folge ab ``pos`` (0, wenn dort kein Backtick steht)."""
    end = pos
    while end < len(text) and text[end] == "`":
        end += 1
    return end - pos


def _flush_text(tokens: list[Token], start: int, end: int) -> None:
    """Hängt einen ``TEXT``-Bereich an oder verlängert das vorige ``TEXT``-Token.

    Args:
        tokens: Bisherige Tokens (wird verändert).
        start: Beginn des Textbereichs.
        end: Ende des Textbereichs.
    """
    if end <= start:
        return
    if tokens and tokens[-1].kind is TokenKind.TEXT and tokens[-1].end == start:
        tokens[-1] = Token(TokenKind.TEXT, tokens[-1].start, end)
    else:
        tokens.append(Token(TokenKind.TEXT, start, end))
