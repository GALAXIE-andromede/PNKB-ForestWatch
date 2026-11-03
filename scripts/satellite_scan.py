"""
Scan satellitaire hebdomadaire du Parc National de Kahuzi-Biega.
Surveillance Sentinel-2 (Planet / Copernicus Sentinel Hub) + alertes.
Exécuté automatiquement par GitHub Actions.
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

# Passerelles OAuth et Processing API
PLANET_TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"
PLANET_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"

CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
SUBSCRIBERS_FILE = "data/subscribers.json"
DASHBOARD_URL = "https://pnkb-forestwatch.vercel.app/"
WHATSAPP_CHANNEL_URL = "https://whatsapp.com/channel/0029Vb94EbL60eBnHy5UNI18"

# Zone du Parc National de Kahuzi-Biega (WGS84)
BBOX = [28.35, -2.35, 28.95, -1.85]  # [lon_min, lat_min, lon_max, lat_max]
IMG_SIZE = 512
GRID = 16                      # Découpage en blocs
NDVI_LOSS_THRESHOLD = 0.30     # Baisse de NDVI considérée comme une perte
NDVI_FOREST_MIN = 0.55         # Seuil minimal de forêt

MIN_MAP_DETECTION_HA = 0.2     # Seuil d'affichage sur la carte
ALERT_AREA_THRESHOLD_HA = 0.5  # Seuil d'alerte critique Telegram/WhatsApp

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


def get_token_and_endpoint():
    """Tente la connexion avec Planet/Sentinel Hub d'abord, puis CDSE (.eu)."""
    client_id = os.environ.get("COPERNICUS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("COPERNICUS_CLIENT_SECRET", "").strip()

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    # 1. Essai avec Planet / Sentinel Hub (votre compte 90 jours)
    print("🛰️ Tentative de connexion via Planet / Sentinel Hub...")
    try:
        resp = requests.post(PLANET_TOKEN_URL, data=payload, timeout=25)
        if resp.status_code == 200:
            print("✅ Authentification réussie auprès de Planet / Sentinel Hub !")
            return resp.json()["access_token"], PLANET_PROCESS_URL
    except Exception as e:
        print(f"Notice Planet : {e}")

    # 2. Essai de secours avec Copernicus Data Space Ecosystem (.eu)
    print("🛰️ Bascule vers Copernicus Data Space Europe (CDSE)...")
    try:
        resp = requests.post(CDSE_TOKEN_URL, data=payload, timeout=25)
        if resp.status_code == 200:
            print("✅ Authentification réussie auprès de Copernicus Data Space !")
            return resp.json()["access_token"], CDSE_PROCESS_URL
    except Exception as e:
        print(f"Notice CDSE : {e}")

    raise ValueError(
        "❌ Impossible de valider vos identifiants. Vérifiez que votre Client ID et "
        "Client Secret sont bien collés dans les secrets GitHub (sans espaces en trop)."
    )


def fetch_ndvi_png(token, process_url, date_from, date_to):
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
        process_url,
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
    """Regroupe les pixels de perte et classe par sévérité."""
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
            
            if area_ha < MIN_MAP_DETECTION_HA:
                continue

            ys, xs = np.where(block)
            row = gy + ys.mean()
            col = gx + xs.mean()
            lat = lat_max - (row / IMG_SIZE) * (lat_max - lat_min)
            lon = lon_min + (col / IMG_SIZE) * (lon_max - lon_min)
            
            severity = "HIGH" if area_ha >= ALERT_AREA_THRESHOLD_HA else "MEDIUM"

            zones.append({
                "type": "deforestation",
                "lat": round(float(lat), 4),
                "lon": round(float(lon), 4),
                "area_ha": area_ha,
                "severity": severity,
                "date": datetime.now(timezone.utc).date().isoformat()
            })
    total_ha = round(float(np.sum(loss)) * ha_per_px, 1)
    return zones, total_ha


def get_bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return {"chat_ids": [], "update_offset": 0}
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}
    data = data if isinstance(data, dict) else {}
    data.setdefault("chat_ids", [])
    data.setdefault("update_offset", 0)
    return data


def save_subscribers(subs):
    subs["_note"] = "Géré automatiquement par satellite_scan.py"
    os.makedirs("data", exist_ok=True)
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)


def process_new_subscribers(token):
    subs = load_subscribers()
    try:
        resp = requests.get(
            TELEGRAM_API.format(token=token, method="getUpdates"),
            params={"offset": subs["update_offset"], "timeout": 0},
            timeout=20,
        )
        if resp.status_code == 200:
            updates = resp.json().get("result", [])
            known = {str(c) for c in subs["chat_ids"]}
            new_ids = []
            for upd in updates:
                subs["update_offset"] = max(subs["update_offset"], upd.get("update_id", 0) + 1)
                msg = upd.get("message") or upd.get("edited_message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                if chat_id is not None and str(chat_id) not in known:
                    new_ids.append(chat_id)
                    known.add(str(chat_id))

            if new_ids:
                subs["chat_ids"].extend(new_ids)
                save_subscribers(subs)
                print(f"✅ {len(new_ids)} nouvel(s) abonné(s) Telegram.")
    except Exception as exc:
        print(f"Notice Telegram getUpdates : {exc}")
    return subs


def send_telegram(message):
    token = get_bot_token()
    main_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not main_id:
        print("ℹ️ Telegram non configuré : alerte enregistrée uniquement sur le tableau de bord.")
        return

    subs = load_subscribers()
    recipients = list({str(main_id)} | {str(c) for c in subs.get("chat_ids", [])})

    for chat_id in recipients:
        try:
            requests.post(
                TELEGRAM_API.format(token=token, method="sendMessage"),
                json={"chat_id": chat_id, "text": message},
                timeout=20,
            )
        except Exception:
            pass


def write_alerts_js(zones, total_ha, scan_date, status, detail=""):
    payload = {
        "status": status,
        "date": scan_date,
        "total_loss_ha": total_ha,
        "zone_count": len(zones),
        "detail": detail,
    }
    content = (
        "// ⚠️ Fichier généré automatiquement par scripts/satellite_scan.py\n"
        f"// Dernier scan : {scan_date or 'récent'} ({status})\n"
        f"const lastScan = {json.dumps(payload, ensure_ascii=False, indent=2)};\n\n"
        f"const pnkbAlerts = {json.dumps(zones, ensure_ascii=False, indent=2)};\n"
    )
    os.makedirs("data", exist_ok=True)
    with open("data/alerts.js", "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ data/alerts.js mis à jour ({len(zones)} zone(s), {total_ha} ha).")


def main():
    if "--abonnements" in sys.argv:
        token = get_bot_token()
        if token:
            process_new_subscribers(token)
        return

    missing = [k for k in ("COPERNICUS_CLIENT_ID", "COPERNICUS_CLIENT_SECRET") if not os.environ.get(k)]
    if missing:
        write_alerts_js([], 0.0, "", "not_configured", "Secrets manquants : " + ", ".join(missing))
        return

    today = datetime.now(timezone.utc).date()
    before_from, before_to = today - timedelta(days=65), today - timedelta(days=45)
    after_from, after_to = today - timedelta(days=15), today

    print(f"📅 Analyse spatiale PNKB : du {after_from} au {after_to}")

    token, process_url = get_token_and_endpoint()
    print("🛰️ Téléchargement des bandes multispectrales Sentinel-2 L2A...")
    ndvi_b, valid_b = fetch_ndvi_png(token, process_url, str(before_from), str(before_to))
    ndvi_a, valid_a = fetch_ndvi_png(token, process_url, str(after_from), str(after_to))

    print("🔍 Analyse algorithmique de la canopée...")
    zones, total_ha = cluster_losses(ndvi_b, valid_b, ndvi_a, valid_a)

    scan_date = today.strftime("%d/%m/%Y")
    write_alerts_js(zones, total_ha, scan_date, "ok")

    if get_bot_token():
        process_new_subscribers(get_bot_token())

    if zones and total_ha >= ALERT_AREA_THRESHOLD_HA:
        top = sorted(zones, key=lambda z: -z["area_ha"])[:5]
        lines = "\n".join(f"• {z['severity']} : ~{z['area_ha']} ha à {z['lat']}, {z['lon']}" for z in top)
        alert_message = (
            "🚨 ALERTE PNKB FOREST WATCH\n"
            f"Perte forestière estimée : ~{total_ha} ha (scan du {scan_date})\n\n"
            f"{lines}\n\n"
            f"🌐 Dashboard : {DASHBOARD_URL}\n"
            f"📢 Chaîne WhatsApp : {WHATSAPP_CHANNEL_URL}"
        )
        send_telegram(alert_message)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"❌ Échec du scan : {exc}")
        sys.exit(1)
