"""
MESLATT Allocation V4 Pipeline — Fog of War Tactical Map Generator
===================================================================
Generates fog_of_war_map_v4.html with interactive multi-parameter controls:
  - Lead Status Selector (All Leads / Hot Leads / Phase 2 Enriched / Standard)
  - Dynamic City Filter Dropdown (All Cities vs Specific City)
  - Dynamic Niche / Category Filter Dropdown (All Niches vs Specific Niche)
  - Tier Filter (All Tiers vs Tier 1 vs Tier 2)
  - Instant Search Filter (Name & Address)
  - Interactive Photo Carousel, WhatsApp direct link & Google Maps deep link
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_config import (
    CLUSTERS_FILE,
    PROCESSED_LEADS_FILE,
    SCANNED_PROBES_FILE,
    FOG_MAP_HTML,
    load_commercial_clusters,
    load_processed_leads,
    load_scanned_state
)

def generate_fog_map_html():
    print("🚀 Generating Fog of War Map V4 with Interactive Filtering Controls...")

    clusters_data = load_commercial_clusters()
    leads_data = load_processed_leads()
    scanned_state = load_scanned_state()
    scanned_probes_list = [pid for pid in scanned_state.keys()]

    hot_leads_count = sum(1 for lead in leads_data.values() if lead.get('is_hot_lead'))
    std_leads_count = len(leads_data) - hot_leads_count

    # Inject Phase status into clusters
    import h3
    scanned_set = set(scanned_probes_list)
    phase2_leads = [ld for ld in leads_data.values() if ld.get("photos")]

    for city, cData in clusters_data.items():
        for cl in cData.get("all_clusters", []):
            phase1 = False
            for p in cl.get("radar_probes", []):
                pid = f"{cl['city']}_{p['centroid_lat']}_{p['centroid_lng']}"
                if pid in scanned_set:
                    phase1 = True
                    break

            phase2 = False
            for ld in phase2_leads:
                try:
                    if h3.latlng_to_cell(ld["lat"], ld["lng"], 8) == cl["h3_index"]:
                        phase2 = True
                        break
                except Exception:
                    pass

            cl["phase1_done"] = phase1
            cl["phase2_done"] = phase2

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>MESLATT V4 - Tactical Fog of War & Lead Inspector</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.4.1/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.4.1/dist/MarkerCluster.Default.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.4.1/dist/leaflet.markercluster.js"></script>
    <script src="https://unpkg.com/h3-js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">

    <style>
        *, *::before, *::after {{ box-sizing: border-box; }}
        body {{ margin: 0; padding: 0; font-family: 'Inter', sans-serif; background-color: #050505; color: #e5e5e5; }}
        
        /* ── MAP ──────────────────────────────────────────────────────────── */
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100vh; background: #030303; }}
        
        #map::after {{
            content: '';
            position: absolute; inset: 0; pointer-events: none; z-index: 399;
            background-image:
                linear-gradient(to right, rgba(255,255,255,0.025) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(255,255,255,0.025) 1px, transparent 1px),
                linear-gradient(to right, rgba(255,255,255,0.008) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(255,255,255,0.008) 1px, transparent 1px);
            background-size: 100px 100px, 100px 100px, 20px 20px, 20px 20px;
        }}
        #map::before {{
            content: '';
            position: absolute; inset: 0; pointer-events: none; z-index: 400;
            background: radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.75) 100%);
        }}
        
        /* ── SIDE PANEL ───────────────────────────────────────────────────── */
        .side-panel {{
            position: absolute; top: 0; left: 0; z-index: 1000;
            height: 100vh; width: 310px;
            background: rgba(5,5,5,0.96); backdrop-filter: blur(20px);
            border-right: 1px solid #222;
            display: flex; flex-direction: column;
            overflow-y: auto;
        }}
        .sp-header {{
            padding: 20px 24px;
            border-bottom: 1px solid #222;
        }}
        .sp-brand {{
            display: flex; align-items: center; gap: 10px; margin-bottom: 4px;
        }}
        .sp-hex {{
            width: 18px; height: 18px;
            background: #3b82f6; clip-path: polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);
        }}
        .sp-title {{
            font-size: 12px; font-weight: 700;
            letter-spacing: 0.2em; color: #ffffff;
            font-family: 'JetBrains Mono', monospace;
        }}
        .sp-title span {{ color: #404040; }}
        .sp-sub {{
            font-size: 9px; color: #525252;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: 0.15em; text-transform: uppercase;
        }}

        /* Controls Section */
        .sp-controls {{
            padding: 16px 20px;
            border-bottom: 1px solid #222;
            display: flex; flex-direction: column; gap: 10px;
        }}
        .sp-control-lbl {{
            font-size: 8px; text-transform: uppercase; letter-spacing: 0.15em;
            color: #737373; font-family: 'JetBrains Mono', monospace;
            margin-bottom: 3px;
        }}
        .sp-input, .sp-select {{
            width: 100%; padding: 7px 10px; background: #111; color: #fff;
            border: 1px solid #333; border-radius: 4px;
            font-family: 'JetBrains Mono', monospace; font-size: 11px;
            outline: none; transition: border-color 0.2s;
        }}
        .sp-input:focus, .sp-select:focus {{ border-color: #3b82f6; }}
        
        .sp-metrics {{
            padding: 16px 20px;
            border-bottom: 1px solid #222;
            display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
        }}
        .sp-metric-lbl {{
            font-size: 8px; text-transform: uppercase;
            letter-spacing: 0.15em; color: #525252;
            font-family: 'JetBrains Mono', monospace;
            margin-bottom: 4px;
        }}
        .sp-metric-val {{
            font-size: 20px; font-weight: 300; color: #ffffff;
            font-family: 'JetBrains Mono', monospace; line-height: 1;
        }}

        .sp-legend {{
            padding: 16px 20px;
            flex: 1;
        }}
        .sp-legend-title {{
            font-size: 9px; font-weight: 600; color: #737373;
            text-transform: uppercase; letter-spacing: 0.2em;
            font-family: 'JetBrains Mono', monospace;
            margin-bottom: 16px;
        }}
        .sp-legend ul {{ list-style: none; padding: 0; margin: 0; }}
        .sp-legend li {{
            display: flex; align-items: center; gap: 12px;
            margin-bottom: 12px;
            font-size: 10px; color: #d4d4d4;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: 0.08em;
        }}
        .sp-legend li.divider {{
            padding-top: 12px; margin-top: 0;
            border-top: 1px solid #222;
        }}
        .ld-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
        .ld-ring {{
            width: 14px; height: 14px; border-radius: 50%;
            border: 1px solid #10b981;
            background: rgba(16,185,129,0.08);
            flex-shrink: 0;
            display: flex; align-items: center; justify-content: center;
        }}
        .ld-ring-inner {{ width: 4px; height: 4px; border-radius: 50%; background: #10b981; }}
        .sp-footer {{
            padding: 12px 20px;
            border-top: 1px solid #222;
            font-size: 9px; font-family: 'JetBrains Mono', monospace;
            color: #404040; text-transform: uppercase; letter-spacing: 0.15em;
            text-align: center;
        }}
        
        /* ── LEAFLET POPUP & CARDS ────────────────────────────────────────── */
        .leaflet-popup-content-wrapper {{
            background: #0a0a0a !important;
            border: 1px solid #333 !important;
            color: #e5e5e5 !important;
            border-radius: 0 !important;
            padding: 0 !important;
            box-shadow: 0 25px 50px rgba(0,0,0,0.8), 0 0 0 1px #222 !important;
        }}
        .leaflet-popup-tip-container {{ display: none !important; }}
        
        .lead-card {{ width: 310px; font-family: 'Inter', sans-serif; }}
        .lead-card-header {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 10px 14px; border-bottom: 1px solid #222; background: #0d0d0d;
        }}
        .lead-card-ref {{
            font-size: 9px; font-family: 'JetBrains Mono', monospace;
            text-transform: uppercase; letter-spacing: 0.15em; color: #737373;
            display: flex; align-items: center; gap: 6px;
        }}
        .ref-dot {{ width: 5px; height: 5px; transform: rotate(45deg); background: #ffffff; }}
        .ref-dot.hot {{ background: #3b82f6; }}
        .lead-badge {{
            font-size: 8px; font-family: 'JetBrains Mono', monospace;
            letter-spacing: 0.15em; text-transform: uppercase;
            padding: 3px 8px;
            border: 1px solid rgba(59,130,246,0.4);
            color: #3b82f6; background: rgba(59,130,246,0.05);
        }}
        .hide-labels .probe-count-label {{ display: none !important; }}
        
        .lead-card-body {{ padding: 14px; }}
        .lead-card h3 {{
            margin: 0 0 10px 0; font-size: 14px; font-weight: 600;
            color: #ffffff; line-height: 1.35;
        }}
        
        .carousel-box {{ position: relative; margin: 0 0 12px 0; overflow: hidden; border: 1px solid #222; }}
        .carousel-img {{ width: 100%; height: 140px; object-fit: cover; display: block; filter: brightness(0.9); }}
        .carousel-bar {{
            position: absolute; bottom: 0; left: 0; right: 0;
            display: flex; justify-content: space-between; align-items: center;
            padding: 6px 10px; background: rgba(0,0,0,0.8);
        }}
        .carousel-btn {{
            background: #3b82f6; color: #ffffff; border: none;
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; letter-spacing: 0.1em; font-weight: 700;
            padding: 4px 10px; cursor: pointer; transition: background 0.2s;
        }}
        .carousel-btn:hover {{ background: #2563eb; }}
        .carousel-count {{ font-size: 9px; font-family: 'JetBrains Mono', monospace; color: #737373; }}
        
        .lead-data-grid {{
            display: grid; grid-template-columns: 1fr 1fr;
            gap: 1px; background: #1a1a1a;
            border: 1px solid #222; margin-bottom: 12px;
        }}
        .lead-data-cell {{ background: #0a0a0a; padding: 8px 10px; }}
        .lead-data-cell.full {{ grid-column: 1 / -1; }}
        .data-lbl {{
            font-size: 8px; text-transform: uppercase;
            letter-spacing: 0.15em; color: #525252;
            font-family: 'JetBrains Mono', monospace; margin-bottom: 3px;
        }}
        .data-val {{ font-size: 11px; font-family: 'JetBrains Mono', monospace; color: #d4d4d4; word-break: break-all; }}
        
        .lead-actions {{ display: flex; gap: 6px; }}
        .btn-action {{
            flex: 1; text-align: center; padding: 8px 0;
            font-size: 9px; font-family: 'JetBrains Mono', monospace;
            font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase;
            text-decoration: none; display: inline-block;
            transition: all 0.2s ease; cursor: pointer; border: none;
        }}
        .btn-wa {{ background: #ffffff; color: #000000 !important; }}
        .btn-wa:hover {{ background: #d4d4d4; }}
        .btn-maps {{ background: transparent; color: #ffffff !important; border: 1px solid #333 !important; }}
        .btn-maps:hover {{ background: #111; }}

        .probe-count-label {{
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            pointer-events: none;
        }}
        .probe-inner-id {{ font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 700; line-height: 1; }}
        .probe-biz-count {{
            font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 700;
            color: #00ff88; text-shadow: 0 0 4px #000, 0 0 4px #000;
            margin-top: 4px; white-space: nowrap;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <!-- ── SIDE PANEL ─────────────────────────────────────────────────── -->
    <div class="side-panel">
        <div class="sp-header">
            <div class="sp-brand">
                <div class="sp-hex"></div>
                <div class="sp-title">MESLATT <span>OS</span></div>
            </div>
            <div class="sp-sub">Tactical Intelligence Grid</div>
        </div>

        <div class="sp-controls">
            <div>
                <div class="sp-control-lbl">Search Business / Address</div>
                <input type="text" id="search-input" class="sp-input" placeholder="FILTER BY NAME..." oninput="filterLeads()">
            </div>
            <div>
                <div class="sp-control-lbl">Lead Status</div>
                <select id="filter-status" class="sp-select" onchange="filterLeads()">
                    <option value="all">ALL LEADS</option>
                    <option value="hot" selected>HOT LEADS ONLY</option>
                    <option value="phase2">PHASE 2 ENRICHED (CDN)</option>
                    <option value="standard">STANDARD PROSPECTS</option>
                </select>
            </div>
            <div>
                <div class="sp-control-lbl">City Filter</div>
                <select id="filter-city" class="sp-select" onchange="filterLeads()">
                    <option value="all">ALL CITIES</option>
                </select>
            </div>
            <div>
                <div class="sp-control-lbl">Niche / Industry</div>
                <select id="filter-niche" class="sp-select" onchange="filterLeads()">
                    <option value="all">ALL CATEGORIES</option>
                </select>
            </div>
            <div>
                <div class="sp-control-lbl">Priority Tier</div>
                <select id="filter-tier" class="sp-select" onchange="filterLeads()">
                    <option value="all">ALL TIERS</option>
                    <option value="1">TIER 1 (HIGH BNAI / WHALES)</option>
                    <option value="2">TIER 2 (STANDARD)</option>
                </select>
            </div>
        </div>

        <div class="sp-metrics">
            <div>
                <div class="sp-metric-lbl">Rendered Leads</div>
                <div class="sp-metric-val" id="metric-rendered">0</div>
            </div>
            <div>
                <div class="sp-metric-lbl">Hot Leads (Total)</div>
                <div class="sp-metric-val" style="color: #3b82f6;">{hot_leads_count}</div>
            </div>
        </div>

        <div class="sp-legend">
            <div class="sp-legend-title">Node Classification</div>
            <ul>
                <li>
                    <div class="ld-dot" style="background:#d946ef;box-shadow:0 0 8px rgba(217,70,239,0.8);"></div>
                    PHASE 2 ENRICHED (CDN)
                </li>
                <li>
                    <div class="ld-dot" style="background:#00e1ff;box-shadow:0 0 8px rgba(0,225,255,0.8);"></div>
                    QUALIFIED HOT LEAD
                </li>
                <li>
                    <div class="ld-dot" style="background:#ffffff;box-shadow:0 0 6px rgba(255,255,255,0.6);"></div>
                    STANDARD PROSPECT
                </li>
                <li>
                    <div class="ld-dot" style="background:#ffea00;box-shadow:0 0 8px rgba(255,234,0,0.8);"></div>
                    SCANNED PROBE
                </li>
                <li>
                    <div class="ld-dot" style="background:#ff0055;box-shadow:0 0 8px rgba(255,0,85,0.8);"></div>
                    PENDING RADAR PROBE
                </li>
                <li class="divider">
                    <div class="ld-ring"><div class="ld-ring-inner"></div></div>
                    INEGI DENSITY HEXAGON
                </li>
            </ul>
        </div>

        <div class="sp-footer">PIPELINE V4 // SECURE CONNECTION</div>
    </div>

    <script>
        var map = L.map('map', {{
            preferCanvas: true,
            zoomControl: false,
            worldCopyJump: true
        }}).setView([20.5888, -100.3899], 12);

        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '&copy; OpenStreetMap &copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 19
        }}).addTo(map);

        const clustersData = {json.dumps(clusters_data, ensure_ascii=False)};
        const leadsData = {json.dumps(leads_data, ensure_ascii=False)};
        const scannedProbes = {json.dumps(scanned_probes_list, ensure_ascii=False)};
        
        // Populate City & Niche Dropdowns dynamically
        const citySet = new Set();
        const nicheSet = new Set();

        Object.keys(clustersData).forEach(c => citySet.add(c));
        Object.values(leadsData).forEach(lead => {{
            if (lead.primary_type) nicheSet.add(lead.primary_type);
        }});

        const citySelect = document.getElementById('filter-city');
        Array.from(citySet).sort().forEach(city => {{
            const opt = document.createElement('option');
            opt.value = city.toLowerCase();
            opt.innerText = city.toUpperCase();
            citySelect.appendChild(opt);
        }});

        const nicheSelect = document.getElementById('filter-niche');
        Array.from(nicheSet).sort().forEach(niche => {{
            const opt = document.createElement('option');
            opt.value = niche.toLowerCase();
            opt.innerText = niche.replace(/_/g, ' ').toUpperCase();
            nicheSelect.appendChild(opt);
        }});

        // Global Photo Carousel
        window.photoIndices = {{}};
        window.changeLeadPhoto = function(pid, direction) {{
            const lead = leadsData[pid];
            if (!lead || !lead.photos || lead.photos.length === 0) return;
            if (window.photoIndices[pid] === undefined) window.photoIndices[pid] = 0;
            
            window.photoIndices[pid] = (window.photoIndices[pid] + direction + lead.photos.length) % lead.photos.length;
            const idx = window.photoIndices[pid];
            
            const imgEl = document.getElementById('img_' + pid);
            const countEl = document.getElementById('cnt_' + pid);
            if (imgEl) imgEl.src = lead.photos[idx];
            if (countEl) countEl.innerText = (idx + 1) + ' / ' + lead.photos.length;
        }};

        // 1. Render Commercial Clusters
        Object.keys(clustersData).forEach(city => {{
            const cData = clustersData[city];
            const allClusters = cData.all_clusters || [];

            allClusters.forEach(cl => {{
                if (cl.boundary) {{
                    const count = cl.establishment_count || 1;
                    const fillOp = Math.min(0.85, Math.max(0.10, count / 80));
                    const breakdown = cl.niche_breakdown || {{}};
                    const batches = cl.active_batches || [];
                    const nicheKeys = Object.keys(breakdown).sort((a, b) => breakdown[b] - breakdown[a]);
                    let nicheRowsHtml = '';
                    if (nicheKeys.length > 0) {{
                        nicheRowsHtml = '<div style="margin-top:6px;font-size:11px;line-height:1.8;">' +
                            nicheKeys.map(n => `<span style="color:#065f46;font-weight:600;">${{n.replace(/_/g,' ')}}</span><span style="color:#111827;">: ${{breakdown[n]}}</span><br>`).join('') +
                            '</div>' + `<div style="margin-top:4px;font-size:10px;color:#5b21b6;">API Batches: [${{batches.join(', ')}}]</div>`;
                    }}

                    L.polygon(cl.boundary, {{
                        color: cl.phase2_done ? 'rgba(249,115,22,0.8)' : cl.phase1_done ? 'rgba(234,179,8,0.7)' : 'rgba(16,185,129,0.55)',
                        fillColor: '#10b981',
                        fillOpacity: fillOp,
                        weight: 1.5,
                        interactive: true
                    }}).bindTooltip(
                        '<div style="min-width:190px;max-width:260px;">' +
                        `<b style="font-size:12px;color:#111827;">${{cl.city}} — H3 Cluster</b><br>` +
                        `<code style="background:#eee;color:#e74c3c;padding:2px;border-radius:3px;font-size:11px;">ID: ${{cl.h3_index}}</code><br>` +
                        `<span style="color:#374151;">Total businesses: </span><b style="color:#111827;">${{cl.establishment_count}}</b>` +
                        nicheRowsHtml + '</div>',
                        {{sticky: true, maxWidth: 280}}
                    ).addTo(map);
                }} else {{
                    const radius = Math.min(1500, Math.max(300, cl.establishment_count * 12));
                    L.circle([cl.centroid_lat, cl.centroid_lng], {{
                        color: cl.phase2_done ? 'rgba(249,115,22,0.8)' : cl.phase1_done ? 'rgba(234,179,8,0.7)' : 'rgba(16,185,129,0.55)',
                        fillColor: 'rgba(16,185,129,0.08)',
                        fillOpacity: 1,
                        weight: 1.5,
                        radius: radius,
                        interactive: false
                    }}).bindTooltip(`<b>${{cl.city}} — Cluster</b><br>Businesses: ${{cl.establishment_count}}`).addTo(map);
                }}
            }});
        }});

        // 2. Render Radar Probes
        Object.keys(clustersData).forEach(city => {{
            const cData = clustersData[city];
            const probes = cData.radar_probes || [];

            probes.forEach((p, i) => {{
                const probeId = city + '_' + p.centroid_lat + '_' + p.centroid_lng;
                const isScanned = scannedProbes.includes(probeId);
                const probeDotClr = isScanned ? '#ffea00' : '#ff0055';
                const lblStatus = isScanned ? '(Scanned)' : '(Pending)';
                const txtColor = isScanned ? '#000000' : '#ffffff';

                L.marker([p.centroid_lat, p.centroid_lng], {{
                    icon: L.divIcon({{
                        className: 'probe-count-label',
                        html: `<div class="probe-inner-id" style="color: ${{txtColor}};">${{i+1}}</div><div class="probe-biz-count">${{p.establishment_count}} biz</div>`,
                        iconSize: [60, 40],
                        iconAnchor: [30, 20]
                    }}),
                    interactive: false
                }}).addTo(map);
                
                L.circleMarker([p.centroid_lat, p.centroid_lng], {{
                    radius: isScanned ? 8 : 6,
                    color: isScanned ? '#000000' : '#ffffff',
                    weight: 1.5,
                    fillColor: probeDotClr,
                    fillOpacity: 0.9,
                    interactive: true
                }}).bindTooltip(`
                    <div style="text-align:center;">
                        <b style="color:${{probeDotClr}}">Probe #${{i+1}} (${{city}})</b><br>
                        ${{p.establishment_count}} businesses detected<br>
                        <span style="color:#a3a3a3;font-size:10px;">${{lblStatus}}</span>
                    </div>
                `, {{direction: 'top'}}).addTo(map);
            }});
        }});

        // 3. Multi-Filter Leads Rendering
        const leadsLayerGroup = L.markerClusterGroup({{ disableClusteringAtZoom: 16, maxClusterRadius: 50 }}).addTo(map);

        window.filterLeads = function() {{
            leadsLayerGroup.clearLayers();
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            const statusFilter = document.getElementById('filter-status').value;
            const cityFilter = document.getElementById('filter-city').value;
            const nicheFilter = document.getElementById('filter-niche').value;
            const tierFilter = document.getElementById('filter-tier').value;

            let renderedCount = 0;

            Object.keys(leadsData).forEach(pid => {{
                const lead = leadsData[pid];
                const name = (lead.business_name || "").toLowerCase();
                const address = (lead.address || "").toLowerCase();
                const cityZone = (lead.city_zone || "").toLowerCase();
                const pType = (lead.primary_type || "").toLowerCase();
                const isHot = !!lead.is_hot_lead;
                const isP2 = !!lead.phase2_done;
                const tier = String(lead.hot_lead_tier || 0);

                // Text search
                if (query !== "" && !name.includes(query) && !address.includes(query)) return;

                // Status filter
                if (statusFilter === 'hot' && !isHot) return;
                if (statusFilter === 'phase2' && !isP2) return;
                if (statusFilter === 'standard' && isHot) return;

                // City filter
                if (cityFilter !== 'all' && cityZone !== cityFilter) return;

                // Niche filter
                if (nicheFilter !== 'all' && pType !== nicheFilter) return;

                // Tier filter
                if (tierFilter !== 'all' && tier !== tierFilter) return;

                if (lead.lat && lead.lng) {{
                    renderedCount++;
                    const photos = (lead.photos && lead.photos.length > 0) ? lead.photos : ['https://via.placeholder.com/800x400/0a0a0a/3b82f6?text=PHOTO+PENDING'];
                    const primaryImg = photos[0];
                    const badgeText = isP2 ? 'PHASE 2 ENRICHED' : isHot ? `HOT LEAD (T${{lead.hot_lead_tier || 1}})` : 'STANDARD';
                    const refDotClass = isHot ? 'hot' : '';

                    const carouselHtml = (isHot || isP2) ? `
                        <div class="carousel-box">
                            <img id="img_${{pid}}" src="${{primaryImg}}" class="carousel-img" alt="Commercial Photo"/>
                            <div class="carousel-bar">
                                <button class="carousel-btn" onclick="window.changeLeadPhoto('${{pid}}', -1)">◄ PREV</button>
                                <span id="cnt_${{pid}}" class="carousel-count">${{photos.length > 1 ? '1 / ' + photos.length : '1 / 1'}}</span>
                                <button class="carousel-btn" onclick="window.changeLeadPhoto('${{pid}}', 1)">NEXT ►</button>
                            </div>
                        </div>
                    ` : '';

                    const cleanPhone = (lead.phone || '').replace(/[^0-9]/g, '');
                    const waUrl = `https://api.whatsapp.com/send?phone=${{cleanPhone}}&text=Hello,%20I%20saw%20your%20business%20on%20Google%20Maps`;
                    const mapsUrl = lead.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${{lead.lat}},${{lead.lng}}`;
                    const shortId = pid.substring(0, 8).toUpperCase();

                    const popupHtml = `
                        <div class="lead-card">
                            <div class="lead-card-header">
                                <div class="lead-card-ref">
                                    <div class="ref-dot ${{refDotClass}}"></div>
                                    REF: ${{shortId}}
                                </div>
                                <span class="lead-badge">${{badgeText}}</span>
                            </div>
                            <div class="lead-card-body">
                                <h3>${{lead.business_name}}</h3>
                                <div style='margin-bottom:10px;'><span style='background:#3b82f6;color:white;padding:3px 8px;border-radius:4px;font-size:10px;text-transform:uppercase;font-weight:bold;letter-spacing:1px;'>${{lead.primary_type || 'BUSINESS'}}</span></div>
                                ${{carouselHtml}}
                                <div class="lead-data-grid">
                                    <div class="lead-data-cell">
                                        <div class="data-lbl">Rating</div>
                                        <div class="data-val">${{lead.rating || 'N/A'}} ★ (${{lead.reviews_count || 0}})</div>
                                    </div>
                                    <div class="lead-data-cell">
                                        <div class="data-lbl">Phone</div>
                                        <div class="data-val">+${{cleanPhone || '—'}}</div>
                                    </div>
                                    <div class="lead-data-cell">
                                        <div class="data-lbl">Score</div>
                                        <div class="data-val" style="color:#22c55e;">${{lead.phase2_score || 0.0}} pts</div>
                                    </div>
                                    <div class="lead-data-cell">
                                        <div class="data-lbl">Price</div>
                                        <div class="data-val" style="color:#fbbf24;">${{ lead.price_level === 'PRICE_LEVEL_INEXPENSIVE' ? '$' : lead.price_level === 'PRICE_LEVEL_MODERATE' ? '$$' : lead.price_level === 'PRICE_LEVEL_EXPENSIVE' ? '$$$' : lead.price_level === 'PRICE_LEVEL_VERY_EXPENSIVE' ? '$$$$' : '—' }}</div>
                                    </div>
                                    <div class="lead-data-cell full">
                                        <div class="data-lbl">Address</div>
                                        <div class="data-val">${{lead.address || 'Pending Phase 2'}}</div>
                                    </div>
                                </div>
                                <div class="lead-actions">
                                    <a href="${{waUrl}}" target="_blank" class="btn-action btn-wa">WhatsApp</a>
                                    <a href="${{mapsUrl}}" target="_blank" class="btn-action btn-maps">Maps</a>
                                </div>
                            </div>
                        </div>
                    `;

                    let dotColor = '#ffffff';
                    let dotBorder = '#52525b';
                    let dotSize = 4;
                    let opac = 0.4;
                    let weight = 1;

                    if (isP2) {{
                        dotColor = '#d946ef';
                        dotBorder = '#4a044e';
                        dotSize = 9;
                        opac = 1.0;
                        weight = 2;
                    }} else if (isHot) {{
                        dotColor = '#00e1ff';
                        dotBorder = '#082f49';
                        dotSize = 6;
                        opac = 0.9;
                        weight = 1.5;
                    }}

                    L.circleMarker([lead.lat, lead.lng], {{
                        radius: dotSize,
                        color: dotBorder,
                        fillColor: dotColor,
                        fillOpacity: opac,
                        weight: weight
                    }}).bindPopup(popupHtml, {{maxWidth: 340}}).addTo(leadsLayerGroup);
                }}
            }});

            document.getElementById('metric-rendered').innerText = renderedCount;
        }};

        filterLeads();

        map.on('zoomend', function() {{
            if (map.getZoom() < 14) {{
                document.getElementById('map').classList.add('hide-labels');
            }} else {{
                document.getElementById('map').classList.remove('hide-labels');
            }}
        }});
        map.fire('zoomend');
    </script>
</body>
</html>"""

    with open(FOG_MAP_HTML, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ Generated Pipeline Fog of War Map at:\n   {FOG_MAP_HTML}")

if __name__ == '__main__':
    generate_fog_map_html()
