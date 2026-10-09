# Development Log

Verlauf aller relevanten Änderungen, auch interner. Neueste Einträge oben.

## 2026-10-09 – Schritt 4: Suche und Filter

- `core/query.py` (Filter, TextQuery mit explizitem Modus, Treffer mit Kontext) und `core/doc_cache.py` (Speicher-Cache) mit Tests: Todo-Ansicht, Status und Dringlichkeit, UND/ODER bei effektiven Tags, geerbte Projekte, Teilstring- gegen Regex-Modus, ungültiger Regex, Datumsbereich, Cache-Invalidierung.

## 2026-10-09 – Schritt 2 abgeschlossen: Vault, Snapshot, Clock, Dokument-Fassade

- `core/vault.py` (Muster, Scan, Dubletten, Konfliktnamen inklusive verschachtelt/eigen/entschieden, Schreibziel-Regel), `core/textfile.py` (lesender Snapshot), `ports/clock.py` und `core/clock.py`, `core/document.py`, `tests/fakes.py` (`FakeClock`).
- Synthetischer Fixture-Korpus `tests/fixtures/` mit Roundtrip-Test über alle Dateien.
- Spike S1: Das neue APK mit `pyjnius` (wird gebündelt) und Zugriffsprüfung ohne `pyjnius` liegt in `SyncSpike/`.

## 2026-10-09 – Schritt 2, Teil 2: Lexer, Zeilensemantik, Notizbaum, Tag-Vererbung

- `core/lexer.py`, `core/inline.py`, `core/outline.py`, `core/tags.py` mit Tests: Konzeptbeispiele (Verschachtelung, Status, Dringlichkeit, `#uni`, Ende der Vererbung beim nächsten Thema), Erläuterungsabsatz, Überschriften-Ebene, Setext, implizites Thema, Fortsetzungszeilen, Codeblock ohne Todos, Zitat/Tabelle/Embed, Projekte explizit/geerbt, Tags ohne Groß-/Kleinschreibung, Tabstopps.
- Obsidian-Abgleich: Tags brauchen nur mindestens ein Nicht-Ziffer-Zeichen (`#2026-10` gilt).
- `FORMAT.md`: zwei GRENZE-Einträge (Zeile direkt unter einem Punkt beginnt ein Thema; Setext mit mindestens 3 Zeichen).

## 2026-10-09 – Schritt 2, Teil 1: Source-Modell und Block-Erkennung

- `core/source.py` (verlustfreies `SourceText`, Encoding-Grenze) und `core/blocks.py` (Frontmatter, Fences, Trenner, Notiz-Spannen) mit Tests: Roundtrip byte-identisch bei LF, CRLF, gemischt, ohne Schluss-Newline, BOM, Emoji, Steuerzeichen; Trennerregel; längere Fences; offene Fences.
- `tools/code_lines.py`: AST/tokenize-basierte Zählung der Code-Zeilen.
- Spike S1, erster Gerätebefund: `pyjnius` ist im APK nicht vorhanden. Ohne „Alle Dateien“ schlägt das Anlegen in `/storage/emulated/0` mit `PermissionError` fehl. Der Spike prüft jetzt den Zugriff ohne `pyjnius`, schreibt seinen Bericht ersatzweise in den App-Speicher und testet `pyjnius` als Abhängigkeit.

## 2026-10-09 – Repo-Gerüst und erste Spikes

- Repo angelegt (Monorepo, ein gemeinsamer Core für Desktop und Android).
- `docs/KONZEPT.md` aus der neuen Fassung des ursprünglichen Konzepts extrahiert. Die Quelldatei im Geschwister-Repo `../tools4school` enthält zwei ineinander geratene Fassungen und bleibt unverändert.
- `docs/PLAN.md`: freigegebener Plan nach vier Audit-Runden, eingefroren. Maschinenspezifische Pfade wurden dabei relativ gemacht.
- `docs/FORMAT.md`: verbindliche Grammatik (Trenner, Themen, Erläuterungsabsatz, Überschriften-Ebene, Tabstopps, Fences, Encoding, Tags/Projekte/Vererbung, Konfliktdateien).
- `AGENTS.md` mit den Repo-Regeln.
- `pyproject.toml`: Extras `dev`/`ui`/`build`, Flet-Konfiguration inklusive `MANAGE_EXTERNAL_STORAGE` und dem `jni_flutter`-Override aus Spike S2.
- Spike S2 bestanden (APK baut mit `jni_flutter`-Override). Spike S3 sowie die Windows-Primitive: Befunde in `ARCHITEKTUR.md`. S1 und S4 sind offen, weil sie Gerät bzw. Obsidian brauchen.
- `.gitattributes`: `tests/fixtures/** -text`. Weil `core.autocrlf` global aktiv ist, würde Git sonst die Zeilenenden der Roundtrip-Fixtures umschreiben, und die Byte-Gleichheit wäre nicht mehr testbar.
- Spike-Quellen nach `spikes/` verschoben (vorher außerhalb des Repos); im S3-Skript den bw-gui-Pfad relativ gemacht (Geschwister-Repo). `SyncSpike/` (Syncthing-Ordner für Spike-APK und -Berichte) und der S4-Test-Vault sind in `.gitignore`.
- `bw_libs/shared_gui_core.py` übernommen: Code wie in der Vorlage, Docstring ohne maschinenspezifischen Pfad.
- In `AGENTS.md` steht die Spike-Konvention nur noch beschreibend, nicht als Regel.
- Nebenarbeit in `../bw-gui`: `docs/QUICKSTART.md` enthält keinen maschinenspezifischen Pfad und keine toten Links mehr (Plan, Nebenaufgabe).
