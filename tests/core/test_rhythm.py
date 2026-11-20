"""Tests für die Rhythmus-Grammatik der Routinen (W9, ``core/rhythm.py``)."""

from datetime import date, timedelta

import pytest

from merkweiser.core.rhythm import (Kind, Options, Rhythm, RhythmError, is_due, next_due, options_text, parse_date_de,
                                    parse_options, parse_rhythm, rhythm_text, split_heading)

MO = date(2026, 11, 16)  # Montag


def due_days(text: str, first: date, count: int) -> list[date]:
    """Fällige Tage in ``count`` Tagen ab ``first``."""
    rhythm = parse_rhythm(text)
    return [first + timedelta(days=i) for i in range(count) if is_due(rhythm, first + timedelta(days=i))]


@pytest.mark.parametrize("text", [
    "täglich", "werktags", "wöchentlich Mo", "wöchentlich Di, Do", "alle 3 Tage ab 17.11.2026",
    "alle 1 Tag ab 17.11.2026", "alle 2 Wochen Mo ab 16.11.2026", "alle 1 Woche Mi, Fr ab 18.11.2026",
    "monatlich 1.", "monatlich 1., 15.", "jährlich 15.09.", "jährlich 29.02.",
])
def test_round_trip_canonical(text: str) -> None:
    """Kanonische Schreibweise liest sich zum selben Rhythmus zurück."""
    rhythm = parse_rhythm(text)
    assert rhythm_text(rhythm) == text and parse_rhythm(rhythm_text(rhythm)) == rhythm


@pytest.mark.parametrize("text, canonical", [
    ("Täglich", "täglich"), ("WÖCHENTLICH di do", "wöchentlich Di, Do"), ("wöchentlich Do,Di,Do", "wöchentlich Di, Do"),
    ("monatlich 15 1", "monatlich 1., 15."), ("jährlich 5.9", "jährlich 05.09."),
    ("alle 2 wochen ab 18.11.2026", "alle 2 Wochen Mi ab 18.11.2026"),  # ohne Wochentag: der des Starts
    ("alle 3 tage ab 1.2.2026", "alle 3 Tage ab 01.02.2026"),
])
def test_lenient_reading(text: str, canonical: str) -> None:
    """Groß-/Kleinschreibung, Trennzeichen und Reihenfolge sind frei; die kanonische Form ist eindeutig."""
    assert rhythm_text(parse_rhythm(text)) == canonical


@pytest.mark.parametrize("text, fragment", [
    ("stündlich", "unbekannt"), ("wöchentlich", "Wochentag fehlt"), ("wöchentlich Xy", "Xy"),
    ("monatlich 32.", "1. bis 31."), ("monatlich", "Tag fehlt"), ("jährlich 30.02.", "gibt es nicht"),
    ("jährlich 31.04.", "gibt es nicht"), ("jährlich 15.9.2026", "TT.MM."), ("alle 3 Tage", "alle 3 Tage ab"),
    ("alle 0 Tage ab 01.01.2026", "Abstand"), ("alle 3 Tage Mo ab 01.01.2026", "keine Wochentage"),
    ("alle 2 Wochen ab 31.02.2026", "gibt es nicht"), ("täglich Mo", "unbekannt"),
])
def test_errors_are_german_and_specific(text: str, fragment: str) -> None:
    """Fehlermeldungen nennen das Problem."""
    with pytest.raises(RhythmError, match=fragment):
        parse_rhythm(text)


def test_weekly_and_workdays() -> None:
    """werktags = Mo–Fr; wöchentlich an den genannten Tagen."""
    assert due_days("werktags", MO, 7) == [MO + timedelta(days=i) for i in range(5)]
    assert due_days("wöchentlich Di, Do", MO, 7) == [date(2026, 11, 17), date(2026, 11, 19)]


def test_every_n_days_phase() -> None:
    """``alle 3 Tage ab S``: S, S+3, …; nichts davor."""
    assert due_days("alle 3 Tage ab 17.11.2026", MO, 10) == [date(2026, 11, 17), date(2026, 11, 20),
                                                              date(2026, 11, 23)]


def test_every_two_weeks_anchor_is_monday_of_start_week() -> None:
    """Start mittwochs: Montag der Startwoche zählt nicht (vor dem Start), die Phase gilt wochenweise."""
    days = due_days("alle 2 Wochen Mo, Mi ab 18.11.2026", MO, 21)
    assert days == [date(2026, 11, 18), date(2026, 11, 30), date(2026, 12, 2)]


def test_monthly_end_of_month() -> None:
    """``monatlich 31.`` → letzter Tag kürzerer Monate; mehrere Tage."""
    rhythm = parse_rhythm("monatlich 31.")
    assert is_due(rhythm, date(2026, 11, 30)) and not is_due(rhythm, date(2026, 11, 29))
    assert is_due(rhythm, date(2026, 2, 28)) and is_due(rhythm, date(2028, 2, 29))
    assert due_days("monatlich 1., 15.", date(2026, 12, 1), 31) == [date(2026, 12, 1), date(2026, 12, 15)]


def test_yearly_leap_day() -> None:
    """``jährlich 29.02.``: im Nicht-Schaltjahr am 28.02."""
    rhythm = parse_rhythm("jährlich 29.02.")
    assert is_due(rhythm, date(2027, 2, 28)) and is_due(rhythm, date(2028, 2, 29))
    assert not is_due(rhythm, date(2028, 2, 28))


def test_next_due_with_skip_and_limit() -> None:
    """``next_due`` überspringt Tage; ohne Treffer in der Grenze ``None``."""
    daily = Rhythm(Kind.TAEGLICH)
    pause = {date(2026, 11, 17), date(2026, 11, 18)}
    assert next_due(daily, MO) == date(2026, 11, 17)
    assert next_due(daily, MO, skip=lambda d: d in pause) == date(2026, 11, 19)
    assert next_due(parse_rhythm("jährlich 01.01."), MO, limit=30) is None


def test_options_and_heading_split() -> None:
    """Klammerteil: Frist (Ein-/Mehrzahl), auch in Pausen, Trenner , oder ;; kanonisch zurück."""
    assert split_heading("wöchentlich Mo (Frist 3 Tage)") == ("wöchentlich Mo", "Frist 3 Tage")
    assert split_heading("täglich") == ("täglich", None)
    assert parse_options("Frist 1 Tag; auch in Pausen") == Options(1, True)
    assert options_text(Options(3, True)) == "Frist 3 Tage, auch in Pausen" and options_text(Options()) == ""
    assert parse_options(options_text(Options(1, False))) == Options(1, False)
    for bad in ("Frist 0 Tage", "Frist 2 Tage, Frist 3 Tage", "bald"):
        with pytest.raises(RhythmError):
            parse_options(bad)
    with pytest.raises(RhythmError):
        split_heading("täglich (Frist 2 Tage) mehr")


def test_parse_date_de() -> None:
    """TT.MM.JJJJ, ein- oder zweistellig; ungültige Daten sind Fehler."""
    assert parse_date_de("1.2.2026") == date(2026, 2, 1)
    for bad in ("2026-02-01", "31.02.2026"):
        with pytest.raises(RhythmError):
            parse_date_de(bad)
