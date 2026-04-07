"""
scripts/fix_data.py
Corrige errores de datos en prospectos CALIENTES:
1. Detecta y corrige profesion mal asignada (basandose en el nombre)
2. Limpia nombres tipo negocio/SEO para display
3. Marca como "skip" entradas demasiado genericas para generar un sitio personal
4. Regenera los sitios HTML corregidos
"""

import os
import sys
import re
import sqlite3
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
#  Detección de profesion por nombre
# ─────────────────────────────────────────

PROF_KEYWORDS = {
    "psicólogo clínico": [
        "psicolog", "psiqu", "terapeuta", "cognitivo", "tcc",
    ],
    "kinesiólogo": [
        "kinesiol", "kinesiolog", "osteopat", "fisioterapia", "fisioterapeuta",
        "rehabilitacion", "rehab",
    ],
    "nutricionista": [
        "nutricion", "nutricionista", "nutri ",
    ],
    "odontólogo independiente": [
        "odontolog", "dental", "dentista", "odonto", "protesis dental",
        "implante", "ortodoncia",
    ],
}

# Patrones que indican que el nombre NO es una persona sino un negocio/SEO genérico
NOMBRE_INVALIDO_PATTERNS = [
    r"\|",                                       # pipes (SEO stuffing)
    r"\b(clínica|clinica|instituto|centro|consultorio)\b(?!.{0,30}(dr|dra|lic|prof))", # clínica sin nombre de doctor
    r"^\s*(dental|odontolog|kinesiol|nutrici|psicolog)\s*$",  # solo la profesion
    r"&\s*(equipo|asociados)",                   # "& equipo" sin nombre
    r"(s\.?r\.?l|s\.?a\.|s\.?a\.?s)",            # sociedades
]

# Palabras que en el nombre indican que es genérico (sin nombre de persona)
PALABRAS_GENERICAS = [
    "integral", "grupo", "center", "corp", "asociacion",
    "profesional", "servicios",
]


def _detectar_profesion_por_nombre(nombre: str) -> str | None:
    """Retorna la profesion correcta si el nombre la revela, o None si no hay cambio."""
    nombre_lower = nombre.lower()
    # Evaluar todas las profesiones y elegir la que tenga más keywords coincidentes
    scores = {}
    for prof, keywords in PROF_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in nombre_lower)
        if score > 0:
            scores[prof] = score
    if not scores:
        return None
    # Retornar la profesion con mayor score
    return max(scores, key=lambda p: scores[p])


def _nombre_es_persona(nombre: str) -> bool:
    """True si parece nombre de una persona (Dr., Lic., apellido, etc.)"""
    nombre_lower = nombre.lower()

    # Si tiene un título profesional explícito, es una persona
    if re.search(r"\b(dr\.?|dra\.?|lic\.?|prof\.?|mg\.?)\b", nombre_lower):
        return True

    # Si coincide con patrón inválido, no es persona
    for pat in NOMBRE_INVALIDO_PATTERNS:
        if re.search(pat, nombre_lower, re.IGNORECASE):
            return False

    # Si el nombre es muy corto y genérico (solo 1-2 palabras sin apellido)
    palabras = nombre.strip().split()
    if len(palabras) <= 2:
        primero = palabras[0].lower().rstrip(".")
        if primero in [kw for kws in PROF_KEYWORDS.values() for kw in kws]:
            return False

    return True


def _limpiar_nombre(nombre: str) -> str:
    """
    Limpia nombres tipo 'Lic. Gabriela Fernández Ortiz -Psicóloga cognitivo...'
    dejando solo el nombre de la persona.
    """
    # Quitar todo lo que viene después de un guion largo/dash si hay nombre antes
    nombre = re.sub(r"\s*[-–]\s*(psicólog|kinesiol|nutricion|odontolog|dental|terapeuta).*", "", nombre, flags=re.IGNORECASE)
    # Quitar descriptores después del nombre propio
    nombre = re.sub(r"\s*(odontología|kinesiología|nutrición|psicología|consultor[io]+|integral|clinica|centro)\s*$", "", nombre, flags=re.IGNORECASE)
    # Normalizar espacios y caracteres raros
    nombre = re.sub(r"\s+", " ", nombre).strip().rstrip(".,")
    return nombre


# ─────────────────────────────────────────
#  Pipeline de corrección
# ─────────────────────────────────────────

def corregir_prospectos():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, place_id, nombre, profesion FROM prospectos WHERE temperatura = 'CALIENTE'"
    ).fetchall()

    corregidos_prof  = 0
    marcados_skip    = 0
    nombres_limpios  = 0

    for row in rows:
        id_     = row["id"]
        nombre  = row["nombre"] or ""
        profesion = row["profesion"] or ""
        cambios = {}

        # 1. Corregir profesion mal asignada
        prof_detectada = _detectar_profesion_por_nombre(nombre)
        if prof_detectada and prof_detectada != profesion:
            logger.info("PROFESION CORREGIDA: '%s' | %s -> %s", nombre[:50], profesion, prof_detectada)
            cambios["profesion"] = prof_detectada
            corregidos_prof += 1

        # 2. Limpiar nombre
        nombre_limpio = _limpiar_nombre(nombre)
        if nombre_limpio != nombre:
            logger.info("NOMBRE LIMPIADO: '%s' -> '%s'", nombre[:60], nombre_limpio[:60])
            cambios["nombre"] = nombre_limpio
            nombres_limpios += 1

        # 3. Marcar como skip si no es persona
        nombre_final = cambios.get("nombre", nombre)
        if not nombre_final.strip():
            cambios["estado_prospecto"] = "skip"
            marcados_skip += 1
            if cambios:
                sets = ", ".join(f"{k} = ?" for k in cambios)
                vals = list(cambios.values()) + [id_]
                conn.execute(f"UPDATE prospectos SET {sets} WHERE id = ?", vals)
            continue
        if not _nombre_es_persona(nombre_final):
            logger.info("MARCADO SKIP (no persona): '%s'", nombre_final[:60])
            cambios["estado_prospecto"] = "skip"
            marcados_skip += 1

        if cambios:
            sets = ", ".join(f"{k} = ?" for k in cambios)
            vals = list(cambios.values()) + [id_]
            conn.execute(f"UPDATE prospectos SET {sets} WHERE id = ?", vals)

    conn.commit()
    conn.close()

    logger.info("Correcciones: profesion=%d | nombres=%d | skip=%d", corregidos_prof, nombres_limpios, marcados_skip)
    return corregidos_prof, nombres_limpios, marcados_skip


def regenerar_calientes():
    """Regenera sitios para CALIENTES que no están en skip."""
    from generator.site_builder import run_generator
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Temporalmente marca skip como FRIO para que run_generator no los incluya
    # (run_generator solo procesa CALIENTE)
    conn.execute("UPDATE prospectos SET temperatura = 'FRIO_TEMP' WHERE estado_prospecto = 'skip' AND temperatura = 'CALIENTE'")
    conn.commit()
    conn.close()

    n = run_generator()

    # Restaurar
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE prospectos SET temperatura = 'CALIENTE' WHERE temperatura = 'FRIO_TEMP'")
    conn.commit()
    conn.close()
    return n


if __name__ == "__main__":
    logger.info("=== Fase 1: Corrección de datos ===")
    c1, c2, c3 = corregir_prospectos()

    logger.info("=== Fase 2: Regeneración de sitios ===")
    n = regenerar_calientes()

    logger.info("=== LISTO ===")
    logger.info("Profesiones corregidas: %d", c1)
    logger.info("Nombres limpiados: %d", c2)
    logger.info("Entradas saltadas (no persona): %d", c3)
    logger.info("Sitios regenerados: %d", n)
