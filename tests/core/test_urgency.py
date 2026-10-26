"""Ampel-Dringlichkeit (W7): Grammatik, Anzeige ohne Markierung, Stufenwechsel ohne Textverlust."""

import pytest

from merkweiser.core.document import parse_document
from merkweiser.core.edits import set_urgency
from merkweiser.core.inline import Urgency, parse_list_item, strip_urgency, urgency
from merkweiser.core.patch import Target


@pytest.mark.parametrize("body, level", [
    ("==a==", Urgency.GELB),
    ("==🔴a==", Urgency.ROT),
    ("==🔴 a==", Urgency.ROT),
    ("  ==a== #t", Urgency.GELB),
    ("==🔴==", Urgency.GELB),       # ohne weiteren Text: Gelb mit Text „🔴“, nichts geht verloren
    ("== ==", Urgency.GELB),
    ("a == b", Urgency.NONE),
    ("x = 1 ==", Urgency.NONE),
    ("==offen", Urgency.NONE),
    ("====", Urgency.NONE),
    ("", Urgency.NONE),
])
def test_grammar(body: str, level: Urgency) -> None:
    assert urgency(body) == level


def test_list_item_and_urgent_property() -> None:
    item = parse_list_item("- [ ] ==🔴Antrag== #t")
    assert item is not None and item.urgency == Urgency.ROT and item.urgent
    assert parse_list_item("- [ ] a == b").urgency == Urgency.NONE


@pytest.mark.parametrize("body, shown", [
    ("==🔴 Antrag== #t", "Antrag #t"),
    ("==Kisten== #keller", "Kisten #keller"),
    ("x = 1 ==", "x = 1 =="),          # andere Gleichheitszeichen bleiben
    ("==a = b== rest", "a = b rest"),
    ("==🔴==", "🔴"),
    ("Plain", "Plain"),
])
def test_strip_removes_only_a_recognised_marker(body: str, shown: str) -> None:
    assert strip_urgency(body) == shown


def _set(text: str, line: str, level: Urgency) -> bytes:
    doc = parse_document(text.encode())
    no = text.replace("\r\n", "\n").split("\n").index(line)
    return set_urgency(doc, Target("x.md", no, line), level)


BASE = "Thema\r\n- [ ] Kisten packen #keller\r\nEnde"


def test_cycle_through_all_levels_keeps_text_and_crlf() -> None:
    gelb = _set(BASE, "- [ ] Kisten packen #keller", Urgency.GELB)
    assert gelb == b"Thema\r\n- [ ] ==Kisten packen== #keller\r\nEnde"
    rot = _set(gelb.decode(), "- [ ] ==Kisten packen== #keller", Urgency.ROT)
    assert rot == "Thema\r\n- [ ] ==🔴Kisten packen== #keller\r\nEnde".encode()
    back = _set(rot.decode(), "- [ ] ==🔴Kisten packen== #keller", Urgency.NONE)
    assert back == BASE.encode()


@pytest.mark.parametrize("start, level, expected", [
    ("- [ ] Feuer", Urgency.ROT, "- [ ] ==🔴Feuer=="),
    ("- [ ] ==🔴 Feuer== #t", Urgency.GELB, "- [ ] ==Feuer== #t"),   # das eine Leerzeichen gehört zur Markierung
    ("- [ ] ==🔴Feuer==", Urgency.NONE, "- [ ] Feuer"),
    ("- [ ] == x==", Urgency.ROT, "- [ ] ==🔴  x=="),               # Leerzeichen am Textanfang bleibt erhalten
    ("- [ ] ==🔴  x==", Urgency.GELB, "- [ ] == x=="),
    ("- [x] Erledigt", Urgency.GELB, "- [x] ==Erledigt=="),
])
def test_transitions_are_lossless(start: str, level: Urgency, expected: str) -> None:
    assert _set(f"T\n{start}\n", start, level) == f"T\n{expected}\n".encode()


def test_same_level_is_idempotent_and_invalid_inputs_are_refused() -> None:
    text = "T\n- [ ] ==a==\n"
    assert _set(text, "- [ ] ==a==", Urgency.GELB) == text.encode()
    with pytest.raises(ValueError):
        _set("T\n- [ ] #nur-tag\n", "- [ ] #nur-tag", Urgency.GELB)
    with pytest.raises(ValueError):  # die Markierung würde am inneren == enden und Text zerschneiden
        _set("T\n- [ ] a == b\n", "- [ ] a == b", Urgency.GELB)


def test_limit_text_starting_with_red_mark_reads_as_red() -> None:
    """GRENZE(Ampel): Ein Text, der selbst mit 🔴 beginnt, wird als Rot gelesen."""
    after = _set("T\n- [ ] 🔴 Feuer\n", "- [ ] 🔴 Feuer", Urgency.GELB)
    assert after == "T\n- [ ] ==🔴 Feuer==\n".encode()
    assert urgency("==🔴 Feuer==") == Urgency.ROT
