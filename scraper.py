import asyncio
import re
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


async def get_match_from_open_jornada(page, jornada, fecha):
    spans = page.locator(f'span[title="{TEAM}"]')
    count = await spans.count()

    if count == 0:
        return None

    span = spans.first

    current = span
    row = None

    # Subimos por el DOM hasta encontrar el contenedor
    # que tiene exactamente dos nombres de equipo.
    for _ in range(10):
        current = current.locator("xpath=..")

        titles = current.locator("span[title]")
        n_titles = await titles.count()

        if n_titles == 2:
            row = current
            break

    if row is None:
        return None

    titles = row.locator("span[title]")

    teams = []

    for j in range(await titles.count()):
        t = await titles.nth(j).get_attribute("title")

        if t:
            t = clean(t)

            if t not in teams:
                teams.append(t)

    if len(teams) != 2:
        return None

    return {
        "jornada": jornada,
        "fecha": fecha,
        "local": teams[0],
        "visitante": teams[1],
    }


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

        await page.wait_for_timeout(4000)

        print("Calendario cargado.")

        # Buscamos todos los encabezados "JORNADA X"
        jornadas = page.get_by_text(
            re.compile(r"^JORNADA\s+\d+$"),
            exact=True
        )

        total_jornadas = await jornadas.count()

        print(f"Jornadas encontradas: {total_jornadas}")

        matches = []

        for i in range(total_jornadas):

            # Reobtenemos el locator en cada vuelta porque
            # React puede modificar el DOM.
            jornadas = page.get_by_text(
                re.compile(r"^JORNADA\s+\d+$"),
                exact=True
            )

            header = jornadas.nth(i)

            jornada_text = clean(
                await header.inner_text()
            )

            print("")
            print(
                f"--- Abriendo {jornada_text} "
                f"({i + 1}/{total_jornadas}) ---"
            )

            await header.scroll_into_view_if_needed()

            # Buscamos un contenedor superior que también
            # contenga la fecha de esa jornada.
            current = header
            fecha = ""

            for _ in range(6):
                current = current.locator("xpath=..")

                txt = clean(
                    await current.inner_text()
                )

                match_fecha = re.search(
                    r"\b20\d{2}-\d{2}-\d{2}\b",
                    txt
                )

                if match_fecha:
                    fecha = match_fecha.group(0)
                    break

            print(f"Fecha detectada: {fecha}")

            # Hacemos clic en la cabecera.
            try:
                await header.click()
            except Exception:
                await header.click(force=True)

            await page.wait_for_timeout(600)

            # ¿Está el Barça dentro de la jornada abierta?
            partido = await get_match_from_open_jornada(
                page,
                jornada_text,
                fecha
            )

            if partido:
                matches.append(partido)

                print(
                    "BARÇA: "
                    f'{partido["local"]} vs '
                    f'{partido["visitante"]}'
                )

            else:
                print("Barça no encontrado en esta jornada.")

        # Eliminar duplicados por jornada
        unique = []

        seen = set()

        for match in matches:
            key = match["jornada"]

            if key not in seen:
                seen.add(key)
                unique.append(match)

        print("")
        print("==============================")
        print(
            f"PARTIDOS DEL BARÇA: {len(unique)}"
        )
        print("==============================")

        for match in unique:
            print(
                f'{match["jornada"]} | '
                f'{match["fecha"]} | '
                f'{match["local"]} vs '
                f'{match["visitante"]}'
            )

        # Calendario base
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
