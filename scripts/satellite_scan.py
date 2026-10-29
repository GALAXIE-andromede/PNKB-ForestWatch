"""
Scan satellitaire hebdomadaire du Parc National de Kahuzi-Biega.
100% gratuit : Copernicus Dataspace (Sentinel-2) + alertes Telegram & Chaîne WhatsApp.
Exécuté automatiquement par GitHub Actions (voir .github/workflows/).

Étapes :
1. Authentification auprès de Copernicus Dataspace (identifiants gratuits)
2. Téléchargement de 2 images NDVI Sentinel-2 (référence / période récente)
3. Détection des pixels de perte forestière (seuil minimum carte : 0.2 ha)
4. Écriture de data/alerts.js (affiché par la carte Leaflet du dashboard)
5. Alerte automatique si la perte atteint ou dépasse 0.5 ha.

Abonnements publics : toute personne qui ouvre le bot
(t.me/pnkb_forestwatch_alert_bot) et appuie sur « DÉMARRER » est ajoutée
automatiquement à data/subscribers.json et recevra les prochaines alertes.

Modes :
- python scripts/satellite_scan.py                → scan satellitaire complet
- python scripts/satellite_scan.py --abonnements → traite uniquement les
  nouveaux abonnés Telegram (utilisé par le workflow quotidien)
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
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
SUBSCRIBERS_FILE = "data/subscribers.json"
DASHBOARD_URL = "https://pnkb-forestwatch.vercel.app/"
WHATSAPP_CHANNEL_URL = "https://whatsapp.com/channel/0029Vb94EbL60eBnHy5UNI18"

# Zone approximative du PNKB (WGS84)
BBOX = [28.35, -2.35, 28.95, -1.85]  # [lon_min, lat_min, lon_max, lat_max]
IMG_SIZE = 512
GRID = 16                      # Découpage de l'image en blocs pour regrouper les pertes
NDVI_LOSS_THRESHOLD = 0.30     # Baisse de NDVI considérée comme une perte
NDVI_FOREST_MIN = 0.55         # NDVI minimal pour considérer la zone forestière

# --- SEUILS CALIBRÉS POUR ÉVITER LES FAUSSES ALERTES ---
MIN_MAP_DETECTION_HA = 0.2     # Seuil minimal d'affichage sur la carte (dès 0.2 ha)
ALERT_AREA_THRESHOLD_HA = 0.5  # Seuil d'alerte critique Telegram/WhatsApp (dès 0.5 ha)

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
    """Regroupe les pixels de perte et classe par sévérité (MEDIUM vs HIGH)."""
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
            
            # FILTRE : On ignore ce qui est inférieur à 0.2 ha pour éviter le bruit
            if area_ha < MIN_MAP_DETECTION_HA:
                continue

            ys, xs = np.where(block)
            row = gy + ys.mean()
            col = gx + xs.mean()
            lat = lat_max - (row / IMG_SIZE) * (lat_max - lat_min)
            lon = lon_min + (col / IMG_SIZE) * (lon_max - lon_min)
            
            # SÉVÉRITÉ : HIGH (>= 0.5 ha, Rouge) ou MEDIUM (0.2 à 0.5 ha, Orange)
            severity = "HIGH" if area_ha >= ALERT_AREA_THRESHOLD_HA else "MEDIUM"

            zones.append({
                "type": "deforestation",
                "lat": round(float(lat), 4),
                "lon": round(float(lon), 4),
                "area_ha": area_ha,
                "severity": severity,
            })
    total_ha = round(float(np.sum(loss)) * ha_per_px, 1)
    return zones, total_ha


# ---------- Abonnements Telegram (public) ----------

def get_bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def load_subscribers():
    """Charge la liste des abonnés (data/subscribers.json)."""
    if not os.path.exists(SUBSCRIBERS_FILE):
        return {"chat_ids": [], "update_offset": 0}
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("chat_ids", [])
    data.setdefault("update_offset", 0)
    return data


def save_subscribers(subs):
    subs["_note"] = "Fichier géré automatiquement par scripts/satellite_scan.py — ne pas modifier à la main."
    os.makedirs("data", exist_ok=True)
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)


def process_new_subscribers(token):
    """Détecte les personnes ayant appuyé sur « DÉMARRER » sur Telegram."""
    subs = load_subscribers()
    try:
        resp = requests.get(
            TELEGRAM_API.format(token=token, method="getUpdates"),
            params={"offset": subs["update_offset"], "timeout": 0},
            timeout=30,
        )
        resp.raise_for_status()
        updates = resp.json().get("result", [])
    except requests.RequestException as exc:
        print(f"⚠️ Impossible de lire getUpdates : {exc}")
        return subs

    known = {str(c) for c in subs["chat_ids"]}
    new_ids = []
    for upd in updates:
        subs["update_offset"] = max(subs["update_offset"], upd.get("update_id", 0) + 1)
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None or str(chat_id) in known or str(chat_id) in {str(n) for n in new_ids}:
            continue
        text = (msg.get("text") or "").strip().lower()
        if chat.get("type") == "private" or text.startswith("/start"):
            new_ids.append(chat_id)

    for chat_id in new_ids:
        subs["chat_ids"].append(chat_id)
        try:
            resp = requests.post(
                TELEGRAM_API.format(token=token, method="sendMessage"),
                json={
                    "chat_id": chat_id,
                    "text": (
                        "✅ Bienvenue sur PNKB Forest Watch !\n\n"
                        "Vous recevrez désormais une alerte dès qu'une perte forestière "
                        "significative (≥ 0.5 ha) est détectée dans le Parc National de Kahuzi-Biega.\n\n"
                        f"🌐 Dashboard : {DASHBOARD_URL}\n"
                        f"📢 Chaîne WhatsApp : {WHATSAPP_CHANNEL_URL}\n\n"
                        "🔕 Pour arrêter : bloquez simplement ce bot."
                    ),
                },
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"⚠️ Message de bienvenue non envoyé à {chat_id} : {exc}")
        print(f"🆕 Nouvel abonné Telegram : {chat_id}")

    if new_ids:
        save_subscribers(subs)
        print(f"✅ {len(new_ids)} nouvel(s) abonné(s) enregistré(s) dans {SUBSCRIBERS_FILE}.")
    return subs


def send_telegram(message):
    """Envoie le message au Chat ID principal et aux abonnés."""
    token = get_bot_token()
    main_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not main_id:
        print("⚠️ Telegram non configuré : alerte ignorée.")
        return

    subs = load_subscribers()
    recipients = []
    if main_id not in {str(c) for c in subs["chat_ids"]}:
        recipients.append(str(main_id))
    recipients += [str(c) for c in subs["chat_ids"]]

    blocked = []
    sent = 0
    for chat_id in recipients:
        try:
            resp = requests.post(
                TELEGRAM_API.format(token=token, method="sendMessage"),
                json={"chat_id": chat_id, "text": message},
                timeout=30,
            )
            resp.raise_for_status()
            sent += 1
        except requests.HTTPError:
            if getattr(resp, "status_code", None) == 403:
                blocked.append(chat_id)
            print(f"⚠️ Envoi impossible à {chat_id} (bot bloqué).")
        except requests.RequestException as exc:
            print(f"⚠️ Erreur d'envoi Telegram ({chat_id}) : {exc}")

    if blocked:
        subs["chat_ids"] = [c for c in subs["chat_ids"] if str(c) not in blocked]
        save_subscribers(subs)
        print(f"🗑️ {len(blocked)} abonné(s) retiré(s) de la liste.")
    print(f"✅ Alerte Telegram envoyée à {sent} destinataire(s).")


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


def subscribers_mode():
    """Mode --abonnements : traite uniquement les nouveaux abonnés Telegram."""
    token = get_bot_token()
    if not token:
        print("⚠️ TELEGRAM_BOT_TOKEN manquant : impossible de traiter les abonnements.")
        return
    subs = process_new_subscribers(token)
    save_subscribers(subs)
    print(f"👥 Abonnés actuels : {len(subs['chat_ids'])}.")


def main():
    if "--abonnements" in sys.argv:
        subscribers_mode()
        return

    missing = [k for k in ("COPERNICUS_CLIENT_ID", "COPERNICUS_CLIENT_SECRET") if not os.environ.get(k)]
    if missing:
        write_alerts_js(
            [], 0.0, "", "not_configured",
            "Identifiants Copernicus manquants. Ajoutez les secrets GitHub : " + ", ".join(missing),
        )
        if get_bot_token():
            process_new_subscribers(get_bot_token())
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

    if get_bot_token():
        process_new_subscribers(get_bot_token())

    # DÉCLENCHEMENT DE L'ALERTE : Uniquement si la perte totale atteint ou dépasse 0.5 ha
    if zones and total_ha >= ALERT_AREA_THRESHOLD_HA:
        top = sorted(zones, key=lambda z: -z["area_ha"])[:5]
        lines = "\n".join(
            f"• {z['severity']} : ~{z['area_ha']} ha à {z['lat']}, {z['lon']}" for z in top
        )
        
        # Message complet prêt à être partagé sur la Chaîne WhatsApp
        alert_message = (
            "🚨 ALERTE PNKB FOREST WATCH\n"
            f"Perte forestière estimée : ~{total_ha} ha (scan du {scan_date})\n\n"
            f"{lines}\n\n"
            f"🌐 Voir la carte : {DASHBOARD_URL}\n"
            f"📢 Chaîne WhatsApp : {WHATSAPP_CHANNEL_URL}"
        )
        send_telegram(alert_message)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Échec du scan : {exc}")
        sys.exit(1)
