# Development Log

Verlauf aller relevanten Änderungen, auch interner. Neueste Einträge oben.

## 2026-10-09 – Repo-Gerüst und erste Spikes

- Repo angelegt (Monorepo, ein gemeinsamer Core für Desktop und Android).
- `docs/KONZEPT.md` aus der neuen Fassung des ursprünglichen Konzepts extrahiert. Die Quelldatei im Geschwister-Repo `../tools4school` enthält zwei ineinander geratene Fassungen und bleibt unverändert.
- `docs/PLAN.md`: freigegebener Plan nach vier Audit-Runden, eingefroren. Maschinenspezifische Pfade wurden dabei relativ gemacht.
- `docs/FORMAT.md`: verbindliche Grammatik (Trenner, Themen, Erläuterungsabsatz, Überschriften-Ebene, Tabstopps, Fences, Encoding, Tags/Projekte/Vererbung, Konfliktdateien).
- `AGENTS.md` mit den Repo-Regeln.
- `pyproject.toml`: Extras `dev`/`ui`/`build`, Flet-Konfiguration inklusive `MANAGE_EXTERNAL_STORAGE` und dem `jni_flutter`-Override aus Spike S2.
- Spikes S2 und S3 sowie die Windows-Primitive: Befunde in `ARCHITEKTUR.md`. S1 und S4 sind offen, weil sie Gerät bzw. Obsidian brauchen.
- Nebenarbeit in `../bw-gui`: `docs/QUICKSTART.md` enthält keinen maschinenspezifischen Pfad und keine toten Links mehr (Plan, Nebenaufgabe).
