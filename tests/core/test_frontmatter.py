"""Tests für den Frontmatter-Kern (S5/Y4) und die Tätigkeitsnamen (R2)."""

import unicodedata
from datetime import datetime, timedelta, timezone

import pytest

from merkweiser.core.activities import is_valid, same_name, valid_activity
from merkweiser.core.cleanup import is_empty_day_text
from merkweiser.core.document import parse_document
from merkweiser.core.frontmatter import (KEEP, NONE, OK, OPAQUE, OPEN, Damaged, FrontmatterError, Stamp, minutes,
                                         parse_bytes, set_own, stamp_of)

BERLIN = timezone(timedelta(hours=2))
STAMP = Stamp(datetime(2026, 10, 22, 8, 15, tzinfo=BERLIN), "Orga")
BODY = b"Thema\n- [ ] a\n"


# --- Lesen -----------------------------------------------------------------------------


def test_flat_entries_lists_blocks_and_colons_in_values() -> None:
    raw = (b"---\ntags:\n  - schule\n- direkt\nurl: https://x.de/a:b\ntext: |\n  Zeile 1\n\n  Zeile 3\n"
           b"zeit_Orga: 90\n---\n" + BODY)
    fm = parse_bytes(raw)
    assert fm.state == OK
    assert [(e.key, e.start, e.end) for e in fm.entries] == [("tags", 1, 4), ("url", 4, 5), ("text", 5, 9),
                                                             ("zeit_Orga", 9, 10)]
    assert fm.by_key("url")[0].value == "https://x.de/a:b"
    assert minutes(fm) == ({"Orga": 90}, [])


@pytest.mark.parametrize("head, reason", [
    (b"# Kommentar\n", "nicht lesbare"), (b'"quoted": 1\n', "nicht lesbare"), (b"? frage\n", "nicht lesbare"),
    (b"\tx: 1\n", "Tabulator"), (b"  eingerueckt\n", "Folgezeile"), (b"a: 1\na: 2\n", "doppelter"),
    (b"{flow: 1}\n", "nicht lesbare")])
def test_unsupported_structures_are_opaque(head: bytes, reason: str) -> None:
    fm = parse_bytes(b"---\n" + head + b"---\n" + BODY)
    assert fm.state == OPAQUE and reason in fm.reason


def test_open_and_missing_frontmatter() -> None:
    assert parse_bytes(b"---\nzeit_Orga: 5\n" + BODY).state == OPEN
    assert parse_bytes(BODY).state == NONE


def test_duplicate_own_minutes_read_as_maximum_and_damaged_are_reported() -> None:
    fm = parse_bytes(b"---\nzeit_Orga: 30\nzeit_Orga: 45\nzeit_Kurs: viel\n---\n")
    assert minutes(fm) == ({"Orga": 45}, ["zeit_Kurs"])


def test_stamp_is_one_record() -> None:
    """Y5: beide Schlüssel gültig → Stamp; nur einer, doppelt, ohne Offset, ungültiger Name → beschädigt."""
    ok = parse_bytes(b"---\nmessung_start: 2026-10-22T08:15:00+02:00\nmessung_taetigkeit: Orga\n---\n")
    assert stamp_of(ok) == STAMP
    assert stamp_of(parse_bytes(b"---\na: 1\n---\n")) is None
    for broken in (b"messung_start: 2026-10-22T08:15:00+02:00\n",
                   b"messung_start: 2026-10-22T08:15:00\nmessung_taetigkeit: Orga\n",
                   b"messung_start: gestern\nmessung_taetigkeit: Orga\n",
                   b"messung_start: 2026-10-22T08:15:00+02:00\nmessung_taetigkeit: Or:ga\n",
                   b"messung_start: 2026-10-22T08:15:00+02:00\nmessung_taetigkeit: Orga\nmessung_taetigkeit: B\n"):
        assert isinstance(stamp_of(parse_bytes(b"---\n" + broken + b"---\n")), Damaged), broken


# --- Schreiben, byte-genau ---------------------------------------------------------


def test_new_frontmatter_on_file_without_one_and_empty_file() -> None:
    assert set_own(BODY, {"Orga": 30}) == b"---\nzeit_Orga: 30\n---\n" + BODY
    assert set_own(b"", {"Orga": 30}) == b"---\nzeit_Orga: 30\n---\n"
    assert set_own(BODY, {"Orga": None}) == BODY  # nichts zu tun


def test_foreign_keys_bom_crlf_and_missing_final_newline_stay_byte_exact() -> None:
    raw = b"\xef\xbb\xbf---\r\ntags: [a, b]\r\nzeit_Orga: 10\r\nnotiz: x: y\r\n---\r\nText"
    out = set_own(raw, {"Orga": 25, "Kurs": 5})
    assert out == b"\xef\xbb\xbf---\r\ntags: [a, b]\r\nzeit_Orga: 25\r\nnotiz: x: y\r\nzeit_Kurs: 5\r\n---\r\nText"


def test_stamp_set_and_remove_and_duplicates_collapse() -> None:
    raw = b"---\nzeit_Orga: 30\nzeit_Orga: 45\n---\n" + BODY
    out = set_own(raw, {"Orga": 50}, STAMP)
    assert out == (b"---\nzeit_Orga: 50\nmessung_start: 2026-10-22T08:15:00+02:00\nmessung_taetigkeit: Orga\n---\n"
                   + BODY)
    assert set_own(out, {}, None) == b"---\nzeit_Orga: 50\n---\n" + BODY
    assert set_own(out, {}, KEEP) == out


def test_frontmatter_becoming_empty_is_removed_only_if_merkweiser_emptied_it() -> None:
    assert set_own(b"---\nzeit_Orga: 5\n---\n" + BODY, {"Orga": None}) == BODY
    assert set_own(b"---\nx: 1\nzeit_Orga: 5\n---\n" + BODY, {"Orga": None}) == b"---\nx: 1\n---\n" + BODY


@pytest.mark.parametrize("raw", [b"---\n# Kommentar\n---\n" + BODY, b"---\nzeit_Orga: 5\n" + BODY,
                                 b"---\na: 1\na: 2\n---\n", b"\xff\xfe---\n"])
def test_unsafe_frontmatter_is_never_rewritten(raw: bytes) -> None:
    with pytest.raises(FrontmatterError):
        set_own(raw, {"Orga": 5})


def test_damaged_own_values_are_not_silently_overwritten() -> None:
    with pytest.raises(FrontmatterError):
        set_own(b"---\nzeit_Orga: viel\n---\n", {"Orga": 5})
    assert set_own(b"---\nzeit_Orga: viel\na: 1\n---\n", {"Orga": None}) == b"---\na: 1\n---\n"
    damaged_stamp = b"---\nmessung_start: x\n---\n"
    with pytest.raises(FrontmatterError):
        set_own(damaged_stamp, {}, STAMP)
    assert set_own(damaged_stamp, {}, None) == b""


def test_body_parsing_and_cleanup_ignore_own_frontmatter() -> None:
    raw = set_own(BODY, {"Orga": 30})
    doc = parse_document(raw, "")
    assert len(doc.notes) == 1 and doc.line_text(doc.notes[0].note.content.start) == "Thema"
    assert not is_empty_day_text(b"---\nzeit_Orga: 30\n---\n")


# --- Namen (R2) ------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Orga", "Unterricht Mathe", "Klasse 7b", "Café", "Fußball", "Übung-2_x", "Ärger"])
def test_allowed_names(name: str) -> None:
    assert valid_activity(f"  {name} ") == unicodedata.normalize("NFC", name)


@pytest.mark.parametrize("name", ["", "a\nb", "a\tb", "a\x00b", "a:b", "#tag", '"x"', "a'b", "a  b", "[x]", "x" * 41,
                                  "́a", "a​b"])
def test_rejected_names(name: str) -> None:
    with pytest.raises(ValueError):
        valid_activity(name)


def test_nfd_equals_nfc_and_casefold_duplicates() -> None:
    nfd = unicodedata.normalize("NFD", "Café")
    assert valid_activity(nfd) == "Café" and len(valid_activity(nfd)) == 4
    assert same_name("orga", "Orga") and same_name(nfd, "café") and not same_name("Orga", "Org")
    assert not is_valid("a:b") and is_valid("b")
