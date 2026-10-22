# Kurzanleitung

## Android-App bauen

Voraussetzungen: Android-SDK (`ANDROID_HOME` bzw. `ANDROID_SDK_ROOT` gesetzt) und `flet-cli 0.86.5` (`pip install -e ".[build]"`).

```bash
PYTHONIOENCODING=utf-8 flet build apk --no-rich-output
```

- Das APK liegt danach in `build/apk/`. Ohne `--no-rich-output` bricht der Build unter Windows ab, sobald die Ausgabe umgeleitet wird (Emoji in der Konsole).
- Während eines Builds kein `flet run` starten: beide laufen als `flet.exe`.
- Die Android-Abhängigkeiten stehen in `[tool.flet.android] dependencies` und müssen `flet` **mit** aufführen. Fehlt es, stürzt die App beim Start mit „No module named certifi“ ab.

## Installieren und einrichten

1. Das APK aufs Handy bringen (z. B. über den Syncthing-Ordner `SyncSpike/`) und installieren.
2. Merkweiser öffnen → **Zugriff erteilen**. Öffnet sich keine Einstellungsseite: *Einstellungen → Apps → Merkweiser → Berechtigungen → Dateien → „Verwaltung aller Dateien zulassen“*.
3. **Notizordner wählen**, oder den Pfad eintippen (z. B. `/storage/emulated/0/Notizen`), falls die Auswahl keinen echten Pfad liefert.

## Syncthing

Trag in die `.stignore` des Notizordners ein:

```text
.*.mw-*
```

Merkweiser legt beim Schreiben kurzlebige Hilfsdateien `.NAME.mw-…` an. Syncthing soll sie nicht verteilen.

## Bedienung

- **Tabs:** Tag (Notizen eines Datums), Todos, Suche, Einstellungen. Jeder Tab merkt sich die zuletzt geöffnete Unterseite; erneutes Antippen des aktiven Tabs führt zu seiner Startseite.
- **Tags antippen** öffnet eine Seite mit allen Notizen dieses Tags. Zurück geht es mit dem Pfeil oben oder der Android-Zurück-Taste.
- **Dringende Todos** (Stern) stehen in jeder Notiz und in den Listen oben.
- **Konflikte** findest du unter *Einstellungen → Konflikte*. Eine Zahl am Einstellungen-Symbol zeigt, wie viele offen sind. Dort stehen auch **unterbrochene Vorgänge**, z. B. ein Verschieben, bei dem sich die Quelle inzwischen geändert hat; Merkweiser ändert dann bewusst nichts weiter und lässt dich wählen.

- **Doppelte Notizen** (gleiche Notiz in mehreren Tagesdateien) erscheinen ebenfalls unter *Konflikte*. Du wählst, welche bleibt (Schnellwahl „Neueste“/„Älteste“); die anderen werden gelöscht.
- **Backups:** Unter *Einstellungen → Backups* stehen alle Änderungen, die Merkweiser gemacht hat, je Datei mit Vergleich vorher/nachher. „Rückgängig“ nimmt nur diese eine Änderung zurück; spätere bleiben. Lässt sich das nicht eindeutig machen, legt Merkweiser den früheren Stand als Konfliktdatei an, und du entscheidest unter *Konflikte*. Gehört eine Änderung zu einem Vorgang mit mehreren Dateien (z. B. Verschieben), steht dabei, was ein teilweises Rückgängig bedeutet.

## Diagnosebericht

*Einstellungen → Diagnosebericht speichern* legt eine Datei `merkweiser-diagnose-<Datum>-<Uhrzeit>.txt` an. Den Zielordner tippst du ins Feld darüber, oder du lässt es leer und wählst ihn aus; Merkweiser merkt sich den Ordner.

Der Bericht enthält nur Metadaten: Version, Notizordner, Schreibgarantie, Dateinamen von Konfliktdateien, unvollständige Vorgänge und die letzten Meldungen der App. Notizinhalte stehen nie darin. Wählst du einen per Syncthing geteilten Ordner außerhalb des Notizordners, kommt der Bericht direkt am Rechner an.
