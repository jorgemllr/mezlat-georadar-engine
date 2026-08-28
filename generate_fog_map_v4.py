"""
Fog of War Map V4 Generator (Lead Inspector & Direct Google Maps Deep Links)
=============================================================================

Generates `fog_of_war_map_v4.html` featuring:
1. 🟢 **Glow Green Markers:** Hot Leads with category-matching CDN photos.
2. 📸 **Interactive Photo Carousel Navigation:** Buttons ◄ Prev and Next ► to cycle through all 3 HD CDN photos.
3. 🗺️ **Exact Google Maps Deep Links:** Button opens the exact Google Maps place deep link (`google_maps_url`).
4. 💬 **WhatsApp API Direct Chat:** Link opens `api.whatsapp.com/send?phone=...` with valid phone number.
5. ⚡ **Ultra-High Contrast Buttons:** Crisp black text on bright green WhatsApp button, bold white text on blue Google Maps button.
6. 🔵 **Restored Global Layers:** All INEGI density circles and radar probes across Mexico.

V4 changes from V3:
  - Reads data from `allocation_v4/` instead of `allocation_v3/`.
  - Uses `actual_probes` field (placed by Step 2) for rendering probe markers.
"""

import json
from pathlib import Path

BASE_DIR             = Path(__file__).resolve().parent.parent.parent
DATASETS_DIR         = BASE_DIR / "Datasets"
V4_DIR               = BASE_DIR / "scripts" / "allocation_v4"
ALLOCATION_V4_FILE   = V4_DIR / "api_budget_allocation_v4.json"
CLUSTERS_V4_FILE     = V4_DIR / "commercial_clusters_v4.json"
PROCESSED_LEADS_FILE = DATASETS_DIR / "processed_leads_v4.json"   # Updated by pipeline after Phase 2 runs
HTML_OUTPUT_V4       = V4_DIR / "fog_of_war_map_v4.html"

def generate_fog_map_v4_html():
    print("🚀 Generating Fog of War Map V4 (Lead Inspector & Google Maps Deep Links)...")

    clusters_data = {}
    if CLUSTERS_V4_FILE.exists():
        with open(CLUSTERS_V4_FILE, 'r', encoding='utf-8') as f:
            clusters_data = json.load(f)

    allocation_data = []
    if ALLOCATION_V4_FILE.exists():
        with open(ALLOCATION_V4_FILE, 'r', encoding='utf-8') as f:
            allocation_data = json.load(f).get("cities", [])

    leads_data = {}
    if PROCESSED_LEADS_FILE.exists():
        try:
            with open(PROCESSED_LEADS_FILE, 'r', encoding='utf-8') as f:
                leads_data = json.load(f).get("leads", {})
        except Exception:
            pass

    scanned_probes = []
    SCANNED_PROBES_FILE = DATASETS_DIR / "scanned_probes_v4.json"
    if SCANNED_PROBES_FILE.exists():
        try:
            with open(SCANNED_PROBES_FILE, 'r', encoding='utf-8') as f:
                scanned_probes = json.load(f)
        except Exception:
            pass

    hot_leads_count = sum(1 for lead in leads_data.values() if lead.get('is_hot_lead'))
    std_leads_count = len(leads_data) - hot_leads_count

    # ── INJECT PHASE STATUS INTO CLUSTERS ──
    import h3
    scanned_set = set(scanned_probes)
    phase2_leads = [ld for ld in leads_data.values() if ld.get("photos")]
    
    for city, cData in clusters_data.items():
        for cl in cData.get("all_clusters", []):
            # A hex is phase 1 done if its ID is in scanned_probes
            phase1 = False
            for p in cl.get("radar_probes", []):
                pid = f"{cl['city']}_{p['centroid_lat']}_{p['centroid_lng']}"
                if pid in scanned_set:
                    phase1 = True
                    break
            
            # Phase 2 done if any lead with photos falls into this hex
            phase2 = False
            for ld in phase2_leads:
                if h3.latlng_to_cell(ld["lat"], ld["lng"], 8) == cl["h3_index"]:
                    phase2 = True
                    break
                    
            cl["phase1_done"] = phase1
            cl["phase2_done"] = phase2

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>MESLATT V4 - Tactical Fog of War & Lead Inspector</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/h3-js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">

    <style>
        *, *::before, *::after {{ box-sizing: border-box; }}
        body {{ margin: 0; padding: 0; font-family: 'Inter', sans-serif; background-color: #050505; color: #e5e5e5; }}
        
        /* ── MAP ──────────────────────────────────────────────────────────── */
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100vh; background: #030303; }}
        
        /* Dark grid background overlay on top of tiles */
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
        /* Vignette */
        #map::before {{
            content: '';
            position: absolute; inset: 0; pointer-events: none; z-index: 400;
            background: radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.75) 100%);
        }}
        
        /* ── SIDE PANEL ───────────────────────────────────────────────────── */
        .side-panel {{
            position: absolute; top: 0; left: 0; z-index: 1000;
            height: 100vh; width: 280px;
            background: rgba(5,5,5,0.96); backdrop-filter: blur(20px);
            border-right: 1px solid #222;
            display: flex; flex-direction: column;
        }}
        .sp-header {{
            padding: 24px;
            border-bottom: 1px solid #222;
        }}
        .sp-brand {{
            display: flex; align-items: center; gap: 10px; margin-bottom: 6px;
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
        .sp-metrics {{
            padding: 20px 24px;
            border-bottom: 1px solid #222;
            display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
        }}
        .sp-metric-lbl {{
            font-size: 9px; text-transform: uppercase;
            letter-spacing: 0.15em; color: #525252;
            font-family: 'JetBrains Mono', monospace;
            margin-bottom: 4px;
        }}
        .sp-metric-val {{
            font-size: 22px; font-weight: 300; color: #ffffff;
            font-family: 'JetBrains Mono', monospace;
            line-height: 1;
        }}
        .sp-metric-val small {{ font-size: 13px; color: #525252; }}
        .sp-legend {{
            padding: 20px 24px;
            flex: 1;
        }}
        .sp-legend-title {{
            font-size: 9px; font-weight: 600; color: #737373;
            text-transform: uppercase; letter-spacing: 0.2em;
            font-family: 'JetBrains Mono', monospace;
            margin-bottom: 20px;
        }}
        .sp-legend ul {{ list-style: none; padding: 0; margin: 0; }}
        .sp-legend li {{
            display: flex; align-items: center; gap: 14px;
            margin-bottom: 14px;
            font-size: 10px; color: #d4d4d4;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: 0.08em;
        }}
        .sp-legend li.divider {{
            padding-top: 14px; margin-top: 0;
            border-top: 1px solid #222;
        }}
        .ld-dot {{
            width: 8px; height: 8px; border-radius: 50%;
            flex-shrink: 0;
        }}
        .ld-diamond {{
            width: 8px; height: 8px;
            transform: rotate(45deg);
            flex-shrink: 0;
        }}
        .ld-ring {{
            width: 14px; height: 14px; border-radius: 50%;
            border: 1px solid #3b82f6;
            background: rgba(59,130,246,0.08);
            flex-shrink: 0;
            display: flex; align-items: center; justify-content: center;
        }}
        .ld-ring-inner {{
            width: 4px; height: 4px; border-radius: 50%;
            background: #3b82f6; opacity: 0.5;
        }}
        .sp-footer {{
            padding: 14px 24px;
            border-top: 1px solid #222;
            font-size: 9px; font-family: 'JetBrains Mono', monospace;
            color: #404040; text-transform: uppercase; letter-spacing: 0.15em;
            text-align: center;
        }}
        
        /* ── LEAFLET POPUP ────────────────────────────────────────────────── */
        .leaflet-popup-content-wrapper {{
            background: #0a0a0a !important;
            border: 1px solid #333 !important;
            color: #e5e5e5 !important;
            border-radius: 0 !important;
            padding: 0 !important;
            box-shadow: 0 25px 50px rgba(0,0,0,0.8), 0 0 0 1px #222 !important;
        }}
        .leaflet-popup-tip-container {{ display: none !important; }}
        
        /* ── LEAD CARD (inside popup) ─────────────────────────────────────── */
        .lead-card {{ width: 310px; font-family: 'Inter', sans-serif; }}
        .lead-card-header {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 10px 14px;
            border-bottom: 1px solid #222;
            background: #0d0d0d;
        }}
        .lead-card-ref {{
            font-size: 9px; font-family: 'JetBrains Mono', monospace;
            text-transform: uppercase; letter-spacing: 0.15em; color: #737373;
            display: flex; align-items: center; gap: 6px;
        }}
        .ref-dot {{
            width: 5px; height: 5px;
            transform: rotate(45deg); background: #ffffff;
        }}
        .ref-dot.hot {{ background: #3b82f6; }}
        .lead-badge {{
            font-size: 8px; font-family: 'JetBrains Mono', monospace;
            letter-spacing: 0.15em; text-transform: uppercase;
            padding: 3px 8px;
            border: 1px solid rgba(59,130,246,0.4);
            color: #3b82f6; background: rgba(59,130,246,0.05);
        }}
        .badge-api {{ color: #22c55e; border: 1px solid rgba(34,197,94,0.25); }}
        .badge-hof {{ color: #3b82f6; border: 1px solid rgba(59,130,246,0.25); }}
        .city-name {{ font-weight: 600; color: #ffffff; }}

        /* Performance Optimization: Hide labels when zoomed out */
        .hide-labels .probe-count-label {{ display: none !important; }}
        
        .lead-card-body {{ padding: 14px; }}
        .lead-card h3 {{
            margin: 0 0 10px 0; font-size: 14px; font-weight: 600;
            color: #ffffff; line-height: 1.35; letter-spacing: 0.01em;
        }}
        
        /* Carousel */
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
        .carousel-count {{
            font-size: 9px; font-family: 'JetBrains Mono', monospace;
            color: #737373;
        }}
        
        /* Data grid */
        .lead-data-grid {{
            display: grid; grid-template-columns: 1fr 1fr;
            gap: 1px; background: #1a1a1a;
            border: 1px solid #222; margin-bottom: 12px;
        }}
        .lead-data-cell {{
            background: #0a0a0a; padding: 10px 12px;
        }}
        .lead-data-cell.full {{ grid-column: 1 / -1; }}
        .data-lbl {{
            font-size: 8px; text-transform: uppercase;
            letter-spacing: 0.15em; color: #525252;
            font-family: 'JetBrains Mono', monospace;
            margin-bottom: 4px;
        }}
        .data-val {{
            font-size: 11px; font-family: 'JetBrains Mono', monospace;
            color: #d4d4d4; word-break: break-all;
        }}
        
        /* Action buttons */
        .lead-actions {{ display: flex; gap: 6px; }}
        .btn-action {{
            flex: 1; text-align: center; padding: 10px 0;
            font-size: 9px; font-family: 'JetBrains Mono', monospace;
            font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase;
            text-decoration: none; display: inline-block;
            transition: all 0.2s ease; cursor: pointer; border: none;
        }}
        .btn-wa {{
            background: #ffffff; color: #000000 !important;
        }}
        .btn-wa:hover {{ background: #d4d4d4; }}
        .btn-maps {{
            background: transparent; color: #ffffff !important;
            border: 1px solid #333 !important;
        }}
        .btn-maps:hover {{ background: #111; }}
        
        /* Probe number label */
        .probe-label {{
            background: transparent;
            border: none; box-shadow: none;
            color: #ffffff;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700; font-size: 10px;
            text-shadow: 0 0 4px #000, 0 0 8px #000;
        }}
        
        /* Hide default Leaflet controls branding */
        .leaflet-control-attribution {{ display: none !important; }}
        .leaflet-control-zoom a {{
            background: #0a0a0a !important; border-color: #222 !important;
            color: #737373 !important; font-family: 'JetBrains Mono', monospace !important;
        }}
        .leaflet-control-zoom a:hover {{ background: #111 !important; color: #ffffff !important; }}

        /* ── PREMIUM MARKER GLOW ────────────────────────────────────────── */
        /*
         * PERFORMANCE NOTE:
         * CSS filter:drop-shadow + animation on 100s of elements causes repaint lag.
         * Strategy: static glow only on leads (circleMarker via SVG class),
         * lightweight ping animation ONLY on probe markers (max ~13/city).
         */

        /* Static SVG glow — applied to Leaflet circleMarker SVG paths */
        .marker-blue  {{ filter: drop-shadow(0 0 5px rgba(59,130,246,0.85)); }}
        .marker-white {{ filter: drop-shadow(0 0 4px rgba(255,255,255,0.7)); }}

        /* Probe ping wrapper — only used on the small set of probe divIcons */
        .ping-wrapper {{ position: relative; width: 0; height: 0; }}
        .ping-ring {{
            position: absolute;
            border-radius: 50%;
            transform: translate(-50%, -50%);
            animation: ring-ping 3s cubic-bezier(0,0,0.2,1) infinite;
            pointer-events: none;
            will-change: transform, opacity;
        }}
        .ping-dot {{
            position: absolute;
            border-radius: 50%;
            transform: translate(-50%, -50%);
        }}
        .ping-number {{
            position: absolute;
            transform: translate(-50%, -50%);
            font-family: 'JetBrains Mono', monospace;
            font-size: 8px; font-weight: 700;
            line-height: 1; pointer-events: none;
            color: #ffffff;
        }}
        /* Amber probes: black text for contrast */
        .probe-amber .ping-number {{ color: #000000; }}

        /* Probe dot glow — static, applied to .ping-dot */
        .probe-red   {{ filter: drop-shadow(0 0 6px rgba(244,63,94,0.9)); }}
        .probe-amber {{ filter: drop-shadow(0 0 6px rgba(251,191,36,0.9)); }}

        @keyframes ring-ping {{
            0%   {{ transform: translate(-50%,-50%) scale(1);   opacity: 0.6; }}
            70%  {{ transform: translate(-50%,-50%) scale(2.4); opacity: 0; }}
            100% {{ transform: translate(-50%,-50%) scale(2.4); opacity: 0; }}
        }}
        .probe-count-label {{
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            pointer-events: none;
        }}
        .probe-inner-id {{
            font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 700;
            text-shadow: none; line-height: 1; margin-top: 0px;
        }}
        .probe-biz-count {{
            font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 700;
            color: #00ff88; text-shadow: 0 0 4px #000, 0 0 4px #000, 0 0 4px #000;
            margin-top: 6px; white-space: nowrap;
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
            <div class="sp-sub">Sistema de Inteligencia Territorial</div>
        </div>

        <div style="padding: 15px 24px; border-bottom: 1px solid #222;">
            <input type="text" id="search-input" placeholder="Buscar negocio..." 
                   style="width: 100%; padding: 8px 12px; background: #111; color: white; border: 1px solid #333; border-radius: 4px; font-family: 'Inter', sans-serif; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;"
                   oninput="filterLeads()">
        </div>

        <div class="sp-metrics">
            <div>
                <div class="sp-metric-lbl">Leads Activos</div>
                <div class="sp-metric-val">{len(leads_data)}</div>
            </div>
            <div>
                <div class="sp-metric-lbl">Hot Leads</div>
                <div class="sp-metric-val" style="color: #3b82f6;">{hot_leads_count}</div>
            </div>
        </div>

        <div class="sp-legend">
            <div class="sp-legend-title">Clasificación de Nodos</div>
            <ul>
                <li>
                    <div class="ld-dot" style="background:#3b82f6;box-shadow:0 0 8px rgba(59,130,246,0.8);"></div>
                    QUALIFIED HOT LEAD <span style="margin-left:auto;color:#3b82f6;font-weight:700;">({hot_leads_count})</span>
                </li>
                <li>
                    <div class="ld-dot" style="background:#ffffff;box-shadow:0 0 6px rgba(255,255,255,0.6);"></div>
                    STANDARD PROSPECT <span style="margin-left:auto;color:#a3a3a3;font-weight:700;">({std_leads_count})</span>
                </li>
                <li>
                    <div class="ld-dot" style="background:#fbbf24;box-shadow:0 0 8px rgba(251,191,36,0.8);"></div>
                    SCANNED PROBE
                </li>
                <li>
                    <div class="ld-dot" style="background:#f43f5e;box-shadow:0 0 8px rgba(244,63,94,0.8);"></div>
                    PENDING RADAR PROBE
                </li>
                <li class="divider">
                    <div class="ld-ring" style="border-color:#10b981;"><div class="ld-ring-inner" style="background:#10b981;"></div></div>
                    INEGI INFLUENCE RADIUS
                </li>
            </ul>
        </div>

        <div class="sp-footer">V 2.4 // SECURE CONNECTION</div>
    </div>

    <script>
        // Initialize
        var map = L.map('map', {{
            preferCanvas: true,
            zoomControl: false,
            worldCopyJump: true // Allow wrapping for global view
        }}).setView([20.5888, -100.3899], 12);

        // CartoDB Dark Matter Tiles
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 19
        }}).addTo(map);

        const clustersData = {json.dumps(clusters_data, ensure_ascii=False)};
        const leadsData = {json.dumps(leads_data, ensure_ascii=False)};
        const scannedProbes = {json.dumps(scanned_probes, ensure_ascii=False)};
        
        const bounds = [];

        // Global Photo Carousel Navigation Function
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

        // 1. Render ALL INEGI DENUE Commercial Clusters (Emerald Green Hexagons)

        Object.keys(clustersData).forEach(city => {{
            const cData = clustersData[city];
            const allClusters = cData.all_clusters || [];

            allClusters.forEach(cl => {{
                bounds.push([cl.centroid_lat, cl.centroid_lng]);
                if (cl.boundary) {{
                    const count   = cl.establishment_count || 1;
                    const fillOp  = Math.min(0.85, Math.max(0.10, count / 80));

                    // Build niche breakdown for tooltip — simple "name: N" per line.
                    // NOTE: Leaflet tooltips have a LIGHT background — use dark colors only.
                    const breakdown = cl.niche_breakdown || {{}};
                    const batches   = cl.active_batches  || [];
                    const nicheKeys = Object.keys(breakdown).sort((a, b) => breakdown[b] - breakdown[a]);
                    let nicheRowsHtml = '';
                    if (nicheKeys.length > 0) {{
                        nicheRowsHtml =
                            '<div style="margin-top:6px;font-size:11px;line-height:1.8;">' +
                            nicheKeys.map(n =>
                                `<span style="color:#065f46;font-weight:600;">${{n.replace(/_/g,' ')}}</span>` +
                                `<span style="color:#111827;">: ${{breakdown[n]}}</span><br>`
                            ).join('') +
                            '</div>' +
                            `<div style="margin-top:4px;font-size:10px;color:#5b21b6;">` +
                            `API Batches: [${{batches.join(', ')}}]</div>`;
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
                        `<code style=\"background:#eee;color:#e74c3c;padding:2px;border-radius:3px;font-size:11px;\">ID: ${{cl.h3_index}}</code><br>` +
                        `<span style="color:#374151;">Total businesses: </span>` +
                        `<b style="color:#111827;">${{cl.establishment_count}}</b>` +
                        nicheRowsHtml +
                        '</div>',
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

        // 2. Render Captured Business Leads at Exact Google Places Street Coordinates
        
        const leadsLayerGroup = L.layerGroup().addTo(map);
        window.filterLeads = function() {{
            leadsLayerGroup.clearLayers();
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            
            Object.keys(leadsData).forEach(pid => {{
                const lead = leadsData[pid];
                const name = (lead.business_name || "").toLowerCase();
                const address = (lead.address || "").toLowerCase();
                
                if (query !== "" && !name.includes(query) && !address.includes(query)) {{
                    return;
                }}

            if (lead.lat && lead.lng) {{
                bounds.push([lead.lat, lead.lng]);
                const isHot = lead.is_hot_lead;
                const markerColor = isHot ? '#3b82f6' : '#ffffff';
                const radius = isHot ? 10 : 5;

                const photos = (lead.photos && lead.photos.length > 0) ? lead.photos : ['https://via.placeholder.com/800x400/0a0a0a/3b82f6?text=FOTO+PENDIENTE'];
                const primaryImg = photos[0];

                const badgeText = isHot ? 'HOT LEAD' : 'ESTÁNDAR';
                const refDotClass = isHot ? 'hot' : '';

                const carouselHtml = isHot ? `
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
                const waUrl = `https://api.whatsapp.com/send?phone=${{cleanPhone}}&text=Hola,%20vi%20tu%20negocio%20en%20Google%20Maps`;
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
                            <h3>${{lead.business_name}}</h3>\n                            <div style='margin-bottom:12px;'><span style='background:#3b82f6;color:white;padding:3px 8px;border-radius:4px;font-size:10px;text-transform:uppercase;font-weight:bold;letter-spacing:1px;'>${{lead.primary_type || 'BUSINESS'}}</span></div>
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
                                    <div class="data-lbl">Status</div>
                                    <div class="data-val" style="color:#22c55e;">🟢 ACTIVE</div>
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
                                <a href="${{waUrl}}" target="_blank" class="btn-action btn-wa">Contact</a>
                                <a href="${{mapsUrl}}" target="_blank" class="btn-action btn-maps">View on Maps</a>
                            </div>
                        </div>
                    </div>
                `;


                let dotColor, dotBorder, dotSize, opac, weight;
                if (lead.phase2_done) {{
                    dotColor = '#d946ef'; // Vivid Fuchsia/Purple
                    dotBorder = '#4a044e'; // Dark border contrast
                    dotSize = 9;
                    opac = 1.0;
                    weight = 2;
                }} else if (isHot) {{
                    dotColor = '#00e1ff'; // Neon Cyan/Blue
                    dotBorder = '#082f49'; // Dark Blue border
                    dotSize = 6;
                    opac = 0.9;
                    weight = 1.5;
                }} else {{
                    dotColor = '#ffffff'; // White
                    dotBorder = '#52525b';
                    dotSize = 4;
                    opac = 0.4;
                    weight = 1;
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
        }};
        filterLeads();

        
        

        
        // --- VISUAL DEBUG FOR ANTEA HEX ---
        const anteaLat = 20.672822884978952;
        const anteaLng = -100.43959300366863;
        const mayaLat = 20.6727673;
        const mayaLng = -100.4359255;
        
        try {{
            const hexVerts = h3.cellToBoundary('884983ca83fffff');
            if (hexVerts && hexVerts.length > 0) {{
                const v0 = hexVerts[0];
                const v1 = hexVerts[1];
                const midLat = (v0[0] + v1[0]) / 2;
                const midLng = (v0[1] + v1[1]) / 2;

                const lineToVertex = L.polyline([[anteaLat, anteaLng], [v0[0], v0[1]]], {{
                    color: 'white', dashArray: '5, 5', weight: 2
                }}).addTo(map);
                const distVertex = map.distance([anteaLat, anteaLng], [v0[0], v0[1]]).toFixed(1);
                lineToVertex.bindTooltip(`Al vértice: ${{distVertex}}m`, {{permanent: true, direction: 'center', className: 'debug-tooltip'}});

                const lineToApothem = L.polyline([[anteaLat, anteaLng], [midLat, midLng]], {{
                    color: 'white', dashArray: '5, 5', weight: 2
                }}).addTo(map);
                const distApothem = map.distance([anteaLat, anteaLng], [midLat, midLng]).toFixed(1);
                lineToApothem.bindTooltip(`A la apotema: ${{distApothem}}m`, {{permanent: true, direction: 'center', className: 'debug-tooltip'}});

                const lineToMaya = L.polyline([[anteaLat, anteaLng], [mayaLat, mayaLng]], {{
                    color: '#f97316', dashArray: '5, 5', weight: 2
                }}).addTo(map);
                const distMaya = map.distance([anteaLat, anteaLng], [mayaLat, mayaLng]).toFixed(1);
                lineToMaya.bindTooltip(`A Maya: ${{distMaya}}m`, {{permanent: true, direction: 'center', className: 'debug-tooltip'}});
            }}
        }} catch (e) {{
            console.log("H3 not loaded yet or error", e);
        }}
        // ----------------------------------

        const allProbeMarkers = [];

        // 3. Render ALL Radar Probes (Canvas CircleMarkers to prevent lag)

        Object.keys(clustersData).forEach(city => {{
            const cData = clustersData[city];
            const probes = cData.radar_probes || [];

            probes.forEach((p, i) => {{
                bounds.push([p.centroid_lat, p.centroid_lng]);
                const probeId = city + '_' + p.centroid_lat + '_' + p.centroid_lng;
                const isScanned = scannedProbes.includes(probeId);
                const probeDotClr = isScanned ? '#ffea00' : '#ff0055';
                const lblStatus = isScanned ? '(Completada)' : '(Pendiente)';
                
                allProbeMarkers.push({{ latlng: L.latLng(p.centroid_lat, p.centroid_lng), biz: p.establishment_count }});

                const txtColor = isScanned ? '#000000' : '#ffffff';

                // Permanent number overlay
                L.marker([p.centroid_lat, p.centroid_lng], {{
                    icon: L.divIcon({{
                        className: 'probe-count-label',
                        html: `<div class="probe-inner-id" style="color: ${{txtColor}};">${{i+1}}</div><div class="probe-biz-count">${{p.establishment_count}} neg.</div>`,
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
                        <b style="color:${{probeDotClr}}">Sonda #${{i+1}}</b><br>
                        ${{p.establishment_count}} negocios detectados<br>
                        <span style="color:#a3a3a3;font-size:10px;">${{lblStatus}}</span>
                    </div>
                `, {{direction: 'top'}}).addTo(map);
            }});
        }});

        // Forzar vista inicial en Querétaro
        map.setView([20.5888, -100.3899], 12);

        // --- Performance Optimization: Toggle Labels on Zoom ---
        // With 3,000+ probes, labels cause browser saturation at city-level zoom.
        // Only render labels at zoom >= 14 (neighbourhood detail level).
        map.on('zoomend', function() {{
            if (map.getZoom() < 14) {{
                document.getElementById('map').classList.add('hide-labels');
            }} else {{
                document.getElementById('map').classList.remove('hide-labels');
            }}
        }});
        map.fire('zoomend'); // Init

        // --- Box Selection Tool (SHIFT + Drag) ---
        let selectionBox = null;
        let startPoint = null;

        map.on('mousedown', function(e) {{
            if (e.originalEvent.shiftKey) {{
                map.dragging.disable();
                startPoint = e.latlng;
                if (selectionBox) map.removeLayer(selectionBox);
                selectionBox = L.rectangle([startPoint, startPoint], {{color: '#00ff88', weight: 1, fillOpacity: 0.15}}).addTo(map);
            }}
        }});

        map.on('mousemove', function(e) {{
            if (startPoint && selectionBox) {{
                selectionBox.setBounds([startPoint, e.latlng]);
            }}
        }});

        map.on('mouseup', function(e) {{
            if (startPoint && selectionBox) {{
                map.dragging.enable();
                const selBounds = selectionBox.getBounds();
                let count = 0;
                let bizCount = 0;
                allProbeMarkers.forEach(pm => {{
                    if (selBounds.contains(pm.latlng)) {{
                        count++;
                        bizCount += pm.biz;
                    }}
                }});
                startPoint = null;
                alert(`📦 MULTI-SELECT V4\n\n- Probes captured: ${{count}}\n- Estimated businesses: ${{bizCount}} DENUE`);
            }}
        }});

    </script>
</body>
</html>"""

    with open(HTML_OUTPUT_V4, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ Generated Fog of War Map V4 at:\n   {HTML_OUTPUT_V4}")
    return HTML_OUTPUT_V4

if __name__ == "__main__":
    generate_fog_map_v4_html()
