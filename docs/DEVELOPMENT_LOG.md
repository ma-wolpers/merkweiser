# Development Log

Verlauf aller relevanten Änderungen, auch interner. Neueste Einträge oben.

## 2026-10-21 – Folgeänderung auch in der Wiederherstellung

- Gerätebefund: Die Konfliktdateien entstanden weiter, und zwar still beim **nächsten Start**. Die App wird meist vor Ablauf der 120-s-Quarantäne geschlossen; dann sah die Wiederherstellung `D` noch auf der Platte und `P ≠ N` und nahm „extern belegt“ an (Zeile 4). Beim Create-only-Pfad wurde eine überholte Neuanlage sogar als „nicht ausgeführt“ gemeldet.
- Fix: `Writer.superseded` (vorher privat) wird in `_recover_displaced` und `_recover_create` abgefragt. Tests: Neustart nach A→B, A→B→A, A→B→C sowie nach Neuanlage + Änderung.

## 2026-10-21 – Diagnosebericht, S1 abgeschlossen

- S1, zweiter Gerätebericht (interner Speicher): wie auf der SD-Karte (`link` verboten, `renameat2` funktioniert, `O_EXCL`, Verzeichnis-`fsync`, `flock` ok). S1 ist damit abgeschlossen.
- Neu: `app/diagnostics.py` (Bericht ohne Notizinhalte, exklusives Anlegen), `Settings.report_dir`, in der Mobile-App ein Protokoll der letzten 30 Statusmeldungen und der Knopf „Diagnosebericht speichern“. Erfolgsmeldungen erscheinen nicht mehr in Fehlerfarbe.

## 2026-10-21 – Eigene Folgeänderung in der Quarantäne, Konfliktansicht

- Gerätebefund: Ab- und sofort wieder Enthaken erzeugte Konfliktdateien in einem Ordner ohne Syncthing. Ursache: Die Abschlussprüfung der ersten Op fand ihr `N` nicht mehr in `P` und machte es als Konflikt sichtbar, obwohl die eigene Folge-Op es verdrängt und gesichert hatte. Fix `Writer._superseded`; Tests für zwei Folgeänderungen, A→B→A→B und „Fremder ersetzt danach“ (dann bleibt die letzte `N` weiterhin sichtbar).
- Konfliktansicht (Mobile) neu als `mobile/ui/conflict_view.py`: Vergleich beider Fassungen statt nur der Konfliktversion, Herkunft, erklärte Knöpfe. Anzeigemodelle `conflict_diff`, `conflict_origin` in `app/views.py` (auch für den Desktop).

## 2026-10-21 – S1-Gerätebefund: Selbsttest der Install-Primitive

- S1-Bericht vom Gerät (SD-Karte): `os.link` ist verboten (`PermissionError`), `renameat2(RENAME_NOREPLACE)` funktioniert. Ohne Änderung wäre auf Android **jedes Speichern** gescheitert, weil `FsOps` auf POSIX fest `link`+`unlink` nutzte.
- Neu: `FsOps`-Variante `noreplace` (`renameat2` per `ctypes`-Syscall, Nummern je Architektur) und `core/fs_probe.py` mit dem im Plan vorgesehenen Selbsttest je Vault. `NotesService` ermittelt die Variante beim Öffnen; Einstellungen zeigen die Schreibgarantie, der Startbanner nur, wenn sie eingeschränkt ist.
- Tests: echtes Dateisystem → `atomic`; simuliert ohne Hardlinks → `noreplace`; ohne atomare Variante → `excl`; still überschreibende Variante wird verworfen; schreibgeschützt → `VaultNotWritableError`; keine Probedateien bleiben liegen; `renameat2` außerhalb von Linux → `ENOSYS` (unter Linux: überschreibt nie).
- Nebenbefund Diagnose: Nach „gleicher Fehler trotz Update“ war das APK in Ordnung (`certifi` per `zipimport` aus `sitepackages.zip` importierbar). Ursache war eine Verwechslung mit der Spike-App. serious_python entpackt nach jedem (Neu-)Installieren neu (Schlüssel enthält `lastUpdateTime`).

## 2026-10-19 – Mobile-App, erste Fassung (Schritt 8)

- Befund S1 vom Gerät: Mit `pyjnius` in `project.dependencies` stürzte das Spike-APK mit `ModuleNotFoundError: certifi` ab. Ursache (`flet_cli/commands/build_base.py`): `flet` wird nur bei leerer Abhängigkeitsliste automatisch gebündelt, und die Startvorlage (`python.dart`) importiert `certifi` immer. Behoben, indem `flet==0.86.5` mit aufgeführt wird; im Spike-APK sind jetzt `flet`, `certifi`, `httpx` und `jnius` enthalten.
- Neu: `ports/storage_access.py`, `app/views.py`, `mobile/platform/flet_access.py`, `mobile/ui/{app,tabs}.py`, `src/main.py`, `[tool.flet.android] dependencies`, `docs/kurzanleitung.md`; Tests für die Anzeigemodelle und ein Rauchtest aller Tabs.
- Die Schichtenprüfung läuft jetzt in einem Unterprozess, weil der Mobile-Rauchtest Flet in den Testprozess lädt.
- Zweiter Fall derselben Upstream-Drift: `shared_preferences_android 2.5.0` (erschienen zwischen zwei Builds) verlangt `jni ^1.1.0` → auf 2.4.28 gepinnt. Das erste echte Merkweiser-APK baut damit und liegt in `SyncSpike/merkweiser.apk`.
- Nebenbefund ohne Eingriff: Der Kommentar in namenfit-mobile (`pyproject.toml`, „flet wird immer gebündelt“) stimmt nicht allgemein; dort zieht `flet-audio` `flet` als Abhängigkeit nach.

## 2026-10-14 – bw-gui-Teilplan umgesetzt, Doku-Reparatur

- bw-gui (`410b9e5`, `d9ad7fb`): `WrappedTextField.get_raw()` liest verlustfrei, `load()` lädt den Ausgangsinhalt ohne Undo-Eintrag, `initial=` nutzt `load()`. `set()` und `get()` sind unverändert (kursplaner nutzt `set()` mitten im Bearbeiten). Damit ist `BAUSTELLE(bw-gui)` aufgelöst.
- Repariert: In `ARCHITEKTUR.md` waren `\r\n`, `\n`, `\r`, `\x0b` und `\u2028` durch ein Ersetzungsskript zu **echten** Steuerzeichen geworden, und die Tabellenzeile zu `source.py` war zerbrochen. In `core/source.py` (Kommentar) und `tests/core/test_source.py` standen echte U+2028-Zeichen statt der Escape-Folge. Ursache: Die Werkzeug-Übertragung interpretiert `\uXXXX` bereits vor Python. Bei solchen Ersetzungen wird der Backslash jetzt zur Laufzeit gebildet (`chr(92)`).

## 2026-10-09 – Schritt 6: App-Schicht

- `app/settings.py`, `app/notes_service.py`, `core/retention.py` und 7 Integrationstests.
- Damit ist der gesamte Core samt Fassade fertig. Offen: Schritt 7 (Desktop), vorher der bw-gui-Teilplan für verlustfreies Auslesen von `WrappedTextField` (Nutzerentscheidung „vor Schritt 7“), sowie Schritt 8 (Mobile, wartet auf S1), S4-Bestätigung und Mobile-Ports (`AppStorage`, `FolderPicker`).

## 2026-10-09 – Move-Ausführung

- `core/move_exec.py` und 5 Tests: neue Zieldatei, gleiche Datei, Absturz nach dem Ziel-Write (kein zweites Anhängen), veränderte Quelle → `INCOMPLETE`, mehrfaches Erneut-Versuchen vervielfacht nichts, Suche nach einem offenen Vorgang.
- Ab jetzt pusht Claude die eigenen Commits (Bitte der Nutzerin bzw. des Nutzers vom 2026-10-09).

## 2026-10-09 – Konfliktschicht: Erkennung, Auto-Merge, Auflösung mit Marker

- `core/conflicts.py`, `core/resolve.py`, `OpStore.read` und 13 Tests.
- Im Entwurf ergänzt: `manual_only_paths`. Für unterbrochene bzw. mit Hinweis abgeschlossene Auflösungen und für die übrigen `MAIN_DELETED`-Versionen läuft nie ein Auto-Merge (Plan, „Regeln“).
- Testbefund: Benachbarte Änderungen beider Seiten werden im diff3 zum Konflikt (konservativ, dokumentiert als `GRENZE`). Die Absturz-Tests brauchen einen simulierten Prozesstod (Locks freigeben), sonst übernimmt die Wiederherstellung korrekt **nicht**.

## 2026-10-09 – Wiederherstellung nach Absturz

- `core/recovery.py` und 20 Absturz-Tests (jede Protokollgrenze, verschachtelter Absturz, fremder Lock, verwaiste Dateien).
- Gemeinsam genutzte Protokollschritte von `Writer` öffentlich gemacht (`save_displaced`, `quarantine`, `own_conflict`, `ensure_visible`, `rel`), statt private Methoden quer über Module aufzurufen.

## 2026-10-09 – Schritt 3: Tausch-Protokoll (vor S4, Nutzerentscheidung)

- `core/fsops.py`, `core/ops.py`, `core/conflict_files.py`, `core/safe_write.py` mit Tests (fremde Schreiber an jeder kritischen Grenze).
- Befund Windows: Ein Sperr-Handle mit `DELETE`-Zugriff blockiert auch das eigene spätere Lesen (Python öffnet ohne `FILE_SHARE_DELETE`). Für den Rename genügt der Share-Mode, das Handle fordert jetzt nur Lesezugriff an. Der Test bestätigt, dass ein fremder Schreiber während des Tauschs blockiert wird.
- Fehler im eigenen Entwurf vor dem Test korrigiert: Beim Rücktausch wäre eine *fremde* Datei in `P` zur Konfliktdatei verschoben worden; jetzt weicht nur die eigene Version `N`.
- Offen: Wiederherstellung nach Absturz (`recovery.py`), Move-Ausführung, Konflikterkennung und -auflösung.

## 2026-10-09 – Watcher, App-Daten-Layout, Beobachtungs-Historie

- `core/watch.py`, `core/appdata.py`, `core/history.py` mit Tests: nur Unterschiede bzw. Endstand, versteckte Dateien ausgenommen, getrennte Vault-IDs und Historien bei gleichem relativen Pfad, App-Daten nie im Vault, Historie nur anhängend, Aufbewahrung ab „ersetzt seit“ (tägliches Lesen verlängert alte Versionen nicht), Schutz referenzierter Versionen, Kandidatenbasis vor einem Zeitstempel.
- Damit sind alle Bausteine umgesetzt, die nicht vom Tausch-Protokoll abhängen. Als Nächstes folgen (nach S4) `textfile`-Primitive, Op-Verzeichnisse, `safe_write`/`safe_remove`, Wiederherstellung, Konflikte mit Resolve-Op und Marker, dann `NotesService`.

## 2026-10-09 – Schritt 5 (Teil): Merge-Algorithmen

- `core/merge/{align,model,diff3,union,verify}.py` mit 22 Tests: Konzeptbeispiel (diff3 automatisch, A zuerst), identische Ersetzung und Einfügung einmal, Löschung gegen Änderung → Konflikt, R1/R2, Union-GRENZE, wiederholte Zeilen bleiben getrennt, gleicher Inhalt an anderer Position wird nicht zusammengelegt, manipulierte Ergebnisse werden abgelehnt, Zufallstest.
- Frage geklärt (Nutzerentscheidung 2026-10-09): Ohne verlässliche Basis wird automatisch „beide, A dann B“ übernommen (Union ist damit immer konfliktfrei; Auto-Merge-Protokoll mit Rückgängig). Ergänzt in `PLAN.md` (Entscheidungstabelle, Zeile „Auto-Merge“).

## 2026-10-09 – Schritt 3 (Teil): Move-Planung

- `core/move_plan.py` mit Tests: Teilbaum inklusive Fortsetzungszeilen, geerbte Tags explizit (außen nach innen), effektive Tags bleiben im Ziel erhalten, Notiz „Verschoben aus“ wird neu angelegt bzw. wiederverwendet, Quelle nur bei exaktem und eindeutigem Block.
- Widerspruch gefunden und gelöst: Die allgemeine Ziel-Regel („steht noch an Ort und Stelle → Treffer“) hätte eine Move-Quelle auch dann entfernt, wenn derselbe Block doppelt in der Datei steht. Der Plan verlangt dort genau ein Vorkommen, deshalb `resolve_block(unique=True)`.
- Refactoring: Strukturabfragen als `Outline.subtree_end` und `Document.item_at`, statt private Helfer quer über Module zu importieren.

## 2026-10-09 – Schritt 3 (Teil): Edit-Planung ohne Schreibprotokoll

- `core/patch.py`, `core/edits.py`, `core/note_ops.py` mit Tests: Minimal-Diff per `difflib`, CRLF und fehlender Schluss-Umbruch bleiben erhalten, identische Todos → `StaleTargetError`, Idempotenz, Dringlichkeit hin und zurück byte-identisch, Projekt ersetzen bzw. entfernen, Kind-Einrückung, Notizgrenzen verändert → `NoteNotFoundError`, Löschen mit genau einem Trenner, Encoding-Schutz.
- Präzisierung gegenüber dem Plan-Wortlaut: `set_done(done)` statt `toggle_done`, weil ein Umschalten nach einer fremden Änderung beim Neuplanen in die falsche Richtung kippen könnte. Für Nutzer bleibt die Funktion gleich.
- Bewusst noch **nicht** umgesetzt: `safe_write`/`safe_remove` (Tausch-Protokoll). Laut Plan wird S4 abgewartet.

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
