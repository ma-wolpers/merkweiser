# Changelog

Alle sichtbaren Änderungen an Merkweiser stehen hier (Format: Keep a Changelog). Interne Änderungen stehen in `docs/DEVELOPMENT_LOG.md`.

## [Unreleased]

### Changed

- **Verschieben von Todos:** Es entsteht keine Notiz „Verschoben aus …“ mehr. Ist das Todo das einzige seiner Notiz, wandert die ganze Notiz mit, und am alten Tag bleibt nichts zurück. Sonst wandert das Todo mit dem Thema seiner Notiz. Gibt es am Zieltag schon genau eine Notiz mit demselben Thema, landet es dort unten. Verschieben auf denselben Tag wird abgelehnt.
- **Gemeinsamer Tag beim Verschieben:** Hat die Notiz weitere Todos, fragt Merkweiser vorher nach und bietet an, Todo und Überpunkt einen gemeinsamen Tag oder Projekttag zu geben, damit du sie wiederfindest. Gibt es den Tag schon, erscheint ein Hinweis. Haben beide schon ein gemeinsames Projekt, heißt der Knopf „Mit bestehendem Tag verschieben“. Ein vorhandenes anderes Projekt wird nie überschrieben.
- **Leeres Thema:** Eine Themenzeile aus nur `...` oder nur Tags (z. B. `#schule`) wird als „kein Thema“ angezeigt, mit ihren Tags. Die Tags gelten weiter für die Todos darunter.
- **Notizformat:** Jede Leerzeile beendet jetzt eine Notiz; `---` ist nicht mehr nötig (vorhandene `---` trennen weiter). Jede Notiz hat höchstens ein Thema. Text direkt unter einem Listenpunkt gehört zu diesem Punkt, auch ohne Einrückung. Überschriften (`#`, `##` …) sind normaler Text; Tags darin gelten weiter. Neue Notizen werden mit einer Leerzeile statt mit `---` angehängt. Bestehende Dateien bleiben unverändert, werden aber nach diesen Regeln gelesen (Details in `docs/FORMAT.md`).
- **Leere Datumsdateien** (nur Leerraum und `---`) werden beim Start automatisch entfernt, mit Backup.

### Fixed

- Beim Bearbeiten einer Notiz überdeckte das Textfeld mit offener Tastatur „Abbrechen“ und „Speichern“. Das Feld ist jetzt höchstens 8 Zeilen hoch (danach scrollt es), der Dialog lässt sich scrollen; das Feld für neue Notizen ist höchstens 6 Zeilen hoch.

- Wer in Obsidian kurz nach einer Änderung durch Merkweiser in derselben Notiz weiterschreibt, bekommt keine überflüssige Konfliktdatei mehr. Merkweiser prüft jetzt, ob seine Änderung in der Datei noch enthalten ist; Weitertippen in derselben Zeile zählt nicht als Verlust.
- In der Notizansicht fehlten Erläuterungen unter dem Thema und Fortsetzungszeilen unter Todos und Listenpunkten. Jetzt: Thema fett, Erläuterung darunter in deutlich schwächerer Schrift, Listenpunkte mit „•“ auf derselben Textkante wie Todos, Fortsetzungen bündig darunter.
- Im Dark Mode waren die farbig hinterlegten Zeilen im Konfliktvergleich unlesbar (helle Schrift auf hellem Grün bzw. Rot).
- Änderungen sind nach 10 Sekunden endgültig abgeschlossen (vorher 2 Minuten). Wird die App früher geschlossen, schließt der nächste Start sie ab, statt von vorn zu warten; versteckte Sicherungsdateien `.NAME.mw-….old` bleiben nicht mehr liegen.
- Schnelles Ab- und wieder Enthaken eines Todos legte unnötige Konfliktdateien (`….sync-conflict-…-MERKWEISER….md`) an, auch wenn die App gleich danach geschlossen wurde.

### Added

- **Einfüge-Knöpfe beim Schreiben und Bearbeiten von Notizen:** Checkbox (macht die Zeile zum Todo bzw. wieder zu Text), Einrücken, Ausrücken und `#` (vor das markierte Wort bzw. ans Zeilenende). Sie wirken auf die Zeile mit dem Cursor bzw. auf alle markierten Zeilen.

- **Android-App (erste Fassung):**
  - Einrichtung mit „Zugriff auf alle Dateien“ und Wahl des Notizordners (auch per eingetipptem Pfad).
  - Tab **Tag** (vorher „Heute“): Mit ◀/▶ oder über das Datum (Kalender) lässt sich jeder Tag ansehen; beim Öffnen der App ist immer heute gewählt, „Heute“ springt zurück. Eine Datumsdatei entsteht erst, wenn du an diesem Tag eine Notiz speicherst. Neue Notiz schreiben; die Notizen des Tages mit abhakbaren Todos, Dringend-Stern und **Verschieben** (Schnellwahl morgen, übermorgen, nächster Montag, in einer Woche, oder ein Datum im Kalender); jede Notiz lässt sich **bearbeiten** und (nach Rückfrage) **löschen**.
  - Wurde eine Datei zwischendurch verändert und landet deine Änderung deshalb als Konfliktdatei, sagt die App das sofort.
  - Tab **Todos**: alle Todos mit Filter nach Status und Tags (UND/ODER).
  - Tab **Suche**: Teilstring oder regulärer Ausdruck.
  - Tab **Konflikte**: Syncthing-Konflikte werden beim Start automatisch zusammengeführt. Übrige Fälle zeigen, woher die Konfliktversion stammt, und beide Fassungen im Vergleich (rot nur in der Hauptdatei, grün nur in der Konfliktversion); Entscheidung per „Hauptdatei behalten“, „Konfliktversion übernehmen“ oder „Zusammenführen“, jeweils mit Erklärung. Bei widersprüchlichen Änderungen lässt sich **jeder Abschnitt einzeln** entscheiden (Hauptdatei, Konfliktversion, beide oder selbst bearbeitet). Die Art des Konflikts steht verständlich auf Deutsch da. Darunter die Liste **„Automatisch zusammengeführt“** mit Vergleich vorher/nachher und **„Rückgängig“**; eine so wiederhergestellte Konfliktversion wird danach nie wieder automatisch zusammengeführt. Einträge lassen sich einzeln oder alle auf einmal **ausblenden** (das Backup bleibt erhalten).
  - Tab **Einstellungen**: Projekt-Präfix, Prüfintervall, Ordner wechseln; Anzeige der **Schreibgarantie** des Notizordners (ist sie eingeschränkt, steht das auch beim Start).
  - Speichern funktioniert auch auf Speicher ohne Hardlinks (z. B. SD-Karte); Merkweiser prüft beim Öffnen jedes Notizordners, welche sichere Schreibweise dort geht.
  - **Diagnosebericht** (Einstellungen): schreibt den Zustand der App ohne Notizinhalte als Textdatei in einen wählbaren Ordner, z. B. einen Syncthing-Ordner.
  - Ein Notizordner, in dem Merkweiser nicht sicher speichern kann, öffnet sich **schreibgeschützt**: Lesen und Suchen gehen, Änderungen werden mit Hinweis abgelehnt.
  - Anleitung in `docs/kurzanleitung.md`.

- Repository-Gerüst mit Konzept (`docs/KONZEPT.md`), freigegebenem Plan (`docs/PLAN.md`) und Formatbeschreibung (`docs/FORMAT.md`).
