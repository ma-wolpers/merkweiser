# Merkweiser – Architektur (Ist-Zustand)

Dieses Dokument beschreibt, **was aktuell umgesetzt ist**. Ziel, Garantien und Protokolle stehen in [PLAN.md](PLAN.md). Sobald ein Teil umgesetzt ist, wandert seine Beschreibung von dort hierher (als Ist-Zustand).

## Stand

- Schritt 1 (Gerüst) ist umgesetzt: Paketstruktur `src/merkweiser/{core,ports,app}`, Doku, `pyproject.toml`.
- Schritt 2 (Einlesen) ist umgesetzt, siehe „Core: Einlesen“.
- Schritt 4 (Suche/Filter) ist umgesetzt, siehe „Core: Suche“.
- Schritt 3 ist **teilweise** umgesetzt: die reine Planung der Edit-Operationen (siehe „Core: Edit-Planung“). Das Tausch-Protokoll (`safe_write`) folgt nach Spike S4.
- Schritt 0 (Spikes) läuft, siehe unten.
- Es gibt noch keine fachliche Funktion.

## Wahrheitsmodell

Gilt unverändert wie in PLAN.md, Abschnitt „Wahrheitsmodell“: Die Markdown-Dateien im Vault sind die einzige fachliche Wahrheit. Alles in den App-Daten (Op-Verzeichnisse, Historie, Sidecars, Settings) ist technischer Zustand und liegt außerhalb des Vaults.

## Paketstruktur

| Paket | Rolle | Status |
|---|---|---|
| `merkweiser.core` | Parser, Schreibprotokoll, Merge; keine UI-Abhängigkeit | leer |
| `merkweiser.ports` | Protocols (`AppStorage`, `Clock`, `FolderPicker`) | leer |
| `merkweiser.app` | `NotesService`, die einzige UI-Fassade | leer |
| `merkweiser.desktop` | bw-gui-Oberfläche (Schritt 7) | fehlt noch |
| `merkweiser.mobile` | Flet-Oberfläche, `platform/` (Schritt 8) | fehlt noch |

## Core: Einlesen (Schritt 2)

Pipeline wie in PLAN.md: `Datei → SourceText → Blocks → Note → Outline → Semantik`. Jede Stufe nutzt nur das Ergebnis der vorherigen.

| Modul | Ist-Zustand |
|---|---|
| `core/source.py` | `SourceText.from_bytes(raw)` → `Line(no, text, eol)` mit dem originalen Zeilenende pro Zeile. Zeilengrenzen sind nur `
`, `
` und `
` (nicht `str.splitlines`, das auch an ``, ` ` … trennt). `to_bytes()` ist für UTF-8 ± BOM byte-identisch, für nicht unterstützte Encodings wird immer `raw` zurückgegeben (`writable == False`). `dominant_eol()` liefert das Zeilenende für neue Zeilen. |
| `core/blocks.py` | `analyze(lines) → FileLayout(frontmatter, fences, separators, notes)`. Das ist die alleinige Instanz für Notizgrenzen. Fence-Regel: gleiches Zeichen, Länge ≥ öffnende Länge; offen bis Dateiende. **GRENZE:** Nicht geschlossenes Frontmatter gilt als Trenner am Notizanfang. |

| `core/lexer.py` | `tokenize(text)` zerlegt eine Zeile in `TEXT`/`CODE`/`WIKILINK`/`LINK_URL` (Inline-Code mit passender Backtick-Länge, `[[…]]`, Link-Ziele, Autolinks, nackte URLs). Das ist die einzige Quelle für „wo ist Code bzw. eine URL“. |
| `core/inline.py` | `parse_list_item` (Marker, Spalte mit Tabstopps 4, Checkbox `[ ]`/`[x]`/`[X]`/`OTHER`, Dringlichkeit `==…==` am Inhaltsanfang), `find_tags` (Wortanfang, nur in `TEXT`, nicht rein numerisch, Vergleich per `casefold`), `project_name`. |
| `core/outline.py` | `build_outline(lines, layout, note)` in zwei Durchgängen: (1) Blöcke (Absatz, ATX- und Setext-Überschrift, Punkt mit Fortsetzungszeilen, Sonstiges inklusive Codeblock); (2) Baum mit Überschriften-Stapel, Thema bzw. Erläuterung, implizitem Thema und Eltern nach Einrückungsspalte. Knoten verweisen nur auf Zeilennummern; Eltern stehen immer vor Kindern. |
| `core/tags.py` | `compute_tags(outline, prefix)`: effektiv = explizit ∪ effektiv(Eltern), ein Durchlauf in Knotenreihenfolge. Liefert explizite, effektive und geerbte Projekte. |

| `core/vault.py` | `DayPattern` (nur `%Y`/`%m`/`%d`, je genau einmal, ganzer Dateiname), `scan(root, pattern)` (rekursiv; versteckte Ordner und Dateien werden übersprungen) → `VaultIndex(day_files, conflicts)` mit `duplicates()`. `parse_conflict_name` leitet die Hauptdatei aus dem Namen ohne **alle** `.sync-conflict-…`-Segmente ab und erkennt `nested`, `own` (`MERKWEISER…`) und `decided` (`…MWENTSCHIEDEN`); Nicht-`.md` wird ignoriert. `write_target` setzt die Schreibziel-Regel um bzw. meldet `AmbiguousDayFile`. Schreibt nie. |
| `core/textfile.py` | `read_snapshot(path)` → `FileSnapshot(raw, mtime_ns, size)` (Stat über den offenen Deskriptor); `same_content` vergleicht nur Bytes. **BAUSTELLE(S4):** Die Tausch-Primitive folgen in Schritt 3. |
| `ports/clock.py`, `core/clock.py` | `Clock`-Protocol (`now`, `today`, `monotonic`) und `SystemClock`. Tests nutzen `tests/fakes.py:FakeClock` mit getrennt verstellbarer Wanduhr und monotoner Zeit. |
| `core/document.py` | `parse_document(raw, prefix)` → `Document(source, layout, notes)`, die einzige Stelle, die die Lese-Stufen verkettet. |

Fixtures: `tests/fixtures/*.md` sind synthetisch und byte-genau (CRLF/gemischt, BOM, ohne Schluss-Newline, Fences, Setext, Tabellen, Embeds); `.gitattributes` schützt sie vor `autocrlf`.

Werkzeug: `tools/code_lines.py` zählt ausführbare Code-Zeilen (ohne Docstrings, Kommentare und Imports) gegen den Richtwert 300.

## Core: Edit-Planung (Schritt 3, ohne Schreibprotokoll)

Alle Operationen nehmen das **aktuell gelesene** `Document` plus ein flüchtiges Ziel und liefern neue Bytes. Neu planen auf frischem Stand heißt also einfach: dieselbe Operation mit dem neu gelesenen Dokument aufrufen.

| Modul | Ist-Zustand |
|---|---|
| `core/patch.py` | `Target`/`BlockTarget`; `resolve_line`/`resolve_block` (an Ort und Stelle oder **genau ein** exaktes Vorkommen, sonst `StaleTargetError`); `apply_edits(source, LineEdits)`: unveränderte Zeilen byte-identisch, neue Zeilen mit dominantem Zeilenende, „ohne Schluss-Umbruch“ bleibt erhalten; nicht unterstütztes Encoding → `UnsupportedEncodingError`. |
| `core/edits.py` | `set_done(done)` (statt „toggle“: der Zielzustand ist idempotent und neu planbar; `[X]` bleibt), `set_urgent` (`==…==` um den Inhalt, Tags am Ende bleiben draußen), `set_project` (ersetzt bzw. entfernt alle expliziten Projekt-Tags der Zeile), `add_todo` (Notizende oder letztes Kind mit passender Einrückung). Todos im Codeblock sind keine Todos. |
| `core/note_ops.py` | `append_note` (Trenner mit Leerzeilen, keiner bei leerer Datei bzw. nur Frontmatter), `replace_note_text` (Notiz nur eindeutig **und** als ganze Notiz auffindbar, sonst `NoteNotFoundError`; der Aufrufer legt dann eine eigene Konfliktdatei an), `delete_note` (genau ein Trenner, Naht ohne doppelte Leerzeilen). |

## Core: Suche (Schritt 4)

| Modul | Ist-Zustand |
|---|---|
| `core/query.py` | `search(documents, Filter)` → `Hit`s auf Knotenebene mit Kontextpfad. Filterarten UND-verknüpft; Tags effektiv, `TagMode.UND`/`ODER`; Projekte effektiv; `status`/`dringend` nur für Todos (`[-]` ist kein Todo); `TextQuery` mit `TEILSTRING` (casefold) oder `REGEX` (`IGNORECASE`, ungültig → `InvalidQuery`); Datumsbereich inklusiv. Die Semantik liegt vollständig im Core; die UIs reichen nur Werte durch. |
| `core/doc_cache.py` | `DocumentCache` im Speicher, invalidiert über `(mtime_ns, size)`. **GRENZE:** Eine Änderung ohne Änderung von mtime/size kann die Suche kurz veraltet zeigen. Schreiboperationen lesen immer neu. Persistenter Index: **BAUSTELLE** laut Plan. |

## Spike-Ergebnisse (Schritt 0)

Der Spike-Code liegt unter `spikes/` (S1/S2: `spikes/s1s2/`, ein eigenes Flet-Projekt; S3: `spikes/s3/`; S4: `spikes/s4/`). Er ist **kein Produktcode** und wird nicht importiert oder getestet. APKs und Berichte laufen über den Syncthing-Ordner `SyncSpike/` im Repo-Root, den Git ignoriert.

| Spike | Ergebnis | Folgen |
|---|---|---|
| **S1** Android-Ordnerzugriff und Primitive | Teilbefunde (2026-10-09): `pyjnius` ist ohne Eintrag in `project.dependencies` **nicht** im APK. Mit dem Eintrag wird `pyjnius 1.8.0` für arm64-v8a, armeabi-v7a und x86_64 gebündelt. Ohne „Alle Dateien“ führt Anlegen in `/storage/emulated/0` zu `PermissionError`. Sonst **offen** (braucht Gerät): Spike-APK mit Selbsttest liegt in `SyncSpike/`. Wählt man in der App diesen synchronisierten Ordner als Testordner, kommt der Bericht per Syncthing zurück. | Füllt die Android-Zeilen der Plattform-Tabelle |
| **S2** APK aus Monorepo-`src/` | Die Python-App wird mitsamt `merkweiser.core` und einem `desktop`-Paket mit `import tkinter` gepackt. Der erste Build scheiterte an einer Upstream-Unverträglichkeit (Flet-0.86.5-Vorlage pinnt `jni 1.0.0`, löst aber `jni_flutter 1.0.4+1` auf, die `jni ^1.1.0` verlangt). Behoben per `[tool.flet.flutter.pubspec.dependency_overrides] jni_flutter = "1.0.2"`. | **Bestanden** (2026-10-09): Mit dem Override baut `flet build apk` erfolgreich; `core`, `mobile` und `desktop` (mit `import tkinter`, auf Android nie importiert) sind gebündelt. Der Override steht in `pyproject.toml`. Hinweis: Dieselbe Upstream-Unverträglichkeit trifft jedes Flet-0.86.5-Projekt beim nächsten Build. |
| **S3** bw-gui | Ein themed `ttk.Treeview` (`widgets.Treeview` nach `configure_ttk_theme`) mit Text-Checkbox-Spalte (☐/☑) und Hierarchie funktioniert; `checkbutton_guard` und `tk_state_guard` sind sauber. Tcl/Tk 8.6.15: Emoji, Tabs, `\r\n` und Leerraum am Rand bleiben über `Text.get("1.0", "end-1c")` byte-genau erhalten. **`WrappedTextField.get()` entfernt dagegen Leerraum am Rand** (`.strip()`) und taugt nicht für Roh-Bearbeitung. | **BAUSTELLE(bw-gui):** eigener bw-gui-Teilplan für verlustfreies Auslesen (z. B. `get_raw()`) vor Schritt 7 (Nutzerentscheidung 2026-10-09). |
| **S4** Tausch-Protokoll unter Windows mit Obsidian und Syncthing | **offen** (braucht laufendes Obsidian) | `W1`, `W2`, `W4`, Windows-Zeile |
| Windows-Primitive (Vorbefund aus dem S1-Selbsttest, NTFS) | `os.rename` auf ein existierendes Ziel → `FileExistsError` (installiert also atomar ohne Überschreiben). `os.link` auf ein existierendes Ziel → `FileExistsError`. `O_EXCL` funktioniert. `st_ino` bleibt über Rename stabil. Verzeichnis-`fsync` ist **nicht** möglich (`PermissionError`). | Bestätigt die Windows-Zeile der Plattform-Tabelle (ohne Verzeichnis-`fsync`, wie geplant). |

## Grenzen und Baustellen

- **BAUSTELLE(S1):** Android-Spike auf dem Gerät durchführen.
- **BAUSTELLE(S4):** Windows-Spike mit Obsidian und Syncthing durchführen.
- **BAUSTELLE(bw-gui):** Teilplan für das verlustfreie Auslesen von `WrappedTextField`.
- `bw_libs/shared_gui_core.py` (Bootstrap für die bw-gui-Pfadinjektion, nur Desktop, liegt außerhalb von `src/` und landet deshalb nicht im APK): Der Code ist identisch mit der gemeinsamen Vorlage. Der Docstring beschreibt das Geschwister-Repo `../bw-gui` statt eines maschinenspezifischen Pfads (Nutzerentscheidung 2026-10-09; die anderen Consumer-Repos stehen auf der Wunschliste).
