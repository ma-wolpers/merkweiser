"""Spike S5: Prüft geplante Benachrichtigungen auf dem Gerät (Wegwerfcode, siehe spikes/s5/ANLEITUNG.md).

Knöpfe für jede Prüfung aus PLAN-SPAETERE-SCHRITTE.md (Y10): Berechtigung,
Planen (2/3/4 Minuten, drei Dringlichkeitsstufen), Stornieren, Status mit
gemessener Verspätung, Antippen → „Über Benachrichtigung geöffnet“, Bericht
in die Zwischenablage.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import flet as ft
from merkweiser_notify import MerkweiserNotify


async def main(page: ft.Page) -> None:
    page.title = "Merkweiser S5"
    notify = MerkweiserNotify()
    clipboard = ft.Clipboard()
    page.services.extend([notify, clipboard])
    log = ft.Column(spacing=2)
    status = ft.Text("", size=12)
    lines: list[str] = []

    def say(text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        lines.append(f"{stamp} {text}")
        log.controls.insert(0, ft.Text(f"{stamp} {text}", size=12))
        page.update()

    async def call(label: str, coro):
        try:
            result = await coro
            say(f"{label}: {result}")
            return result
        except Exception as exc:  # Spike: alles sichtbar machen
            say(f"{label}: FEHLER {type(exc).__name__}: {exc}")
            return None

    async def refresh(_e=None) -> None:
        info = await call("Status", notify.status())
        if isinstance(info, dict):
            delivered = info.get("delivered") or []
            delays = [f"#{d['id']}: {(d['gezeigt'] - d['geplant']) / 1000:+.0f} s" for d in delivered]
            status.value = (f"Berechtigung: {info.get('permission')} · geplant: {info.get('pending')} · "
                            f"Exakt-Alarme erlaubt: {info.get('exact_allowed')} · "
                            f"Akku ohne Einschränkung: {info.get('battery_unrestricted')}\n"
                            f"Gezeigt (Verspätung): {', '.join(delays) or '–'}")
            page.update()

    async def request(_e) -> None:
        await call("Berechtigung anfragen", notify.request_permission())
        await refresh()

    async def plan(_e) -> None:
        now = datetime.now().astimezone()
        items = [{"id": 1 + i, "at": int((now + timedelta(minutes=2 + i)).timestamp() * 1000),
                  "title": f"S5-Test {level}", "body": f"Geplant für {(now + timedelta(minutes=2 + i)):%H:%M}",
                  "level": level} for i, level in enumerate(("normal", "hoch", "maximal"))]
        await call("Planen (2/3/4 min)", notify.schedule(items))
        await refresh()

    async def plan_later(_e) -> None:
        at = datetime.now().astimezone() + timedelta(minutes=10)
        await call("Planen (10 min, für Neustart-Test)", notify.schedule([
            {"id": 10, "at": int(at.timestamp() * 1000), "title": "S5 nach Neustart", "body": f"Geplant für {at:%H:%M}",
             "level": "normal"}]))
        await refresh()

    async def cancel(_e) -> None:
        await call("Alles stornieren", notify.cancel_all())
        await refresh()

    async def copy(_e) -> None:
        await clipboard.set("\n".join(["Merkweiser S5-Bericht", status.value or "", *lines]))
        say("Bericht in die Zwischenablage kopiert")

    async def check_payload(_e=None) -> None:
        payload = await call("Start-Payload", notify.launch_payload())
        if payload == "heute":
            say("✔ ÜBER BENACHRICHTIGUNG GEÖFFNET (würde Tab „Tag“ mit heute zeigen)")

    async def lifecycle(e) -> None:
        if "resume" in str(e.state).lower():
            await check_payload()
            await refresh()

    page.on_app_lifecycle_state_change = lifecycle
    page.add(ft.SafeArea(content=ft.Column([
        ft.Text("Spike S5 – Benachrichtigungen", size=20, weight=ft.FontWeight.BOLD),
        status,
        ft.Button("1. Berechtigung anfragen", on_click=request),
        ft.Button("2. Drei Tests planen (in 2, 3, 4 Minuten)", on_click=plan),
        ft.Button("3. Einen Test in 10 Minuten planen (Neustart)", on_click=plan_later),
        ft.Button("Alles stornieren", on_click=cancel),
        ft.Button("Status aktualisieren", on_click=refresh),
        ft.Button("Bericht kopieren", on_click=copy),
        ft.Divider(), log], scroll=ft.ScrollMode.AUTO, expand=True), expand=True))
    await check_payload()
    await refresh()


ft.run(main)
