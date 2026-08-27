import asyncio
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright
from icalendar import Calendar, Event


FCF_URL = (
    "https://www.fcf.cat/ca/competicio"
    "?temporadaId=22"
    "&disciplinaId=19308235"
    "&competicioId=58162084"
    "&grupId=58162087"
    "&tab=calendari"
)

TEAM_NAMES = [
    "BARCELONA, F.C. A",
    "BARCELONA F.C. A",
    "FC BARCELONA A",
    "BARCELONA, FC A",
]

TZ = ZoneInfo("Europe/Madrid")


async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(headless=True)

        page = await browser.new_page(
            viewport={"width": 1600, "height": 1200}
        )

        print("Abriendo FCF...")
        await page.goto(
            FCF_URL,
            wait_until="networkidle",
            timeout=90000
        )

        await page.wait_for_timeout(5000)

        body_text = await page.locator("body").inner_text()

        print("Página cargada.")
        print("--------------------------------")
        print(body_text[:15000])
        print("--------------------------------")

        # Guardamos todo el texto para poder revisar
        # fácilmente la primera ejecución.
        with open("fcf_debug.txt", "w", encoding="utf-8") as f:
            f.write(body_text)

        lines = [
            line.strip()
            for line in body_text.splitlines()
            if line.strip()
        ]

        cal = Calendar()

        cal.add("prodid", "-//FC Barcelona S11A//FCF Calendar//ES")
        cal.add("version", "2.0")
        cal.add("x-wr-calname", "FC Barcelona S11A 26/27")
        cal.add("x-wr-timezone", "Europe/Madrid")

        team_matches = []

        for i, line in enumerate(lines):

            if any(team.lower() in line.lower() for team in TEAM_NAMES):

                start = max(0, i - 15)
                end = min(len(lines), i + 16)

                block = lines[start:end]

                team_matches.append(block)

        print(
            f"Bloques encontrados relacionados con Barça: "
            f"{len(team_matches)}"
        )

        # Primera versión diagnóstica.
        #
        # En la primera ejecución veremos exactamente cómo devuelve
        # la FCF cada partido y ajustaremos automáticamente/parsing
        # en función de ese formato.
        #
        # Creamos un ICS válido aunque todavía no haya eventos,
        # para poder comprobar toda la infraestructura.

        with open("barca-s11a.ics", "wb") as f:
            f.write(cal.to_ical())

        print("Calendario generado: barca-s11a.ics")

        for n, block in enumerate(team_matches, start=1):

            print("")
            print(f"===== PARTIDO/BLOQUE {n} =====")

            for line in block:
                print(line)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
