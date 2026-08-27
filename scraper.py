import asyncio
from icalendar import Calendar
from playwright.async_api import async_playwright

FCF_URL = (
    "https://www.fcf.cat/ca/competicio"
    "?temporadaId=22"
    "&disciplinaId=19308235"
    "&competicioId=58162084"
    "&grupId=58162087"
    "&tab=calendari"
)

TEAM = "BARCELONA, F.C."


def clean(text):
    return " ".join(text.split()).strip()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        page = await browser.new_page(
            viewport={"width": 1600, "height": 1200}
        )

        print("Abriendo calendario FCF...")

        await page.goto(
            FCF_URL,
            wait_until="domcontentloaded",
            timeout=90000
        )

        await page.wait_for_selector(
            f'span[title="{TEAM}"]',
            timeout=90000
        )

        print("Calendario cargado.")

        # --------------------------------------------------
        # FORZAR CARGA DE TODO EL CALENDARIO
        # --------------------------------------------------

        previous_height = 0

        for _ in range(30):

            current_height = await page.evaluate(
                "document.body.scrollHeight"
            )

            await page.evaluate(
                "window.scrollTo(0, document.body.scrollHeight)"
            )

            await page.wait_for_timeout(1200)

            if current_height == previous_height:
                break

            previous_height = current_height

        # Volvemos arriba
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1000)

        print("Scroll completo realizado.")

        # --------------------------------------------------
        # BUSCAR TODOS LOS PARTIDOS
        # --------------------------------------------------

        all_spans = page.locator('span[title]')

        count = await all_spans.count()

        print(f"Elementos con title encontrados: {count}")

        matches = []

        for i in range(count):

            span = all_spans.nth(i)

            title = await span.get_attribute("title")

            if not title:
                continue

            if clean(title).upper() != TEAM:
                continue

            # Subimos al contenedor del partido
            current = span

            row = None

            for _ in range(8):

                current = current.locator("xpath=..")

                titles = current.locator("span[title]")

                n_titles = await titles.count()

                if n_titles == 2:
                    row = current
                    break

            if row is None:
                continue

            titles = row.locator("span[title]")

            teams = []

            for j in range(await titles.count()):
                t = await titles.nth(j).get_attribute("title")

                if t:
                    t = clean(t)

                    if t not in teams:
                        teams.append(t)

            if len(teams) != 2:
                continue

            local = teams[0]
            visitante = teams[1]

            matches.append(
                (local, visitante)
            )

        # --------------------------------------------------
        # QUITAR DUPLICADOS
        # --------------------------------------------------

        unique = []

        seen = set()

        for match in matches:

            key = tuple(match)

            if key not in seen:
                seen.add(key)
                unique.append(match)

        print(
            f"Partidos del Barça encontrados: "
            f"{len(unique)}"
        )

        for n, (local, visitante) in enumerate(
            unique,
            start=1
        ):

            print("")
            print(f"===== PARTIDO {n} =====")
            print(f"{local} vs {visitante}")

        # --------------------------------------------------
        # CREAR ICS BASE
        # --------------------------------------------------

        cal = Calendar()

        cal.add(
            "prodid",
            "-//FC Barcelona S11A//FCF Calendar//ES"
        )

        cal.add("version", "2.0")

        cal.add(
            "x-wr-calname",
            "FC Barcelona S11A 26/27"
        )

        with open("barca-s11a.ics", "wb") as f:
            f.write(cal.to_ical())

        print("")
        print("Calendario base generado.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
