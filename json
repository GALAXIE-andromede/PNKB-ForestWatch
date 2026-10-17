// Gestion des onglets de navigation
function switchTab(evt, tabName) {
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    evt.currentTarget.classList.add('active');

    if (tabName === 'carte' && window.mapInstance) {
        window.mapInstance.invalidateSize();
    }
}

document.addEventListener("DOMContentLoaded", () => {
    // Initialisation de la carte Leaflet centrée sur le PNKB
    const pnkbCenter = [-2.30, 28.75];
    const map = L.map('map').setView(pnkbCenter, 10);
    window.mapInstance = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // TEMPORAIRE : Marqueur en attendant le fichier des limites officielles (GeoJSON)
    L.marker(pnkbCenter).addTo(map)
        .bindPopup('<b>Parc National de Kahuzi-Biega</b><br>Limites officielles à intégrer (GeoJSON)');

    /* 
      COMMENT INTÉGRER LES VRAIES LIMITES PLUS TARD :
      Quand vous aurez votre fichier 'pnkb.geojson', vous pourrez décommenter 
      le code ci-dessous pour tracer automatiquement les frontières du parc :
      
      fetch('pnkb.geojson')
        .then(response => response.json())
        .then(data => {
            L.geoJSON(data, {
                style: { color: '#2e7d32', weight: 2, fillColor: '#4caf50', fillOpacity: 0.2 }
            }).addTo(map);
        });
    */

    // Initialisation du Graphique sur 10 ans
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
            plugins: {
                legend: { position: 'bottom' }
            },
            scales: {
                y: { min: 90, max: 100 }
            }
        }
    });

    // Enregistrement du Service Worker pour la PWA
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('sw.js');
    }
});

// Fonction d'export de rapport
function generateReport() {
    window.print();
}
