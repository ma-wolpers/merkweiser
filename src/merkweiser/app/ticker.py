"""Höchstens ein Aktualisierungs-Task für die Laufzeitanzeige im Zeit-Tab (Y12, PLAN-SPAETERE-SCHRITTE.md).

* ``start`` bricht einen vorhandenen Task ab und startet **genau einen** neuen.
* ``stop`` bricht ab (Tabwechsel, Unterseite, Dialog, App im Hintergrund).
* Der Task aktualisiert nur Anzeige-Controls; er schreibt nie. Gespeichert wird
  weiterhin nur der Startstempel.

UI-neutral: ``run`` startet eine Coroutine-Funktion und liefert ein Objekt mit
``cancel()`` (in Flet ``page.run_task``, in Tests eine Attrappe).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class Ticker:
    """Verwaltet den einen Aktualisierungs-Task.

    Args:
        run: Startet ``coroutine_function()`` und liefert ein Handle mit ``cancel()``.
    """

    def __init__(self, run: Callable[[Callable[[], Awaitable[None]]], Any]) -> None:
        self._run = run
        self._handle: Any = None

    @property
    def active(self) -> bool:
        """``True``, solange ein Task läuft."""
        return self._handle is not None

    def start(self, tick: Callable[[], Awaitable[None]]) -> None:
        """Startet den Task neu (ein evtl. laufender wird vorher abgebrochen).

        Args:
            tick: Coroutine-Funktion, die bis zum Abbruch regelmäßig die Anzeige aktualisiert.
        """
        self.stop()
        self._handle = self._run(tick)

    def stop(self) -> None:
        """Bricht den laufenden Task ab (ohne Task: nichts)."""
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
