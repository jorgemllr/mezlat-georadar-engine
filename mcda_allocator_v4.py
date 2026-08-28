"""
MEZLAT — MCDA Budget Allocator V4 (Mexico-First, Dynamic Budget)
=================================================================

Key improvements over V3:
  1. Budget is derived from `budget_state.json` (real remaining calls this month),
     NOT hardcoded as a fixed number of probes.
  2. Auto-resets usage counters when the billing month rolls over.
  3. Mexico-first allocation: all available probes are offered to Mexican cities
     first. International cities only receive the leftover capacity.
  4. No fixed 80/20 split. The split emerges naturally from city density data.
  5. Phase 2 hot-lead projection is estimated numerically, not left as a string.

Output:
  - scripts/allocation_v4/api_budget_allocation_v4.json
"""

import json
import math
import csv
import unicodedata
import datetime
import duckdb
from pathlib import Path

# ── Directory references ──────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent.parent
DATASETS    = BASE_DIR / "Datasets"
V4_DIR      = BASE_DIR / "scripts" / "allocation_v4"

CITIES_FILE   = DATASETS / "SimpleMaps_Cities - worldcities.csv"
HOFSTEDE_FILE = DATASETS / "Hofstede_6D - hofstede_full.json"
PARQUET_FILE  = DATASETS / "denue_mexico.parquet"

BUDGET_STATE_FILE = V4_DIR / "budget_state.json"
OUTPUT_FILE       = V4_DIR / "api_budget_allocation_v4.json"

# ── Google Maps API limits (monthly free tier) ────────────────────────────────
PHASE1_MONTHLY_LIMIT = 10_000   # Essentials — Nearby Search calls
PHASE2_MONTHLY_LIMIT = 5_000    # Pro         — Place Details calls

# ── Probe / call assumptions ──────────────────────────────────────────────────
CALLS_PER_PROBE           = 3    # 3 niche batches per radar probe
RESULTS_PER_CALL          = 20   # Google Places API max results per Nearby Search
HOT_LEAD_CONVERSION_RATE  = 0.05 # 5 % of raw results become hot leads (Phase 2 targets)

# ── MCDA weight coefficients (V4 — same logic as V3) ─────────────────────────
ALPHA_PRESENCE  = 0.45
ALPHA_DENSITY   = 0.25
ALPHA_HOFSTEDE  = 0.20
ALPHA_TOURISM   = 0.05
ALPHA_MAPS_COV  = 0.05
ZIPF_EXPONENT   = 0.85   # Softened Zipf for fairer inter-city distribution

# Ideal Hofstede profile for a SaaS-receptive market
IDEAL_HOFSTEDE = {"pdi": 20, "idv": 80, "mas": 50, "uai": 25, "ltowvs": 50, "ivr": 80}

# Minimum population to consider a city (applies only to international cities)
INTL_POP_THRESHOLD = 500_000

# Manual Mexican cities too small for the SimpleMaps dataset but strategically relevant
MANUAL_MX_CITIES = [
    {"city": "Juriquilla",   "country": "Mexico", "iso3": "MEX", "lat": 20.7125,  "lng": -100.4583, "population": 45_000},
    {"city": "El Pueblito (Centro)",  "country": "Mexico", "iso3": "MEX", "admin_name": "Querétaro", "lat": 20.5397,  "lng": -100.4410, "population": 75_000},
    {"city": "Jesus Maria",  "country": "Mexico", "iso3": "MEX", "lat": 21.9614,  "lng": -102.3444, "population": 120_000},
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def norm(s: str) -> str:
    """Lowercase, strip accents, trim whitespace."""
    if not s:
        return ""
    s = str(s).lower().strip()
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def load_budget_state() -> dict:
    """
    Reads budget_state.json and auto-resets usage counters if the billing
    month has rolled over since the last run.
    Returns the (possibly updated) state dict.
    """
    current_month = datetime.datetime.now().strftime("%Y-%m")

    if BUDGET_STATE_FILE.exists():
        with open(BUDGET_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    else:
        # First-run bootstrap — create a clean state for the current month
        state = {
            "billing_month": current_month,
            "limits":  {"phase1_monthly": PHASE1_MONTHLY_LIMIT, "phase2_monthly": PHASE2_MONTHLY_LIMIT},
            "used":    {"phase1_calls": 0, "phase2_calls": 0},
            "remaining": {"phase1_calls": PHASE1_MONTHLY_LIMIT, "phase2_calls": PHASE2_MONTHLY_LIMIT},
            "last_updated": datetime.datetime.now().isoformat(timespec="seconds"),
            "notes": "Auto-created on first run."
        }

    # Auto-reset when the billing month changes
    if state.get("billing_month") != current_month:
        print(f"📅 New billing month detected ({state['billing_month']} → {current_month}). "
              f"Resetting usage counters.")
        state["billing_month"]    = current_month
        state["used"]             = {"phase1_calls": 0, "phase2_calls": 0}
        state["remaining"]        = {
            "phase1_calls": state["limits"]["phase1_monthly"],
            "phase2_calls": state["limits"]["phase2_monthly"]
        }
        state["last_updated"] = datetime.datetime.now().isoformat(timespec="seconds")
        _save_budget_state(state)

    return state


def _save_budget_state(state: dict) -> None:
    with open(BUDGET_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_hofstede() -> dict:
    if not HOFSTEDE_FILE.exists():
        return {}
    with open(HOFSTEDE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["ctr"]: item for item in data if "ctr" in item}


def hofstede_score(country_data: dict) -> float:
    """
    Computes a [0, 1] cultural-compatibility score using Euclidean distance
    from the ideal Hofstede profile defined above.
    """
    try:
        vec_c = [float(country_data.get(k) or 50) for k in IDEAL_HOFSTEDE]
        vec_i = list(IDEAL_HOFSTEDE.values())
        max_d = math.sqrt(6 * 100 ** 2)
        dist  = math.sqrt(sum((c - i) ** 2 for c, i in zip(vec_c, vec_i)))
        return max(0.0, min(1.0, 1.0 - dist / max_d))
    except Exception:
        return 0.5


def load_denue_counts() -> dict:
    """
    Returns a dict of {normalized_city_name: business_count} from the DENUE
    Parquet file. Falls back gracefully if the file is missing.
    """
    if not PARQUET_FILE.exists():
        print("⚠️  DENUE Parquet not found. Density scores will fall back to population estimates.")
        return {}

    try:
        con = duckdb.connect(database=":memory:")
        df  = con.execute(f"""
            SELECT city, COUNT(*) AS cnt
            FROM '{PARQUET_FILE}'
            WHERE city IS NOT NULL AND city != ''
            GROUP BY city
        """).df()

        counts: dict = {}
        for _, row in df.iterrows():
            k = norm(row["city"])
            counts[k] = counts.get(k, 0) + int(row["cnt"])

        # Aggregate CDMX by state name (its municipality structure is fragmented)
        try:
            cdmx = con.execute(
                f"SELECT COUNT(*) FROM '{PARQUET_FILE}' "
                f"WHERE LOWER(state) LIKE '%ciudad de m%xico%'"
            ).fetchone()[0]
            counts["mexico city"] = cdmx
            counts["cdmx"]        = cdmx
        except Exception:
            pass

        # Common name aliases to reconcile SimpleMaps city names with DENUE
        aliases = {
            "leon de los aldama":    "leon",
            "toluca de lerdo":       "toluca",
            "heroica puebla de zaragoza": "puebla",
            "santiago de queretaro": "queretaro",
            "ecatepec de morelos":   "ecatepec",
            "naucalpan de juarez":   "naucalpan",
        }
        for full, short in aliases.items():
            if short in counts:
                counts[full] = counts.get(full, 0) + counts[short]

        return counts

    except Exception as exc:
        print(f"⚠️  DENUE load error: {exc}")
        return {}


def partial_weight(city: dict, denue_counts: dict, hofstede_db: dict,
                   max_denue: int) -> float:
    """
    Computes the raw MCDA weight for a city before Pareto rank adjustment.
    """
    is_mexico = city["country"] == "Mexico"

    # --- Presence score ---
    presence = 1.0 if is_mexico else 0.10

    # --- Density score ---
    denue_cnt = denue_counts.get(norm(city["city"]), 0) if is_mexico else 0
    if is_mexico and denue_cnt == 0:
        # Estimate when the city is missing from DENUE (~0.12 % of population)
        denue_cnt = int(city["population"] * 0.0012)

    if is_mexico and denue_cnt > 0:
        density = math.log1p(denue_cnt) / math.log1p(max_denue)
    else:
        density = math.log1p(city["population"]) / math.log1p(39_000_000.0)

    # --- Hofstede score ---
    h_data   = hofstede_db.get(city["iso3"], {})
    h_score  = hofstede_score(h_data)

    # --- Fixed minor scores ---
    tourism  = 0.5
    maps_cov = 0.9 if is_mexico else 0.7

    return (
        ALPHA_PRESENCE * presence
        + ALPHA_DENSITY  * density
        + ALPHA_HOFSTEDE * h_score
        + ALPHA_TOURISM  * tourism
        + ALPHA_MAPS_COV * maps_cov
    )


def allocate_pool(cities: list, probe_budget: int) -> list:
    """
    Given a list of cities (each with a 'partial_weight' key) and an integer
    probe budget, assigns probe counts using a softened Zipf (Pareto) law.

    A hard ceiling pass runs after the initial rounding to ensure the total
    assigned probes never exceed probe_budget (rounding drift can cause a
    small surplus that this corrects by trimming from the lowest-ranked cities).

    Returns only cities that received at least 1 probe.
    """
    if not cities or probe_budget <= 0:
        return []

    # Sort descending by partial weight
    cities = sorted(cities, key=lambda x: x.get("partial_weight", 0), reverse=True)

    # Apply Zipf rank weighting
    total_pareto = 0.0
    for rank, city in enumerate(cities, start=1):
        city["pareto_weight"] = (1.0 / rank ** ZIPF_EXPONENT) * city["partial_weight"]
        total_pareto += city["pareto_weight"]

    # First pass: integer truncation (no forced minimum — cities that don't
    # earn a full probe stay at 0 and are excluded from allocation)
    for city in cities:
        share = city["pareto_weight"] / total_pareto if total_pareto > 0 else 0
        city["_share"]     = share
        city["max_probes"] = int(share * probe_budget)   # floor, no min(1)

    # Distribute leftover probes (from truncation) to the highest-ranked
    # cities that lost the most fractional value — greedy largest-remainder method
    leftover = probe_budget - sum(c["max_probes"] for c in cities)
    if leftover > 0:
        # Sort by fractional part descending, then give 1 extra probe each
        ranked_by_remainder = sorted(
            cities,
            key=lambda c: (c["_share"] * probe_budget) - c["max_probes"],
            reverse=True
        )
        for city in ranked_by_remainder[:leftover]:
            city["max_probes"] += 1

    # Second pass: compute derived fields now that probe counts are final
    allocated = []
    for city in cities:
        max_probes = city["max_probes"]
        if max_probes <= 0:
            continue

        share = city["_share"]
        city.pop("_share", None)

        city["budget_percentage"]   = f"{share * 100:.2f}%"
        city["final_weight"]        = round(city["partial_weight"], 3)
        city["phase1_calls"]        = max_probes * CALLS_PER_PROBE
        city["phase2_calls"]        = 0   # Updated during Phase 1 execution based on actual hot leads found
        city["allocated_api_calls"] = city["phase1_calls"]

        # Projected estimates (planning only — not real values)
        raw_results = max_probes * RESULTS_PER_CALL * CALLS_PER_PROBE
        est_hot     = int(raw_results * HOT_LEAD_CONVERSION_RATE)
        city["projections"] = {
            "est_raw_businesses":   raw_results,
            "est_hot_leads_phase2": est_hot,
        }

        allocated.append(city)

    return allocated


def assign_tiers(cities: list) -> list:
    """Assigns S/A/B/C tiers based on final rank position."""
    for idx, city in enumerate(cities):
        if   idx < 5:  city["tier"] = "S"
        elif idx < 20: city["tier"] = "A"
        elif idx < 50: city["tier"] = "B"
        else:          city["tier"] = "C"
    return cities


# ── Main routine ──────────────────────────────────────────────────────────────

def run_mcda_v4_allocation():
    print("🚀 MEZLAT — MCDA Budget Allocator V4 (Mexico-First, Dynamic Budget)")
    V4_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Load live budget state ─────────────────────────────────────────────
    state = load_budget_state()
    phase1_remaining = state["remaining"]["phase1_calls"]
    phase2_remaining = state["remaining"]["phase2_calls"]

    print(f"💳 Budget this month ({state['billing_month']}):")
    print(f"   Phase 1 remaining: {phase1_remaining:,} / {state['limits']['phase1_monthly']:,} calls")
    print(f"   Phase 2 remaining: {phase2_remaining:,} / {state['limits']['phase2_monthly']:,} calls")

    # Derive the maximum number of probes we can afford with what is left
    max_probes_total = phase1_remaining // CALLS_PER_PROBE
    print(f"   → Max probes available this month: {max_probes_total:,}  "
          f"({phase1_remaining} ÷ {CALLS_PER_PROBE} calls/probe)")

    if max_probes_total == 0:
        print("🛑 Phase 1 budget exhausted for this billing month. Nothing to allocate.")
        return {}

    # ── 2. Load reference data ────────────────────────────────────────────────
    denue_counts = load_denue_counts()
    hofstede_db  = load_hofstede()
    max_denue    = max(denue_counts.values(), default=1)

    # ── 3. Parse city database ────────────────────────────────────────────────
    mx_cities, intl_cities = [], []

    if CITIES_FILE.exists():
        with open(CITIES_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    pop = float(row["population"])
                except ValueError:
                    continue

                country = row["country"]
                is_mexico = country == "Mexico"
                
                # Exclude the ghost "El Pueblito" from SimpleMaps to favor our manual entry
                if is_mexico and row.get("city") == "El Pueblito":
                    continue

                # Filter: keep all Mexican cities ≥ 50k pop, only large intl cities
                if not is_mexico and pop < INTL_POP_THRESHOLD:
                    continue
                if pop < 50_000:
                    continue

                city = {
                    "city":       row["city_ascii"],
                    "country":    country,
                    "iso3":       row["iso3"],
                    "lat":        float(row["lat"]),
                    "lng":        float(row["lng"]),
                    "population": pop,
                    "h_ij_score": 0.0,
                    "denue_target_count": 0,
                }

                # Compute DENUE count for dashboard display
                if is_mexico:
                    cnt = denue_counts.get(norm(city["city"]), 0)
                    city["denue_target_count"] = cnt if cnt > 0 else int(pop * 0.0012)

                # Hofstede compatibility score
                h_data = hofstede_db.get(row["iso3"], {})
                city["h_ij_score"]      = round(hofstede_score(h_data), 3)
                city["partial_weight"]  = partial_weight(city, denue_counts, hofstede_db, max_denue)

                if is_mexico:
                    mx_cities.append(city)
                else:
                    intl_cities.append(city)
    else:
        print(f"❌ Cities file not found: {CITIES_FILE}")
        return {}

    # Inject manual Mexican cities
    for mc in MANUAL_MX_CITIES:
        cnt = denue_counts.get(norm(mc["city"]), 350)
        mc["denue_target_count"] = cnt
        mc["h_ij_score"]         = round(hofstede_score(hofstede_db.get("MEX", {})), 3)
        mc["partial_weight"]     = partial_weight(mc, denue_counts, hofstede_db, max_denue)
        mx_cities.append(mc)

    print(f"\n📊 City pool: {len(mx_cities)} Mexican, {len(intl_cities)} International")

    # ── 4. Mexico-first allocation ────────────────────────────────────────────
    # Step A: How many probes does Mexico "want" at full capacity?
    mx_sorted = sorted(mx_cities, key=lambda x: x["partial_weight"], reverse=True)
    total_mx_pareto = sum(
        (1.0 / (r + 1) ** ZIPF_EXPONENT) * c["partial_weight"]
        for r, c in enumerate(mx_sorted)
    )
    # Ideal probe count Mexico would absorb if budget were unlimited
    mx_ideal_probes = sum(
        max(1, int(round(
            ((1.0 / (r + 1) ** ZIPF_EXPONENT) * c["partial_weight"] / total_mx_pareto)
            * max_probes_total
        )))
        for r, c in enumerate(mx_sorted)
    )

    # Step B: Clamp to available budget
    mx_probe_budget   = min(mx_ideal_probes, max_probes_total)
    intl_probe_budget = max(0, max_probes_total - mx_probe_budget)

    print(f"\n🇲🇽 Mexico probe budget   : {mx_probe_budget:,}  (ideal demand: {mx_ideal_probes:,})")
    print(f"🌍 International leftover : {intl_probe_budget:,}")

    # Step C: Run allocation for each pool
    allocated_mx   = allocate_pool(mx_sorted,   mx_probe_budget)
    allocated_intl = allocate_pool(
        sorted(intl_cities, key=lambda x: x["partial_weight"], reverse=True)[:150],
        intl_probe_budget
    )

    # Step D: Merge, re-sort by probe count for tier assignment
    all_cities = sorted(allocated_mx + allocated_intl,
                        key=lambda x: x["max_probes"], reverse=True)
    all_cities = assign_tiers(all_cities)

    # ── 5. Global projections ─────────────────────────────────────────────────
    total_probes       = sum(c["max_probes"]                             for c in all_cities)
    total_ph1_calls    = sum(c["phase1_calls"]                           for c in all_cities)
    mx_probes          = sum(c["max_probes"]   for c in all_cities if c["country"] == "Mexico")
    intl_probes        = total_probes - mx_probes
    est_raw_biz        = sum(c["projections"]["est_raw_businesses"]      for c in all_cities)
    est_hot_total      = sum(c["projections"]["est_hot_leads_phase2"]    for c in all_cities)
    # Hot leads are capped by Phase 2 budget so we don't project more than we can afford
    est_hot_capped     = min(est_hot_total, phase2_remaining)

    # ── 6. Build and save output JSON ─────────────────────────────────────────
    output = {
        "metadata": {
            "strategy":      "Mexico-First Dynamic Budget V4",
            "billing_month": state["billing_month"],
            "generated_at":  datetime.datetime.now().isoformat(timespec="seconds"),
            "budget_summary": {
                "phase1_available_this_month":  phase1_remaining,
                "phase1_calls_per_probe":       CALLS_PER_PROBE,
                "max_probes_available":         max_probes_total,
                "phase1_allocated_mexico":      mx_probes * CALLS_PER_PROBE,
                "phase1_allocated_intl":        intl_probes * CALLS_PER_PROBE,
                "phase1_total_allocated":       total_ph1_calls,
                "phase1_total_remaining_after": phase1_remaining - total_ph1_calls,
                "probes_mexico":                mx_probes,
                "probes_intl":                  intl_probes,
                "probes_total":                 total_probes,
                "phase2_available_this_month":  phase2_remaining,
                "phase2_projected_hot_leads":   est_hot_total,
                "phase2_hot_leads_capped_by_budget": est_hot_capped,
                "phase2_within_budget":         est_hot_total <= phase2_remaining,
            },
        },
        "cities": all_cities,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── 7. Console summary ────────────────────────────────────────────────────
    bs = output["metadata"]["budget_summary"]
    print(f"""
╔══════════════════════════════════════════════════════════╗
║          MCDA V4 — Allocation Summary ({state['billing_month']})         ║
╠══════════════════════════════════════════════════════════╣
║  Cities allocated : {len(all_cities):>5}                                 ║
║  Total probes     : {bs['probes_total']:>5}  (Mexico: {bs['probes_mexico']}, Intl: {bs['probes_intl']})
║  Phase 1 calls    : {bs['phase1_total_allocated']:>5} / {phase1_remaining:,} available
║  Phase 1 leftover : {bs['phase1_total_remaining_after']:>5} calls unused this month
║  Phase 2 est. hot : {bs['phase2_projected_hot_leads']:>5}  → capped at {bs['phase2_hot_leads_capped_by_budget']} (budget limit)
║  Phase 2 OK?      : {'✅ YES' if bs['phase2_within_budget'] else '❌ OVER BUDGET'}
╚══════════════════════════════════════════════════════════╝
    """)
    print(f"💾 Saved: {OUTPUT_FILE}")
    return output


if __name__ == "__main__":
    run_mcda_v4_allocation()
