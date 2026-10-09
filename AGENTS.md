# AGENTS.md – Regeln für dieses Repo

Diese Regeln gelten für alle Änderungen an Merkweiser, egal ob durch Menschen oder Agents.

## Maßgebliche Dokumente

- **`docs/PLAN.md`**: der freigegebene Umsetzungsplan mit Garantien, Protokollen und Entscheidungen. Getroffene Entscheidungen werden **nie stillschweigend** aufgeweicht, ersetzt oder fallen gelassen. Bei Widersprüchen wird nachgefragt.
- **`docs/FORMAT.md`**: die verbindliche Markdown-Grammatik (was eine Notiz, ein Thema, ein Todo, ein Tag ist).
- **`docs/ARCHITEKTUR.md`**: der *Ist-Zustand*, keine Historie.
- **`docs/DEVELOPMENT_LOG.md`**: der Verlauf, inklusive interner Refactorings.
- **`CHANGELOG.md`**: nur Änderungen, die man bei der Nutzung bemerkt (Keep a Changelog).

## Code-Regeln

- **Schichten:** `core/` hat keine UI-, Flet-, Tk- oder Android-Abhängigkeit; Dateisystem-I/O ist dort erlaubt, wo es fachlich nötig ist.
  - `ports/` enthält nur Protocols.
  - `app/` (`NotesService`) ist die einzige Fassade für die UIs.
  - `desktop/` nutzt ausschließlich bw-gui; es gibt keine eigenen Tk-Widgets und kein `bind_all`.
  - `mobile/platform/` ist der **einzige** Ort, der Flet- oder Android-APIs benennt.
  - Jede Framework-Annahme wird gegen die gepinnte Version (Flet 0.86.5) geprüft, bevor sie in Code oder Doku landet.
- **Dateigröße:** ~300 Zeilen **ausführbarer Code** pro Datei. Gezählt wird per AST bzw. tokenize; Docstrings, Kommentare, Leerzeilen und Imports zählen nicht, `wc -l` ist also nicht das Maß. Diese Grenze ist ein Richtwert und kein Anlass für künstliche `*_helpers`/`*_utils`-Module. Ausnahmen bekommen `# GRENZE(dateigroesse): <Grund>` und einen Eintrag in `docs/ARCHITEKTUR.md`.
- **Docstrings** im Google-Stil für jede neue oder geänderte Funktion bzw. Methode. Sie beschreiben Zweck, Argumente, Rückgabe, Invarianten und Fehlerfälle.
- **Marker:** `GRENZE:` für bewusst akzeptierte Einschränkungen, `BAUSTELLE:` für offene Punkte, optional mit Scope, z. B. `GRENZE(W1):`. Keine `TODO`/`FIXME`. Suche: `rg -n "\b(GRENZE|BAUSTELLE)\b"`.
- **Pfade:** keine maschinenspezifischen absoluten Pfade in Code, Doku oder Konfiguration. Pfade stehen relativ zum Repo oder als Geschwister-Repo (`../bw-gui`).
- **Testdaten:** ausschließlich synthetische Fixtures. Niemals echte Notizen, Vault-Inhalte oder Schülerdaten lesen oder kopieren.
- **Tests:** `pytest`; Zeit nur über `FakeClock`; Dateisystem-Abstürze über Fault-Injection.

## Arbeitsweise

- **Spikes** liegen unter `spikes/`; das ist kein Produktcode. Austausch mit dem Handy (APKs, Berichte) läuft über den Syncthing-Ordner `SyncSpike/`, den Git ignoriert. Wegwerfcode kommt nicht ins Scratchpad, sondern ins Repo.

- Jeder abgeschlossene Teilschritt wird ein eigener Commit **direkt auf `main`**, ohne Feature-Branches. Gestaged werden nur eigene Änderungen. Keine Co-Authored-By-Zeile. Gepusht wird nur von Hand.
- Doku (CHANGELOG, ARCHITEKTUR, DEVELOPMENT_LOG, FORMAT) wird **im selben Commit** gepflegt.
- Unverwandte Bugs, die während der Umsetzung auffallen, werden gemeldet und erst nach Rückfrage behoben.
- bw-gui wird nur über einen eigenen, freigegebenen Teilplan erweitert.
