# ============================================================
#  CALUD.IO — Configuración central
# ============================================================

# ---------------------
#  Zonas de búsqueda
# ---------------------
ZONAS = [
    "Palermo, Buenos Aires",
    "Belgrano, Buenos Aires",
    "Caballito, Buenos Aires",
    "Villa Urquiza, Buenos Aires",
    "San Isidro, Buenos Aires",
]

# ---------------------
#  Profesiones a buscar
# ---------------------
PROFESIONES = [
    "odontólogo independiente",
    "kinesiólogo",
    "nutricionista",
    "psicólogo clínico",
]

# Mapa profesión → template HTML
TEMPLATE_MAP = {
    "odontólogo independiente": "odontologo.html",
    "kinesiólogo":              "kinesiologo.html",
    "nutricionista":            "nutricionista.html",
    "psicólogo clínico":        "psicologo.html",
}

# ---------------------
#  Google Places API
# ---------------------
PLACES_API_BASE       = "https://maps.googleapis.com/maps/api/place"
TEXT_SEARCH_ENDPOINT  = f"{PLACES_API_BASE}/textsearch/json"
DETAILS_ENDPOINT      = f"{PLACES_API_BASE}/details/json"
DETAILS_FIELDS        = (
    "name,formatted_address,formatted_phone_number,"
    "website,rating,user_ratings_total,opening_hours,"
    "reviews,place_id,types"
)
MAX_PAGES             = 3          # hasta 60 resultados por búsqueda
API_SLEEP             = 0.2        # segundos entre requests de detalle

# ---------------------
#  Temperatura — umbrales
# ---------------------
# CALIENTE: sin web propia Y reseñas entre 2 y 50
TEMP_CALIENTE_RESENAS_MIN = 2
TEMP_CALIENTE_RESENAS_MAX = 50

# TIBIO:    web básica (Wix/WP/Blogspot) O reseñas > 50 pero sin web
TEMP_TIBIO_RESENAS_UMBRAL = 50

# FRÍO:     web profesional O reseñas > 150
TEMP_FRIO_RESENAS_UMBRAL  = 150

# Dominios considerados "web básica"
DOMINIOS_WEB_BASICA = [
    "wix.com", "wixsite.com",
    "wordpress.com",
    "blogspot.com",
    "weebly.com",
    "jimdo.com",
    "site123.com",
    "webnode.com",
]

# ---------------------
#  Rutas del proyecto
# ---------------------
import os
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DB_PATH         = os.path.join(BASE_DIR, "data", "prospectos.db")
OUTPUT_DIR      = os.path.join(BASE_DIR, "output", "sites")
TEMPLATES_DIR   = os.path.join(BASE_DIR, "generator", "templates")
LOGS_DIR        = os.path.join(BASE_DIR, "logs")

# ---------------------
#  Dashboard
# ---------------------
DASHBOARD_HOST  = "127.0.0.1"
DASHBOARD_PORT  = 5000
DASHBOARD_DEBUG = True
