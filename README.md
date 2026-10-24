# PNKB-ForestWatch

Application de surveillance satellitaire du couvert forestier du **Parc National de Kahuzi-Biega** (Sud-Kivu, RDC).

## ✅ Les 3 fonctionnalités — coût total : 0 $/mois

| Fonctionnalité | Implémentation | Service utilisé (gratuit) |
|---|---|---|
| 🌳 Détection de déforestation | `scripts/satellite_scan.py` exécuté chaque lundi | Copernicus Dataspace (Sentinel-2) |
| 📊 Dashboard en ligne | `index.html` + `app.js` (carte Leaflet, graphiques Chart.js) | GitHub Pages |
| 🚨 Alertes automatiques | `send_telegram()` dans le script de scan | Bot Telegram |

## ⚙️ Fonctionnement

1. GitHub Actions déclenche le scan chaque lundi à 06:00 UTC (ou manuellement via l'onglet **Actions**).
2. Le script télécharge 2 images NDVI Sentinel-2 (période de référence vs 15 derniers jours).
3. Les zones de perte forestière sont écrites dans `data/alerts.js`, puis commitées automatiquement.
4. GitHub Pages met à jour le dashboard ; si la perte dépasse ~5 ha, une alerte Telegram est envoyée.

## 🔧 Configuration (10 minutes, 0 €)

### 1. Compte Copernicus Dataspace (gratuit)
1. Créez un compte : https://dataspace.copernicus.eu
2. Ouvrez https://shapps.dataspace.copernicus.eu/dashboard → **Add OAuth Client** → notez le **Client ID** et le **Client Secret**.

### 2. Bot Telegram (gratuit)
1. Sur Telegram, écrivez à **@BotFather** → `/newbot` → suivez les instructions → notez le **token**.
2. Ouvrez une conversation avec votre bot et appuyez sur **Start**.
3. Visitez `https://api.telegram.org/bot<TOKEN>/getUpdates` → notez votre **chat.id**.

### 3. Secrets GitHub
Dans le dépôt : **Settings → Secrets and variables → Actions → New repository secret**, ajoutez :

- `COPERNICUS_CLIENT_ID`
- `COPERNICUS_CLIENT_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### 4. Premier scan
Onglet **Actions** → workflow **« Analyse satellitaire PNKB »** → **Run workflow**.
Après quelques minutes, `data/alerts.js` est mis à jour et le dashboard affiche les résultats réels.

## 🌐 Activation de GitHub Pages (si pas déjà fait)

**Settings → Pages** → Source : branche `main`, dossier racine →
URL : https://galaxie-andromede.github.io/PNKB-ForestWatch/

## ⚠️ Limites connues (version MVP)

- Résolution grossière (le parc entier sur une image 512×512, ≈120 m/pixel) : à affiner par tuilage pour détecter les petites clairières.
- Simple différence NDVI : sensible aux nuages et à la saisonnalité.
- Limites du parc approximatives : remplacez `data/pnkb_boundary.geojson` par le fichier officiel (ICCN / Protected Planet : https://www.protectedplanet.net).

## 🚀 Améliorations futures (toujours gratuites)

- Masque de nuages (bande SCL de Sentinel-2)
- Tuilage du parc pour une résolution de 10 m
- Comparaison avec les alertes GLAD/UMD de Global Forest Watch (API gratuite)
- Historique des scans (`data/history/`) et graphique des pertes hebdomadaires
