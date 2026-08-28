import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_FILE = BASE_DIR / "Datasets" / "processed_leads_v4.json"
HTML_OUT = BASE_DIR / "scripts" / "allocation_v4" / "crm_pipeline_v4.html"

def generate_crm():
    if not PROCESSED_FILE.exists():
        print("No processed_leads_v4.json found.")
        return
        
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    hot_leads = [L for L in data.get("leads", {}).values() if L.get("is_hot_lead")]
    hot_leads.sort(key=lambda x: x.get("phase2_score", 0), reverse=True)
    
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>MESLATT CRM Pipeline V4</title>
    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background-color: #050505;
            color: #e5e5e5;
            margin: 0;
            padding: 0;
            min-height: 100vh;
        }

        /* ── TOPBAR ─────────────────────────────────────────────────── */
        .topbar {
            display: flex; align-items: center; gap: 14px;
            padding: 20px 40px;
            border-bottom: 1px solid #222;
            background: rgba(5,5,5,0.98);
            position: sticky; top: 0; z-index: 100;
        }
        .topbar-hex {
            width: 18px; height: 18px;
            background: #22c55e;
            clip-path: polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);
            flex-shrink: 0;
        }
        .topbar-title {
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px; font-weight: 700;
            letter-spacing: 0.2em; color: #ffffff;
        }
        .topbar-title span { color: #404040; }
        .topbar-sub {
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; color: #525252;
            letter-spacing: 0.15em; text-transform: uppercase;
            margin-left: 4px;
        }
        .topbar-spacer { flex: 1; }

        /* ── MAIN CONTENT ───────────────────────────────────────────── */
        .main { padding: 40px; }
        
        .search-row {
            display: flex; align-items: center; gap: 16px;
            margin-bottom: 24px;
        }
        .search-box {
            background: #111; border: 1px solid #333; color: #fff;
            padding: 8px 12px; font-family: 'JetBrains Mono', monospace; font-size: 11px;
            outline: none; width: 300px; transition: border-color 0.2s;
        }
        .search-box:focus { border-color: #555; }
        .row-count {
            font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #737373;
        }

        /* ── TABLE ──────────────────────────────────────────────────── */
        .table-wrap {
            border: 1px solid #222;
            background: #0a0a0a;
            overflow-x: auto;
        }
        table {
            width: 100%; border-collapse: collapse; text-align: left;
        }
        th {
            background: #111; padding: 12px 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; font-weight: 700;
            text-transform: uppercase; letter-spacing: 0.15em;
            color: #525252; white-space: nowrap;
        }
        td {
            padding: 12px 16px; border-bottom: 1px solid #111;
            font-size: 12px; color: #d4d4d4; white-space: nowrap;
        }
        tr:hover td { background: rgba(255,255,255,0.02); }
        tr:last-child td { border-bottom: none; }

        /* ── TIER BADGES ────────────────────────────────────────────── */
        .tier-badge {
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; font-weight: 700;
            letter-spacing: 0.15em; padding: 3px 8px; display: inline-block;
        }
        .tier-1 { background: rgba(251,191,36,0.1); color: #fbbf24; border: 1px solid rgba(251,191,36,0.3); }
        .tier-2 { background: rgba(115,115,115,0.1); color: #737373; border: 1px solid #333; }

        /* ── INLINE BADGES ──────────────────────────────────────────── */
        .badge {
            font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 0.1em;
            padding: 3px 8px; display: inline-block;
        }
        .badge-type { color: #3b82f6; border: 1px solid rgba(59,130,246,0.25); }
        .business-name { font-weight: 600; color: #ffffff; }
        
        .btn-call {
            background: rgba(34,197,94,0.1); color: #22c55e; border: 1px solid rgba(34,197,94,0.3);
            font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700;
            text-decoration: none; padding: 4px 10px; display: inline-block; transition: all 0.2s;
        }

        .btn-call:hover { background: rgba(34,197,94,0.2); }
        .btn-map {
            background: rgba(59,130,246,0.1); color: #3b82f6; border: 1px solid rgba(59,130,246,0.3);
            font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700;
            text-decoration: none; padding: 4px 10px; display: inline-block; transition: all 0.2s;
        }
        .btn-map:hover { background: rgba(59,130,246,0.2); }
        .btn-disabled {

            font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700;
            background: #111; color: #525252; border: 1px solid #333;
            padding: 4px 10px; display: inline-block;
        }
    </style>
</head>
<body>
    <!-- TOPBAR -->
    <div class="topbar">
        <div class="topbar-hex"></div>
        <div class="topbar-title">MESLATT <span>OS</span></div>
        <div class="topbar-sub">// Sales CRM Pipeline V4</div>
        <div class="topbar-spacer"></div>
    </div>

    <div class="main">
        <div class="search-row">
            <input type="text" id="searchInput" class="search-box" placeholder="Search business or niche..." onkeyup="filterTable()">
            <span class="row-count" id="rowCount">{HOT_LEADS_COUNT} Total Hot Leads</span>
        </div>

        <!-- TABLE -->
        <div class="table-wrap">
            <table id="crmTable">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Tier</th>
                        <th>Business</th>
                        <th>Map Link</th>
                        <th>Phone</th>
                        <th>Niche</th>
                        <th>Rating / Reviews</th>
                        <th>Priority (Score)</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    rows_html = ""
    for idx, lead in enumerate(hot_leads, 1):
        tier = lead.get("hot_lead_tier", 2)
        score = lead.get("phase2_score", 0)
        tier_class = "tier-1" if tier == 1 else "tier-2"
        tier_label = f"<span class='tier-badge {tier_class}'>NIVEL {tier}</span>"
        
        name = lead.get("business_name", "Unknown")
        niche = lead.get("primary_type", "BUSINESS")
        rating = lead.get("rating", 0)
        reviews = lead.get("reviews_count", 0)
        phone = lead.get("phone", "")
        
        if phone:
            btn = f"<a href='tel:{phone}' class='btn-call'>📞 {phone}</a>"
        else:
            btn = f"<span class='btn-disabled'>PENDING EXTRACTION</span>"
            
        map_url = lead.get("google_maps_url", "#")
        map_btn = f"<a href='{map_url}' target='_blank' class='btn-map'>📍 Open Map</a>" if map_url != "#" else "<span class='btn-disabled'>NO MAP</span>"
            
        rows_html += f"""
                    <tr>
                        <td>{idx}</td>
                        <td>{tier_label}</td>
                        <td class="business-name">{name}</td>
                        <td>{map_btn}</td>
                        <td>{btn}</td>
                        <td><span class="badge badge-type">{niche.upper()}</span></td>
                        <td>{rating} ★ <span style="color:#737373;">({reviews})</span></td>
                        <td style="font-family:'JetBrains Mono', monospace; color: #22c55e;">{score:.2f}</td>
                    </tr>"""
                    
    html = html.replace("{HOT_LEADS_COUNT}", str(len(hot_leads)))
    html += rows_html
    html += """
                </tbody>
            </table>
        </div>
    </div>

    <script>
        function filterTable() {
            const input = document.getElementById("searchInput").value.toLowerCase();
            const rows = document.querySelectorAll("#crmTable tbody tr");
            let visible = 0;
            rows.forEach(row => {
                const textMatch = row.innerText.toLowerCase().includes(input);
                row.style.display = textMatch ? "" : "none";
                if (textMatch) visible++;
            });
            document.getElementById("rowCount").innerText = visible + " filtered leads";
        }
    </script>
</body>
</html>
"""

    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ CRM generado en: {HTML_OUT}")

if __name__ == "__main__":
    generate_crm()
