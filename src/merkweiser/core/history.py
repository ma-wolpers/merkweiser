"""Beobachtungs-Historie: nur anhängend, liefert ausschließlich Merge-Vorschläge.

Regeln (PLAN.md, „Beobachtungs-Historie“):

* Einträge ``<sha1>.md`` sind **unveränderlich** und dedupliziert.
* ``record`` (bei jedem Lesen bzw. nach eigenem Schreiben) hängt neue
  Versionen an und aktualisiert nur Metadaten: ``last_seen`` der aktuellen
  Version, ``ersetzt_seit`` der zuvor aktuellen. Ein Scan löscht oder
  überschreibt nie einen Eintrag; dadurch zerstört erneutes Einlesen keine
  ältere Basis.
* Aufbewahrung „30 Tage“ zählt ab ``ersetzt_seit``, also wie lange eine
  Version schon **veraltet** ist. Die aktuelle Version, die neuesten 5 und
  geschützte Einträge offener Konflikte bleiben immer.
* ``candidate_base``: neueste Version mit ``last_seen`` vor einem Zeitpunkt,
  die sich von den Konfliktseiten unterscheidet. GRENZE: reine Heuristik über
  lokale Beobachtungszeiten und unsynchronisierte Geräteuhren. Sie behauptet
  keine Kausalität und wird **nie** für einen Auto-Merge verwendet.
* Fehlt ein Eintrag (z. B. nach Absturz), werden nur Vorschläge schwächer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..ports.clock import Clock
from .appdata import VaultData, write_json_atomic


@dataclass(frozen=True)
class Version:
    """Ein beobachteter Stand einer Datei.

    Attributes:
        sha1: Inhalts-Hash.
        first_seen: Erste Beobachtung (UTC).
        last_seen: Letzte Beobachtung als aktueller Stand (UTC).
        replaced_since: Seit wann veraltet (UTC) oder ``None`` für die aktuelle Version.
    """

    sha1: str
    first_seen: datetime
    last_seen: datetime
    replaced_since: datetime | None


class History:
    """Historie aller Dateien eines Vaults.

    Args:
        data: App-Daten-Verzeichnisse des Vaults.
        clock: Zeitquelle (Wanduhr; Zeitpunkte werden in UTC gespeichert).
    """

    def __init__(self, data: VaultData, clock: Clock) -> None:
        self._dir = data.history_dir
        self._clock = clock

    def record(self, relpath: str, raw: bytes | None) -> None:
        """Hält den aktuell beobachteten Stand einer Datei fest.

        Args:
            relpath: Datei relativ zum Vault.
            raw: Aktueller Inhalt oder ``None``, wenn die Datei fehlt.
        """
        now = self._now()
        folder = self._folder(relpath)
        index = self._load(relpath)
        current = index.get("current")
        sha = hashlib.sha1(raw).hexdigest() if raw is not None else None
        entries = index["entries"]
        if sha == current:
            if sha is not None:
                entries[sha]["last_seen"] = now
        else:
            if current is not None and entries[current].get("replaced_since") is None:
                entries[current]["replaced_since"] = now
            if sha is not None:
                blob = folder / f"{sha}.md"
                if not blob.exists():
                    folder.mkdir(parents=True, exist_ok=True)
                    with open(blob, "xb") as handle:  # unveränderlich, nie überschreiben
                        handle.write(raw)  # type: ignore[arg-type]
                entry = entries.setdefault(sha, {"first_seen": now})
                entry.update(last_seen=now, replaced_since=None)
            index["current"] = sha
        write_json_atomic(folder / "index.json", index)

    def versions(self, relpath: str) -> list[Version]:
        """Alle bekannten Versionen einer Datei, neueste ``last_seen`` zuerst.

        Args:
            relpath: Datei relativ zum Vault.

        Returns:
            Versionen.
        """
        entries = self._load(relpath)["entries"]
        out = [Version(sha, _dt(e["first_seen"]), _dt(e["last_seen"]),
                       _dt(e["replaced_since"]) if e.get("replaced_since") else None) for sha, e in entries.items()]
        return sorted(out, key=lambda v: v.last_seen, reverse=True)

    def read(self, relpath: str, sha1: str) -> bytes:
        """Liest den Inhalt einer gespeicherten Version.

        Args:
            relpath: Datei relativ zum Vault.
            sha1: Inhalts-Hash.

        Returns:
            Die Bytes.
        """
        return (self._folder(relpath) / f"{sha1}.md").read_bytes()

    def candidate_base(self, relpath: str, before: datetime, exclude: set[str]) -> str | None:
        """Heuristische Kandidatenbasis für Merge-**Vorschläge** (nie Auto-Merge).

        Args:
            relpath: Hauptdatei.
            before: Zeitpunkt aus dem Konfliktnamen (zeitzonenbewusst).
            exclude: Hashes der Konfliktseiten.

        Returns:
            Hash der neuesten passenden Version oder ``None``.
        """
        for version in self.versions(relpath):
            if version.last_seen < before.astimezone(timezone.utc) and version.sha1 not in exclude:
                return version.sha1
        return None

    def prune(self, relpath: str, protected: set[str], days: int = 30, keep: int = 5) -> list[str]:
        """Löscht veraltete Versionen nach der Aufbewahrungsregel.

        Args:
            relpath: Datei relativ zum Vault.
            protected: Hashes, die offene Konflikte referenzieren.
            days: Aufbewahrung ab ``replaced_since``.
            keep: Anzahl der neuesten Versionen, die immer bleiben.

        Returns:
            Gelöschte Hashes.
        """
        index = self._load(relpath)
        limit = self._clock.now().astimezone(timezone.utc) - timedelta(days=days)
        newest = {v.sha1 for v in self.versions(relpath)[:keep]}
        removed = []
        for sha, entry in list(index["entries"].items()):
            since = entry.get("replaced_since")
            if sha == index.get("current") or sha in newest or sha in protected or not since or _dt(since) > limit:
                continue
            (self._folder(relpath) / f"{sha}.md").unlink(missing_ok=True)
            del index["entries"][sha]
            removed.append(sha)
        if removed:
            write_json_atomic(self._folder(relpath) / "index.json", index)
        return removed

    def _folder(self, relpath: str) -> Path:
        """Ordner einer Datei: ``history/<sha1(relpath)>``."""
        return self._dir / hashlib.sha1(relpath.encode("utf-8")).hexdigest()

    def _load(self, relpath: str) -> dict:
        """Lädt den Index einer Datei (leer, wenn noch keiner existiert)."""
        path = self._folder(relpath) / "index.json"
        if not path.exists():
            return {"relpath": relpath, "current": None, "entries": {}}
        return json.loads(path.read_text(encoding="utf-8"))

    def _now(self) -> str:
        """Aktueller Zeitpunkt als UTC-ISO-Zeichenkette."""
        return self._clock.now().astimezone(timezone.utc).isoformat()


def _dt(value: str) -> datetime:
    """Liest einen gespeicherten ISO-Zeitpunkt."""
    return datetime.fromisoformat(value)
