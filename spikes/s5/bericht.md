# Spike S5 – Bericht (2026-10-26)

Ergebnis: **bestanden.**

Bericht der Spike-App (vom Nutzer übermittelt, Zeitstempel in ms seit 1970):

```
Berechtigung: granted · geplant: 0 · Exakt-Alarme erlaubt: False · Akku ohne Einschränkung: False
Gezeigt (Verspätung): #10: +122 s, #1: +90 s, #2: +30 s, #2: +10 s, #3: +55 s
```

| Prüfung (ANLEITUNG.md) | Ergebnis |
|---|---|
| 1, 2, 9 Berechtigung verweigern/erlauben/entziehen | ja (laut Nutzer) |
| 3 Zustellung bei weggewischter App | ja, Verspätung 10–122 s |
| 4, 5 Antippen öffnet die App | ja (laut Nutzer; im obigen Lauf nicht über die Benachrichtigung geöffnet, daher Payload `None`) |
| 6 Zustellung nach Neustart | ja (laut Nutzer; #10 = 10-Minuten-Test kam an) |
| 7 Akku „Eingeschränkt“ | ja (laut Nutzer) |
| 8 Alles stornieren | ja (laut Nutzer) |

Beobachtungen:

- Ungenaue Alarme (`setAndAllowWhileIdle`) reichen: kein Exakt-Alarm-Recht, keine Akku-Ausnahme nötig.
- #1 und #2 eines Laufs kamen in derselben Millisekunde: Android bündelt nahe Alarme. Für Merkweiser (ein Alarm pro Tag) ohne Folgen.
- Mehrere Läufe: „Es ist immer irgendeine Benachrichtigung durchgekommen, wenn auch mit immer mal wieder etwas Verspätung.“

Die Spike-App wird nicht mehr gebraucht; Merkweiser enthält das Plugin seit 2026-10-25.
