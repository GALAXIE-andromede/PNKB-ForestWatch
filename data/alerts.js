// Surveillance satellitaire Sentinel-2 — Parc National de Kahuzi-Biega
// Fichier de données d'alertes actives

const lastScan = {
  "status": "ok",
  "date": "27 Octobre 2026",
  "total_loss_ha": 2.8,
  "zone_count": 3,
  "detail": "Scan optique Sentinel-2 L2A analysé avec succès sur le PNKB."
};

const pnkbAlerts = [
  {
    "lat": -2.3164,
    "lon": 28.7051,
    "severity": "HIGH",
    "area_ha": 1.4,
    "sector": "Secteur Tshivanga",
    "date": "2026-10-27"
  },
  {
    "lat": -2.2850,
    "lon": 28.6620,
    "severity": "HIGH",
    "area_ha": 0.9,
    "sector": "Corridor Lemera",
    "date": "2026-10-27"
  },
  {
    "lat": -2.2150,
    "lon": 28.5300,
    "severity": "MEDIUM",
    "area_ha": 0.5,
    "sector": "Secteur Nzovu",
    "date": "2026-10-27"
  }
];
