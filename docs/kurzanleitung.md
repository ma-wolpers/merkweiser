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

- **Tabs:** Tag (Notizen eines Datums), Todos, Suche, Zeit, Einstellungen. Jeder Tab merkt sich die zuletzt geöffnete Unterseite; erneutes Antippen des aktiven Tabs führt zu seiner Startseite.
- **Tags antippen** öffnet eine Seite mit allen Notizen dieses Tags. Zurück geht es mit dem Pfeil oben oder der Android-Zurück-Taste.
- **Dringende Todos** (Stern) stehen in jeder Notiz und in den Listen oben.
- **Konflikte** findest du unter *Einstellungen → Konflikte*. Eine Zahl am Einstellungen-Symbol zeigt, wie viele offen sind. Dort stehen auch **unterbrochene Vorgänge**, z. B. ein Verschieben, bei dem sich die Quelle inzwischen geändert hat; Merkweiser ändert dann bewusst nichts weiter und lässt dich wählen.

- **Doppelte Notizen** (gleiche Notiz in mehreren Tagesdateien) erscheinen ebenfalls unter *Konflikte*. Du wählst, welche bleibt (Schnellwahl „Neueste“/„Älteste“); die anderen werden gelöscht.
- **Backups:** Unter *Einstellungen → Backups* stehen alle Änderungen, die Merkweiser gemacht hat, je Datei mit Vergleich vorher/nachher. „Rückgängig“ nimmt nur diese eine Änderung zurück; spätere bleiben. Lässt sich das nicht eindeutig machen, legt Merkweiser den früheren Stand als Konfliktdatei an, und du entscheidest unter *Konflikte*. Gehört eine Änderung zu einem Vorgang mit mehreren Dateien (z. B. Verschieben), steht dabei, was ein teilweises Rückgängig bedeutet.

## Arbeitszeit (Tab „Zeit“)

- **Messen:** Tätigkeit wählen, *Start*. Oben steht „Orga läuft seit 08:15 (1:23)“. *Stopp* trägt die Minuten (immer abgerundet) in die Tagesdatei ein, über Mitternacht aufgeteilt auf beide Tage.
- **Wechseln:** Während eine Messung läuft, eine andere Tätigkeit wählen und *Wechseln zu …* tippen: Die laufende endet jetzt, die neue beginnt jetzt.
- **Messung abbrechen:** Endzeit wählen (die Zeit bis dahin wird eingetragen) oder *Keine Zeit eintragen*.
- **Vergessen?** Eine Messung, die länger als 24 Stunden läuft, verwirft Merkweiser beim nächsten Öffnen von App bzw. Zeit-Tab ohne Eintrag und sagt es dir.
- **Übersicht:** die letzten 7 Tage (oder 14/30), je Tag eine Zeile, darunter die Summen.
- **Tätigkeiten verwalten:** hinzufügen, umbenennen (ändert auch alle früheren Einträge; gibt es den Namen schon, fragt Merkweiser vor dem Zusammenführen), löschen (die eingetragenen Zeiten bleiben). Die Liste gilt nur für dieses Gerät; Namen aus deinen Dateien erscheinen trotzdem.
- **Zwei Geräte:** Unterschiedliche Minuten derselben Tätigkeit nach einem Sync-Konflikt → der größere Wert zählt. Laufen auf zwei Geräten Messungen, fragt Merkweiser, welche zählt.
- Gespeichert wird im YAML-Kopf der Tagesdatei (`zeit_Orga: 90`), siehe `docs/FORMAT.md`.

## Morgen-Benachrichtigung (Android)

*Einstellungen → Benachrichtigungen*: einschalten (Android fragt einmal nach der Erlaubnis), Uhrzeit wählen (Standard 7:00). Morgens kommt eine Liste deiner offenen Todos von heute und aller dringenden (⭐). Öffnest du die App danach nicht, erinnert Merkweiser an den Folgetagen neutral – auf Wunsch zunehmend dringlich. Im **Urlaub** (bis einschließlich dem gewählten Tag) kommt nichts. Android kann die Zustellung bei Akkusparen verzögern; was nach dem Schließen der App per Sync dazukommt, steht erst in der nächsten Benachrichtigung. *Hinweis:* Diese Funktion wird gerade getestet (Spike S5) und ist in der App erst danach aktiv.

## Diagnosebericht

*Einstellungen → Diagnosebericht speichern* legt eine Datei `merkweiser-diagnose-<Datum>-<Uhrzeit>.txt` an. Den Zielordner tippst du ins Feld darüber, oder du lässt es leer und wählst ihn aus; Merkweiser merkt sich den Ordner.

Der Bericht enthält nur Metadaten: Version, Notizordner, Schreibgarantie, Dateinamen von Konfliktdateien, unvollständige Vorgänge und die letzten Meldungen der App. Notizinhalte stehen nie darin. Wählst du einen per Syncthing geteilten Ordner außerhalb des Notizordners, kommt der Bericht direkt am Rechner an.
