# Changelog

Alle sichtbaren Änderungen an Merkweiser stehen hier (Format: Keep a Changelog). Interne Änderungen stehen in `docs/DEVELOPMENT_LOG.md`.

## [Unreleased]

### Added

- **Android-App (erste Fassung):**
  - Einrichtung mit „Zugriff auf alle Dateien“ und Wahl des Notizordners (auch per eingetipptem Pfad).
  - Tab **Heute**: neue Notiz schreiben; die heutigen Notizen mit abhakbaren Todos, Dringend-Stern und „auf morgen verschieben“.
  - Tab **Todos**: alle Todos mit Filter nach Status und Tags (UND/ODER).
  - Tab **Suche**: Teilstring oder regulärer Ausdruck.
  - Tab **Konflikte**: Syncthing-Konflikte werden beim Start automatisch zusammengeführt; übrige Fälle mit „Hauptdatei behalten“, „Konfliktversion übernehmen“ oder „Beide behalten“.
  - Tab **Einstellungen**: Projekt-Präfix, Prüfintervall, Ordner wechseln; Anzeige der **Schreibgarantie** des Notizordners (ist sie eingeschränkt, steht das auch beim Start).
  - Speichern funktioniert auch auf Speicher ohne Hardlinks (z. B. SD-Karte); Merkweiser prüft beim Öffnen jedes Notizordners, welche sichere Schreibweise dort geht.
  - Anleitung in `docs/kurzanleitung.md`.

- Repository-Gerüst mit Konzept (`docs/KONZEPT.md`), freigegebenem Plan (`docs/PLAN.md`) und Formatbeschreibung (`docs/FORMAT.md`).
