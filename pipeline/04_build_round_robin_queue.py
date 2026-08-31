#!/usr/bin/env python3
"""
MEZLAT PIPELINE V4 — 06 ROUND-ROBIN QUEUE & API BUDGET PLANNER
===============================================================
Groups hot leads across granular Google categories, prioritizes them by
Master Archetype BNAI score, and schedules balanced extraction rounds.
Reads real budget state from Datasets/budget_state.json (5,000 calls ceiling).
Includes direct Google Maps deep links, coordinates, and address metadata.
"""

import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_config import (
    PROCESSED_LEADS_FILE as LEADS_FILE,
    BUDGET_FILE,
    DATASETS_DIR
)

# Resolve ARCHETYPE_FILE: prefer repo root, fall back to monorepo location
_repo_root = Path(__file__).resolve().parent.parent
_mono_root = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "allocation_v4"
ARCHETYPE_FILE = (
    _repo_root / "archetype_mapping.json"
    if (_repo_root / "archetype_mapping.json").exists()
    else _mono_root / "archetype_mapping.json"
)

OUTPUT_QUEUE_FILE = DATASETS_DIR / "phase2_round_robin_queue.json"

DEFAULT_PHASE2_BUDGET_LIMIT = 5000  # Default 5,000 calls ($100 USD Google Cloud credits)
SAFETY_RESERVE_CALLS = 30          # Reserve calls for 06_inject_manual_lead.py during sales pitches

def load_budget_limits():
    limit = DEFAULT_PHASE2_BUDGET_LIMIT
    used = 0
    if BUDGET_FILE.exists():
        try:
            with open(BUDGET_FILE, "r", encoding="utf-8") as f:
                bdata = json.load(f)
                limit = bdata.get("limits", {}).get("phase2_monthly", DEFAULT_PHASE2_BUDGET_LIMIT)
                used = bdata.get("used", {}).get("phase2_calls", 0)
        except Exception:
            pass
    return limit, used

def build_round_robin_queue(safety_reserve: int = SAFETY_RESERVE_CALLS):
    print("============================================================")
    print("   MEZLAT V4 — ROUND-ROBIN QUEUE & API BUDGET PLANNER     ")
    print("============================================================")
    
    if not LEADS_FILE.exists():
        print(f"❌ Leads file not found at: {LEADS_FILE}")
        return

    with open(LEADS_FILE, "r", encoding="utf-8") as f:
        all_leads = json.load(f).get("leads", {})

    max_budget, used_calls = load_budget_limits()

    # Load Archetype mapping
    category_to_archetype = {}
    archetype_bnai = {}
    if ARCHETYPE_FILE.exists():
        with open(ARCHETYPE_FILE, "r", encoding="utf-8") as f:
            arch_data = json.load(f)
            for arch in arch_data.get("archetypes", []):
                aid = arch["archetype_id"]
                bnai = arch["bnai_score"]
                archetype_bnai[aid] = bnai
                for cat in arch.get("absorbed_google_categories", []):
                    category_to_archetype[cat["google_type"]] = {
                        "archetype_id": aid,
                        "archetype_name": arch["display_name"],
                        "bnai_score": bnai
                    }

    # Group qualified hot leads with verified WhatsApp by primary_type category
    leads_by_category = defaultdict(list)
    total_hot_leads = 0
    total_whatsapp_leads = 0
    already_enriched_count = 0

    for pid, lead in all_leads.items():
        if lead.get("is_hot_lead"):
            total_hot_leads += 1
            # Strict WhatsApp Verification Filter: Must have has_whatsapp == True
            if lead.get("has_whatsapp") is True:
                total_whatsapp_leads += 1
                cat = lead.get("primary_type") or "UNKNOWN"
                leads_by_category[cat].append(lead)
                if lead.get("phase2_done") or (lead.get("photos") and len(lead.get("photos")) > 0):
                    already_enriched_count += 1

    # Sort categories by Archetype BNAI score (descending), then by lead count
    sorted_categories = sorted(
        leads_by_category.keys(),
        key=lambda c: (
            category_to_archetype.get(c, {}).get("bnai_score", 0),
            len(leads_by_category[c])
        ),
        reverse=True
    )

    # Sort leads within each category by phase2_score / rating / reviews
    for cat in sorted_categories:
        leads_by_category[cat].sort(
            key=lambda l: (
                l.get("phase2_score", 0),
                l.get("rating", 0),
                l.get("reviews_count", 0)
            ),
            reverse=True
        )

    # Build Round-Robin Rounds
    rounds = []
    round_idx = 1
    total_assigned = 0
    cumulative_calls = used_calls
    usable_budget = max(0, max_budget - safety_reserve)

    max_depth = max((len(v) for v in leads_by_category.values()), default=0)

    for depth in range(max_depth):
        current_round_leads = []
        for cat in sorted_categories:
            lead_list = leads_by_category[cat]
            if depth < len(lead_list):
                lead = lead_list[depth]
                arch_info = category_to_archetype.get(cat, {"archetype_id": "general", "archetype_name": "General", "bnai_score": 100})
                
                is_enriched = bool(lead.get("phase2_done") or (lead.get("photos") and len(lead.get("photos")) > 0))
                
                # If already enriched, cost is 0 new API calls, otherwise 1 call
                call_cost = 0 if is_enriched else 1
                cumulative_calls += call_cost
                
                within_budget = cumulative_calls <= usable_budget
                in_safety_reserve = (not within_budget) and (cumulative_calls <= max_budget)

                maps_url = lead.get("google_maps_url")
                if not maps_url and lead.get("lat") and lead.get("lng"):
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={lead['lat']},{lead['lng']}"

                current_round_leads.append({
                    "place_id": lead["place_id"],
                    "business_name": lead["business_name"],
                    "category": cat,
                    "city": lead.get("city_zone", "Unknown"),
                    "address": lead.get("address", "Address pending extraction"),
                    "lat": lead.get("lat"),
                    "lng": lead.get("lng"),
                    "google_maps_url": maps_url or "#",
                    "archetype_id": arch_info["archetype_id"],
                    "archetype_name": arch_info["archetype_name"],
                    "bnai_score": arch_info["bnai_score"],
                    "phase2_score": lead.get("phase2_score", 0),
                    "target_tier": lead.get("target_tier", 1),
                    "suggested_price": lead.get("suggested_price", 0),
                    "rating": lead.get("rating", 0),
                    "reviews_count": lead.get("reviews_count", 0),
                    "phone": lead.get("phone", ""),
                    "already_enriched": is_enriched,
                    "within_budget": within_budget,
                    "in_safety_reserve": in_safety_reserve,
                    "estimated_call_order": cumulative_calls if not is_enriched else 0
                })
                total_assigned += 1

        if current_round_leads:
            new_calls_in_round = sum(1 for l in current_round_leads if not l["already_enriched"])
            rounds.append({
                "round_number": round_idx,
                "total_prospects": len(current_round_leads),
                "new_api_calls_required": new_calls_in_round,
                "cumulative_api_calls": cumulative_calls,
                "leads": current_round_leads
            })
            round_idx += 1

    scheduled_for_extraction = sum(
        1 for r in rounds for l in r["leads"] if l["within_budget"] and not l["already_enriched"]
    )

    queue_payload = {
        "generated_at": str(Path(__file__).stat().st_mtime),
        "metrics": {
            "total_qualified_hot_leads": total_hot_leads,
            "total_whatsapp_verified_hot_leads": total_whatsapp_leads,
            "active_categories_count": len(sorted_categories),
            "already_enriched_leads": already_enriched_count,
            "used_api_calls": used_calls,
            "total_rounds_constructed": len(rounds),
            "budget_limit": max_budget,
            "safety_reserve_buffer": safety_reserve,
            "usable_budget": usable_budget,
            "scheduled_new_extractions": scheduled_for_extraction,
            "unfunded_backlog_leads": max(0, (total_whatsapp_leads - already_enriched_count) - scheduled_for_extraction)
        },
        "category_summary": [
            {
                "category": cat,
                "archetype_id": category_to_archetype.get(cat, {}).get("archetype_id", "unknown"),
                "archetype_name": category_to_archetype.get(cat, {}).get("archetype_name", "Unknown"),
                "bnai_score": category_to_archetype.get(cat, {}).get("bnai_score", 0),
                "hot_leads_count": len(leads_by_category[cat])
            }
            for cat in sorted_categories
        ],
        "rounds": rounds
    }

    OUTPUT_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue_payload, f, indent=2, ensure_ascii=False)

    print(f"📊 Total Hot Leads:               {total_hot_leads:,}")
    print(f"📱 WhatsApp Verified Hot Leads:   {total_whatsapp_leads:,}")
    print(f"🏷️  Active Categories:             {len(sorted_categories)}")
    print(f"🔄 Total Rounds Scheduled:        {len(rounds)}")
    print(f"💰 API Budget Ceiling:            {max_budget:,} calls")
    print(f"📈 Used API Calls:                {used_calls} calls")
    print(f"🛡️  Safety Reserve Buffer:         {safety_reserve} calls")
    print(f"⚡ Scheduled for Extraction:      {scheduled_for_extraction:,} calls")
    print(f"💾 Queue saved to:                {OUTPUT_QUEUE_FILE}")
    print("============================================================\n")

if __name__ == "__main__":
    build_round_robin_queue()
