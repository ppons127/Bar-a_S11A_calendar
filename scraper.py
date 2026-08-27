import asyncio
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, Alarm
from playwright.async_api import async_playwright


# ============================================================
# CONFIGURACIÓN
# ============================================================

FCF_URL = (
    "https://www.fcf.cat/ca/competicio"
    "?temporadaId=22"
    "&disciplinaId=19308235"
    "&competicioId=58162084"
    "&grupId=58162087"
    "&tab=calendari"
)

FCF_BASE = "https://www.fcf.cat"

TEAM = "BARCELONA, F.C."
CALENDAR_NAME = "FC Barcelona S11B 26/27"

TZ = ZoneInfo("Europe/Madrid")


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def clean(text):
    return " ".join(text.split()).strip()


def jornada_number(jornada):
    match = re.search(r"(\d+)", jornada)

    if match:
        return int(match.group(1))

    return 0


def pretty_team(team):
    """
    Para que en el calendario aparezca S11B
    en vez de BARCELONA, F.C.
    """
    if clean(team).upper() == TEAM:
        return "S11B"

    return clean(team)


def build_summary(local, visitante):
    local_name = pretty_team(local)
    visitante_name = pretty_team(visitante)

    return f"⚽ {local_name} - {visitante_name}"


# ============================================================
# EXTRAER PARTIDO DE LA JORNADA ABIERTA
# ============================================================

async def get_match_from_open_jornada(page, jornada, fecha):
    spans = page.locator(f'span[title="{TEAM}"]')

    count = await spans.count()

    if count == 0:
        return None

    span = spans.first

    current = span
    row = None

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
        team_name = await titles.nth(j).get_attribute("title")

        if team_name:
            team_name = clean(team_name)

            if team_name not in teams:
                teams.append(team_name)

    if len(teams) != 2:
        return None

    local = teams[0]
    visitante = teams[1]

    acta_href = None
    current = row

    for _ in range(8):
        acta_links = current.locator(
            'a[href*="/ca/competicio/acta/"]'
        )

        if await acta_links.count() > 0:
            acta_href = await acta_links.first.get_attribute("href")
            break

        current = current.locator("xpath=..")

    acta_url = None

    if acta_href:
        if acta_href.startswith("http"):
            acta_url = acta_href
        else:
            acta_url = FCF_BASE + acta_href

    return {
        "jornada": jornada,
        "fecha": fecha,
        "local": local,
        "visitante": visitante,
        "acta_url": acta_url,
    }


# ============================================================
# LEER FECHA / HORA / CAMPO DEL ACTA
# ============================================================

async def read_acta_details(context, match):
    acta_url = match.get("acta_url")

    if not acta_url:
        print("   Sin enlace de acta.")
        return match

    acta_page = await context.new_page()

    try:
        await acta_page.goto(
            acta_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        await acta_page.wait_for_timeout(1200)

        body = clean(
            await acta_page.locator("body").inner_text()
        )

        # FECHA
        date_match = re.search(
            r"DATA\s*:\s*(\d{1,2}/\d{1,2}/\d{4})",
            body,
            flags=re.IGNORECASE
        )

        if date_match:
            parsed = datetime.strptime(
                date_match.group(1),
                "%d/%m/%Y"
            )

            match["fecha"] = parsed.strftime("%Y-%m-%d")

        # HORA
        time_match = re.search(
            r"HORA\s*:\s*(\d{1,2}:\d{2})",
            body,
            flags=re.IGNORECASE
        )

        if time_match:
            match["hora"] = time_match.group(1)
        else:
            match["hora"] = None

        # ESTADIO
        stadium_match = re.search(
            r"ESTADI\s*:\s*(.+?)(?="
            r"ENTRENADOR|DELEGAT|COORDINADOR|$)",
            body,
            flags=re.IGNORECASE
        )

        if stadium_match:
            stadium = clean(stadium_match.group(1))

            for separator in [
                " TEMPORADA",
                " DATA:",
                " HORA:",
            ]:
                if separator in stadium:
                    stadium = stadium.split(separator)[0]

            match["estadi"] = stadium.strip()
        else:
            match["estadi"] = None

        print(
            f'   Hora: {match.get("hora") or "pendiente"}'
        )

        print(
            f'   Campo: {match.get("estadi") or "pendiente"}'
        )

    except Exception as error:
        print(f"   No se pudo leer el acta: {error}")

        match["hora"] = None
        match["estadi"] = None

    finally:
        await acta_page.close()

    return match


# ============================================================
# AÑADIR RECORDATORIOS
# ============================================================

def add_alarm(event, days_before, text):
    alarm = Alarm()

    alarm.add("action", "DISPLAY")
    alarm.add("description", text)

    alarm.add(
        "trigger",
        timedelta(days=-days_before)
    )

    event.add_component(alarm)


# ============================================================
# CREAR EVENTO ICS
# ============================================================

def add_match_to_calendar(cal, match):
    event = Event()

    jornada_n = jornada_number(match["jornada"])

    local = match["local"]
    visitante = match["visitante"]

    summary = build_summary(local, visitante)

    event.add("summary", summary)

    # UID estable para que no se dupliquen eventos
    uid = (
        f"barca-s11a-2627-jornada-"
        f"{jornada_n:02d}@fcf-calendar"
    )

    event.add("uid", uid)

    event.add(
        "dtstamp",
        datetime.now(timezone.utc)
    )

    fecha = datetime.strptime(
        match["fecha"],
        "%Y-%m-%d"
    ).date()

    hora = match.get("hora")

    # SI HAY HORA
    if hora:
        hour, minute = map(
            int,
            hora.split(":")
        )

        start = datetime(
            fecha.year,
            fecha.month,
            fecha.day,
            hour,
            minute,
            tzinfo=TZ
        )

        end = start + timedelta(
            hours=1,
            minutes=30
        )

        event.add("dtstart", start)
        event.add("dtend", end)

    # SI NO HAY HORA
    else:
        event.add("dtstart", fecha)
        event.add(
            "dtend",
            fecha + timedelta(days=1)
        )

    estadio = match.get("estadi")

    if estadio:
        event.add("location", estadio)

    lines = [
        "FC Barcelona S11B",
        "Preferent Aleví S11 - Grup 4",
        match["jornada"],
        "",
        f'Local: {pretty_team(local)}',
        f'Visitante: {pretty_team(visitante)}',
    ]

    if hora:
        lines.append(f"Hora FCF: {hora}")
    else:
        lines.append(
            "Hora pendiente de confirmar por la FCF"
        )

    if estadio:
        lines.append(f"Camp: {estadio}")

    if match.get("acta_url"):
        lines.extend([
            "",
            "Acta oficial FCF:",
            match["acta_url"],
        ])

        event.add(
            "url",
            match["acta_url"]
        )

    event.add(
        "description",
        "\n".join(lines)
    )

    # ========================================================
    # RECORDATORIOS
    # ========================================================

    add_alarm(
        event,
        8,
        f"Partit S11B d'aquí a 8 dies: {summary}"
    )

    add_alarm(
        event,
        3,
        f"Partit S11B d'aquí a 3 dies: {summary}"
    )

    add_alarm(
        event,
        1,
        f"Partit S11B demà: {summary}"
    )

    cal.add_component(event)


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

async def main():
    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            viewport={
                "width": 1600,
                "height": 1200
            }
        )

        page = await context.new_page()

        print("Abriendo calendario FCF...")

        await page.goto(
            FCF_URL,
            wait_until="domcontentloaded",
            timeout=90000
        )

        await page.wait_for_timeout(4000)

        print("Calendario cargado.")

        jornadas = page.get_by_text(
            re.compile(r"^JORNADA\s+\d+$"),
            exact=True
        )

        total_jornadas = await jornadas.count()

        print(
            f"Jornadas encontradas: {total_jornadas}"
        )

        matches = []

        # RECORRER TODAS LAS JORNADAS
        for i in range(total_jornadas):

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
                f"--- {jornada_text} "
                f"({i + 1}/{total_jornadas}) ---"
            )

            await header.scroll_into_view_if_needed()

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

            print(f"Fecha jornada: {fecha}")

            # Jornada 1 ya está abierta por defecto
            if i > 0:
                try:
                    await header.click()
                except Exception:
                    await header.click(force=True)

                await page.wait_for_timeout(500)

            partido = (
                await get_match_from_open_jornada(
                    page,
                    jornada_text,
                    fecha
                )
            )

            if partido:
                matches.append(partido)

                print(
                    "BARÇA: "
                    f'{partido["local"]} vs '
                    f'{partido["visitante"]}'
                )

                print(
                    "Acta: "
                    f'{partido["acta_url"]}'
                )

            else:
                print("Barça no encontrado.")

        # ELIMINAR DUPLICADOS
        unique = []
        seen = set()

        for match in matches:
            key = jornada_number(
                match["jornada"]
            )

            if key not in seen:
                seen.add(key)
                unique.append(match)

        unique.sort(
            key=lambda x: jornada_number(
                x["jornada"]
            )
        )

        print("")
        print("==============================")

        print(
            f"PARTIDOS DEL BARÇA: {len(unique)}"
        )

        print("==============================")

        # LEER HORARIOS Y CAMPOS
        print("")
        print("Leyendo horarios y campos...")

        detailed_matches = []

        for index, match in enumerate(
            unique,
            start=1
        ):
            print("")
            print(
                f'[{index}/{len(unique)}] '
                f'{match["jornada"]}'
            )

            detailed = (
                await read_acta_details(
                    context,
                    match
                )
            )

            detailed_matches.append(detailed)

        # CREAR CALENDARIO
        cal = Calendar()

        cal.add(
            "prodid",
            "-//FC Barcelona S11B//FCF Calendar//ES"
        )

        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")

        cal.add(
            "x-wr-calname",
            CALENDAR_NAME
        )

        cal.add(
            "x-wr-timezone",
            "Europe/Madrid"
        )

        cal.add(
            "x-wr-caldesc",
            "Calendari automàtic FC Barcelona S11B - FCF"
        )

        # AÑADIR PARTIDOS
        for match in detailed_matches:

            if not match.get("fecha"):
                print(
                    "Partido sin fecha, no se añade:"
                )
                print(match["jornada"])
                continue

            add_match_to_calendar(
                cal,
                match
            )

        # GUARDAR ICS
        with open(
            "barca-s11a.ics",
            "wb"
        ) as f:
            f.write(
                cal.to_ical()
            )

        print("")
        print("================================")
        print("CALENDARIO ICS GENERADO")
        print(
            f"Eventos: {len(detailed_matches)}"
        )
        print("================================")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
