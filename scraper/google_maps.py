"""
scraper/google_maps.py
Busca profesionales de salud en Google Places API y los persiste en SQLite.
"""

import os
import sys
import time
import sqlite3
import logging
from datetime import datetime

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    ZONAS, PROFESIONES, TEXT_SEARCH_ENDPOINT, DETAILS_ENDPOINT,
    DETAILS_FIELDS, MAX_PAGES, API_SLEEP,
    TEMP_CALIENTE_RESENAS_MIN, TEMP_CALIENTE_RESENAS_MAX,
    TEMP_TIBIO_RESENAS_UMBRAL, TEMP_FRIO_RESENAS_UMBRAL,
    DOMINIOS_WEB_BASICA, DB_PATH,
)

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
#  Base de datos
# ─────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS prospectos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre            TEXT NOT NULL,
    profesion         TEXT,
    direccion         TEXT,
    telefono          TEXT,
    web_actual        TEXT,
    rating            REAL,
    total_resenas     INTEGER,
    place_id          TEXT UNIQUE NOT NULL,
    zona              TEXT,
    fecha_scrape      TEXT,
    temperatura       TEXT,
    estado_prospecto  TEXT DEFAULT 'nuevo',
    -- campos que rellena web_analyzer
    web_score         INTEGER,
    web_tecnologia    TEXT,
    solo_directorios  INTEGER DEFAULT 0
);
"""


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(DDL)
    logger.info("DB inicializada en %s", DB_PATH)


def place_id_exists(conn, place_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM prospectos WHERE place_id = ?", (place_id,)
    ).fetchone()
    return row is not None


def insert_prospecto(conn, data: dict):
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    sql = f"INSERT OR IGNORE INTO prospectos ({cols}) VALUES ({placeholders})"
    conn.execute(sql, list(data.values()))
    conn.commit()


# ─────────────────────────────────────────
#  Lógica de temperatura
# ─────────────────────────────────────────

def _es_web_basica(url: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    return any(dom in url_lower for dom in DOMINIOS_WEB_BASICA)


def calcular_temperatura(web_actual: str, total_resenas: int) -> str:
    resenas = total_resenas or 0
    tiene_web = bool(web_actual)
    web_basica = _es_web_basica(web_actual)

    if resenas > TEMP_FRIO_RESENAS_UMBRAL and tiene_web and not web_basica:
        return "FRIO"
    if tiene_web and not web_basica:
        return "FRIO"
    if not tiene_web and TEMP_CALIENTE_RESENAS_MIN <= resenas <= TEMP_CALIENTE_RESENAS_MAX:
        return "CALIENTE"
    if web_basica or (resenas > TEMP_TIBIO_RESENAS_UMBRAL and not tiene_web):
        return "TIBIO"
    if not tiene_web and resenas < TEMP_CALIENTE_RESENAS_MIN:
        return "TIBIO"

    return "FRIO"


# ─────────────────────────────────────────
#  Google Places API
# ─────────────────────────────────────────

def _get(url: str, params: dict) -> dict:
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key or api_key == "TU_API_KEY_AQUI":
        raise EnvironmentError(
            "GOOGLE_API_KEY no configurada. Editá el archivo .env con tu clave."
        )
    params["key"] = api_key
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def text_search(query: str, page_token: str = None) -> dict:
    params = {"query": query, "language": "es"}
    if page_token:
        params["pagetoken"] = page_token
    return _get(TEXT_SEARCH_ENDPOINT, params)


def place_details(place_id: str) -> dict:
    params = {"place_id": place_id, "fields": DETAILS_FIELDS, "language": "es"}
    return _get(DETAILS_ENDPOINT, params)


# ─────────────────────────────────────────
#  Pipeline de scraping
# ─────────────────────────────────────────

def scrape_profesion_zona(profesion: str, zona: str, conn) -> int:
    """Busca una profesión en una zona. Devuelve cuántos registros nuevos insertó."""
    query = f"{profesion} {zona}"
    logger.info("Buscando: %s", query)

    nuevos = 0
    page_token = None

    for page_num in range(1, MAX_PAGES + 1):
        try:
            if page_num > 1 and page_token:
                # Google requiere una pequeña espera antes de usar next_page_token
                time.sleep(2)
            data = text_search(query, page_token)
        except Exception as exc:
            logger.error("Error en text_search '%s' (pág %d): %s", query, page_num, exc)
            break

        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            logger.warning("Status inesperado '%s' para '%s'", status, query)
            break
        if status == "ZERO_RESULTS":
            logger.info("Sin resultados para '%s'", query)
            break

        results = data.get("results", [])
        logger.info("  Página %d — %d resultados", page_num, len(results))

        for item in results:
            pid = item.get("place_id")
            if not pid:
                continue

            if place_id_exists(conn, pid):
                logger.debug("  place_id %s ya existe, skip.", pid)
                continue

            # Detalle completo
            time.sleep(API_SLEEP)
            try:
                det = place_details(pid).get("result", {})
            except Exception as exc:
                logger.error("  Error en place_details %s: %s", pid, exc)
                continue

            nombre        = det.get("name", item.get("name", ""))
            direccion     = det.get("formatted_address", item.get("formatted_address", ""))
            telefono      = det.get("formatted_phone_number", "")
            web_actual    = det.get("website", "")
            rating        = det.get("rating", item.get("rating"))
            total_resenas = det.get("user_ratings_total", item.get("user_ratings_total", 0))

            temperatura = calcular_temperatura(web_actual, total_resenas or 0)

            row = {
                "nombre":           nombre,
                "profesion":        profesion,
                "direccion":        direccion,
                "telefono":         telefono,
                "web_actual":       web_actual,
                "rating":           rating,
                "total_resenas":    total_resenas,
                "place_id":         pid,
                "zona":             zona,
                "fecha_scrape":     datetime.now().isoformat(timespec="seconds"),
                "temperatura":      temperatura,
                "estado_prospecto": "nuevo",
            }

            insert_prospecto(conn, row)
            nuevos += 1
            logger.info(
                "  + %s | %s | resenas=%s | web=%s | temp=%s",
                nombre, zona, total_resenas, web_actual or "—", temperatura,
            )

        page_token = data.get("next_page_token")
        if not page_token:
            break

    return nuevos


def run_scraper():
    """Punto de entrada principal del módulo."""
    init_db()
    conn = get_connection()
    total_nuevos = 0

    for profesion in PROFESIONES:
        for zona in ZONAS:
            try:
                n = scrape_profesion_zona(profesion, zona, conn)
                total_nuevos += n
            except EnvironmentError as exc:
                logger.critical(str(exc))
                conn.close()
                raise
            except Exception as exc:
                logger.error(
                    "Error inesperado en profesion='%s' zona='%s': %s",
                    profesion, zona, exc, exc_info=True,
                )

    conn.close()
    logger.info("Scraping finalizado. Nuevos prospectos: %d", total_nuevos)
    return total_nuevos


# ─────────────────────────────────────────
#  Ejecución directa
# ─────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    run_scraper()
