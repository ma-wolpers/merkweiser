# Changelog

Alle sichtbaren Änderungen an Merkweiser stehen hier (Format: Keep a Changelog). Interne Änderungen stehen in `docs/DEVELOPMENT_LOG.md`.

## [Unreleased]

### Fixed

- Änderungen sind nach 10 Sekunden endgültig abgeschlossen (vorher 2 Minuten). Wird die App früher geschlossen, schließt der nächste Start sie ab, statt von vorn zu warten; versteckte Sicherungsdateien `.NAME.mw-….old` bleiben nicht mehr liegen.
- Schnelles Ab- und wieder Enthaken eines Todos legte unnötige Konfliktdateien (`….sync-conflict-…-MERKWEISER….md`) an, auch wenn die App gleich danach geschlossen wurde.

### Added

- **Android-App (erste Fassung):**
  - Einrichtung mit „Zugriff auf alle Dateien“ und Wahl des Notizordners (auch per eingetipptem Pfad).
  - Tab **Heute**: neue Notiz schreiben; die heutigen Notizen mit abhakbaren Todos, Dringend-Stern und **Verschieben** (Schnellwahl morgen, übermorgen, nächster Montag, in einer Woche, oder ein Datum im Kalender); jede Notiz lässt sich **bearbeiten** und (nach Rückfrage) **löschen**.
  - Wurde eine Datei zwischendurch verändert und landet deine Änderung deshalb als Konfliktdatei, sagt die App das sofort.
  - Tab **Todos**: alle Todos mit Filter nach Status und Tags (UND/ODER).
  - Tab **Suche**: Teilstring oder regulärer Ausdruck.
  - Tab **Konflikte**: Syncthing-Konflikte werden beim Start automatisch zusammengeführt. Übrige Fälle zeigen, woher die Konfliktversion stammt, und beide Fassungen im Vergleich (rot nur in der Hauptdatei, grün nur in der Konfliktversion); Entscheidung per „Hauptdatei behalten“, „Konfliktversion übernehmen“ oder „Zusammenführen“, jeweils mit Erklärung. Bei widersprüchlichen Änderungen lässt sich **jeder Abschnitt einzeln** entscheiden (Hauptdatei, Konfliktversion, beide oder selbst bearbeitet). Die Art des Konflikts steht verständlich auf Deutsch da. Darunter die Liste **„Automatisch zusammengeführt“** mit Vergleich vorher/nachher und **„Rückgängig“**; eine so wiederhergestellte Konfliktversion wird danach nie wieder automatisch zusammengeführt.
  - Tab **Einstellungen**: Projekt-Präfix, Prüfintervall, Ordner wechseln; Anzeige der **Schreibgarantie** des Notizordners (ist sie eingeschränkt, steht das auch beim Start).
  - Speichern funktioniert auch auf Speicher ohne Hardlinks (z. B. SD-Karte); Merkweiser prüft beim Öffnen jedes Notizordners, welche sichere Schreibweise dort geht.
  - **Diagnosebericht** (Einstellungen): schreibt den Zustand der App ohne Notizinhalte als Textdatei in einen wählbaren Ordner, z. B. einen Syncthing-Ordner.
  - Anleitung in `docs/kurzanleitung.md`.

- Repository-Gerüst mit Konzept (`docs/KONZEPT.md`), freigegebenem Plan (`docs/PLAN.md`) und Formatbeschreibung (`docs/FORMAT.md`).
