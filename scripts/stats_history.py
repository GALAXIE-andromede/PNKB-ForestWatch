"""
Journal des alertes + statistiques d'impact publics pour PNKB Forest Watch.

Ce module est appelé par scripts/satellite_scan.py à la fin de chaque scan :
- data/history.json : historique des scans (date, perte, zones principales)
- data/stats.json   : statistiques d'impact affichées sur le dashboard
  (abonnés, alertes envoyées, scans réalisés, hectares surveillés).

Fichiers gérés automatiquement — ne pas modifier à la main.
"""
import json
import os

HISTORY_FILE = "data/history.json"
STATS_FILE = "data/stats.json"

# Superficie officielle du PNKB (hectares) — statistique « hectares surveillés ».
PNKB_AREA_HA = 600000

# Nombre maximum de scans conservés dans le journal (~2 ans en hebdomadaire).
HISTORY_MAX_SCANS = 104


def load_json(path, default):
    """Charge un fichier JSON, ou retourne la valeur par défaut si absent/corrompu."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path, data):
    """Écrit un fichier JSON en créant le dossier data si nécessaire."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_history():
    """Charge le journal des scans."""
    return load_json(HISTORY_FILE, {"scans": []})


def load_stats():
    """Charge les statistiques d'impact publics."""
    return load_json(STATS_FILE, {
        "first_scan_date": None,
        "scans_total": 0,
        "alerts_sent": 0,
        "subscribers_peak": 0,
        "current_subscribers": 0,
        "loss_cumulative_ha": 0.0,
        "monitored_area_ha": PNKB_AREA_HA,
    })


def update_history_and_stats(zones, total_ha, scan_date, status, subscribers_file="data/subscribers.json"):
    """Met à jour le journal (history.json) et les statistiques (stats.json)
    après un scan. Renvoie 1 si une alerte a été envoyée pour ce scan, sinon 0.

    - zones : liste des zones de perte détectées (dicts lat/lon/area_ha/severity)
    - total_ha : perte totale estimée (hectares)
    - scan_date : date ISO du scan (ex. "2026-10-25")
    - status : "ok" ou autre statut de scan
    """
    # Nombre de destinataires Telegram (abonnés + chat principal éventuel)
    subs = load_json(subscribers_file, {"chat_ids": []})
    subscribers_count = len(subs.get("chat_ids", []))
    main_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if main_id and str(main_id) not in {str(c) for c in subs.get("chat_ids", [])}:
        subscribers_count += 1

    alert_sent = 1 if (zones and total_ha >= 0.05) else 0

    # --- Journal des scans (une entrée par date ; re-scan même date = remplace) ---
    history = load_history()
    scans = [s for s in history.get("scans", []) if s.get("date") != scan_date]
    scans.append({
        "date": scan_date,
        "status": status,
        "total_loss_ha": total_ha,
        "zone_count": len(zones),
        "alert_sent": bool(alert_sent),
        "top_zones": sorted(zones, key=lambda z: -z["area_ha"])[:3],
    })
    scans.sort(key=lambda s: s["date"])
    history["scans"] = scans[-HISTORY_MAX_SCANS:]
    save_json(HISTORY_FILE, history)
    print(f"✅ {HISTORY_FILE} mis à jour ({len(history['scans'])} scan(s) conservé(s)).")

    # --- Statistiques d'impact ---
    stats = load_stats()
    if not stats.get("first_scan_date") or scan_date < stats["first_scan_date"]:
        stats["first_scan_date"] = scan_date
    stats["scans_total"] = stats.get("scans_total", 0) + 1
    stats["alerts_sent"] = stats.get("alerts_sent", 0) + alert_sent
    stats["subscribers_peak"] = max(stats.get("subscribers_peak", 0), subscribers_count)
    stats["current_subscribers"] = subscribers_count
    stats["monitored_area_ha"] = PNKB_AREA_HA
    stats["loss_cumulative_ha"] = round(
        stats.get("loss_cumulative_ha", 0.0) + float(total_ha), 1
    )
    save_json(STATS_FILE, stats)
    print(f"✅ {STATS_FILE} mis à jour.")

    return alert_sent


def update_subscriber_stats(subscribers_file="data/subscribers.json"):
    """Met à jour uniquement la statistique « abonnés » dans stats.json.
    Utilisée par le mode --abonnements (workflow quotidien Telegram)."""
    subs = load_json(subscribers_file, {"chat_ids": []})
    subscribers_count = len(subs.get("chat_ids", []))
    stats = load_stats()
    stats["subscribers_peak"] = max(stats.get("subscribers_peak", 0), subscribers_count)
    stats["current_subscribers"] = subscribers_count
    stats["monitored_area_ha"] = PNKB_AREA_HA
    save_json(STATS_FILE, stats)
    print(f"📊 Abonnés actuels : {subscribers_count} — {STATS_FILE} mis à jour.")