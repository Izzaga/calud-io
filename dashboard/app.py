"""
dashboard/app.py
Dashboard de métricas de CALUD.IO — accesible desde la red local.
"""

import csv
import io
import os
import sys
import sqlite3

from flask import Flask, render_template, jsonify, request, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_DEBUG, OUTPUT_DIR

app = Flask(__name__)


# ─────────────────────────────────────────
#  DB helpers
# ─────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=()):
    if not os.path.exists(DB_PATH):
        return []
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def execute(sql, params=()):
    conn = get_conn()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def sitio_existe(place_id: str) -> bool:
    path = os.path.join(OUTPUT_DIR, place_id, "index.html")
    return os.path.exists(path)


# ─────────────────────────────────────────
#  Stats para KPIs y gráficos
# ─────────────────────────────────────────

def get_stats():
    total        = query("SELECT COUNT(*) AS n FROM prospectos")[0]["n"]
    por_temp     = query("SELECT temperatura, COUNT(*) AS n FROM prospectos GROUP BY temperatura ORDER BY n DESC")
    por_prof     = query("SELECT profesion, COUNT(*) AS n FROM prospectos GROUP BY profesion ORDER BY n DESC")
    por_zona     = query("SELECT zona, COUNT(*) AS n FROM prospectos GROUP BY zona ORDER BY n DESC")
    sin_web      = query("SELECT COUNT(*) AS n FROM prospectos WHERE web_actual IS NULL OR web_actual = ''")[0]["n"]
    por_tec      = query("""
        SELECT web_tecnologia, COUNT(*) AS n FROM prospectos
        WHERE web_tecnologia IS NOT NULL
        GROUP BY web_tecnologia ORDER BY n DESC
    """)
    contactados  = query("SELECT COUNT(*) AS n FROM prospectos WHERE estado_prospecto = 'contactado'")[0]["n"]
    ultima_fecha = query("SELECT MAX(fecha_scrape) AS f FROM prospectos")[0]["f"]

    return dict(
        total=total,
        por_temp=por_temp,
        por_prof=por_prof,
        por_zona=por_zona,
        sin_web=sin_web,
        por_tec=por_tec,
        contactados=contactados,
        ultima_fecha=ultima_fecha,
    )


# ─────────────────────────────────────────
#  Filtros disponibles
# ─────────────────────────────────────────

def get_filtros():
    temperaturas = [r["temperatura"] for r in query("SELECT DISTINCT temperatura FROM prospectos WHERE temperatura IS NOT NULL ORDER BY temperatura")]
    profesiones  = [r["profesion"]   for r in query("SELECT DISTINCT profesion   FROM prospectos WHERE profesion   IS NOT NULL ORDER BY profesion")]
    zonas        = [r["zona"]        for r in query("SELECT DISTINCT zona         FROM prospectos WHERE zona         IS NOT NULL ORDER BY zona")]
    return {"temperaturas": temperaturas, "profesiones": profesiones, "zonas": zonas}


# ─────────────────────────────────────────
#  Rutas
# ─────────────────────────────────────────

@app.route("/")
def index():
    stats   = get_stats()
    filtros = get_filtros()
    return render_template("dashboard.html", **stats, **filtros)


@app.route("/api/prospectos")
def api_prospectos():
    temp   = request.args.get("temperatura", "")
    prof   = request.args.get("profesion", "")
    zona   = request.args.get("zona", "")
    estado = request.args.get("estado", "")
    limit  = int(request.args.get("limit", 200))

    where, params = ["1=1"], []
    if temp:
        where.append("temperatura = ?"); params.append(temp)
    if prof:
        where.append("profesion = ?"); params.append(prof)
    if zona:
        where.append("zona = ?"); params.append(zona)
    if estado:
        where.append("estado_prospecto = ?"); params.append(estado)

    sql = f"""
        SELECT id, place_id, nombre, profesion, zona, telefono,
               web_actual, web_tecnologia, web_score,
               total_resenas, rating, temperatura, estado_prospecto,
               solo_directorios, fecha_scrape
        FROM prospectos
        WHERE {' AND '.join(where)}
        ORDER BY total_resenas DESC
        LIMIT ?
    """
    params.append(limit)
    rows = query(sql, params)

    # Agregar flag de sitio generado
    for r in rows:
        r["sitio_generado"] = sitio_existe(r["place_id"])

    return jsonify(rows)


@app.route("/api/marcar-contactado/<place_id>", methods=["POST"])
def api_marcar_contactado(place_id):
    execute(
        "UPDATE prospectos SET estado_prospecto = 'contactado' WHERE place_id = ?",
        (place_id,)
    )
    return jsonify({"ok": True})


@app.route("/api/desmarcar-contactado/<place_id>", methods=["POST"])
def api_desmarcar_contactado(place_id):
    execute(
        "UPDATE prospectos SET estado_prospecto = 'nuevo' WHERE place_id = ?",
        (place_id,)
    )
    return jsonify({"ok": True})


@app.route("/api/exportar-csv")
def api_exportar_csv():
    temp   = request.args.get("temperatura", "")
    prof   = request.args.get("profesion", "")
    zona   = request.args.get("zona", "")
    estado = request.args.get("estado", "")

    where, params = ["1=1"], []
    if temp:
        where.append("temperatura = ?"); params.append(temp)
    if prof:
        where.append("profesion = ?"); params.append(prof)
    if zona:
        where.append("zona = ?"); params.append(zona)
    if estado:
        where.append("estado_prospecto = ?"); params.append(estado)

    rows = query(f"""
        SELECT nombre, profesion, zona, telefono, web_actual,
               web_tecnologia, web_score, total_resenas, rating,
               temperatura, estado_prospecto, direccion, fecha_scrape
        FROM prospectos
        WHERE {' AND '.join(where)}
        ORDER BY total_resenas DESC
    """, params)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys() if rows else [])
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=prospectos.csv"}
    )


@app.route("/sitio/<place_id>")
def ver_sitio(place_id):
    from flask import send_from_directory
    sitio_dir = os.path.join(OUTPUT_DIR, place_id)
    return send_from_directory(sitio_dir, "index.html")


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


if __name__ == "__main__":
    print(f"\n CALUD.IO Dashboard corriendo en http://localhost:{DASHBOARD_PORT}")
    print(f" Desde tu celular: http://192.168.1.54:{DASHBOARD_PORT}\n")
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=DASHBOARD_DEBUG)
