# Development Log

Verlauf aller relevanten Änderungen, auch interner. Neueste Einträge oben.

## 2026-10-22 – Verschieben ohne Tracking (Teilschritt 2)

- `MOVED_HEADER` und die Wiederverwendung über die Kopfzeile entfernt; PLAN.md und FORMAT.md korrigiert (dort stand die Kopfzeile versehentlich als Entscheidung).
- `move_plan`: Fälle `notiz`/`todo`, Themenkopie mit gefilterter Tag-Materialisierung, Zusammenführen nur mit genau einer Notiz gleichen Themas (`topics.find_topic_note`).
- Deterministische Wiederaufnahme: Die Zielwahl wird beim Anlegen der Op gespeichert (`ziel`) und beim Neuplanen nur exakt wiedergefunden; verändert → `INCOMPLETE`, Quelle unberührt. Alt-Ops ohne `mode` laufen ohne Kopfzeile zu Ende.
- `NotesService.move_todo` lehnt gleiches Datum vor jedem Schreiben ab (`SameDayMoveError`, `day_of`).
- Tests: Datenverlust-Invariante an 8 Absturzgrenzen × beide Fälle; gespeicherte Zielwahl gegen neue Dublette und gegen veränderte Zielnotiz.

## 2026-10-22 – Leeres Thema (Wunschliste, Teilschritt 1)

- Planrunde zu fünf Wünschen (Verschieben ohne Tracking, Tab „Tag“, Editor-Buttons, kleinere Textfelder, Suche mit ganzen Notizen); Plan in sieben Teilschritten.
- Neu `core/topics.py` (Themenschlüssel, leeres Thema, Tag-Thema, eindeutige Themensuche) als Grundlage für das neue Verschieben.
- `views.note_rows` setzt `Row.empty_topic`; die Mobile-Ansicht zeigt „kein Thema“ kursiv. Parser, Vererbung und Suche unverändert.
- Testumgebung: `tests/test_package.py` braucht `PYTHONPATH=src` (Unterprozess), wenn das Paket nicht installiert ist.

## 2026-10-21 – S4 Teil E: Obsidian behält den Tab; Abschlussprüfung prüft die Änderung statt ganz N

- Teil E mit echtem `Writer`: Obsidian schließt den Tab nicht und führt Merkweisers Änderungen selbst in den offenen Text ein. S4 abgeschlossen.
- Aber: fünf Konfliktdateien, alle Fehlalarme. `N` enthielt die gerade getippte Zeile in älterer Länge; die Regel „alle Zeilen von N enthalten“ war zu streng. Neu `core/kept.py` mit `change_kept` (Änderung `E → N` muss erhalten sein, mit Zählung gegen zufällig gleiche Zeilen); `contains_all_lines` dorthin verschoben (Rückfall für Create-only).
- Tests: Weitertippen in derselben Zeile → kein Konflikt; verlorener Haken, verlorene doppelte Einfügung, zurückgekehrte Löschung → Konflikt.

## 2026-10-21 – Obsidian-Tests ausgewertet; Abschlussprüfung mit Zeilen-Teilfolge; S4 Teil E

- Test A (Handy): bestanden. Test B (PC, Teile A–D): Befunde in `ARCHITEKTUR.md`.
- Per Wegwerftest bestätigt: Speichert ein externer Schreiber in der Quarantäne `N` plus neuen Text, legte `finish` eine überflüssige Konfliktdatei an (vermutliche Quelle der Auto-Merges vom Mittag). Neu `contains_all_lines` in `safe_write.py`, genutzt in `finish` (`_kept`) und in der Wiederherstellung (Zeile 4a, Create-only). Tests: enthalten mit CRLF-Wechsel → kein Konflikt; Zeile von `N` fehlt → Konflikt; Neustart mit externem Weiterschreiben.
- `spike_s4.py --teil-e`: fünf Schreibvorgänge mit dem echten `Writer` in die offene Notiz; Trockenlauf ohne Obsidian erfolgreich. App-Daten in `spikes/s4/MerkweiserS4-AppData/` (ignoriert).

## 2026-10-21 – Anleitung für die Obsidian-Tests; Schritte 7 und 9 zurückgestellt

- `spikes/obsidian-tests.md`: Test A (Obsidian Mobile als Szenario-Test mit der echten App, weil sich Handles auf Android ohne Root nicht messen lassen) und Test B (S4 unter Windows mit `spike_s4.py`).
- `spike_s4.py` an den Produktivcode angeglichen: Sperre ohne `DELETE`-Zugriff, Wegbenennen bei gehaltener Sperre (am Wegwerfordner geprüft: Rename klappt, fremdes Schreiben bleibt blockiert).
- Plan: Schritte 7 (Desktop-UI) und 9 (Abschluss) zurückgestellt bis nach den Obsidian-Tests und der Planrunde.

## 2026-10-21 – Plan: Backup-Ansicht vorgemerkt, S1-Stand präzisiert

- Nutzerwunsch unter „noch zu planen“: Konflikte in die Einstellungen, daneben eine Ansicht aller Backups mit „Rückgängig“.
- Korrektur im Fortschritt: S1 ist nur im Speicherteil abgeschlossen; die Schreibweise von Obsidian Mobile ist noch nicht untersucht.

## 2026-10-21 – Thema ohne Unterstreichung, Erläuterung schwächer

- Nutzerwunsch: Unterstreichung entfernt (fett genügt); Erläuterung in `style.EXPLANATION` (`with_opacity(0.5, ON_SURFACE)`) statt `ON_SURFACE_VARIANT`.

## 2026-10-21 – Auto-Merges ausblenden

- Nutzerwunsch: Die Liste „Automatisch zusammengeführt“ zeigte jeden Merge für die ganze Aufbewahrung (30 Tage). Neu `hide_automerges` (Zustandsfeld `ausgeblendet`), `NotesService.hide_automerges`, Knöpfe „Ausblenden“ und „Alle ausblenden“. Tests: ausgeblendet verschwindet aus der Liste, Backup und „nur manuell“ bleiben; andere Op-Arten unberührt.

## 2026-10-21 – Notizdarstellung: Thema, Erläuterung, Fortsetzungen, Listenpunkte

- Gerätebefund: Je Knoten wurde nur die erste Zeile gezeigt; Erläuterung und Fortsetzungen fehlten, Listenpunkte hatten kein Zeichen und eine andere Textkante als Todos.
- `Row.more` in `views.py`; neues Modul `mobile/ui/note_view.py` (aus `tabs.py` ausgelagert). Der Todo-Text ist nicht mehr die Checkbox-Beschriftung (wegen der festen Markerspalte), bleibt aber per `GestureDetector` antippbar.

## 2026-10-21 – Konfliktvergleich im Dark Mode lesbar

- Gerätebefund: Grüne (und rote) Vergleichszeilen waren im Dark Mode unlesbar, weil `GREEN_100`/`RED_100` feste helle Töne sind und die Schrift dort hell ist. Neu `mobile/ui/style.py` mit halbtransparenten Tönungen, genutzt von `conflict_view` und `hunk_view`.

## 2026-10-21 – Formatänderung: Leerzeilen trennen Notizen; Aufräumen leerer Tagesdateien

- Nutzerentscheidung: Jede Leerzeile beendet eine Notiz (außer in Codeblöcken); `---` bleibt Trenner, auch direkt unter Text, wird aber nicht mehr geschrieben; höchstens ein Thema je Notiz; nicht eingerückter Text direkt unter einem Punkt ist Fortsetzung; Überschriften sind gewöhnlicher Text (`#tags` darin bleiben Tags).
- `blocks.analyze`: Notizen als Läufe ohne Leerzeile/Trenner, keine leeren Notizen. `outline`: `NodeKind.HEADING` und `Node.level` entfernt, ein Thema je Notiz, Fortsetzung ohne Einrückung, Text nach „Sonstigem“ wird `OTHER`. `note_ops`: `append_note` ohne `---`, `delete_note` entfernt eine Lücke. `move_plan.remove_moved_source`: ganze Notiz samt Lücke. `views`: `# …` wird unverändert angezeigt.
- Folge für bestehende Dateien (dokumentiert in `FORMAT.md` und im Fixture-Test): Thema und Liste mit Leerzeile dazwischen sind getrennte Notizen, „lockere“ Listen zerfallen in Einzelnotizen ohne Verschachtelung und Vererbung.
- Neu: `core/cleanup.py` und Schritt im Start: leere Tagesdateien (nur Leerraum und `---`, kein BOM, kein offener Konflikt) über `Writer.remove`; `StartReport.removed_empty`, Hinweis in der Mobile-App, Zähler im Diagnosebericht.
- Tests angepasst (Blocks, Outline, Query, Edits, Move, Views, Fixture-Semantik) und ergänzt (Leerzeile im Codeblock, lockere Liste, Fortsetzung ohne Einrückung, Überschrift als Text, Setext, Lücke beim Löschen und Verschieben, Aufräumen).
- Plan: weiterer „noch zu planen“-Wunsch (gleiche Notiz in zwei Dateien).

## 2026-10-21 – Schreibschutz-Modus

- Ordner ohne sichere Schreibweise öffnen jetzt schreibgeschützt statt mit Fehler (Plan „No-Go“): `NotesService.read_only`, Decorator `_writes`, `ReadOnlyVaultError`, Start nur mit Scan. Mobile öffnet lesbare Ordner; Diagnosebericht nennt `schreibgeschuetzt`.
- Test: lesen und Konflikte anzeigen geht, Notiz anlegen und Auto-Merge werden abgelehnt, Poll ändert nichts.

## 2026-10-21 – Abschnittsweise Konfliktauflösung

- Core: `HunkPick`, `apply_hunk_picks` (Optionen laut Plan: A, B, Beide nur bei `offers_both`, Bearbeitet). App: `hunk_result`. Mobile: `mobile/ui/hunk_view.py` unter den Ganzdatei-Knöpfen bei `MANUAL`-Fällen mit Merge. Vorausgewählt ist „Hauptdatei“, solange es keine Historien-Vorschläge gibt (`BAUSTELLE(Vorschläge)`).
- Nebenbei behoben: Die Konfliktansicht zeigte die interne Fallart (`manual`, `busy` …); jetzt deutsche Texte (`CASE_KIND_LABELS`).
- Refactoring: Konflikt-Anzeigemodelle aus `app/views.py` nach `app/conflict_views.py` (views.py wäre sonst auf 338 Zeilen gewachsen).
- Tests: Wahl je Hunk inkl. Bearbeitet mit CRLF und leerem Text, ungültige Wahl, `hunk_result` im CRLF-Stil, Mobile-Durchlauf mit Radio-Auswahl und Bearbeiten.

## 2026-10-21 – Auto-Merge-Liste mit Rückgängig

- Befund beim Umsetzen: `undo_automerge` legte die Konfliktdatei wieder an, aber nichts hinderte den nächsten Start daran, sie erneut automatisch zusammenzuführen (Verstoß gegen Garantie 4). Neu `core/automerge_log.py` mit Markierung `nur_manuell` im Op-Zustand, idempotentem Rückgängig und Liste; `undo_automerge` ist aus `conflicts.py` dorthin umgezogen.
- `OpStore.read_blob` (lesen ohne Lock, Hash geprüft), Aufbewahrung schont Ops mit existierender `nur_manuell`-Datei, `NotesService.automerges`/`undo_automerge` (gibt den Pfad zurück), `views.line_diff`.
- Mobile: Abschnitt „Automatisch zusammengeführt“ im Tab Konflikte.
- Tests: bleibt nach Rückgängig manuell, Liste vorher/nachher und Zustand, Rückgängig nach späterer Änderung ohne Wirkung, zweimal Rückgängig, Aufbewahrung; Mobile-Durchlauf Start → Merge → Rückgängig → offener Fall.

## 2026-10-21 – Mobile: Datumswahl beim Verschieben

- Das Kalendersymbol am Todo öffnet jetzt einen Dialog (vorher: sofort auf morgen). „Morgen“ ist der erste Knopf, die Funktion bleibt also mit einem Tipp mehr erhalten.
- `app/views.py`: `move_choices`; `mobile/ui/move_dialog.py` mit `DatePicker` und `picked_date`. Tests: Schnellwahl an Mittwoch, Samstag, Montag; Picker-Werte naiv/UTC/None; Dialog verschiebt in die Tagesdatei von morgen.

## 2026-10-21 – Mobile: Notizen bearbeiten und löschen

- `app/views.py`: `NoteRef`/`note_ref` (Planungsstand und Inhaltszeilen einer Notiz). `mobile/ui/note_dialogs.py`: Bearbeiten- und Lösch-Dialog im Tab Heute.
- `MobileApp.act` gibt das Ergebnis zurück und meldet `CONFLICTED` sofort (vorher nur über den Tab Konflikte sichtbar).
- Tests: `NoteRef` mit echtem Service (ersetzen, löschen), leere Notizen, Dialog-Handler mit Seiten-Attrappe (speichern, leerer Text, löschen).
- Plan: Abschnitt „Spätere Schritte“ mit zwei Nutzerwünschen (dringende Todos oben, Tag anklicken), Ausarbeitung im Planmodus.

## 2026-10-21 – Quarantäne 10 s + Wanduhr

- Nutzerentscheidung: Quarantäne von 120 s auf 10 s; nach einem Neustart wird eine laut Wanduhr abgelaufene Quarantäne sofort abgeschlossen statt neu begonnen (`quarantaene_seit` in `state.json`, `Writer.wall_quarantine_over`). Grund: Typische Handy-Sitzungen sind kürzer als 2 min, Quarantänen wurden nie fertig.
- Beim Testen gefunden: Die Regel muss am **Anfang** der Zustandstabelle greifen; sonst ging der häufigste Fall (`D` noch vorhanden) über Zeile 5/6 und begann die Quarantäne wieder neu. Tests: abgelaufen → DONE ohne `.old`; kaum Zeit vergangen bzw. Uhr zurückgestellt → Quarantäne beginnt neu.

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
