# MEZLAT Allocation V4 Pipeline (Decoupled Engine)

The `pipeline/` module provides a decoupled, resilient, and interactive command-line interface (CLI) for territory data extraction, intelligent lead classification, deep enrichment, and interactive visualization.

---

## 🏗️ Architecture Overview

The system separates concerns into chronological, ordered stages:

```
[commercial_clusters_v4.json] 
              │
              ▼
    01_extract_phase1.py            ──> [Datasets/processed_leads_v4.json] (Raw)
              │
              ▼
    02_classify_leads.py            ──> [Datasets/processed_leads_v4.json] (Tiers 1, 2, 3)
              │
              ▼
    03_verify_whatsapp.py           ──> [Datasets/processed_leads_v4.json] (has_whatsapp: true/false)
              │
              ▼
    04_build_round_robin_queue.py   ──> [Datasets/phase2_round_robin_queue.json] (WhatsApp Only)
              │
              ▼
    05_enrich_phase2.py             ──> [Datasets/processed_leads_v4.json] (CDN Photos & Details)
              │
              ▼
    06_inject_manual_lead.py        ──> [Datasets/processed_leads_v4.json] (Hidden Gems VIP)
```

---

## 📜 Script Reference (Execution Order)

### 1. `01_extract_phase1.py` (Phase 1 Raw Extractor)
Performs Google Places API (New) `places:searchNearby` across defined radar probes.
- **Interactive CLI Options:**
  - `[1] Probe Test`: Single probe / coordinate test.
  - `[2] Targeted City / Multi-City`: Interactive city picker.
  - `[3] Nationwide Full Scan`: All radar probes across Mexico (`EXECUTE`).

### 2. `02_classify_leads.py` (Commercial Tier Classifier)
Applies intelligence rules and BNAI matrices without API cost.
- Categorizes prospects into **Tier 1 (Starter)**, **Tier 2 (Growth)**, and **Tier 3 (Enterprise VIP)**.
- Automatically regenerates map and CRM visualizers.

### 3. `03_verify_whatsapp.py` (Headless WhatsApp Verifier)
Orchestrates the Node.js Baileys WebSocket presence checker ($0 API cost).
- Flags each lead with `has_whatsapp: true` or `has_whatsapp: false`.

### 4. `04_build_round_robin_queue.py` (Round-Robin Budget Planner)
Filters hot leads with **verified WhatsApp presence** and distributes calls evenly across archetypes.
- Generates `Datasets/phase2_round_robin_queue.json` under monthly quota limits (5,000 calls).

### 5. `05_enrich_phase2.py` (Phase 2 Deep Enrichment Engine)
Queries Google Places API (New) `places/{place_id}` (*Place Details*) for Qualified Leads.
- **Interactive CLI Modes:**
  - `[1] Test Mode`: Specific Place ID or Top N test batch.
  - `[2] Targeted City / Multi-City Enrichment`: Select cities with pending hot leads.
  - `[3] Global Priority Queue`: Processes all pending leads ordered by BNAI score.
  - `[4] Round-Robin Queue Execution`: Processes balanced rounds from `phase2_round_robin_queue.json`.

### 6. `06_inject_manual_lead.py` (Manual Lead Injector)
Allows sales reps to inject specific Google Place IDs directly as high-priority hot leads.

---

## 📊 Interactive Dashboards with Multi-Filter UI

### `fog_of_war_map_v4.html` (Generated via `generate_pipeline_fog_map.py`)
- **Status Filter:** All Leads, Hot Leads Only, Phase 2 Enriched (CDN) Only, Standard Prospects.
- **City Filter:** Dynamic dropdown populated from active data.
- **Category Filter:** Dynamic dropdown of all 24 commercial niches.
- **Tier Filter:** Tier 1 vs Tier 2.
- **Instant Search:** Instant client-side text filter by business name or street address.

### `crm_pipeline_v4.html` (Generated via `generate_pipeline_crm_dashboard.py`)
- **Client-Side Filters:** City, Niche, Priority Tier, and Search Bar.
- **Live Metrics:** Real-time count of rendered cards, total hot leads, Tier 1 Whales, and Enriched leads.
- **Direct Outreach:** One-click WhatsApp direct chat link with auto-populated greetings and Google Maps deep link buttons.

---

## 🔒 Budget & Cost Guardrails
All API requests check and deduct against `budget_state.json`:
- **Phase 1 Limit:** 10,000 monthly Nearby Search calls.
- **Phase 2 Limit:** 5,000 monthly Place Details calls.
