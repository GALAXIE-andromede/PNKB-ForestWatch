const PNKB_CENTER = [-2.30, 28.75];

function switchTab(evt, tabName) {
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    evt.currentTarget.classList.add('active');
    if (tabName === 'carte' && window.mapInstance) { window.mapInstance.invalidateSize(); }
}

/* ---------- Bannière d'état du dernier scan ---------- */
function renderScanBanner() {
    const banner = document.getElementById('scan-banner');
    if (!banner || typeof lastScan === 'undefined') return;
    if (lastScan.status === 'ok') {
        banner.className = 'card demo-banner';
        banner.innerHTML = `
            <h3>✅ Données réelles — Dernier scan : ${lastScan.date}</h3>
            <p>Perte forestière estimée sur les 15 derniers jours : <strong>${lastScan.total_loss_ha} ha</strong> (${lastScan.zone_count} zone(s) détectée(s)) — analyse Sentinel-2 automatique.</p>`;
    } else if (lastScan.status === 'not_configured') {
        banner.className = 'card demo-banner';
        banner.innerHTML = `
            <h3>⚠️ Configuration incomplète</h3>
            <p>${lastScan.detail || 'Identifiants Copernicus manquants : ajoutez les secrets GitHub (voir README.md).'}</p>`;
    } else {
        banner.className = 'card demo-banner';
        banner.innerHTML = `
            <h3>⏳ En attente du premier scan</h3>
            <p>${lastScan.detail || 'Lancez le workflow « Analyse satellitaire PNKB » dans l\\'onglet Actions du dépôt GitHub.'}</p>`;
    }
}

/* ---------- Chargement asynchrone de history.json / stats.json ---------- */
async function loadDataFile(path) {
    try {
        const res = await fetch(path, { cache: 'no-store' });
        if (!res.ok) return null;
        return await res.json();
    } catch (e) {
        console.warn(`Impossible de charger ${path} :`, e);
        return null;
    }
}

/* ---------- Statistiques d'impact (bandeau public) ---------- */
function renderImpactStats(stats) {
    const card = document.getElementById('impact-stats-card');
    const box = document.getElementById('impact-stats');
    if (!card || !box || !stats) return;

    const since = stats.first_scan_date
        ? `depuis le ${stats.first_scan_date}`
        : 'en attente du premier scan';
    const subscribers = stats.current_subscribers || 0;
    const alertsSent = stats.alerts_sent || 0;
    const scansTotal = stats.scans_total || 0;
    const hectares = (stats.monitored_area_ha || 600000).toLocaleString('fr-FR');
    const lossCumul = (stats.loss_cumulative_ha || 0).toLocaleString('fr-FR');

    card.style.display = 'block';
    box.innerHTML = `
        <div style="display:flex;flex-wrap:wrap;gap:12px;text-align:center;">
            <div style="flex:1;min-width:130px;background:#e8f5e9;border-radius:10px;padding:14px;">
                <div style="font-size:26px;font-weight:bold;color:#2e7d32;">👥 ${subscribers}</div>
                <div style="font-size:12px;color:#555;">abonnés aux alertes</div>
            </div>
            <div style="flex:1;min-width:130px;background:#fff3e0;border-radius:10px;padding:14px;">
                <div style="font-size:26px;font-weight:bold;color:#e65100;">🚨 ${alertsSent}</div>
                <div style="font-size:12px;color:#555;">alertes envoyées</div>
            </div>
            <div style="flex:1;min-width:130px;background:#e3f2fd;border-radius:10px;padding:14px;">
                <div style="font-size:26px;font-weight:bold;color:#1565c0;">🛰️ ${scansTotal}</div>
                <div style="font-size:12px;color:#555;">scans réalisés</div>
            </div>
            <div style="flex:1;min-width:130px;background:#f3e5f5;border-radius:10px;padding:14px;">
                <div style="font-size:26px;font-weight:bold;color:#6a1b9a;">🌳 ${hectares}</div>
                <div style="font-size:12px;color:#555;">hectares surveillés</div>
            </div>
        </div>
        <p style="font-size:12px;color:#777;margin-top:10px;margin-bottom:0;">
            Perte cumulée détectée : <strong>${lossCumul} ha</strong> — ${since}.
        </p>`;
}

/* ---------- Journal des alertes (historique) ---------- */
function renderAlertsHistory(history) {
    const box = document.getElementById('alerts-history');
    if (!box) return;
    if (!history || !history.scans || history.scans.length === 0) {
        box.innerHTML = '<p>📜 Le journal se remplira automatiquement à chaque scan hebdomadaire (chaque lundi). Revenez bientôt !</p>';
        return;
    }
    const rows = history.scans.slice().reverse().map(s => {
        const icon = s.alert_sent ? '🚨' : '✅';
        const loss = (s.total_loss_ha || 0).toLocaleString('fr-FR');
        return `
            <tr>
                <td>${s.date}</td>
                <td>${icon} ${loss} ha</td>
                <td>${s.zone_count || 0}</td>
                <td>${s.alert_sent ? 'Alerte envoyée' : 'Rien de significatif'}</td>
            </tr>`;
    }).join('');
    box.innerHTML = `
        <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
                <tr style="border-bottom:2px solid #2e7d32;text-align:left;">
                    <th style="padding:6px;">Date du scan</th>
                    <th style="padding:6px;">Perte estimée</th>
                    <th style="padding:6px;">Zones</th>
                    <th style="padding:6px;">Résultat</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
        </div>`;
}

/* ---------- Panneau Alertes ---------- */
function renderAlertsPanel() {
    const summary = document.getElementById('alerts-summary');
    const list = document.getElementById('alerts-list');
    if (!summary || !list) return;
    const alerts = (typeof pnkbAlerts !== 'undefined' && pnkbAlerts) ? pnkbAlerts : [];

    summary.innerHTML = (typeof lastScan !== 'undefined' && lastScan && lastScan.date)
        ? `<p>Dernier scan : <strong>${lastScan.date}</strong> — Perte estimée : <strong>${lastScan.total_loss_ha} ha</strong></p>`
        : '<p>Aucun scan effectué pour le moment.</p>';

    if (alerts.length === 0) {
        list.innerHTML = '<p>✅ Aucune perte forestière significative détectée lors du dernier scan.</p>';
        return;
    }
    const sorted = [...alerts].sort((a, b) => b.area_ha - a.area_ha);
    list.innerHTML = sorted.map(z => `
        <div style="background:#fee2e2;padding:12px;border-radius:8px;margin-bottom:10px;">
            <strong>${z.severity === 'HIGH' ? '🔴' : '🟠'} ${z.severity}</strong> — ${z.area_ha} ha
            <br><small>Position : ${z.lat}, ${z.lon}</small>
        </div>`).join('');
}

/* ---------- Carte Leaflet ---------- */
async function initMap() {
    const map = L.map('map').setView(PNKB_CENTER, 9);
    window.mapInstance = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Limites du parc (GeoJSON) — style bien visible
    try {
        const res = await fetch('data/pnkb_boundary.geojson');
        if (res.ok) {
            const geojson = await res.json();
            const parkLayer = L.geoJSON(geojson, {
                style: {
                    color: '#2e7d32',        // bordure vert foncé
                    weight: 4,              // bordure épaisse
                    opacity: 1,
                    fillColor: '#4caf50',   // remplissage vert
                    fillOpacity: 0.15       // remplissage visible
                },
                onEachFeature: (feature, layer) => {
                    const name = feature.properties && feature.properties.name
                        ? feature.properties.name
                        : 'Parc National de Kahuzi-Biega';
                    layer.bindPopup(
                        `<b>🌳 ${name}</b><br>` +
                        `Parc National de Kahuzi-Biega<br>` +
                        `<small>Limites approximatives — le fichier officiel ICCN remplacera ce tracé.</small>`
                    );
                    // Étiquette permanente du secteur sur la carte
                    layer.bindTooltip(name, {
                        permanent: true,
                        direction: 'center',
                        className: 'park-label'
                    });
                }
            }).addTo(map);
            // Cadre automatique sur l'ensemble du parc (les 2 secteurs)
            try {
                map.fitBounds(parkLayer.getBounds(), { padding: [20, 20] });
            } catch (e) { /* bornes indisponibles : on garde la vue par défaut */ }
        }
    } catch (e) {
        console.warn('GeoJSON des limites non chargé :', e);
    }

    // Zones de déforestation détectées
    const alerts = (typeof pnkbAlerts !== 'undefined' && pnkbAlerts) ? pnkbAlerts : [];
    alerts.forEach(z => {
        const color = z.severity === 'HIGH' ? '#d32f2f' : '#f57c00';
        L.circle([z.lat, z.lon], {
            radius: Math.max(300, z.area_ha * 40),
            color: color,
            fillColor: color,
            fillOpacity: 0.35,
            weight: 1.5
        }).addTo(map).bindPopup(
            `<b>🚨 Perte forestière (${z.severity})</b><br>` +
            `Superficie : <strong>${z.area_ha} ha</strong><br>` +
            `Position : ${z.lat}, ${z.lon}`
        );
    });
}

/* ---------- Graphiques ---------- */
function initChart() {
    const ctx = document.getElementById('forestChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: forestHistoricalData.years,
            datasets: [{
                label: 'Couvert forestier estimé (%)',
                data: forestHistoricalData.canopyCoverPercent,
                borderColor: '#2e7d32',
                backgroundColor: 'rgba(46, 125, 50, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.2
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { min: 90, max: 100 } }
        }
    });
}

function initHistoryChart(history) {
    const canvas = document.getElementById('historyChart');
    if (!canvas) return;
    if (!history || !history.scans || history.scans.length === 0) {
        canvas.parentElement.insertAdjacentHTML('beforeend',
            '<p style="font-size:13px;color:#555;">Le graphique apparaîtra dès le premier scan.</p>');
        return;
    }
    const ctx = canvas.getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: history.scans.map(s => s.date),
            datasets: [{
                label: 'Perte forestière estimée (ha)',
                data: history.scans.map(s => s.total_loss_ha || 0),
                backgroundColor: 'rgba(211, 47, 47, 0.6)',
                borderColor: '#d32f2f',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { beginAtZero: true } }
        }
    });
}

/* ---------- Initialisation ---------- */
document.addEventListener("DOMContentLoaded", async () => {
    renderScanBanner();
    renderAlertsPanel();
    initMap();
    initChart();

    const [stats, history] = await Promise.all([
        loadDataFile('data/stats.json'),
        loadDataFile('data/history.json')
    ]);
    renderImpactStats(stats);
    renderAlertsHistory(history);
    initHistoryChart(history);

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('sw.js');
    }
});

function generateReport() {
    window.print();
}