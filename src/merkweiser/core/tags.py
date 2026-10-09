"""Effektive Tags und Projekte: reine Auswertung über einem fertigen Notizbaum.

Interpretiert **keine** Struktur selbst: ``outline`` liefert Eltern-Beziehungen,
``inline`` die expliziten Tags. Regel (``docs/FORMAT.md``):

    effektiv(Knoten) = explizit(Knoten) ∪ effektiv(Eltern)

Weil Listenpunkte am Eltern-Punkt bzw. Thema hängen, Themen an der
umschließenden Überschrift und Überschriften an der übergeordneten, ergibt
das genau „explizit ∪ Eltern-Punkt ∪ aktuelles Thema ∪ umschließende
Überschriften“. Ein neues Thema beendet die Vererbung automatisch, weil
spätere Punkte am neuen Thema hängen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .inline import project_name
from .outline import Outline

DEFAULT_PROJECT_PREFIX = "projekt"


@dataclass(frozen=True)
class NodeTags:
    """Tags und Projekte eines Knotens.

    Attributes:
        explicit: Schlüssel (ohne Groß-/Kleinschreibung) der eigenen Tags.
        effective: Schlüssel aller wirksamen Tags (eigene und geerbte).
        explicit_projects: Projektnamen direkt am Knoten (Originalschreibweise).
        effective_projects: Alle wirksamen Projektnamen.
    """

    explicit: frozenset[str]
    effective: frozenset[str]
    explicit_projects: tuple[str, ...]
    effective_projects: tuple[str, ...]

    @property
    def inherited_projects(self) -> tuple[str, ...]:
        """Projekte, die nur geerbt sind (für die Anzeige „geerbt“)."""
        own = {p.casefold() for p in self.explicit_projects}
        return tuple(p for p in self.effective_projects if p.casefold() not in own)


def compute_tags(outline: Outline, project_prefix: str = DEFAULT_PROJECT_PREFIX) -> tuple[NodeTags, ...]:
    """Berechnet für jeden Knoten explizite und effektive Tags und Projekte.

    Args:
        outline: Fertiger Notizbaum.
        project_prefix: Einstellbares Projekt-Präfix.

    Returns:
        Ein ``NodeTags`` pro Knoten, gleiche Reihenfolge wie ``outline.nodes``.
    """
    result: list[NodeTags] = []
    for node in outline.nodes:  # Eltern stehen vor Kindern → ein Durchlauf genügt
        explicit = frozenset(tag.key for tag in node.tags)
        projects = _unique(p for p in (project_name(t, project_prefix) for t in node.tags) if p)
        if node.parent is None:
            effective, effective_projects = explicit, projects
        else:
            parent = result[node.parent]
            effective = explicit | parent.effective
            effective_projects = _unique((*projects, *parent.effective_projects))
        result.append(NodeTags(explicit, effective, projects, effective_projects))
    return tuple(result)


def _unique(names) -> tuple[str, ...]:
    """Entfernt Duplikate (ohne Groß-/Kleinschreibung), erste Schreibweise gewinnt.

    Args:
        names: Iterierbare Projektnamen.

    Returns:
        Eindeutige Namen in ursprünglicher Reihenfolge.
    """
    seen: set[str] = set()
    out = []
    for name in names:
        if name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return tuple(out)
