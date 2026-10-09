# Merkweiser – Architektur (Ist-Zustand)

Dieses Dokument beschreibt, **was aktuell umgesetzt ist**. Ziel, Garantien und Protokolle stehen in [PLAN.md](PLAN.md). Sobald ein Teil umgesetzt ist, wandert seine Beschreibung von dort hierher (als Ist-Zustand).

## Stand

- Schritt 1 (Gerüst) ist umgesetzt: Paketstruktur `src/merkweiser/{core,ports,app}`, Doku, `pyproject.toml`.
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

## Spike-Ergebnisse (Schritt 0)

Der Spike-Code liegt unter `spikes/` (S1/S2: `spikes/s1s2/`, ein eigenes Flet-Projekt; S3: `spikes/s3/`; S4: `spikes/s4/`). Er ist **kein Produktcode** und wird nicht importiert oder getestet. APKs und Berichte laufen über den Syncthing-Ordner `SyncSpike/` im Repo-Root, den Git ignoriert.

| Spike | Ergebnis | Folgen |
|---|---|---|
| **S1** Android-Ordnerzugriff und Primitive | **offen** (braucht Gerät): Spike-APK mit Selbsttest liegt in `SyncSpike/`. Wählt man in der App diesen synchronisierten Ordner als Testordner, kommt der Bericht per Syncthing zurück. | Füllt die Android-Zeilen der Plattform-Tabelle |
| **S2** APK aus Monorepo-`src/` | Die Python-App wird mitsamt `merkweiser.core` und einem `desktop`-Paket mit `import tkinter` gepackt. Der erste Build scheiterte an einer Upstream-Unverträglichkeit (Flet-0.86.5-Vorlage pinnt `jni 1.0.0`, löst aber `jni_flutter 1.0.4+1` auf, die `jni ^1.1.0` verlangt). Behoben per `[tool.flet.flutter.pubspec.dependency_overrides] jni_flutter = "1.0.2"`. | **Bestanden** (2026-10-09): Mit dem Override baut `flet build apk` erfolgreich; `core`, `mobile` und `desktop` (mit `import tkinter`, auf Android nie importiert) sind gebündelt. Der Override steht in `pyproject.toml`. Hinweis: Dieselbe Upstream-Unverträglichkeit trifft jedes Flet-0.86.5-Projekt beim nächsten Build. |
| **S3** bw-gui | Ein themed `ttk.Treeview` (`widgets.Treeview` nach `configure_ttk_theme`) mit Text-Checkbox-Spalte (☐/☑) und Hierarchie funktioniert; `checkbutton_guard` und `tk_state_guard` sind sauber. Tcl/Tk 8.6.15: Emoji, Tabs, `\r\n` und Leerraum am Rand bleiben über `Text.get("1.0", "end-1c")` byte-genau erhalten. **`WrappedTextField.get()` entfernt dagegen Leerraum am Rand** (`.strip()`) und taugt nicht für Roh-Bearbeitung. | **BAUSTELLE(bw-gui):** eigener bw-gui-Teilplan für verlustfreies Auslesen (z. B. `get_raw()`) vor Schritt 7 (Nutzerentscheidung 2026-10-09). |
| **S4** Tausch-Protokoll unter Windows mit Obsidian und Syncthing | **offen** (braucht laufendes Obsidian) | `W1`, `W2`, `W4`, Windows-Zeile |
| Windows-Primitive (Vorbefund aus dem S1-Selbsttest, NTFS) | `os.rename` auf ein existierendes Ziel → `FileExistsError` (installiert also atomar ohne Überschreiben). `os.link` auf ein existierendes Ziel → `FileExistsError`. `O_EXCL` funktioniert. `st_ino` bleibt über Rename stabil. Verzeichnis-`fsync` ist **nicht** möglich (`PermissionError`). | Bestätigt die Windows-Zeile der Plattform-Tabelle (ohne Verzeichnis-`fsync`, wie geplant). |

## Grenzen und Baustellen

- **BAUSTELLE(S1):** Android-Spike auf dem Gerät durchführen.
- **BAUSTELLE(S4):** Windows-Spike mit Obsidian und Syncthing durchführen.
- **BAUSTELLE(bw-gui):** Teilplan für das verlustfreie Auslesen von `WrappedTextField`.
- `bw_libs/shared_gui_core.py` (Bootstrap für die bw-gui-Pfadinjektion, nur Desktop, liegt außerhalb von `src/` und landet deshalb nicht im APK): Der Code ist identisch mit der gemeinsamen Vorlage. Der Docstring beschreibt das Geschwister-Repo `../bw-gui` statt eines maschinenspezifischen Pfads (Nutzerentscheidung 2026-10-09; die anderen Consumer-Repos stehen auf der Wunschliste).
