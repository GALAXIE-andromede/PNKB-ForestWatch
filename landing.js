/* ===== Logique de la landing page : affichage des statistiques d'impact ===== */

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

document.addEventListener("DOMContentLoaded", async () => {
    const grid = document.getElementById('landing-impact');
    const note = document.getElementById('landing-impact-note');
    if (!grid) return;

    const stats = await loadDataFile('data/stats.json');
    const subscribers = stats ? (stats.current_subscribers || 0) : 0;
    const alertsSent = stats ? (stats.alerts_sent || 0) : 0;
    const scansTotal = stats ? (stats.scans_total || 0) : 0;
    const hectares = ((stats && stats.monitored_area_ha) || 600000).toLocaleString('fr-FR');

    grid.innerHTML = `
        <div class="impact-item"><span class="impact-number">👥 ${subscribers}</span><span class="impact-label">abonnés aux alertes</span></div>
        <div class="impact-item"><span class="impact-number">🚨 ${alertsSent}</span><span class="impact-label">alertes envoyées</span></div>
        <div class="impact-item"><span class="impact-number">🛰️ ${scansTotal}</span><span class="impact-label">scans réalisés</span></div>
        <div class="impact-item"><span class="impact-number">🌳 ${hectares}</span><span class="impact-label">hectares surveillés</span></div>`;

    if (note) {
        const since = stats && stats.first_scan_date
            ? `depuis le ${stats.first_scan_date}`
            : '— les chiffres monteront dès le premier scan satellitaire';
        note.textContent = `Compteur public ${since}.`;
    }
});