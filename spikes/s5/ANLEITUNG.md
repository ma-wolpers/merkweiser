# Spike S5 – Benachrichtigungen auf dem Handy testen

Diese Spike-App („Merkweiser S5“) ist eine **eigene kleine App** neben Merkweiser. Sie liest keine Notizen und braucht keinen Ordnerzugriff. Sie prüft nur, ob geplante Benachrichtigungen mit Flet 0.86.5 zuverlässig funktionieren. Dauer: etwa 30 Minuten, davon viel Warten.

## Installieren

`SyncSpike/merkweiser-s5.apk` installieren und die App öffnen.

## Prüfungen

Nach jedem Schritt kannst du *Status aktualisieren* tippen. Die oberste Zeile zeigt Berechtigung, Anzahl geplanter Benachrichtigungen, ob Exakt-Alarme erlaubt sind, ob die Akku-Optimierung die App einschränkt, und bei schon gezeigten Benachrichtigungen die gemessene **Verspätung** in Sekunden.

| Nr. | Was du tust | Worauf du achtest |
|---|---|---|
| 1 | *1. Berechtigung anfragen* → im Systemdialog **„Nicht zulassen“** | Status zeigt `denied`? |
| 2 | Android-Einstellungen → Apps → Merkweiser S5 → Benachrichtigungen → **erlauben**, zurück zur App | Status zeigt `granted`? |
| 3 | *2. Drei Tests planen*, dann die App **aus dem App-Umschalter wegwischen** | Kommen nach 2, 3 und 4 Minuten drei Benachrichtigungen („normal“, „hoch“, „maximal“)? Erscheinen „hoch“/„maximal“ als Banner oben? |
| 4 | Eine davon **antippen** (App war zu) | Öffnet sich die App mit der Zeile „✔ ÜBER BENACHRICHTIGUNG GEÖFFNET“? |
| 5 | Wieder planen, App **offen lassen**, Benachrichtigung antippen | Wieder „✔ ÜBER BENACHRICHTIGUNG GEÖFFNET“? |
| 6 | *3. Einen Test in 10 Minuten planen*, dann das Handy **neu starten** (nicht entsperren ist ok) | Kommt die Benachrichtigung nach dem Neustart (ggf. etwas später)? |
| 7 | Einstellungen → Apps → Merkweiser S5 → Akku → **„Eingeschränkt“**, dann wieder planen und App wegwischen | Kommt sie trotzdem? Wie viel später? |
| 8 | *Alles stornieren* nach dem Planen | Es kommt nichts mehr? |
| 9 | Berechtigung in den Einstellungen wieder **entziehen**, App öffnen | Status zeigt `denied`? |

## Ergebnis

*Bericht kopieren* tippen und mir den Text schicken, dazu kurz je Nummer: ja/nein und was auffiel (z. B. „7: kam 9 Minuten später“). Bitte auch das Handy-Modell und die Android-Version.

Danach kannst du die Spike-App wieder deinstallieren.
