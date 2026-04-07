"""
main.py — Pipeline completo de CALUD.IO

Uso:
  python main.py                  → pipeline completo (scrape → analyze → generate)
  python main.py --solo-scrape    → solo scraping de Google Places
  python main.py --solo-analizar  → solo análisis de webs
  python main.py --solo-generar   → solo generación de sitios
  python main.py --dashboard      → arranca el dashboard Flask
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def cmd_scrape():
    from scraper.google_maps import run_scraper
    logger.info("═══ PASO 1: Scraping Google Places ═══")
    n = run_scraper()
    logger.info("Scraping OK — nuevos prospectos: %d", n)
    return n


def cmd_analizar():
    from scraper.web_analyzer import run_analyzer
    logger.info("═══ PASO 2: Análisis de webs ═══")
    n = run_analyzer()
    logger.info("Análisis OK — webs procesadas: %d", n)
    return n


def cmd_generar():
    from generator.site_builder import run_generator
    logger.info("═══ PASO 3: Generación de sitios ═══")
    n = run_generator()
    logger.info("Generación OK — sitios creados: %d", n)
    return n


def cmd_dashboard():
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import DASHBOARD_HOST, DASHBOARD_PORT
    from dashboard.app import app
    logger.info("═══ Dashboard iniciando en http://%s:%d ═══", DASHBOARD_HOST, DASHBOARD_PORT)
    logger.info("Red local: http://192.168.1.54:%d", DASHBOARD_PORT)
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)


def main():
    parser = argparse.ArgumentParser(
        description="CALUD.IO — Pipeline de prospección de profesionales de la salud"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--solo-scrape",    action="store_true", help="Solo scraping Google Places")
    group.add_argument("--solo-analizar",  action="store_true", help="Solo análisis de webs")
    group.add_argument("--solo-generar",   action="store_true", help="Solo generación de sitios")
    group.add_argument("--dashboard",      action="store_true", help="Arranca el dashboard Flask")

    args = parser.parse_args()

    if args.solo_scrape:
        cmd_scrape()
    elif args.solo_analizar:
        cmd_analizar()
    elif args.solo_generar:
        cmd_generar()
    elif args.dashboard:
        cmd_dashboard()
    else:
        # Pipeline completo
        logger.info("╔══════════════════════════════════════╗")
        logger.info("║      CALUD.IO — Pipeline Completo    ║")
        logger.info("╚══════════════════════════════════════╝")
        n1 = cmd_scrape()
        n2 = cmd_analizar()
        n3 = cmd_generar()
        logger.info("")
        logger.info("╔══════════════════════════════════════╗")
        logger.info("║            RESUMEN FINAL             ║")
        logger.info("║  Prospectos nuevos : %-16d║", n1)
        logger.info("║  Webs analizadas   : %-16d║", n2)
        logger.info("║  Sitios generados  : %-16d║", n3)
        logger.info("╚══════════════════════════════════════╝")


if __name__ == "__main__":
    main()
