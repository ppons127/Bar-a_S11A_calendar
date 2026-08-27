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

TEAM = "BARCELONA, F.C."
TZ = ZoneInfo("Europe/Madrid")


def clean(text):
    return " ".join(text.split()).strip()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        page = await browser.new_page(
            viewport={"width": 1600, "height": 2000}
        )

        print("Abriendo calendario FCF...")

        await page.goto(
            FCF_URL,
            wait_until="domcontentloaded",
            timeout=90000
        )

        # Esperamos explícitamente a que el calendario
        # haya renderizado al FC Barcelona.
        await page.wait_for_selector(
            f'span[title="{TEAM}"]',
            timeout=90000
        )

        await page.wait_for_timeout(3000)

        print("Calendario cargado.")

        cal = Calendar()
        cal.add("prodid", "-//FC Barcelona S11A//FCF Calendar//ES")
        cal.add("version", "2.0")
        cal.add("x-wr-calname", "FC Barcelona S11A 26/27")
        cal.add("x-wr-timezone", "Europe/Madrid")

        # Buscamos todos los span con nombres de equipos.
        team_spans = page.locator('span[title]')

        count = await team_spans.count()

        print(f"Elementos con title encontrados: {count}")

        matches = []

        # Buscamos las filas donde aparece Barça.
        for i in range(count):

            span = team_spans.nth(i)

            title = await span.get_attribute("title")

            if not title:
                continue

            if clean(title).upper() != TEAM:
                continue

            # Subimos hasta encontrar el contenedor de la fila
            # que contiene exactamente los dos equipos.
            row = span.locator(
                "xpath=ancestor::div[contains(@class,'flex') "
                "and contains(@class,'items-center')]"
            ).first

            row_html = await row.evaluate(
                "(el) => el.outerHTML"
            )

            # Dentro de esa fila buscamos los nombres de equipos.
            row_locator = row.locator('span[title]')
            row_count = await row_locator.count()

            teams = []

            for j in range(row_count):
                t = await row_locator.nth(j).get_attribute("title")

                if t:
                    t = clean(t)

                    if t not in teams:
                        teams.append(t)

            # Buscamos una combinación que contenga al Barça
            # y exactamente otro equipo.
            teams = [
                t for t in teams
                if len(t) > 2
            ]

            if TEAM not in teams:
                continue

            if len(teams) < 2:
                continue

            # Nos quedamos con los dos primeros nombres distintos.
            local = teams[0]
            visitante = teams[1]

            matches.append(
                {
                    "local": local,
                    "visitante": visitante,
                    "html": row_html
                }
            )

        # Eliminamos duplicados.
        unique = []

        seen = set()

        for match in matches:

            key = (
                match["local"],
                match["visitante"]
            )

            if key not in seen:
                seen.add(key)
                unique.append(match)

        print(f"Partidos del Barça encontrados: {len(unique)}")

        for n, match in enumerate(unique, start=1):

            print("")
            print(f"===== PARTIDO {n} =====")
            print(
                f'{match["local"]} vs '
                f'{match["visitante"]}'
            )

        # -----------------------------------------------------
        # SEGUNDA PARTE:
        # fecha + jornada + hora
        # -----------------------------------------------------

        # De momento creamos el calendario.
        # En la siguiente ejecución vamos a comprobar
        # que los partidos se detectan correctamente.
        #
        # Después añadiremos fecha/hora/jornada,
        # que están en el contenedor superior.

        with open("barca-s11a.ics", "wb") as f:
            f.write(cal.to_ical())

        print("")
        print("Calendario base generado.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
