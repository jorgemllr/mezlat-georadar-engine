"""
MESLATT Allocation V4 Pipeline — Phase 2 Deep Enrichment Engine
===============================================================
Enriches Qualified Hot Leads with Google Places (New) Place Details:
  - Up to 3 Google CDN High-Definition Photos (Static redirect URLs)
  - Full Customer Reviews with author ratings & timestamps
  - Regular Opening Hours & Daily schedules
  - National & International Phone numbers for WhatsApp outreach
  - Price levels and payment options

Interactive CLI Modes:
  [1] Test Mode (Specific Place ID or Top N hot leads)
  [2] Targeted City / Multi-City Enrichment
  [3] Global Priority Queue (Processes all pending hot leads ordered by score)

Updates Datasets/processed_leads_v4.json, deducts budget, and updates UI.
"""

import os
import sys
import json
import requests
from pathlib import Path

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_config import (
    API_KEY,
    MAX_PHOTOS_TO_EXTRACT,
    DATASETS_DIR,
    load_budget,
    save_budget,
    check_and_deduct_budget,
    load_processed_leads,
    save_processed_leads,
    load_commercial_clusters,
    resolve_photo_cdn_url,
    trigger_ui_updates
)

def enrich_single_lead(lead: dict, budget: dict) -> bool:
    """Performs Place Details extraction for a single lead."""
    pid = lead.get("place_id")
    if not pid:
        return False

    if not check_and_deduct_budget(budget, "phase2_calls", cost=1):
        return False

    url = f"https://places.googleapis.com/v1/places/{pid}"
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": (
            "id,internationalPhoneNumber,nationalPhoneNumber,regularOpeningHours,"
            "priceLevel,paymentOptions,photos,reviews,googleMapsUri"
        )
    }

    try:
        print(f"   📞 Fetching Details: {lead.get('business_name', 'Unknown')[:32]:32s} (Score: {lead.get('phase2_score', 0)})...", end="", flush=True)
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code != 200:
            print(f" ❌ Status {res.status_code}")
            return False

        data = res.json()

        # 1. Resolve CDN Photos
        static_photo_urls = []
        raw_photos = data.get("photos", [])[:MAX_PHOTOS_TO_EXTRACT]
        for photo in raw_photos:
            if photo_name := photo.get("name"):
                if cdn_url := resolve_photo_cdn_url(photo_name):
                    static_photo_urls.append(cdn_url)

        # 2. Extract Customer Reviews
        extracted_reviews = []
        for rev in data.get("reviews", []):
            extracted_reviews.append({
                "author": rev.get("authorAttribution", {}).get("displayName"),
                "rating": rev.get("rating"),
                "text": rev.get("text", {}).get("text"),
                "relative_time": rev.get("relativePublishTimeDescription")
            })

        # 3. Update Lead Attributes
        lead["phone"] = data.get("nationalPhoneNumber") or data.get("internationalPhoneNumber") or lead.get("phone", "")
        lead["google_maps_url"] = data.get("googleMapsUri", f"https://maps.google.com/?cid={pid}")
        lead["photos"] = static_photo_urls
        lead["opening_hours"] = data.get("regularOpeningHours", {}).get("weekdayDescriptions", [])
        lead["payment_options"] = data.get("paymentOptions", {})
        lead["reviews"] = extracted_reviews
        lead["price_level"] = data.get("priceLevel", lead.get("price_level", "UNKNOWN"))
        lead["phase2_done"] = True

        print(f" ✅ {len(static_photo_urls)} photos, {len(extracted_reviews)} reviews.")
        return True

    except Exception as e:
        print(f" ❌ Exception: {e}")
        return False

def run_cli():
    print("=" * 60)
    print("   MESLATT PIPELINE V4 — PHASE 2 DEEP ENRICHMENT")
    print("=" * 60)

    budget = load_budget()
    used_p2 = budget["used"]["phase2_calls"]
    limit_p2 = budget["limits"]["phase2_monthly"]
    remaining_p2 = limit_p2 - used_p2
    print(f"📊 API Quota Status: {used_p2}/{limit_p2} Place Details calls used ({remaining_p2} remaining)\n")

    all_leads = load_processed_leads()
    if not all_leads:
        print("❌ No leads found in processed_leads_v4.json.")
        return

    # Filter hot leads needing Phase 2
    pending_hot_leads = [
        lead for lead in all_leads.values()
        if lead.get("is_hot_lead") and not lead.get("phase2_done") and not lead.get("photos")
    ]
    pending_hot_leads.sort(key=lambda x: x.get("phase2_score", 0), reverse=True)

    print(f"🎯 Total Qualified Hot Leads pending enrichment: {len(pending_hot_leads)}")
    print("\nSelect Enrichment Mode:")
    print("  [1] Test Mode (Specific Place ID or Top N test batch)")
    print("  [2] Targeted City / Multi-City Enrichment (Select from city list)")
    print("  [3] Global Priority Queue (Processes pending hot leads by BNAI score)")
    print("  [4] Round-Robin Queue Execution (Balanced rounds from phase2_round_robin_queue.json)")

    mode = input("\nEnter mode (1/2/3/4): ").strip()
    target_leads = []

    if mode == "1":
        sub = input("Type 'ID' for specific Place ID or enter number of Top Leads to test (e.g. 5): ").strip()
        if sub.upper() == "ID":
            pid = input("Paste Place ID: ").strip()
            if pid in all_leads:
                target_leads = [all_leads[pid]]
            else:
                print(f"⚠️ Place ID {pid} not found in database. Creating placeholder...")
                target_leads = [{"place_id": pid, "business_name": "Direct Test Target", "phase2_score": 100.0}]
        elif sub.isdigit():
            count = int(sub)
            target_leads = pending_hot_leads[:count]
        else:
            print("❌ Invalid input.")
            return

    elif mode == "2":
        # Extraer las ciudades únicas disponibles que realmente tienen leads pendientes
        available_cities = set()
        for lead in pending_hot_leads:
            cz = lead.get("city_zone")
            if cz:
                available_cities.add(cz)
        
        if not available_cities:
            print("❌ No cities found in pending leads. (Leads might need city_zone backfilling).")
            return
            
        cities = sorted(list(available_cities))
        print("\nAvailable Cities (with pending leads):")
        for i, c in enumerate(cities, 1):
            print(f"  [{i:2d}] {c}")

        selection = input("\nEnter city number(s) separated by comma (e.g. '1, 4'): ").strip()
        selected_indices = [int(x.strip()) for x in selection.split(",") if x.strip().isdigit()]
        selected_cities = [cities[idx - 1] for idx in selected_indices if 1 <= idx <= len(cities)]

        # Filtro estricto usando el nuevo campo city_zone
        for lead in pending_hot_leads:
            if lead.get("city_zone") in selected_cities:
                target_leads.append(lead)

        print(f"\n📍 Found {len(target_leads)} pending hot leads matching selected cities.")

    elif mode == "3":
        target_leads = pending_hot_leads[:remaining_p2]

    elif mode == "4":
        queue_file = DATASETS_DIR / "phase2_round_robin_queue.json"
        if not queue_file.exists():
            print("⚠️ Queue file not found. Generating fresh Round-Robin queue...")
            try:
                import importlib
                mod = importlib.import_module("04_build_round_robin_queue")
                mod.build_round_robin_queue()
            except Exception as e:
                print(f"❌ Error generating queue: {e}")
                return

        if not queue_file.exists():
            print("❌ Queue file still not found. Aborting.")
            return

        with open(queue_file, "r", encoding="utf-8") as qf:
            q_data = json.load(qf)

        rounds = q_data.get("rounds", [])
        total_rounds = len(rounds)
        print(f"\n📋 Loaded Round-Robin Queue: {total_rounds} rounds available.")
        
        round_choice = input(f"Select rounds to execute [e.g. '1', '1-3', 'all'] (Default: all within budget): ").strip().lower()
        
        selected_pids = []
        if not round_choice or round_choice == "all":
            for r in rounds:
                for l in r.get("leads", []):
                    if l.get("within_budget") and not l.get("already_enriched"):
                        selected_pids.append(l.get("place_id"))
        elif "-" in round_choice:
            try:
                start_r, end_r = [int(x.strip()) for x in round_choice.split("-")]
                for r in rounds:
                    r_num = r.get("round_number", 0)
                    if start_r <= r_num <= end_r:
                        for l in r.get("leads", []):
                            if not l.get("already_enriched"):
                                selected_pids.append(l.get("place_id"))
            except Exception:
                print("❌ Invalid round range format.")
                return
        elif round_choice.isdigit():
            r_num_target = int(round_choice)
            for r in rounds:
                if r.get("round_number") == r_num_target:
                    for l in r.get("leads", []):
                        if not l.get("already_enriched"):
                            selected_pids.append(l.get("place_id"))

        # Map back to lead objects
        target_leads = [all_leads[pid] for pid in selected_pids if pid in all_leads and not all_leads[pid].get("phase2_done")]
        print(f"📍 Selected {len(target_leads)} leads from Round-Robin queue for enrichment.")

    else:
        print("❌ Invalid mode.")
        return

    if not target_leads:
        print("⚠️ No eligible leads to process.")
        return

    print(f"\n📋 Queue: {len(target_leads)} leads selected for Phase 2 enrichment.")
    confirm = input("Proceed and execute Place Details API calls? (y/n): ").strip().lower()
    if confirm not in ["y", "yes", "s", "si"]:
        print("🛑 Enrichment aborted by user.")
        return

    print(f"\n🚀 Starting Phase 2 Enrichment...\n")
    enriched_count = 0

    for i, lead in enumerate(target_leads, 1):
        success = enrich_single_lead(lead, budget)
        if success:
            enriched_count += 1
            all_leads[lead["place_id"]] = lead
            save_budget(budget)
            save_processed_leads(all_leads)
        else:
            if budget["used"]["phase2_calls"] >= budget["limits"]["phase2_monthly"]:
                print("🛑 Phase 2 monthly API quota limit reached.")
                break

    print(f"\n🎉 Phase 2 Complete! Enriched {enriched_count} leads with photos, reviews, and detailed metadata.")

    # Update visualizers
    trigger_ui_updates(update_dashboard=True, update_fog_map=True, update_crm=True)

if __name__ == "__main__":
    run_cli()
