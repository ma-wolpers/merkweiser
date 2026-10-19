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
