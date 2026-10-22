"""Tätigkeitsnamen für den Zeit-Tracker: sichere Allowlist (R2, PLAN-SPAETERE-SCHRITTE.md 1.8).

Ein Name wird zu einem YAML-Schlüssel ``zeit_<Name>`` und zum Wert von
``messung_taetigkeit``. Statt YAML-Sonderzeichen aufzuzählen, ist nur
**erlaubt**:

* Buchstaben jeder Schrift (Unicode-Kategorie ``L*``, also auch Umlaute,
  Akzente und ``ß``),
* Kombinationszeichen (``M*``) direkt nach einem Buchstaben bzw. einem
  anderen Kombinationszeichen,
* Ziffern (``Nd``), ``-`` und ``_``,
* einzelne Leerzeichen zwischen anderen Zeichen.

Vorher wird nach **NFC** normalisiert und Leerraum am Rand entfernt; so wird
„Café“ in NFC und NFD gleich behandelt. Länge 1–40. Damit sind Steuerzeichen,
Zeilenumbrüche, Tabs, ``:``, ``#``, Anführungszeichen, Klammern usw.
ausgeschlossen. Der Vergleich „gibt es schon“ nutzt zusätzlich ``casefold``.
"""

from __future__ import annotations

import unicodedata

MAX_LENGTH = 40
DEFAULT_ACTIVITY = "Orga"


def valid_activity(name: str) -> str:
    """Prüft einen Tätigkeitsnamen und liefert ihn normalisiert.

    Args:
        name: Eingabe.

    Returns:
        Der Name in NFC ohne Rand-Leerraum.

    Raises:
        ValueError: mit deutscher Begründung, wenn der Name nicht erlaubt ist.
    """
    text = unicodedata.normalize("NFC", name).strip()
    if not 1 <= len(text) <= MAX_LENGTH:
        raise ValueError(f"Der Name muss 1 bis {MAX_LENGTH} Zeichen lang sein.")
    previous = ""
    for char in text:
        category = unicodedata.category(char)
        if char == " ":
            if previous == " ":
                raise ValueError("Bitte nur einzelne Leerzeichen.")
        elif category.startswith("M"):
            if not previous or not (unicodedata.category(previous).startswith(("L", "M"))):
                raise ValueError("Ungültiges Zeichen im Namen.")
        elif not (category.startswith("L") or category == "Nd" or char in "-_"):
            shown = repr(char) if not char.isprintable() else f"„{char}“"
            raise ValueError(f"Nicht erlaubt: {shown}. Erlaubt sind Buchstaben, Ziffern, Leerzeichen, - und _.")
        previous = char
    return text


def same_name(a: str, b: str) -> bool:
    """``True``, wenn zwei Namen als derselbe gelten (NFC, ohne Groß-/Kleinschreibung)."""
    norm = lambda s: unicodedata.normalize("NFC", s).strip().casefold()  # noqa: E731
    return norm(a) == norm(b)


def is_valid(name: str) -> bool:
    """``True``, wenn ``valid_activity`` den Namen akzeptiert (für nur lesend angezeigte Altnamen)."""
    try:
        valid_activity(name)
    except ValueError:
        return False
    return True
