function switchTab(evt, tabName) {
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    evt.currentTarget.classList.add('active');
    if (tabName === 'carte' && window.mapInstance) { window.mapInstance.invalidateSize(); }
}

document.addEventListener("DOMContentLoaded", () => {
    const pnkbCenter = [-2.30, 28.75];
    const map = L.map('map').setView(pnkbCenter, 10);
    window.mapInstance = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    L.marker(pnkbCenter).addTo(map)
        .bindPopup('<b>Parc National de Kahuzi-Biega</b><br>Prêt pour intégration GeoJSON');

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

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('sw.js');
    }
});

function generateReport() {
    window.print();
}
