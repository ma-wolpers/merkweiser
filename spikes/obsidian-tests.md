# Obsidian-Tests (Spikes S1-Rest und S4)

Zwei Tests klären, ob Merkweisers sicheres Speichern mit Obsidian zusammenarbeitet. Beide laufen **nur mit Testdaten in eigenen Testordnern**, nie mit deinen echten Notizen.

| Test | Wo | Dauer | Was er klärt |
|---|---|---|---|
| **A – Obsidian am Handy** | Handy | ca. 15 min | Übernimmt Obsidian Änderungen, die Merkweiser macht, während die Notiz in Obsidian offen ist? Gehen Haken oder getippter Text verloren? |
| **B – Obsidian am Rechner** | Windows-PC | ca. 15 min | Hält Obsidian Dateien offen? Wie reagiert es, wenn Merkweiser kurz sperrt oder die Datei austauscht? |

Die Reihenfolge ist egal.

---

## Test A – Obsidian am Handy

### Vorbereitung

1. Lege auf dem Handy einen neuen, **nicht synchronisierten** Ordner an, z. B. `/storage/emulated/0/MerkweiserObsidianTest`.
2. Öffne ihn in Obsidian als **neuen Vault** (*Vault öffnen → Ordner als Vault öffnen*).
3. Lege darin eine Notiz an, deren Name das heutige Datum ist (z. B. `2026-10-22`), mit genau diesem Inhalt:

   ```markdown
   Testthema #test
   - [ ] Aufgabe eins
   - [ ] Aufgabe zwei
   - [ ] Aufgabe drei
   ```

4. In Merkweiser: *Einstellungen → Ordner wechseln* → den Testordner wählen bzw. den Pfad eintippen. Im Tab **Heute** erscheinen jetzt die drei Aufgaben.

Wechsle zwischen den Apps immer über den App-Umschalter, **ohne** eine der Apps zu schließen. Die Notiz bleibt in Obsidian die ganze Zeit im Bearbeitungsmodus offen.

### A1 – Merkweiser ändert, während die Notiz in Obsidian offen ist

1. Obsidian: Tippe am Ende der Notiz eine neue Zeile `OBS-1`. Warte 5 Sekunden.
2. Merkweiser: Hake **Aufgabe eins** ab. Warte 15 Sekunden.
3. Obsidian: Ist der Haken bei Aufgabe eins zu sehen? Tippe am Ende eine neue Zeile `OBS-2`. Warte 5 Sekunden.
4. Merkweiser: Ist Aufgabe eins noch abgehakt? Sind `OBS-1` und `OBS-2` zu sehen? Gibt es im Tab Konflikte etwas Neues?

### A2 – schneller Wechsel (innerhalb von 10 Sekunden)

1. Merkweiser: Hake **Aufgabe zwei** ab und wechsle **sofort** zu Obsidian.
2. Obsidian: Tippe sofort eine neue Zeile `OBS-3`. Warte 5 Sekunden.
3. Warte weitere 15 Sekunden, dann zu Merkweiser: Haken bei Aufgabe zwei? `OBS-3` da? Konflikte?

### A3 – beide schreiben fast gleichzeitig

1. Obsidian: Tippe `OBS-4`, ohne zu warten, und wechsle **sofort** zu Merkweiser.
2. Merkweiser: Schreibe eine neue Notiz `MW-Notiz` und speichere sie.
3. Sofort zurück zu Obsidian: Tippe `OBS-5`. Warte 5 Sekunden.
4. Warte 15 Sekunden, dann zu Merkweiser: Was ist da (`OBS-4`, `OBS-5`, `MW-Notiz`)? Konflikte?

### Ergebnis festhalten

Schließe zum Schluss die Notiz in Obsidian und öffne sie neu, damit Obsidian sie frisch von der Platte liest. Notiere je Test:

| Test | Haken da? | OBS-Zeilen da? | `MW-Notiz` da? (nur A3) | Neue Konfliktdatei? | Meldung oder Auffälligkeit in Obsidian? |
|---|---|---|---|---|---|
| A1 | | | – | | |
| A2 | | | – | | |
| A3 | – | | | | |

Speichere danach in Merkweiser einen **Diagnosebericht** (*Einstellungen*, z. B. nach `/storage/emulated/0/Download`) und schick mir die Tabelle und den Bericht. Den Inhalt der Testnotiz kannst du gern mitschicken; es sind ja nur Testdaten.

Danach in Merkweiser über *Einstellungen → Ordner wechseln* wieder deinen echten Notizordner wählen.

---

## Test B – Obsidian am Rechner

### Vorbereitung

1. PowerShell im Repo-Ordner `merkweiser` öffnen und starten:

   ```powershell
   python spikes\s4\spike_s4.py
   ```

   Das Skript legt den Testordner `spikes\s4\MerkweiserS4-Testvault` mit einer Testnotiz an (Git ignoriert ihn).
2. Öffne diesen Ordner in Obsidian als **neuen Vault** und darin die Notiz `2026-01-01`.
3. Optional, aber hilfreich: Gib den Testordner zusätzlich in Syncthing frei, z. B. an dein Handy. Dann prüft Teil D auch Syncthings Verhalten.

### Ablauf

Das Skript führt dich durch vier Teile und hält an jeder Stelle an, an der du in Obsidian etwas tun sollst. Fragt es nach einer Beobachtung, tippe kurz ein, was du gesehen hast; nur Enter heißt „nichts Auffälliges“.

| Teil | Was du tust | Worauf du achtest |
|---|---|---|
| **A** – offen halten | 30 Sekunden lang in der Notiz tippen | nichts, das Skript misst |
| **B** – Schreibsperre | während der 15-Sekunden-Sperre `SPERRE-B` tippen | Fehlermeldung in Obsidian? Text weg? |
| **C** – Austausch mit Haltepunkten | an fünf Haltepunkten jeweils `HP-A` … `HP-E` tippen | Meldung? Tab geschlossen? Text verworfen? |
| **D** – Datei 60 s weg | nichts tippen, nur beobachten | Schließt Obsidian den Tab? Legt es die Datei neu an? Verteilt Syncthing eine Löschung? |

### Ergebnis

Am Ende schreibt das Skript `spikes\s4\MerkweiserS4-Testvault\s4-bericht-<Datum>-<Uhrzeit>.txt`. Sag mir einfach Bescheid, wenn er da ist. Ich lese ihn direkt, weil er nur Testdaten enthält.

Danach kannst du den Test-Vault aus Obsidian (und ggf. Syncthing) wieder entfernen.

### Teil E – echtes Speichern (Zusatz vom 2026-10-21)

Die Teile A–D bilden das Speichern von Hand nach und halten an Haltepunkten an. Teil E nutzt dagegen **Merkweisers echten Speichercode**: Die Datei ist dabei nur Mikrosekunden „weg“.

1. Die Notiz `2026-01-01` im Test-Vault in Obsidian öffnen, Cursor ans Ende.
2. Starten:

   ```powershell
   python spikes\s4\spike_s4.py --teil-e
   ```

3. Nach Enter schreibt das Skript fünfmal im Abstand von 3 Sekunden eine Zeile `- [ ] Merkweiser-E1` … `E5` in die Notiz. **Tippe währenddessen laufend weiter** (z. B. `E-TIPP` und ein paar Wörter).
4. Achte darauf: Bleibt der Tab offen? Erscheinen die E-Zeilen in Obsidian? Bleibt dein getippter Text erhalten? Kommt eine Fehlermeldung?
5. Am Ende fragt das Skript nach deiner Beobachtung und schreibt wie oben einen `s4-bericht-…txt`.
