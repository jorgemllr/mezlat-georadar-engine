"""
MEZLAT Allocation V4 Pipeline — CRM Dashboard Generator
========================================================
Generates a virtualized HTML CRM interface showing ALL leads.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_config import load_processed_leads, DATASETS_DIR

CRM_HTML = Path(__file__).resolve().parent.parent / "crm_pipeline_v4.html"

def generate_crm():
    print("🚀 Generating Enhanced CRM Pipeline Dashboard...")
    all_leads = load_processed_leads()
    
    # We want ALL leads, not just hot ones.
    leads = list(all_leads.values())
    # Sort: hot leads first, then by phase2_score
    leads.sort(key=lambda x: (x.get("is_hot_lead", False), x.get("phase2_score", 0)), reverse=True)

    tier1_count = sum(1 for L in leads if L.get("target_tier") == 3 or L.get("hot_lead_tier") == 1)
    p2_count = sum(1 for L in leads if L.get("phase2_done") or L.get("photos"))
    total_leads = len(leads)

    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>MEZLAT // Sales Pipeline CRM</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background-color: #050505; color: #e5e5e5; margin: 0; padding: 0; min-height: 100vh; }
        
        /* ── TOPBAR ─────────────────────────────────────────────────── */
        .topbar { display: flex; align-items: center; gap: 14px; padding: 20px 36px; border-bottom: 1px solid #1f1f1f; background: #0a0a0a; }
        .topbar-hex { width: 18px; height: 18px; background: #22c55e; clip-path: polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%); }
        .topbar-title { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700; letter-spacing: 0.2em; color: #ffffff; }
        .topbar-title span { color: #404040; }
        
        /* ── FILTER CONTROLS BAR ────────────────────────────────────── */
        .filter-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 14px 36px; background: #0a0a0a; border-bottom: 1px solid #1f1f1f; }
        .filter-group { display: flex; flex-direction: column; gap: 4px; }
        .filter-lbl { font-size: 8px; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; letter-spacing: 0.15em; color: #737373; }
        .filter-input, .filter-select { padding: 8px 12px; background: #141414; color: #fff; border: 1px solid #333; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 11px; outline: none; transition: border-color 0.2s; }
        .filter-input { width: 300px; }
        .filter-input:focus, .filter-select:focus { border-color: #22c55e; }

        /* ── METRICS BAR ────────────────────────────────────────────── */
        .metrics-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; padding: 20px 36px 10px; }
        .metric-card { background: #0d0d0d; border: 1px solid #222; border-radius: 6px; padding: 14px 18px; }
        .metric-card-lbl { font-size: 9px; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; letter-spacing: 0.15em; color: #737373; margin-bottom: 6px; }
        .metric-card-val { font-size: 24px; font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #fff; }

        /* ── LEADS GRID ─────────────────────────────────────────────── */
        .container { padding: 20px 36px 60px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
        .card { background: #0a0a0a; border: 1px solid #222; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; transition: border-color 0.2s; }
        .card:hover { border-color: #444; }
        .card-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: #111; border-bottom: 1px solid #222; }
        .card-niche { font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 700; letter-spacing: 0.15em; color: #3b82f6; text-transform: uppercase; }
        
        .badge-tier { font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 700; letter-spacing: 0.1em; padding: 3px 8px; border-radius: 4px; }
        .tier-3 { background: rgba(239,68,68,0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); } /* Enterprise */
        .tier-2 { background: rgba(59,130,246,0.1); color: #3b82f6; border: 1px solid rgba(59,130,246,0.3); } /* Growth */
        .tier-1 { background: rgba(34,197,94,0.1); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); } /* Starter */
        
        .badge-status { display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 700; letter-spacing: 0.1em; padding: 2px 6px; background: #333; color: #fff; border-radius: 2px; margin-right: 4px; }
        
        .card-body { padding: 16px; flex: 1; display: flex; flex-direction: column; gap: 12px; }
        .card-title { margin: 0; font-size: 15px; font-weight: 600; color: #fff; line-height: 1.3; }
        
        /* Carousel */
        .carousel-box { position: relative; width: 100%; height: 140px; background: #000; border-radius: 4px; overflow: hidden; border: 1px solid #222; }
        .carousel-img { width: 100%; height: 100%; object-fit: cover; }
        .carousel-bar { position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.8); display: flex; justify-content: space-between; align-items: center; padding: 4px 8px; backdrop-filter: blur(4px); }
        .carousel-btn { background: none; border: none; color: #fff; font-family: 'JetBrains Mono', monospace; font-size: 9px; cursor: pointer; padding: 4px; }
        .carousel-cnt { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #a3a3a3; }
        
        .card-details { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 4px; }
        .detail-item { display: flex; flex-direction: column; gap: 2px; }
        .detail-lbl { font-family: 'JetBrains Mono', monospace; font-size: 8px; color: #737373; text-transform: uppercase; }
        .detail-val { font-size: 12px; color: #d4d4d4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        
        .card-actions { display: flex; gap: 8px; margin-top: auto; padding-top: 12px; border-top: 1px dotted #333; }
        .btn-act { flex: 1; text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700; text-decoration: none; padding: 8px; border-radius: 4px; transition: all 0.2s; }
        .btn-wa { background: rgba(34,197,94,0.1); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); }
        .btn-wa:hover { background: rgba(34,197,94,0.2); }
        .btn-map { background: rgba(59,130,246,0.1); color: #3b82f6; border: 1px solid rgba(59,130,246,0.3); }
        .btn-map:hover { background: rgba(59,130,246,0.2); }
        
        #btn-load-more { display: none; padding: 12px 24px; background: #22c55e; color: #000; border: none; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-weight: 700; cursor: pointer; margin: 20px auto; transition: opacity 0.2s; }
        #btn-load-more:hover { opacity: 0.8; }
    </style>
</head>
<body>
    <div class="topbar">
        <div class="topbar-hex"></div>
        <div class="topbar-title">MEZLAT <span>CRM // PIPELINE V4</span></div>
    </div>

    <!-- FILTERS -->
    <div class="filter-bar">
        <div class="filter-group" style="flex:1;">
            <div class="filter-lbl">Search Name / Address / Phone</div>
            <input type="text" id="filter-search" class="filter-input" placeholder="SEARCH PROSPECTS..." onkeyup="applyFilters()">
        </div>
        <div class="filter-group">
            <div class="filter-lbl">City</div>
            <select id="filter-city" class="filter-select" onchange="applyFilters()">
                <option value="all">ALL CITIES</option>
            </select>
        </div>
        <div class="filter-group">
            <div class="filter-lbl">Category / Niche</div>
            <select id="filter-niche" class="filter-select" onchange="applyFilters()">
                <option value="all">ALL CATEGORIES</option>
            </select>
        </div>
        <div class="filter-group">
            <div class="filter-lbl">Sales Target (Pricing Tier)</div>
            <select id="filter-target" class="filter-select" onchange="applyFilters()">
                <option value="all">ALL TARGET TIERS</option>
                <option value="3">TIER 3 (ENTERPRISE VIP / $6k-$12k)</option>
                <option value="2">TIER 2 (GROWTH / $2.5k-$5.9k)</option>
                <option value="1">TIER 1 (STARTER / $300-$990)</option>
            </select>
        </div>
        <div class="filter-group">
            <div class="filter-lbl">Sales Status</div>
            <select id="filter-status" class="filter-select" onchange="applyFilters()">
                <option value="all">ALL STATUSES</option>
                <option value="NEW">NEW (UNCONTACTED)</option>
                <option value="CONTACTED">CONTACTED</option>
                <option value="PITCHED">PITCHED</option>
                <option value="SOLD">SOLD</option>
                <option value="REJECTED">REJECTED</option>
            </select>
        </div>
        <div class="filter-group">
            <div class="filter-lbl">Lead Quality</div>
            <select id="filter-quality" class="filter-select" onchange="applyFilters()">
                <option value="all">ALL (INCLUDING TRASH)</option>
                <option value="hot" selected>HOT LEADS ONLY</option>
            </select>
        </div>
        <div class="filter-group">
            <div class="filter-lbl">WhatsApp</div>
            <select id="filter-whatsapp" class="filter-select" onchange="applyFilters()" style="color: #22c55e; font-weight: bold;">
                <option value="all">ALL (WA & NON-WA)</option>
                <option value="verified">✅ VERIFIED WHATSAPP ONLY</option>
                <option value="unverified">❌ NO WHATSAPP / UNCHECKED</option>
            </select>
        </div>
    </div>

    <!-- METRICS -->
    <div class="metrics-bar">
        <div class="metric-card">
            <div class="metric-card-lbl">Displayed Leads</div>
            <div class="metric-card-val" id="metric-displayed">0</div>
        </div>
        <div class="metric-card">
            <div class="metric-card-lbl">Total Database Leads</div>
            <div class="metric-card-val" style="color: #a3a3a3;">__TOTAL_LEADS__</div>
        </div>
        <div class="metric-card">
            <div class="metric-card-lbl">Tier 3 (Enterprise) & Tier 1 (Whales)</div>
            <div class="metric-card-val" style="color: #3b82f6;">__TIER1_COUNT__</div>
        </div>
        <div class="metric-card">
            <div class="metric-card-lbl">Phase 2 Enriched</div>
            <div class="metric-card-val" style="color: #d946ef;">__P2_COUNT__</div>
        </div>
    </div>

    <!-- GRID -->
    <div class="container">
        <div class="grid" id="leads-grid"></div>
        <div style="text-align: center;">
            <button id="btn-load-more" onclick="window.loadMore()">LOAD MORE 50 LEADS ▼</button>
        </div>
    </div>

    <script>
        const leads = __JSON_LEADS__;
        
        let currentPage = 1;
        const pageSize = 50;
        let filteredLeads = [];
        window.photoIndices = {};

        // Populate dynamic dropdowns
        const citySet = new Set();
        const nicheSet = new Set();
        leads.forEach(L => {
            if (L.city_zone) citySet.add(L.city_zone);
            if (L.primary_type) nicheSet.add(L.primary_type);
        });

        const citySelect = document.getElementById('filter-city');
        Array.from(citySet).sort().forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.toLowerCase();
            opt.innerText = c.toUpperCase();
            citySelect.appendChild(opt);
        });

        const nicheSelect = document.getElementById('filter-niche');
        Array.from(nicheSet).sort().forEach(n => {
            const opt = document.createElement('option');
            opt.value = n.toLowerCase();
            opt.innerText = n.replace(/_/g, ' ').toUpperCase();
            nicheSelect.appendChild(opt);
        });

        window.changeCardPhoto = function(pid, direction, total) {
            if (!window.photoIndices[pid]) window.photoIndices[pid] = 0;
            window.photoIndices[pid] = (window.photoIndices[pid] + direction + total) % total;
            const idx = window.photoIndices[pid];
            const lead = leads.find(x => x.place_id === pid);
            if (lead && lead.photos && lead.photos[idx]) {
                document.getElementById('img_' + pid).src = lead.photos[idx];
                document.getElementById('cnt_' + pid).innerText = (idx + 1) + ' / ' + total;
            }
        };

        function renderGrid(append = false) {
            const grid = document.getElementById('leads-grid');
            if (!append) grid.innerHTML = '';
            
            const start = (currentPage - 1) * pageSize;
            const end = start + pageSize;
            const chunk = filteredLeads.slice(start, end);
            
            chunk.forEach(L => {
                const tt = L.target_tier || 1;
                const tierClass = 'tier-' + tt;
                let tierLabel = '';
                if (tt === 3) tierLabel = 'TIER 3 (ENTERPRISE)';
                else if (tt === 2) tierLabel = 'TIER 2 (GROWTH)';
                else tierLabel = 'TIER 1 (STARTER)';
                
                const cleanPhone = (L.phone || '').replace(/[^0-9]/g, '');
                const waUrl = `https://api.whatsapp.com/send?phone=${cleanPhone}&text=Hello,%20I%20saw%20your%20business%20${encodeURIComponent(L.business_name)}%20on%20Google%20Maps`;
                const mapsUrl = L.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${L.lat},${L.lng}`;

                const photos = (L.photos && L.photos.length > 0) ? L.photos : [];
                let photoSection = '';
                if (photos.length > 0) {
                    photoSection = `
                        <div class="carousel-box">
                            <img id="img_${L.place_id}" src="${photos[0]}" class="carousel-img" alt="Photo">
                            ${photos.length > 1 ? `
                                <div class="carousel-bar">
                                    <button class="carousel-btn" onclick="window.changeCardPhoto('${L.place_id}', -1, ${photos.length})">◄ PREV</button>
                                    <span id="cnt_${L.place_id}" class="carousel-cnt">1 / ${photos.length}</span>
                                    <button class="carousel-btn" onclick="window.changeCardPhoto('${L.place_id}', 1, ${photos.length})">NEXT ►</button>
                                </div>
                            ` : ''}
                        </div>
                    `;
                }

                const waBadge = L.has_whatsapp === true
                    ? `<span style="font-family:'JetBrains Mono', monospace; font-size:9px; font-weight:700; padding:2px 6px; border-radius:3px; background:rgba(34,197,94,0.15); color:#22c55e; border:1px solid rgba(34,197,94,0.3); margin-right:4px;">WA VERIFIED</span>`
                    : (L.has_whatsapp === false
                        ? `<span style="font-family:'JetBrains Mono', monospace; font-size:9px; font-weight:700; padding:2px 6px; border-radius:3px; background:rgba(239,68,68,0.1); color:#ef4444; border:1px solid rgba(239,68,68,0.2); margin-right:4px;">NO WA</span>`
                        : '');

                const cardHtml = `
                    <div class="card">
                        <div class="card-header">
                            <span class="card-niche">${L.primary_type || 'BUSINESS'}</span>
                            <div>
                                ${waBadge}
                                <span class="badge-tier ${tierClass}">${tierLabel}</span>
                            </div>
                        </div>
                        <div class="card-body">
                            <h3 class="card-title">${L.business_name}</h3>
                            <div style="margin-bottom: 8px;">
                                <span class="badge-status">${L.sales_status || 'NEW'}</span>
                                <span class="badge-status" style="background:#059669;">ANCHOR: $${L.suggested_price || 0}</span>
                            </div>
                            ${photoSection}
                            <div class="card-details">
                                <div class="detail-item">
                                    <span class="detail-lbl">Rating / Revs</span>
                                    <span class="detail-val">${L.rating || 'N/A'} ★ (${L.reviews_count || 0})</span>
                                </div>
                                <div class="detail-item">
                                    <span class="detail-lbl">P2 Score</span>
                                    <span class="detail-val" style="color: #22c55e; font-weight:700;">${L.phase2_score || 0} pts</span>
                                </div>
                                <div class="detail-item" style="grid-column: 1 / -1;">
                                    <span class="detail-lbl">Address</span>
                                    <span class="detail-val" title="${L.address || ''}">${L.address || '—'}</span>
                                </div>
                            </div>
                            <div class="card-actions">
                                <a href="${waUrl}" target="_blank" class="btn-act btn-wa">WhatsApp</a>
                                <a href="${mapsUrl}" target="_blank" class="btn-act btn-map">Maps</a>
                            </div>
                        </div>
                    </div>
                `;
                grid.insertAdjacentHTML('beforeend', cardHtml);
            });

            document.getElementById('metric-displayed').innerText = filteredLeads.length;
            
            const btnMore = document.getElementById('btn-load-more');
            if (end < filteredLeads.length) {
                btnMore.style.display = 'inline-block';
            } else {
                btnMore.style.display = 'none';
            }
        }

        window.loadMore = function() {
            currentPage++;
            renderGrid(true);
        };

        window.applyFilters = function() {
            const q = document.getElementById('filter-search').value.toLowerCase().trim();
            const cityFilter = document.getElementById('filter-city').value;
            const nicheFilter = document.getElementById('filter-niche').value;
            const targetFilter = document.getElementById('filter-target').value;
            const statusFilter = document.getElementById('filter-status').value;
            const qualityFilter = document.getElementById('filter-quality').value;
            const waFilter = document.getElementById('filter-whatsapp').value;

            filteredLeads = leads.filter(L => {
                const name = (L.business_name || "").toLowerCase();
                const addr = (L.address || "").toLowerCase();
                const phone = (L.phone || "").toLowerCase();
                const niche = (L.primary_type || "").toLowerCase();
                const cityZone = (L.city_zone || "").toLowerCase();
                const tier = String(L.target_tier || 1);
                const status = (L.sales_status || "NEW").toUpperCase();
                const isHot = !!L.is_hot_lead;
                
                if (q && !name.includes(q) && !addr.includes(q) && !phone.includes(q)) return false;
                if (cityFilter !== 'all' && cityZone !== cityFilter) return false;
                if (nicheFilter !== 'all' && niche !== nicheFilter) return false;
                if (targetFilter !== 'all' && tier !== targetFilter) return false;
                if (statusFilter !== 'all' && status !== statusFilter) return false;
                if (qualityFilter === 'hot' && !isHot) return false;
                
                if (waFilter === 'verified' && L.has_whatsapp !== true) return false;
                if (waFilter === 'unverified' && L.has_whatsapp === true) return false;
                
                return true;
            });
            
            currentPage = 1;
            renderGrid(false);
        };

        // Init
        applyFilters();
    </script>
</body>
</html>"""

    html = html_template.replace("__TOTAL_LEADS__", str(total_leads))
    html = html.replace("__TIER1_COUNT__", str(tier1_count))
    html = html.replace("__P2_COUNT__", str(p2_count))
    html = html.replace("__JSON_LEADS__", json.dumps(leads, ensure_ascii=False))

    with open(CRM_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ Generated Enhanced CRM Dashboard at:\n   {CRM_HTML}")

if __name__ == '__main__':
    generate_crm()
