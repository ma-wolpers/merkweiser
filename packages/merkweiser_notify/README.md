# merkweiser-notify

Kleine Flet-0.86.5-Erweiterung für **geplante Benachrichtigungen auf Android** (Spike S5, siehe `docs/PLAN-SPAETERE-SCHRITTE.md`, W5).

- **Python:** `merkweiser_notify.MerkweiserNotify` ist ein Flet-`Service`.
- **Dart:** `lib/src/notify_service.dart` reicht die Aufrufe per `MethodChannel` an Android weiter.
- **Android:** `android/` ist ein eigenes Flutter-Plugin in Kotlin. Es nutzt nur Bordmittel: `AlarmManager.setAndAllowWhileIdle` (ungenau, ohne Exact-Alarm-Recht), `Notification` mit drei Kanälen (normal, hoch, maximal) und zwei Receiver für Auslösen und Neustart. Sie stehen im Manifest des Plugins, und Android mischt dieses Manifest beim Build automatisch ein.

Warum kein `flutter_local_notifications`? Ab Version 10 verlangt es „core library desugaring“ in der `build.gradle` der App. Die Flet-Build-Vorlage aktiviert das nicht. Man bräuchte also eine eigene Build-Vorlage, die bei jedem Flet-Update gepflegt werden müsste.

## Schnittstelle

| Methode | Wirkung |
|---|---|
| `permission()` | `"granted"` oder `"denied"` (ab Android 13 die Laufzeitberechtigung, sonst die App-Einstellung) |
| `request_permission()` | fragt ab Android 13 nach und liefert danach den Zustand |
| `schedule(items)` | ersetzt **alle** geplanten Benachrichtigungen; Felder je Eintrag: `id` (int), `at` (ms seit 1970, UTC), `title`, `body`, `level` (`normal`/`hoch`/`maximal`) |
| `cancel_all()` | storniert alle geplanten (bereits angezeigte bleiben) |
| `status()` | `permission`, `pending`, `exact_allowed`, `battery_unrestricted` (für den Spike-Bericht) |
| `launch_payload()` | `"heute"`, wenn die App über eine Benachrichtigung geöffnet wurde (einmalig), sonst `None` |
