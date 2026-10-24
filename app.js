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
            <p>${lastScan.detail || 'Lancez le workflow « Analyse satellitaire PNKB » dans l\'onglet Actions du dépôt GitHub.'}</p>`;
    }
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
    const map = L.map('map').setView(PNKB_CENTER, 10);
    window.mapInstance = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Limites officielles du parc (GeoJSON)
    try {
        const res = await fetch('data/pnkb_boundary.geojson');
        if (res.ok) {
            const geojson = await res.json();
            L.geoJSON(geojson, {
                style: { color: '#2e7d32', weight: 2, fillOpacity: 0.05 }
            }).addTo(map).bindPopup('<b>Parc National de Kahuzi-Biega</b><br>Limites (approximatives, à remplacer par le fichier officiel ICCN)');
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

/* ---------- Graphique historique ---------- */
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

document.addEventListener("DOMContentLoaded", () => {
    renderScanBanner();
    renderAlertsPanel();
    initMap();
    initChart();

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('sw.js');
    }
});

function generateReport() {
    window.print();
}
