"""
Allocation Dashboard V4 Generator
===================================

Reads `api_budget_allocation_v4.json` (Step 1 output, updated with actual probe
counts by Step 2) and `commercial_clusters_v4.json` to render the operations
dashboard HTML.

Key V4 differences from V3:
  - Budget state is read from `budget_state.json` (single source of truth),
    not from a legacy `current_api_usage.json`.
  - Table shows both planned probes (max_probes, from Step 1) and actual probes
    placed (actual_probes, written by Step 2) for easy comparison.
  - Phase 1 / Phase 2 status cards reflect real remaining credits this month.
"""

import json
from pathlib import Path

BASE_DIR           = Path(__file__).resolve().parent.parent.parent
V4_DIR             = BASE_DIR / "scripts" / "allocation_v4"
ALLOCATION_V4_FILE = V4_DIR / "api_budget_allocation_v4.json"
CLUSTERS_V4_FILE   = V4_DIR / "commercial_clusters_v4.json"
BUDGET_STATE_FILE  = V4_DIR / "budget_state.json"
DASHBOARD_V4_FILE  = V4_DIR / "allocation_dashboard_v4.html"

def generate_dashboard_v4_html():
    print("🚀 Generating Allocation Dashboard V4...")

    allocation_data = []
    if ALLOCATION_V4_FILE.exists():
        with open(ALLOCATION_V4_FILE, 'r', encoding='utf-8') as f:
            allocation_data = json.load(f).get("cities", [])

    clusters_data = {}
    if CLUSTERS_V4_FILE.exists():
        with open(CLUSTERS_V4_FILE, 'r', encoding='utf-8') as f:
            clusters_data = json.load(f)

    # ── Budget state: read from budget_state.json (V4 source of truth) ────────
    ess_used,  ess_limit  = 0, 10000
    pro_used,  pro_limit  = 0, 5000
    billing_month         = "—"

    if BUDGET_STATE_FILE.exists():
        with open(BUDGET_STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
        ess_used      = state.get("used", {}).get("phase1_calls", 0)
        ess_limit     = state.get("limits", {}).get("phase1_monthly", 10000)
        pro_used      = state.get("used", {}).get("phase2_calls", 0)
        pro_limit     = state.get("limits", {}).get("phase2_monthly", 5000)
        billing_month = state.get("billing_month", "—")
    else:
        # Fallback: parse the spending log directly
        log_file = BASE_DIR / "logs" / "api_spending_log.txt"
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as lf:
                for line in lf:
                    if "PHASE_1_NEARBY_NEW" in line:
                        ess_used += 1
                    elif "PHASE_2_DETAILS" in line:
                        pro_used += 1

    unique_countries = sorted(list(set(c.get('country', '') for c in allocation_data if c.get('country'))))
    country_options = '<option value="">All Countries</option>\n'
    for country in unique_countries:
        country_options += f'            <option value="{country}">{country}</option>\n'

    rows_html = ""
    global_planned_probes = 0
    global_actual_probes  = 0

    for idx, c in enumerate(allocation_data):
        tier = c.get('tier', 'C')
        denue_badge = (
            f"<span class='badge badge-denue'>{c.get('denue_target_count', 0):,} DENUE</span>"
            if c.get('country') == 'Mexico'
            else "<span style='color:#404040;'>—</span>"
        )

        # Step 1 planned value
        planned_probes = c.get('max_probes', 0)
        # Step 2 actual placed value (written by extract_clusters_v4)
        actual_probes  = c.get('actual_probes', planned_probes)

        global_planned_probes += planned_probes
        global_actual_probes  += actual_probes

        phase1    = actual_probes * 3
        phase2    = c.get('phase2_calls', 0)
        eff_total = phase1 + phase2

        rows_html += f"""
        <tr>
            <td style="color:#525252;font-family:'JetBrains Mono',monospace;font-size:10px;">#{idx+1}</td>
            <td><span style="color:#a3a3a3;">{c.get('country', '')}</span></td>
            <td><span class="city-name">{c['city']}</span></td>
            <td><span class="tier-badge tier-{tier}">{tier}</span></td>
            <td>{denue_badge}</td>
            <td><span class="badge badge-hof">{c.get('h_ij_score', 0.5):.3f}</span></td>
            <td style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#737373;">{c.get('final_weight', 0):.3f}</td>
            <td style="font-family:'JetBrains Mono',monospace;line-height:1.3;">
                <div style="font-size:12px;font-weight:600;color:#ffffff;">Planned: {planned_probes}</div>
                <div style="font-size:10px;color:#a78bfa;">Actual: {actual_probes}</div>
            </td>
            <td style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#737373;">{phase1}</td>
            <td style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#737373;">{phase2}</td>
            <td><span class="badge badge-api">{eff_total} calls</span></td>
            <td style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#737373;">{c.get('budget_percentage', '0%')}</td>
        </tr>
        """

    # Use the real 5 % pipeline conversion rate (not the legacy 15 % estimate)

    # --- DYNAMIC PHASE 2 COST CALCULATOR ---
    PROCESSED_LEADS_FILE = DATA_DIR / "processed_leads_v4.json" if 'DATA_DIR' in locals() else BASE_DIR / "Datasets" / "processed_leads_v4.json"
    actual_db_hot_leads = 0
    exact_ph2_cost_usd = 0.0

    if PROCESSED_LEADS_FILE.exists():
        with open(PROCESSED_LEADS_FILE, 'r', encoding='utf-8') as pf:
            leads_data = json.load(pf).get("leads", {})
            for lead in leads_data.values():
                if lead.get('is_hot_lead') and not lead.get('phase2_done'):
                    actual_db_hot_leads += 1
                    photos_to_extract = min(3, lead.get('photo_count', 0))
                    exact_ph2_cost_usd += 0.017 + (photos_to_extract * 0.007)

    # ----------------------------------------

    HOT_LEAD_CONV_RATE  = 0.05
    results_per_probe   = 3 * 20   # 3 batches × 20 max results per Nearby Search
    ph2_calls_per_probe = int(results_per_probe * HOT_LEAD_CONV_RATE)

    global_ph1_calls = global_actual_probes * 3
    global_ph2_calls = global_actual_probes * ph2_calls_per_probe

    ess_remaining = ess_limit - ess_used
    pro_remaining = pro_limit - pro_used

    ph1_balance = ess_remaining - global_ph1_calls
    ph2_balance = pro_remaining - global_ph2_calls


    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MESLATT — Allocation Matrix V4</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{ box-sizing: border-box; }}
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #050505;
            color: #e5e5e5;
            margin: 0;
            padding: 0;
            min-height: 100vh;
        }}

        /* ── TOPBAR ─────────────────────────────────────────────────── */
        .topbar {{
            display: flex; align-items: center; gap: 14px;
            padding: 20px 40px;
            border-bottom: 1px solid #222;
            background: rgba(5,5,5,0.98);
            position: sticky; top: 0; z-index: 100;
        }}
        .topbar-hex {{
            width: 18px; height: 18px;
            background: #3b82f6;
            clip-path: polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);
            flex-shrink: 0;
        }}
        .topbar-title {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px; font-weight: 700;
            letter-spacing: 0.2em; color: #ffffff;
        }}
        .topbar-title span {{ color: #404040; }}
        .topbar-sub {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; color: #525252;
            letter-spacing: 0.15em; text-transform: uppercase;
            margin-left: 4px;
        }}
        .topbar-spacer {{ flex: 1; }}
        .topbar-version {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; color: #404040;
            letter-spacing: 0.15em; text-transform: uppercase;
        }}

        /* ── MAIN CONTENT ───────────────────────────────────────────── */
        .main {{ padding: 40px; }}

        /* ── STATS ROW ──────────────────────────────────────────────── */
        .stats-row {{
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 1px;
            background: #1a1a1a;
            border: 1px solid #222;
            margin-bottom: 32px;
        }}
        .stat-cell {{
            background: #0a0a0a;
            padding: 20px 24px;
        }}
        .stat-lbl {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; text-transform: uppercase;
            letter-spacing: 0.15em; color: #525252;
            margin-bottom: 8px;
        }}
        .stat-val {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 24px; font-weight: 300; color: #ffffff;
            line-height: 1;
        }}
        .stat-val small {{ font-size: 14px; color: #525252; }}

        /* Progress bar */
        .progress-wrap {{ margin-top: 12px; }}
        .progress-track {{
            width: 100%; height: 2px;
            background: #222;
            margin-bottom: 6px;
        }}
        .progress-fill-green {{ height: 100%; background: #22c55e; transition: width 0.4s; }}
        .progress-fill-blue  {{ height: 100%; background: #3b82f6; transition: width 0.4s; }}
        .progress-meta {{
            display: flex; justify-content: space-between;
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; color: #525252;
        }}

        /* ── SEARCH ─────────────────────────────────────────────────── */
        .search-row {{
            margin-bottom: 20px;
            display: flex; align-items: center; gap: 12px;
        }}
        .search-box {{
            background: #0a0a0a;
            border: 1px solid #333;
            color: #e5e5e5;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px; letter-spacing: 0.05em;
            padding: 10px 16px;
            width: 300px; outline: none;
            transition: border-color 0.2s;
        }}
        .search-box::placeholder {{ color: #404040; }}
        .search-box:focus {{ border-color: #3b82f6; }}
        .row-count {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; color: #525252;
            text-transform: uppercase; letter-spacing: 0.1em;
        }}

        /* ── TABLE ──────────────────────────────────────────────────── */
        .table-wrap {{
            border: 1px solid #222;
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #0a0a0a;
        }}
        th {{
            padding: 12px 16px;
            text-align: left;
            background: #050505;
            border-bottom: 1px solid #222;
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; font-weight: 700;
            text-transform: uppercase; letter-spacing: 0.15em;
            color: #525252; white-space: nowrap;
            cursor: pointer; user-select: none;
        }}
        th:hover {{ color: #e5e5e5; }}
        td {{
            padding: 12px 16px;
            border-bottom: 1px solid #111;
            font-size: 12px; color: #d4d4d4;
            white-space: nowrap;
        }}
        tr:hover td {{ background: rgba(255,255,255,0.02); }}
        tr:last-child td {{ border-bottom: none; }}

        /* ── TIER BADGES ────────────────────────────────────────────── */
        .tier-badge {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; font-weight: 700;
            letter-spacing: 0.15em;
            padding: 3px 8px;
            display: inline-block;
        }}
        .tier-S {{ background: rgba(251,191,36,0.1);  color: #fbbf24; border: 1px solid rgba(251,191,36,0.3); }}
        .tier-A {{ background: rgba(167,139,250,0.1); color: #a78bfa; border: 1px solid rgba(167,139,250,0.3); }}
        .tier-B {{ background: rgba(59,130,246,0.1);  color: #60a5fa; border: 1px solid rgba(59,130,246,0.3); }}
        .tier-C {{ background: rgba(115,115,115,0.1); color: #737373; border: 1px solid #333; }}

        /* ── INLINE BADGES ──────────────────────────────────────────── */
        .badge {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px; letter-spacing: 0.1em;
            padding: 3px 8px; display: inline-block;
        }}
        .badge-denue {{ color: #fbbf24; border: 1px solid rgba(251,191,36,0.25); }}
        .badge-api   {{ color: #22c55e; border: 1px solid rgba(34,197,94,0.25); }}
        .badge-hof   {{ color: #3b82f6; border: 1px solid rgba(59,130,246,0.25); }}
        .city-name   {{ font-weight: 600; color: #ffffff; }}
    </style>
</head>
<body>
    <!-- TOPBAR -->
    <div class="topbar">
        <div class="topbar-hex"></div>
        <div class="topbar-title">MESLATT <span>OS</span></div>
        <div class="topbar-sub">// Allocation Matrix V4</div>
        <div class="topbar-spacer"></div>
        <div class="topbar-version">MCDA · DENUE · Pareto</div>
    </div>

    <div class="main">

        <!-- STATS ROW -->
        <div class="stats-row">
            <div class="stat-cell">
                <div class="stat-lbl">Phase 1 (Nearby Search)</div>
                <div class="stat-val">{ess_used:,}<small> / 10,000 calls</small></div>
                <div class="progress-wrap">
                    <div class="progress-track"><div class="progress-fill" style="width: {min(100, (ess_used/10000)*100)}%; background: #22c55e;"></div></div>
                    <div class="progress-meta">
                        <span style="color:#22c55e;">Est: ${ess_used * 0.04:.2f} USD</span>
                        <span>Monthly Limit: $400 USD</span>
                    </div>
                </div>
            </div>
            <div class="stat-cell">
                <div class="stat-lbl">Phase 2 (Place Details)</div>
                <div class="stat-val">{pro_used:,}<small> / 5,000 calls</small></div>
                <div class="progress-wrap">
                    <div class="progress-track"><div class="progress-fill" style="width: {min(100, (pro_used/5000)*100)}%; background: #3b82f6;"></div></div>
                    <div class="progress-meta">
                        <span style="color:#3b82f6;">Est: ${pro_used * 0.038:.2f} USD</span>
                        <span>Monthly Limit: $100 USD</span>
                    </div>
                </div>
            </div>
            <div class="stat-cell">
                <div class="stat-lbl">All Mexico Projection (P1)</div>
                <div class="stat-val">{global_ph1_calls:,}<small> total calls</small></div>
                <div class="progress-wrap">
                    <div class="progress-track"><div class="progress-fill" style="width: {min(100, (global_ph1_calls/10000)*100)}%; background: {'#22c55e' if ph1_balance >= 0 else '#f43f5e'};"></div></div>
                    <div class="progress-meta">
                        <span style="color:{'#22c55e' if ph1_balance >= 0 else '#f43f5e'};">
                            {'Balance OK' if ph1_balance >= 0 else 'Overdraft'}
                        </span>
                        <span>Buffer: {ph1_balance:,} extra calls</span>
                    </div>
                </div>
            </div>
            <div class="stat-cell">
                <div class="stat-lbl">P2 Exact Cost (DB Pending Hot Leads)</div>
                <div class="stat-val">${exact_ph2_cost_usd:.2f} USD<small> exact required</small></div>
                <div class="progress-wrap">
                    <div class="progress-track"><div class="progress-fill" style="width: {min(100, (exact_ph2_cost_usd/190)*100)}%; background: #3b82f6;"></div></div>
                    <div class="progress-meta">
                        <span style="color:#3b82f6;">Pending Leads: {actual_db_hot_leads}</span>
                        <span>Global Est: {global_ph2_calls} leads</span>
                    </div>
                </div>
            </div>
            <div class="stat-cell">
                <div class="stat-lbl">Global Probes</div>
                <div class="stat-val">{global_actual_probes:,}<small> / {global_planned_probes:,}</small></div>
                <div class="progress-wrap">
                    <div class="progress-meta">
                        <span style="color:#a78bfa;">Actual</span>
                        <span>Planned</span>
                    </div>
                </div>
            </div>
            <div class="stat-cell">
                <div class="stat-lbl">Evaluated Cities</div>
                <div class="stat-val">{len(allocation_data)}</div>
                <div class="progress-wrap">
                    <div class="progress-meta">
                        <span style="color:#737373;">In the Matrix</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- SEARCH -->
        <div class="search-row">
            <input type="text" id="searchInput" class="search-box"
                   placeholder="Search city..." onkeyup="filterTable()">
            <select id="countryFilter" class="search-box" style="width:200px;" onchange="filterTable()">
{country_options}
            </select>
            <span class="row-count" id="rowCount">{len(allocation_data)} cities</span>
        </div>

        <!-- TABLE -->
        <div class="table-wrap">
            <table id="allocationTable">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>País</th>
                        <th>Ciudad</th>
                        <th>Tier</th>
                        <th>DENUE Target</th>
                        <th>Hofstede Score</th>
                        <th>Weight (W_ij)</th>
                        <th>Sondas (Max / Reales)</th>
                        <th>Ph1 Calls</th>
                        <th>Ph2 Calls</th>
                        <th>Eff. Total</th>
                        <th>Budget %</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        function filterTable() {{
            const input = document.getElementById("searchInput").value.toLowerCase();
            const country = document.getElementById("countryFilter").value.toLowerCase();
            const rows = document.querySelectorAll("#allocationTable tbody tr");
            let visible = 0;
            rows.forEach(row => {{
                const textMatch = row.innerText.toLowerCase().includes(input);
                const countryCell = row.cells[1].innerText.toLowerCase();
                const countryMatch = (country === "" || countryCell === country);
                
                const match = textMatch && countryMatch;
                row.style.display = match ? "" : "none";
                if (match) visible++;
            }});
            document.getElementById("rowCount").innerText = visible + " cities";
        }}
    </script>
</body>
</html>"""

    with open(DASHBOARD_V4_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ Generated Dashboard V4 HTML at:\n   {DASHBOARD_V4_FILE}")
    return DASHBOARD_V4_FILE

if __name__ == "__main__":
    generate_dashboard_v4_html()
