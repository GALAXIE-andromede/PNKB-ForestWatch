"""
Scan satellitaire hebdomadaire du Parc National de Kahuzi-Biega.
100% gratuit : Copernicus Dataspace (Sentinel-2) + alertes Telegram.
Exécuté automatiquement par GitHub Actions (voir .github/workflows/satellite.yml).

Étapes :
1. Authentification auprès de Copernicus Dataspace (identifiants gratuits)
2. Téléchargement de 2 images NDVI Sentinel-2 (référence / période récente)
3. Détection des pixels de perte forestière
4. Écriture de data/alerts.js (affiché par la carte Leaflet du dashboard)
5. Alerte Telegram si la perte dépasse le seuil

Limites connues (MVP) :
- Résolution grossière (le parc entier sur une image 512x512) ; à affiner
  par tuilage pour détecter de petites clairières.
- Les nuages peuvent masquer certaines zones.
"""
import io
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import requests
from PIL import Image

TOKEN_URL = "https://identity.dataspace.copernicus.com/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.com/api/v1/process"

# Zone approximative du PNKB (à remplacer par les limites officielles,
# voir data/pnkb_boundary.geojson)
BBOX = [28.35, -2.35, 28.95, -1.85]  # [lon_min, lat_min, lon_max, lat_max] WGS84
IMG_SIZE = 512
GRID = 16                      # découpage de l'image en blocs pour regrouper les pertes
NDVI_LOSS_THRESHOLD = 0.30     # baisse de NDVI considérée comme une perte
NDVI_FOREST_MIN = 0.55         # NDVI minimal pour considérer la zone forestière
ALERT_AREA_THRESHOLD_HA = 5    # seuil d'alerte Telegram (hectares)

# Renvoie [NDVI quantifié sur 255 niveaux, masque de validité]
EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "dataMask"],
    output: { bands: 2, sampleType: "UINT8" }
  };
}
function evaluatePixel(s) {
  var ndvi = (s.B08 - s.B04) / (s.B08 + s.B04 + 1e-6);
  var v = Math.max(0, Math.min(255, Math.round((ndvi + 1) * 127.5)));
  return [v, s.dataMask * 255];
}
"""


def get_token():
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["COPERNICUS_CLIENT_ID"],
            "client_secret": os.environ["COPERNICUS_CLIENT_SECRET"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_ndvi_png(token, date_from, date_to):
    body = {
        "input": {
            "bounds": {
                "bbox": BBOX,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": f"{date_from}T00:00:00Z",
                            "to": f"{date_to}T23:59:59Z",
                        }
                    },
                }
            ],
        },
        "output": {
            "width": IMG_SIZE,
            "height": IMG_SIZE,
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": EVALSCRIPT,
    }
    resp = requests.post(
        PROCESS_URL,
        json=body,
        headers={"Authorization": f"Bearer {token}", "Accept": "image/png"},
        timeout=300,
    )
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content))
    arr = np.array(img)
    ndvi = arr[:, :, 0].astype("float32") / 127.5 - 1.0
    valid = arr[:, :, 1] == 255
    return ndvi, valid


def cluster_losses(ndvi_before, valid_before, ndvi_after, valid_after):
    """Regroupe les pixels de perte par blocs et retourne des zones estimées."""
    loss = (
        valid_before
        & valid_after
        & (ndvi_before > NDVI_FOREST_MIN)
        & (ndvi_after < ndvi_before - NDVI_LOSS_THRESHOLD)
    )
    lon_min, lat_min, lon_max, lat_max = BBOX
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians((lat_min + lat_max) / 2))
    area_m2 = (
        (lat_max - lat_min) * m_per_deg_lat
        * (lon_max - lon_min) * m_per_deg_lon
        / (IMG_SIZE * IMG_SIZE)
    )
    ha_per_px = area_m2 / 10000.0

    step = IMG_SIZE // GRID
    zones = []
    for gy in range(0, IMG_SIZE, step):
        for gx in range(0, IMG_SIZE, step):
            block = loss[gy:gy + step, gx:gx + step]
            n = int(np.sum(block))
            if n == 0:
                continue
            area_ha = round(n * ha_per_px, 1)
            if area_ha < 0.5:
                continue
            ys, xs = np.where(block)
            row = gy + ys.mean()
            col = gx + xs.mean()
            lat = lat_max - (row / IMG_SIZE) * (lat_max - lat_min)
            lon = lon_min + (col / IMG_SIZE) * (lon_max - lon_min)
            zones.append({
                "type": "deforestation",
                "lat": round(float(lat), 4),
                "lon": round(float(lon), 4),
                "area_ha": area_ha,
                "severity": "HIGH" if area_ha >= ALERT_AREA_THRESHOLD_HA else "MEDIUM",
            })
    total_ha = round(float(np.sum(loss)) * ha_per_px, 1)
    return zones, total_ha


def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("⚠️ Telegram non configuré (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) : alerte ignorée.")
        return
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=30,
    )
    resp.raise_for_status()
    print("✅ Alerte Telegram envoyée.")


def write_alerts_js(zones, total_ha, scan_date, status, detail=""):
    payload = {
        "status": status,
        "date": scan_date,
        "total_loss_ha": total_ha,
        "zone_count": len(zones),
        "detail": detail,
    }
    content = (
        "// ⚠️ Fichier généré automatiquement par scripts/satellite_scan.py — ne pas modifier à la main.\n"
        f"// Dernier scan : {scan_date or 'jamais'} ({status})\n"
        f"const lastScan = {json.dumps(payload, ensure_ascii=False, indent=2)};\n\n"
        f"const pnkbAlerts = {json.dumps(zones, ensure_ascii=False, indent=2)};\n"
    )
    with open("data/alerts.js", "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ data/alerts.js mis à jour ({len(zones)} zone(s), ~{total_ha} ha au total).")


def main():
    missing = [k for k in ("COPERNICUS_CLIENT_ID", "COPERNICUS_CLIENT_SECRET") if not os.environ.get(k)]
    if missing:
        write_alerts_js(
            [], 0.0, "", "not_configured",
            "Identifiants Copernicus manquants. Ajoutez les secrets GitHub : " + ", ".join(missing),
        )
        return

    today = datetime.now(timezone.utc).date()
    before_from, before_to = today - timedelta(days=65), today - timedelta(days=45)
    after_from, after_to = today - timedelta(days=15), today

    print(f"Période référence : {before_from} → {before_to}")
    print(f"Période récente  : {after_from} → {after_to}")

    token = get_token()
    ndvi_b, valid_b = fetch_ndvi_png(token, str(before_from), str(before_to))
    ndvi_a, valid_a = fetch_ndvi_png(token, str(after_from), str(after_to))
    zones, total_ha = cluster_losses(ndvi_b, valid_b, ndvi_a, valid_a)

    scan_date = today.isoformat()
    write_alerts_js(zones, total_ha, scan_date, "ok")

    if zones and total_ha >= ALERT_AREA_THRESHOLD_HA:
        top = sorted(zones, key=lambda z: -z["area_ha"])[:5]
        lines = "\n".join(
            f"• {z['severity']} : ~{z['area_ha']} ha à {z['lat']}, {z['lon']}" for z in top
        )
        send_telegram(
            "🚨 PNKB Forest Watch\n"
            f"Perte forestière estimée : ~{total_ha} ha (scan du {scan_date})\n\n"
            f"{lines}\n\nCarte : voir le dashboard GitHub Pages."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Échec du scan : {exc}")
        sys.exit(1)