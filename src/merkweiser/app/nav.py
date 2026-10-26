"""Navigation mit eigenem Unterseiten-Stapel je Tab (W4, PLAN-SPAETERE-SCHRITTE.md 1.6).

``Nav`` ist die **einzige Wahrheit** über die angezeigte Seite. Die Oberfläche
leitet daraus bei jedem Zeichnen ab, was sie zeigt, und meldet nur Ereignisse
zurück (Tab gewählt, Zurück). Es gibt keinen zweiten Stapel aus Flet-Views.

Regeln:

* Jeder Tab hat seinen eigenen Stapel. Ein Tabwechsel löscht die Stapel der
  anderen Tabs **nicht**: Wer in „Todos“ eine Tag-Seite öffnet, zur Suche
  wechselt und zurückkommt, sieht die Tag-Seite wieder.
* ``back()`` wirkt nur auf den aktuellen Tab. An der Wurzel eines anderen Tabs
  wechselt es zum Start-Tab (``home``); an dessen Wurzel liefert es ``False``
  (dann darf das System die App verlassen).
* Erneutes Wählen des aktiven Tabs springt zu dessen Wurzel.
* Dialoge sind keine Stapel-Einträge; sie schließt das System selbst.
* Seiten sind **Daten** (``PageRef``), keine Controls; sie werden immer frisch
  gerendert.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..core.patch import Target


@dataclass(frozen=True)
class PageRef:
    """Eine Unterseite als Datum.

    Attributes:
        kind: Art, z. B. ``tag`` (Tag-Seite), ``konflikte``, ``backups``.
        arg: Parameter der Seite, z. B. der Tag-Schlüssel oder ein Dateipfad.
    """

    kind: str
    arg: str = ""


def note_arg(target: Target) -> str:
    """Argument der Unterseite ``notiz`` für das Todo an ``target`` (einzige Kodierung, W7).

    Args:
        target: Adresse des Todos (Datei, Zeile, erwarteter Text).

    Returns:
        JSON ``[relpath, zeile, text]``; robust gegen beliebige Zeichen im Text.
    """
    return json.dumps([target.relpath, target.line_no, target.expected_text], ensure_ascii=False)


def parse_note_arg(arg: str) -> Target | None:
    """Liest das Argument von ``note_arg`` zurück (einzige Dekodierung).

    Args:
        arg: ``PageRef.arg``.

    Returns:
        Das Target oder ``None`` bei ungültigem Argument (die Seite zeigt dann einen Hinweis).
    """
    try:
        relpath, line_no, text = json.loads(arg)
    except (ValueError, TypeError):
        return None
    if not (isinstance(relpath, str) and isinstance(line_no, int) and isinstance(text, str)) or line_no < 0:
        return None
    return Target(relpath, line_no, text)


class Nav:
    """Tab-Auswahl und Unterseiten-Stapel je Tab.

    Args:
        tabs: Anzahl der Tabs.
        home: Index des Start-Tabs (Ziel von „Zurück“ an der Wurzel anderer Tabs).
    """

    def __init__(self, tabs: int, home: int = 0) -> None:
        self.home = home
        self.current = home
        self._stacks: list[list[PageRef]] = [[] for _ in range(tabs)]

    def select(self, tab: int) -> None:
        """Wählt einen Tab; der aktive Tab springt zu seiner Wurzel.

        Args:
            tab: Index des Tabs.
        """
        if tab == self.current:
            self._stacks[tab].clear()
        self.current = tab

    def show_root(self, tab: int) -> None:
        """Zeigt die Wurzel eines Tabs (z. B. „Tag“ mit gewähltem Datum aus der Suche).

        Args:
            tab: Index des Tabs.
        """
        self._stacks[tab].clear()
        self.current = tab

    def push(self, page: PageRef) -> None:
        """Öffnet eine Unterseite im aktuellen Tab.

        Args:
            page: Die Seite.
        """
        self._stacks[self.current].append(page)

    def back(self) -> bool:
        """Eine Seite zurück im aktuellen Tab.

        Returns:
            ``True``, wenn Merkweiser zurückgegangen ist; ``False`` an der Wurzel
            des Start-Tabs (dann gehört „Zurück“ dem System).
        """
        stack = self._stacks[self.current]
        if stack:
            stack.pop()
            return True
        if self.current != self.home:
            self.current = self.home
            return True
        return False

    def top(self) -> PageRef | None:
        """Oberste Unterseite des aktuellen Tabs oder ``None`` (Wurzel)."""
        stack = self._stacks[self.current]
        return stack[-1] if stack else None

    def depth(self, tab: int | None = None) -> int:
        """Anzahl offener Unterseiten eines Tabs (Standard: aktueller Tab)."""
        return len(self._stacks[self.current if tab is None else tab])
