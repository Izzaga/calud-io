"""
dashboard/app.py
Dashboard de métricas de CALUD.IO — accesible desde la red local.
"""

import os
import sys
import sqlite3

from flask import Flask, render_template, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_DEBUG

app = Flask(__name__)


def query(sql, params=()):
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    total        = query("SELECT COUNT(*) AS n FROM prospectos")[0]["n"]
    por_temp     = query("SELECT temperatura, COUNT(*) AS n FROM prospectos GROUP BY temperatura ORDER BY n DESC")
    por_prof     = query("SELECT profesion, COUNT(*) AS n FROM prospectos GROUP BY profesion ORDER BY n DESC")
    por_zona     = query("SELECT zona, COUNT(*) AS n FROM prospectos GROUP BY zona ORDER BY n DESC")
    sin_web      = query("SELECT COUNT(*) AS n FROM prospectos WHERE web_actual IS NULL OR web_actual = ''")[0]["n"]
    con_web      = total - sin_web
    por_tec      = query("""
        SELECT web_tecnologia, COUNT(*) AS n FROM prospectos
        WHERE web_tecnologia IS NOT NULL
        GROUP BY web_tecnologia ORDER BY n DESC
    """)
    calientes    = query("""
        SELECT nombre, profesion, zona, telefono, web_actual, total_resenas, rating
        FROM prospectos WHERE temperatura = 'CALIENTE'
        ORDER BY total_resenas DESC LIMIT 100
    """)
    tibios       = query("""
        SELECT nombre, profesion, zona, telefono, web_actual, total_resenas, rating, web_tecnologia
        FROM prospectos WHERE temperatura = 'TIBIO'
        ORDER BY total_resenas DESC LIMIT 100
    """)
    ultima_fecha = query("SELECT MAX(fecha_scrape) AS f FROM prospectos")[0]["f"]

    return dict(
        total=total,
        por_temp=por_temp,
        por_prof=por_prof,
        por_zona=por_zona,
        sin_web=sin_web,
        con_web=con_web,
        por_tec=por_tec,
        calientes=calientes,
        tibios=tibios,
        ultima_fecha=ultima_fecha,
    )


@app.route("/")
def index():
    stats = get_stats()
    return render_template("dashboard.html", **stats)


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


if __name__ == "__main__":
    print(f"\n CALUD.IO Dashboard corriendo en http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    print(" Desde tu celular (misma WiFi): http://<IP-de-tu-PC>:5000\n")
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=DASHBOARD_DEBUG)
