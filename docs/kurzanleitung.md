# Kurzanleitung

## Android-App bauen

Voraussetzungen: Android-SDK (`ANDROID_HOME` bzw. `ANDROID_SDK_ROOT` gesetzt) und `flet-cli 0.86.5` (`pip install -e ".[build]"`).

```bash
python tools/build_apk.py                     # die App
python tools/build_apk.py --project spikes/s5 # ein Spike (eigene App-ID)
```

- Das Skript signiert mit dem **gemeinsamen Keystore** und kopiert das APK nach `SyncSpike/`. Ohne eigene Signatur nimmt `flet build` den Debug-Schlüssel des jeweiligen Rechners, und Android lehnt ein Update von einem anderen Rechner ab („package conflicts with an existing package“).
- Der Keystore (`merkweiser.jks`, `passwort.txt`) liegt im Syncthing-Ordner 7thCloud unter `tools/merkweiser-signing/`. Das Skript findet ihn relativ zum Repo (`../../7thCloud/tools/merkweiser-signing`); liegt er woanders, `MERKWEISER_SIGNING_DIR` setzen. Pfad und Passwort gehen nur über Umgebungsvariablen an flet-cli, nie ins Repo. **Den Keystore nie neu anlegen:** Ein neuer Schlüssel erzwingt wieder eine Neuinstallation samt Verlust der App-Daten.
- Nach dem Build prüft das Skript per `apksigner` (Android-SDK), ob die APK wirklich mit dem Merkweiser-Schlüssel signiert ist, und kopiert sie nur dann.
- Unsigniert (nur zum Ausprobieren auf einem Gerät ohne installierte Merkweiser-App): `PYTHONIOENCODING=utf-8 flet build apk --no-rich-output`.
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
- **Dringlichkeit (Ampel):** Der Stern am Todo schaltet bei jedem Tipp weiter: farblos → **gelb** (dringend) → **rot** (sehr dringend) → farblos. Offene dringende Todos haben links eine farbige Leiste und stehen in jeder Notiz oben, Rot vor Gelb. In Obsidian erscheinen sie als Hervorhebung: `==Text==` bzw. `==🔴Text==`.
- **Tab Todos:** oben alle offenen roten Todos, dann die von heute, darunter die früheren Tage – je Abschnitt gelbe zuerst. Ein gelbes Todo von gestern steht also unter den heutigen. Todos aus zukünftigen Tagen erscheinen hier nicht. Der Knopf rechts am Todo (Blatt-Symbol) öffnet die ganze Notiz; dort kannst du sie mit dem Kalender-Symbol **komplett verschieben** (am Zieltag wird sie mit genau einer Notiz gleichen Themas zusammengeführt).
- **Konflikte** findest du unter *Einstellungen → Konflikte*. Eine Zahl am Einstellungen-Symbol zeigt, wie viele offen sind. Dort stehen auch **unterbrochene Vorgänge**, z. B. ein Verschieben, bei dem sich die Quelle inzwischen geändert hat; Merkweiser ändert dann bewusst nichts weiter und lässt dich wählen.

- **Doppelte Notizen** (gleiche Notiz in mehreren Tagesdateien) erscheinen ebenfalls unter *Konflikte*. Du wählst, welche bleibt (Schnellwahl „Neueste“/„Älteste“); die anderen werden gelöscht.
- **Backups:** Unter *Einstellungen → Backups* stehen alle Änderungen, die Merkweiser gemacht hat, je Datei mit Vergleich vorher/nachher. „Rückgängig“ nimmt nur diese eine Änderung zurück; spätere bleiben. Lässt sich das nicht eindeutig machen, legt Merkweiser den früheren Stand als Konfliktdatei an, und du entscheidest unter *Konflikte*. Gehört eine Änderung zu einem Vorgang mit mehreren Dateien (z. B. Verschieben), steht dabei, was ein teilweises Rückgängig bedeutet.

## Arbeitszeit (Tab „Zeit“)

- **Messen:** Tätigkeit wählen, *Start*. Oben steht „Orga läuft seit 08:15 (1:23)“. *Stopp* trägt die Minuten (immer abgerundet) in die Tagesdatei ein, über Mitternacht aufgeteilt auf beide Tage.
- **Wechseln:** Während eine Messung läuft, eine andere Tätigkeit wählen. *Wechseln zu … …* fragt nach der Uhrzeit (vorbelegt mit jetzt) – so trägst du einen vergessenen Wechsel nach; die Uhrzeit muss nach dem Beginn der laufenden Messung liegen. Der kleine Knopf daneben wechselt sofort. Die laufende Messung endet zur gewählten Uhrzeit, die neue beginnt im selben Moment. Eine Startzeit kann man bewusst nicht nachtragen: Das Starten gehört zur Arbeitsstart-Routine.
- **Messung abbrechen:** Endzeit wählen (die Zeit bis dahin wird eingetragen) oder *Keine Zeit eintragen*.
- **Vergessen?** Eine Messung, die länger als 24 Stunden läuft, verwirft Merkweiser beim nächsten Öffnen von App bzw. Zeit-Tab ohne Eintrag und sagt es dir.
- **Übersicht:** die letzten 7 Tage (oder 14/30), je Tag eine Zeile, darunter die Summen.
- **Tätigkeiten verwalten:** hinzufügen, umbenennen (ändert auch alle früheren Einträge; gibt es den Namen schon, fragt Merkweiser vor dem Zusammenführen), löschen (die eingetragenen Zeiten bleiben). Die Liste gilt nur für dieses Gerät; Namen aus deinen Dateien erscheinen trotzdem.
- **Zwei Geräte:** Unterschiedliche Minuten derselben Tätigkeit nach einem Sync-Konflikt → der größere Wert zählt. Laufen auf zwei Geräten Messungen, fragt Merkweiser, welche zählt.
- Gespeichert wird im YAML-Kopf der Tagesdatei (`zeit_Orga: 90`), siehe `docs/FORMAT.md`.

## Morgen-Benachrichtigung (Android)

*Einstellungen → Benachrichtigungen*: einschalten (Android fragt einmal nach der Erlaubnis), Uhrzeit wählen (Standard 7:00). Morgens kommt eine Liste: zuerst alle roten Todos (🔥), dann die Todos von heute (gelbe ⭐ zuerst), dann gelbe Todos früherer Tage. Dringende sind fett, der Titel zählt sie (z. B. „· 🔥 2 · ⭐ 3“); gibt es ein rotes, erscheint die Benachrichtigung als Banner (sofern Android das für den Kanal „Erinnerung (wichtig)“ zulässt). Öffnest du die App danach nicht, erinnert Merkweiser an den Folgetagen neutral – auf Wunsch zunehmend dringlich. Im **Urlaub** (bis einschließlich dem gewählten Tag) kommt nichts. Die Benachrichtigung kann ein paar Minuten später kommen (Android bündelt Alarme zum Akkusparen; im Test bis etwa 2 Minuten). Was nach dem Schließen der App per Sync dazukommt, steht erst in der nächsten Benachrichtigung.

## Diagnosebericht

*Einstellungen → Diagnosebericht speichern* legt eine Datei `merkweiser-diagnose-<Datum>-<Uhrzeit>.txt` an. Den Zielordner tippst du ins Feld darüber, oder du lässt es leer und wählst ihn aus; Merkweiser merkt sich den Ordner.

Der Bericht enthält nur Metadaten: Version, Notizordner, Schreibgarantie, Dateinamen von Konfliktdateien, unvollständige Vorgänge und die letzten Meldungen der App. Notizinhalte stehen nie darin. Wählst du einen per Syncthing geteilten Ordner außerhalb des Notizordners, kommt der Bericht direkt am Rechner an.
