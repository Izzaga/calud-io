"""
scripts/enrich_data.py
Re-fetch place_details para prospectos CALIENTES y guarda horarios + reseñas reales.
"""

import os, sys, time, json, sqlite3, logging
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, DETAILS_ENDPOINT, API_SLEEP

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

FIELDS = "opening_hours,reviews"


def fetch_details(place_id: str) -> dict:
    api_key = os.getenv("GOOGLE_API_KEY", "")
    resp = requests.get(DETAILS_ENDPOINT, params={
        "place_id": place_id, "fields": FIELDS, "language": "es", "key": api_key
    }, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", {})


def parse_horarios(result: dict) -> str | None:
    oh = result.get("opening_hours", {})
    weekday = oh.get("weekday_text", [])
    if weekday:
        return json.dumps(weekday, ensure_ascii=False)
    return None


def parse_resenas(result: dict) -> str | None:
    reviews = result.get("reviews", [])
    if not reviews:
        return None
    cleaned = []
    for r in reviews[:3]:
        rating = r.get("rating", 0)
        text   = (r.get("text") or "").strip()
        author = r.get("author_name", "Paciente")
        if text and rating >= 4:
            cleaned.append({"autor": author, "rating": rating, "texto": text[:300]})
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else None


def run_enricher():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT place_id FROM prospectos
           WHERE temperatura = 'CALIENTE' AND estado_prospecto != 'skip'
             AND (horarios IS NULL AND resenas_json IS NULL)"""
    ).fetchall()

    logger.info("Prospectos a enriquecer: %d", len(rows))
    enriquecidos = 0

    for row in rows:
        pid = row["place_id"]
        try:
            result = fetch_details(pid)
            horarios   = parse_horarios(result)
            resenas    = parse_resenas(result)
            conn.execute(
                "UPDATE prospectos SET horarios = ?, resenas_json = ? WHERE place_id = ?",
                (horarios, resenas, pid)
            )
            conn.commit()
            enriquecidos += 1
            logger.info("OK %s | horarios=%s | resenas=%d",
                pid[:15], "si" if horarios else "no",
                len(json.loads(resenas)) if resenas else 0)
        except Exception as exc:
            logger.warning("ERR %s: %s", pid[:15], exc)
        time.sleep(API_SLEEP)

    conn.close()
    logger.info("Enriquecimiento finalizado: %d", enriquecidos)
    return enriquecidos


if __name__ == "__main__":
    run_enricher()
