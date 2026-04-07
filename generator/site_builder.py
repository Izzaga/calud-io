"""
generator/site_builder.py
Genera sitios web estáticos personalizados para cada prospecto CALIENTE.
Guarda cada sitio en output/sites/{place_id}/index.html
"""

import json
import os
import sys
import re
import sqlite3
import logging
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, OUTPUT_DIR, TEMPLATES_DIR, TEMPLATE_MAP

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
#  Servicios inferidos por profesión
# ─────────────────────────────────────────
SERVICIOS = {
    "odontólogo independiente": [
        ("🦷", "Odontología general",     "Diagnóstico, tratamiento y prevención de enfermedades bucales."),
        ("✨", "Blanqueamiento dental",    "Tratamientos para una sonrisa más brillante y saludable."),
        ("🔧", "Ortodoncia",               "Corrección de la posición de los dientes con brackets o alineadores."),
        ("🛡️", "Implantes dentales",       "Solución permanente y estética para dientes faltantes."),
        ("👶", "Odontopediatría",          "Atención especializada y amigable para niños."),
        ("🔬", "Endodoncia",               "Tratamiento del nervio dental (conducto) sin dolor."),
    ],
    "kinesiólogo": [
        ("💪", "Rehabilitación traumatológica", "Recuperación de lesiones musculares, articulares y post-quirúrgicas."),
        ("🏃", "Kinesiología deportiva",         "Prevención y recuperación de lesiones en deportistas."),
        ("🧘", "Kinesiología respiratoria",       "Técnicas para mejorar la función pulmonar."),
        ("⚡", "Electroterapia",                  "Ultrasonido, TENS y corrientes terapéuticas."),
        ("🤲", "Masoterapia",                     "Masajes terapéuticos para aliviar el dolor y la tensión."),
        ("🦵", "Neurorehabilitación",             "Rehabilitación de pacientes con alteraciones neurológicas."),
    ],
    "nutricionista": [
        ("🥗", "Nutrición clínica",         "Plan nutricional personalizado según tu estado de salud."),
        ("⚖️", "Control de peso",            "Programas para alcanzar tu peso ideal de forma saludable."),
        ("🏋️", "Nutrición deportiva",        "Alimentación optimizada para mejorar tu rendimiento físico."),
        ("🤰", "Nutrición en embarazo",      "Guía nutricional para el embarazo y la lactancia."),
        ("👶", "Nutrición pediátrica",       "Alimentación saludable para niños y adolescentes."),
        ("🫀", "Patologías específicas",     "Manejo de diabetes, hipertensión, celiaquía y más."),
    ],
    "psicólogo clínico": [
        ("🧠", "Psicoterapia individual",   "Sesiones personalizadas para adultos, adolescentes y niños."),
        ("💑", "Terapia de pareja",         "Herramientas para mejorar la comunicación y el vínculo."),
        ("😰", "Ansiedad y estrés",         "Técnicas para gestionar la ansiedad y los ataques de pánico."),
        ("😔", "Depresión",                 "Acompañamiento y tratamiento para superar la depresión."),
        ("🌙", "Trastornos del sueño",      "Evaluación y tratamiento del insomnio y otros trastornos."),
        ("🔄", "Terapia Cognitivo-Conductual", "TCC basada en evidencia científica."),
    ],
}

PALETA = {
    "odontólogo independiente": {
        "primary": "#1a56a0", "primary_dark": "#133f7a", "primary_light": "#dbeafe", "accent": "#60a5fa", "emoji_prof": "D",
    },
    "kinesiólogo": {
        "primary": "#0d7a5f", "primary_dark": "#095c47", "primary_light": "#d1fae5", "accent": "#34d399", "emoji_prof": "K",
    },
    "nutricionista": {
        "primary": "#b45309", "primary_dark": "#92400e", "primary_light": "#fef3c7", "accent": "#fbbf24", "emoji_prof": "N",
    },
    "psicólogo clínico": {
        "primary": "#5b21b6", "primary_dark": "#4c1d95", "primary_light": "#ede9fe", "accent": "#a78bfa", "emoji_prof": "P",
    },
}

def _get_paleta(profesion: str) -> dict:
    for key, pal in PALETA.items():
        if key in (profesion or "").lower():
            return pal
    return {"primary": "#1e5f74", "primary_dark": "#164559", "primary_light": "#cffafe", "accent": "#38bdf8", "emoji_prof": "S"}

SOBRE_MI = {
    "odontólogo independiente": (
        "Profesional de la odontología con atención personalizada en {zona}. "
        "Me dedico a cuidar la salud bucal de mis pacientes con tratamientos modernos "
        "y tecnología de punta, en un ambiente cómodo y de plena confianza. "
        "Atiendo adultos, adolescentes y niños con el mismo nivel de compromiso y dedicación."
    ),
    "kinesiólogo": (
        "Kinesiólogo con consultorio en {zona}. "
        "Especializado en rehabilitación física, tratamiento del dolor y recuperación de lesiones. "
        "Trabajo con planes de tratamiento personalizados para que cada paciente recupere "
        "su movilidad y calidad de vida de la manera más eficiente y segura posible."
    ),
    "nutricionista": (
        "Nutricionista con consultorio en {zona}. "
        "Creo planes alimentarios 100% personalizados, adaptados a tus gustos, "
        "estilo de vida y objetivos. Mi enfoque es la alimentación saludable y sostenible "
        "en el tiempo, sin dietas restrictivas ni sacrificios innecesarios."
    ),
    "psicólogo clínico": (
        "Psicólogo/a clínico/a con atención en {zona}. "
        "Ofrezco un espacio terapéutico seguro, confidencial y sin juicios. "
        "Trabajo desde un enfoque actualizado y basado en evidencia para acompañarte "
        "en tu proceso de cambio, crecimiento y bienestar emocional."
    ),
}

# ─────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────

def _wa_link(telefono: str) -> str:
    """Convierte número a link wa.me."""
    if not telefono:
        return ""
    digits = re.sub(r"\D", "", telefono)
    # Argentina: si empieza con 0, sacar el 0 y agregar 54
    if digits.startswith("0"):
        digits = "54" + digits[1:]
    elif not digits.startswith("54"):
        digits = "54" + digits
    msg = "Hola%2C+quiero+consultar+un+turno"
    return f"https://wa.me/{digits}?text={msg}"


def _stars(rating) -> str:
    if not rating:
        return ""
    full  = int(rating)
    half  = 1 if (rating - full) >= 0.5 else 0
    empty = 5 - full - half
    return "★" * full + ("½" if half else "") + "☆" * empty


def _get_servicios(profesion: str) -> list:
    for key, svcs in SERVICIOS.items():
        if key in (profesion or "").lower():
            return svcs
    # fallback genérico
    return [
        ("🏥", "Consulta general",      "Atención integral y personalizada."),
        ("📋", "Diagnóstico",           "Evaluación completa de tu estado de salud."),
        ("💊", "Tratamiento",           "Plan terapéutico adaptado a tus necesidades."),
        ("🔄", "Seguimiento",           "Controles periódicos para asegurar tu evolución."),
    ]


def _get_sobre_mi(profesion: str, zona: str) -> str:
    for key, texto in SOBRE_MI.items():
        if key in (profesion or "").lower():
            return texto.format(zona=zona or "Buenos Aires")
    return f"Profesional de la salud con atención en {zona or 'Buenos Aires'}."


def _get_template_name(profesion: str) -> str:
    prof = (profesion or "").lower()
    for key, tmpl in TEMPLATE_MAP.items():
        if key in prof:
            return tmpl
    return "odontologo.html"


# ─────────────────────────────────────────
#  DB helpers
# ─────────────────────────────────────────

def get_calientes(conn) -> list:
    rows = conn.execute(
        """
        SELECT * FROM prospectos
        WHERE temperatura = 'CALIENTE' AND estado_prospecto != 'skip'
        ORDER BY total_resenas DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def marcar_generado(conn, place_id: str):
    conn.execute(
        "UPDATE prospectos SET estado_prospecto = 'sitio_generado' WHERE place_id = ?",
        (place_id,),
    )
    conn.commit()


# ─────────────────────────────────────────
#  Generador principal
# ─────────────────────────────────────────

def generar_sitio(prospecto: dict, env: Environment) -> str:
    """Genera el HTML para un prospecto y lo guarda. Retorna la ruta."""
    place_id  = prospecto["place_id"]
    nombre    = prospecto.get("nombre", "Profesional")
    profesion = prospecto.get("profesion", "")
    zona      = prospecto.get("zona", "Buenos Aires")
    direccion = prospecto.get("direccion", "")
    telefono  = prospecto.get("telefono", "")
    rating    = prospecto.get("rating")
    resenas_n = prospecto.get("total_resenas", 0)

    template_name = _get_template_name(profesion)

    try:
        template = env.get_template(template_name)
    except Exception:
        logger.warning("Template %s no encontrado, usando odontologo.html", template_name)
        template = env.get_template("odontologo.html")

    paleta = _get_paleta(profesion)

    # Reseñas y horarios enriquecidos
    resenas_raw = prospecto.get("resenas_json")
    resenas     = json.loads(resenas_raw) if resenas_raw else []
    horarios_raw = prospecto.get("horarios")
    horarios_lista = json.loads(horarios_raw) if horarios_raw else []

    context = {
        "nombre":         nombre,
        "profesion":      profesion.title() if profesion else "Profesional de la Salud",
        "zona":           zona,
        "direccion":      direccion,
        "telefono":       telefono,
        "wa_link":        _wa_link(telefono),
        "rating":         rating,
        "rating_stars":   _stars(rating),
        "total_resenas":  resenas_n,
        "servicios":      _get_servicios(profesion),
        "sobre_mi":       _get_sobre_mi(profesion, zona),
        "resenas":        resenas,
        "horarios_lista": horarios_lista,
        "generado":       datetime.now().strftime("%d/%m/%Y"),
        "place_id":       place_id,
        **paleta,
    }

    html = template.render(**context)

    # Guardar archivo
    out_dir = os.path.join(OUTPUT_DIR, place_id)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return out_path


def run_generator():
    """Punto de entrada principal."""
    if not os.path.exists(DB_PATH):
        logger.error("DB no encontrada en %s. Corré primero el scraper.", DB_PATH)
        return 0

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=False,
    )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    prospectos = get_calientes(conn)
    logger.info("Prospectos CALIENTES a generar: %d", len(prospectos))

    generados = 0
    for p in prospectos:
        try:
            ruta = generar_sitio(p, env)
            marcar_generado(conn, p["place_id"])
            generados += 1
            logger.info("  OK %s -> %s", p["nombre"], ruta)
        except Exception as exc:
            logger.error("  ERR generando sitio para %s: %s", p.get("nombre"), exc, exc_info=True)

    conn.close()
    logger.info("Generación finalizada. Sitios creados: %d", generados)
    return generados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_generator()
