"""Tests für das verlustfreie Source-Modell (Roundtrip-Invariante)."""

import pytest

from merkweiser.core.source import UTF8_BOM, Encoding, SourceText, split_lines

ROUNDTRIP_CASES = {
    "leer": b"",
    "lf": b"Thema\n- [ ] a\n",
    "crlf": b"Thema\r\n- [ ] a\r\n",
    "gemischt": b"a\r\nb\nc\rd\r\n",
    "ohne_schluss_newline": b"Thema\n- [ ] a",
    "nur_newlines": b"\n\n\n",
    "bom": UTF8_BOM + b"Thema #tag\n",
    "emoji_tabs_raender": "  eingerückt\n\t- [ ] \U0001F600 x   \n\n".encode(),
    "steuerzeichen_bleiben": "a\x0bb\x1cc d\n".encode(),
}


@pytest.mark.parametrize("raw", ROUNDTRIP_CASES.values(), ids=ROUNDTRIP_CASES.keys())
def test_roundtrip_is_byte_identical(raw: bytes) -> None:
    """Parsen und unverändert Serialisieren ergibt exakt die Rohbytes."""
    assert SourceText.from_bytes(raw).to_bytes() == raw


def test_lines_keep_their_own_eol() -> None:
    """Jede Zeile behält ihr Zeilenende; die letzte Zeile ohne Umbruch hat ``""``."""
    lines = split_lines("a\r\nb\nc")
    assert [(line.text, line.eol) for line in lines] == [("a", "\r\n"), ("b", "\n"), ("c", "")]


def test_trailing_newline_creates_no_extra_line() -> None:
    """``"a\\n"`` ist genau eine Zeile, eine leere Datei hat keine Zeilen."""
    assert len(split_lines("a\n")) == 1
    assert split_lines("") == ()


def test_only_cr_lf_and_crlf_split_lines() -> None:
    """Vertikaler Tab, Gruppentrenner und U+2028 trennen keine Zeilen."""
    assert len(split_lines("a\x0bb\x1cc d")) == 1


@pytest.mark.parametrize("raw, encoding", [
    (b"abc", Encoding.UTF8),
    (UTF8_BOM + b"abc", Encoding.UTF8_BOM),
    (b"\xff\xfea\x00", Encoding.UNSUPPORTED),
    (b"abc \xe4 def", Encoding.UNSUPPORTED),
])
def test_encoding_detection(raw: bytes, encoding: Encoding) -> None:
    """UTF-8 ± BOM ist schreibbar, UTF-16-BOM und ungültige Bytes nicht."""
    source = SourceText.from_bytes(raw)
    assert source.encoding is encoding
    assert source.writable is (encoding is not Encoding.UNSUPPORTED)


def test_unsupported_encoding_is_readable_and_serializes_raw() -> None:
    """Ungültige Bytes werden mit Ersatzzeichen lesbar, ``to_bytes`` liefert ``raw``."""
    raw = b"Thema \xe4\n- [ ] a\n"
    source = SourceText.from_bytes(raw)
    assert "�" in source.lines[0].text
    assert source.to_bytes() == raw


@pytest.mark.parametrize("raw, eol", [
    (b"a\r\nb\r\nc\n", "\r\n"),
    (b"a\nb\r\n", "\n"),
    (b"abc", "\n"),
])
def test_dominant_eol(raw: bytes, eol: str) -> None:
    """Das häufigste Zeilenende gewinnt, bei Gleichstand oder ohne Umbruch ``\\n``."""
    assert SourceText.from_bytes(raw).dominant_eol() == eol
