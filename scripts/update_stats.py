"""
Met à jour le journal des alertes et les statistiques d'impact après un scan.

Ce script est appelé par les workflows GitHub Actions APRÈS scripts/satellite_scan.py :
il lit data/alerts.js (dernier scan) et met à jour :
- data/history.json (journal des scans)
- data/stats.json (statistiques d'impact publics)

Modes :
- python scripts/update_stats.py                → journalise le dernier scan
- python scripts/update_stats.py --abonnements → met à jour uniquement la
  statistique « abonnés » (utilisé par le workflow quotidien Telegram)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stats_history


def extract_json(content, varname, next_marker=None):
    """Extrait un objet JSON écrit dans data/alerts.js après « const <varname> = »."""
    start_marker = f"const {varname} = "
    start = content.index(start_marker) + len(start_marker)
    end = content.index(next_marker, start) if next_marker else len(content)
    blob = content[start:end].strip()
    if blob.endswith(";"):
        blob = blob[:-1]
    return json.loads(blob)


def main():
    if "--abonnements" in sys.argv:
        stats_history.update_subscriber_stats()
        return

    with open("data/alerts.js", "r", encoding="utf-8") as f:
        content = f.read()
    last_scan = extract_json(content, "lastScan", "const pnkbAlerts")
    zones = extract_json(content, "pnkbAlerts")
    date = last_scan.get("date") or ""
    status = last_scan.get("status") or "unknown"

    if not date or status != "ok":
        print(f"ℹ️ Aucun scan valide à journaliser (statut : {status or 'inconnu'}).")
        return

    stats_history.update_history_and_stats(
        zones, last_scan.get("total_loss_ha", 0.0), date, status
    )


if __name__ == "__main__":
    main()