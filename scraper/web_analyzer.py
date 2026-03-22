"""
scraper/web_analyzer.py
Analiza las webs de los prospectos guardados en la DB y completa
los campos: web_score, web_tecnologia, solo_directorios.
"""

import os
import sys
import time
import sqlite3
import logging

import requests
from requests.exceptions import RequestException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
#  Directorios médicos / listings conocidos
# ─────────────────────────────────────────

DIRECTORIOS = [
    "doctoralia.com",
    "tumedico.com",
    "saludnow.com",
    "tuotromedico.com",
    "topdoctors.com",
    "healthgrades.com",
    "zocdoc.com",
    "guia-medica.com",
    "paginasamarillas.com.ar",
    "cylex.com.ar",
    "infobae.com",
    "clarin.com",
    "mercadolibre.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "linktr.ee",
    "linktree",
]

# Plataformas "web básica" y su nombre
PLATAFORMAS = [
    ("wix.com",        "Wix"),
    ("wixsite.com",    "Wix"),
    ("wordpress.com",  "WordPress.com"),
    ("blogspot.com",   "Blogger"),
    ("weebly.com",     "Weebly"),
    ("jimdo.com",      "Jimdo"),
    ("site123.com",    "Site123"),
    ("webnode.com",    "Webnode"),
    ("tiendanube.com", "Tienda Nube"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

TIMEOUT = 8  # segundos


# ─────────────────────────────────────────
#  Detección de tecnología
# ─────────────────────────────────────────

def _es_directorio(url: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    return any(d in url_lower for d in DIRECTORIOS)


def _plataforma_por_url(url: str):
    """Detecta plataforma básica solo por URL. Retorna nombre o None."""
    url_lower = url.lower()
    for dominio, nombre in PLATAFORMAS:
        if dominio in url_lower:
            return nombre
    return None


def _detectar_en_html(html: str):
    """
    Detecta tecnología a partir del HTML.
    Retorna (tecnologia: str, es_wp_selfhosted: bool).
    """
    h = html.lower()

    # WordPress auto-hospedado
    if "wp-content" in h or "wp-includes" in h:
        return "WordPress (auto-hospedado)", True

    # Wix
    if "wix.com" in h or "_wix_browser_" in h or "X-Wix-Published-Version".lower() in h:
        return "Wix", False

    # Squarespace
    if "squarespace.com" in h or "squarespace-cdn" in h:
        return "Squarespace", False

    # Webflow
    if "webflow.io" in h or 'data-wf-site' in h:
        return "Webflow", True

    # Shopify
    if "shopify" in h and "cdn.shopify" in h:
        return "Shopify", False

    # Blogger
    if "blogger.com" in h or "blogspot.com" in h:
        return "Blogger", False

    return None, False


def analizar_web(url: str) -> dict:
    """
    Analiza una URL y devuelve un dict con:
      web_score (int 0-100),
      web_tecnologia (str),
      solo_directorios (int 0/1).
    """
    if not url:
        return {"web_score": 0, "web_tecnologia": None, "solo_directorios": 0}

    # 1. ¿Es directorio?
    if _es_directorio(url):
        return {"web_score": 5, "web_tecnologia": "Directorio", "solo_directorios": 1}

    # 2. ¿Plataforma básica por URL?
    plataforma_url = _plataforma_por_url(url)

    # 3. Intentar fetch del HTML
    html = ""
    tiene_ssl = url.lower().startswith("https://")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        html = resp.text
    except RequestException as exc:
        logger.warning("No se pudo fetchear %s: %s", url, exc)

    # 4. Detectar tecnología en HTML
    tec_html, es_wp_selfhosted = _detectar_en_html(html) if html else (None, False)

    # Decidir tecnología final
    if tec_html:
        tecnologia = tec_html
    elif plataforma_url:
        tecnologia = plataforma_url
    else:
        tecnologia = "Personalizada"

    # 5. Calcular score
    score = _calcular_score(url, html, tecnologia, tiene_ssl, es_wp_selfhosted)

    return {
        "web_score":      score,
        "web_tecnologia": tecnologia,
        "solo_directorios": 0,
    }


def _calcular_score(url: str, html: str, tecnologia: str, tiene_ssl: bool, es_wp_self: bool) -> int:
    """Score 0-100: qué tan "trabajada" / profesional está la web."""
    score = 0

    # SSL
    if tiene_ssl:
        score += 15

    # Dominio propio (no subdominio de plataforma)
    plataforma_url = _plataforma_por_url(url)
    if not plataforma_url:
        score += 20

    # Tecnología
    if tecnologia == "Personalizada":
        score += 25
    elif tecnologia in ("WordPress (auto-hospedado)", "Webflow"):
        score += 15
    elif tecnologia in ("Squarespace",):
        score += 10
    elif tecnologia in ("Wix", "WordPress.com", "Blogger", "Weebly", "Jimdo", "Site123", "Webnode", "Tienda Nube"):
        score += 5

    if html:
        h = html.lower()
        # Viewport (mobile friendly)
        if 'name="viewport"' in h:
            score += 10
        # Tiene formulario de contacto
        if "<form" in h and ("contact" in h or "contacto" in h or "turno" in h):
            score += 10
        # Meta description
        if 'name="description"' in h:
            score += 10
        # Tiene más de 1000 chars de contenido real (no vacía)
        if len(html) > 1000:
            score += 10

    return min(score, 100)


# ─────────────────────────────────────────
#  Pipeline DB
# ─────────────────────────────────────────

def get_pendientes(conn) -> list:
    """Prospectos con web pero sin análisis previo."""
    rows = conn.execute(
        """
        SELECT id, web_actual FROM prospectos
        WHERE web_actual IS NOT NULL
          AND web_actual != ''
          AND web_score IS NULL
        """
    ).fetchall()
    return rows


def actualizar_prospecto(conn, id_: int, datos: dict):
    conn.execute(
        """
        UPDATE prospectos
        SET web_score = ?, web_tecnologia = ?, solo_directorios = ?
        WHERE id = ?
        """,
        (datos["web_score"], datos["web_tecnologia"], datos["solo_directorios"], id_),
    )
    conn.commit()


def run_analyzer(sleep_entre: float = 0.5):
    """Punto de entrada principal."""
    if not os.path.exists(DB_PATH):
        logger.error("DB no encontrada en %s. Corré primero el scraper.", DB_PATH)
        return 0

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    pendientes = get_pendientes(conn)
    logger.info("Prospectos con web sin analizar: %d", len(pendientes))

    analizados = 0
    for row in pendientes:
        pid, url = row["id"], row["web_actual"]
        logger.info("Analizando [%d] %s", pid, url)
        try:
            resultado = analizar_web(url)
            actualizar_prospecto(conn, pid, resultado)
            logger.info(
                "  -> score=%d | tec=%s | directorio=%d",
                resultado["web_score"],
                resultado["web_tecnologia"],
                resultado["solo_directorios"],
            )
            analizados += 1
        except Exception as exc:
            logger.error("  Error analizando %s: %s", url, exc)
        time.sleep(sleep_entre)

    conn.close()
    logger.info("Analisis finalizado. Procesados: %d", analizados)
    return analizados


# ─────────────────────────────────────────
#  Ejecución directa
# ─────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    run_analyzer()
