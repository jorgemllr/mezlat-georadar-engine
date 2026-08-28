"""
MEZLAT Allocation V4 Pipeline — Phase 1 Raw Leads Extractor
============================================================
Executes Google Places API (New) Nearby Search calls for commercial radar probes.
Supports 3 operational modes via interactive CLI:
  [1] Probe Test Mode (Single probe ID / hex with custom batch selection)
  [2] Targeted City / Multi-City Scan (Interactive city picker with budget confirmation)
  [3] Nationwide Full Scan (Scans all available probes with strict confirmation)

Saves raw leads to Datasets/processed_leads_v4.json and checkpoints scanned probes.
"""

import os
import sys
import json
import math
import requests
import h3
from pathlib import Path

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_config import (
    API_KEY,
    BATCH_NICHES,
    DEFAULT_SEARCH_RADIUS_M,
    haversine,
    load_budget,
    save_budget,
    check_and_deduct_budget,
    load_processed_leads,
    save_processed_leads,
    load_scanned_state,
    save_scanned_state,
    load_commercial_clusters,
    trigger_ui_updates
)

def search_nearby_places(lat: float, lng: float, radius: int, types_list: list) -> list:
    """Performs Google Places searchNearby API request."""
    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.location,places.primaryType,places.types,"
            "places.rating,places.userRatingCount,places.websiteUri,places.formattedAddress,"
            "places.businessStatus,places.nationalPhoneNumber,places.internationalPhoneNumber,"
            "places.regularOpeningHours,places.priceLevel,places.googleMapsUri,places.photos,"
            "places.paymentOptions,places.editorialSummary,places.reservable,places.delivery,"
            "places.allowsDogs,places.goodForChildren,places.goodForGroups,places.goodForWatchingSports,"
            "places.liveMusic,places.menuForChildren,places.outdoorSeating,places.restroom,"
            "places.servesBeer,places.servesBreakfast,places.servesBrunch,places.servesCocktails,"
            "places.servesCoffee,places.servesDessert,places.servesDinner,places.servesLunch,"
            "places.servesVegetarianFood,places.servesWine,places.parkingOptions"
        )
    }
    payload = {
        "includedTypes": types_list,
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius}
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=12)
        if response.status_code == 200:
            return response.json().get("places", [])
        else:
            print(f"   ❌ API returned status {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"   ❌ Request failed: {e}")
    return []

def extract_probe(
    city_name: str,
    probe: dict,
    probe_idx: int,
    total_probes: int,
    requested_batches: list,
    all_leads: dict,
    scanned_state: dict,
    budget: dict
) -> tuple[int, bool]:
    """Extracts raw leads from a single probe across requested batches."""
    lat = probe.get("centroid_lat")
    lng = probe.get("centroid_lng")
    hex_id = probe.get("h3_index", "unknown_hex")
    probe_id = f"{city_name}_{lat}_{lng}"
    
    completed_batches = scanned_state.get(probe_id, set())
    batches_to_run = [b for b in requested_batches if b not in completed_batches]
    
    if not batches_to_run:
        print(f"   ⏭️ Probe {probe_idx}/{total_probes} ({city_name} - {hex_id}) already fully scanned. Skipping...")
        return 0, False

    # Compute dynamic radius based on hex boundary if available
    dynamic_radius = DEFAULT_SEARCH_RADIUS_M
    if hex_id and hex_id != "unknown_hex":
        try:
            boundary = h3.cell_to_boundary(hex_id)
            if boundary:
                v0_lat, v0_lng = boundary[0]
                dist = haversine(lat, lng, v0_lat, v0_lng)
                dynamic_radius = int(math.ceil(dist / 10.0)) * 10
        except Exception:
            pass

    print(f"\n📍 Scanning Hexagon [{hex_id}] in {city_name} (Probe {probe_idx}/{total_probes} | Radius: {dynamic_radius}m)...")
    new_prospects_found = 0

    for batch_idx in batches_to_run:
        if batch_idx not in BATCH_NICHES:
            continue

        if not check_and_deduct_budget(budget, "phase1_calls", cost=1):
            return new_prospects_found, True  # Budget exceeded

        print(f"   📡 Executing Batch {batch_idx} ({len(BATCH_NICHES[batch_idx])} niche types)...", end="", flush=True)
        places = search_nearby_places(lat, lng, dynamic_radius, BATCH_NICHES[batch_idx])
        print(f" ✅ {len(places)} raw results found.")

        for p in places:
            place_id = p.get("id")
            if not place_id:
                continue

            status = p.get("businessStatus", "OPERATIONAL")
            if status in ["CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"]:
                continue

            if place_id not in all_leads:
                new_prospects_found += 1
                all_leads[place_id] = {
                    "place_id": place_id,
                    "business_name": p.get("displayName", {}).get("text", "Unknown"),
                    "city_zone": city_name,
                    "lat": p.get("location", {}).get("latitude", lat),
                    "lng": p.get("location", {}).get("longitude", lng),
                    "address": p.get("formattedAddress", ""),
                    "rating": p.get("rating", 0),
                    "reviews_count": p.get("userRatingCount", 0),
                    "website": p.get("websiteUri", ""),
                    "phone": p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber", ""),
                    "price_level": p.get("priceLevel", "UNKNOWN"),
                    "opening_hours": p.get("regularOpeningHours", {}).get("weekdayDescriptions", []),
                    "payment_options": p.get("paymentOptions", {}),
                    "editorial_summary": p.get("editorialSummary", {}).get("text", ""),
                    "reservable": p.get("reservable"),
                    "delivery": p.get("delivery"),
                    "primary_type": p.get("primaryType", "UNKNOWN"),
                    "google_maps_url": p.get("googleMapsUri", f"https://maps.google.com/?cid={place_id}"),
                    "photo_count": len(p.get("photos", [])),
                    "batch_origin": batch_idx,
                    "chatbot_context": {
                        "allows_dogs": p.get("allowsDogs"),
                        "good_for_children": p.get("goodForChildren"),
                        "good_for_groups": p.get("goodForGroups"),
                        "live_music": p.get("liveMusic"),
                        "outdoor_seating": p.get("outdoorSeating"),
                        "restroom": p.get("restroom"),
                        "serves_alcohol": any([p.get("servesBeer"), p.get("servesWine"), p.get("servesCocktails")]),
                        "serves_meals": any([p.get("servesBreakfast"), p.get("servesLunch"), p.get("servesDinner")]),
                        "parking_options": p.get("parkingOptions", {})
                    },
                    "photos": [],
                    "is_hot_lead": False,
                    "hot_lead_tier": 0,
                    "phase2_score": 0.0,
                    "phase2_done": False
                }

        completed_batches.add(batch_idx)
        scanned_state[probe_id] = completed_batches

        # Incremental state persist after each batch
        save_budget(budget)
        save_processed_leads(all_leads)
        save_scanned_state(scanned_state)

    return new_prospects_found, False

def run_cli():
    print("=" * 60)
    print("   MEZLAT PIPELINE V4 — PHASE 1 RAW LEADS EXTRACTOR")
    print("=" * 60)
    
    budget = load_budget()
    used_p1 = budget["used"]["phase1_calls"]
    limit_p1 = budget["limits"]["phase1_monthly"]
    print(f"📊 API Quota Status: {used_p1}/{limit_p1} calls used ({limit_p1 - used_p1} remaining)")

    clusters_data = load_commercial_clusters()
    if not clusters_data:
        print("❌ Error: commercial_clusters_v4.json not found! Run cluster extraction first.")
        return

    all_leads = load_processed_leads()
    scanned_state = load_scanned_state()
    print(f"💾 Existing Dataset: {len(all_leads)} leads loaded from disk.")

    print("\nSelect Scan Mode:")
    print("  [1] Probe Test (Single probe ID or hex with custom batches)")
    print("  [2] Targeted City / Multi-City Scan (Select from city list)")
    print("  [3] Nationwide Full Scan (All available probes across Mexico)")
    
    mode = input("\nEnter mode (1/2/3): ").strip()

    tasks = []  # List of tuples (city_name, probe_dict, requested_batches)

    if mode == "1":
        probe_input = input("Paste Probe ID or H3 Hex ID: ").strip()
        matched_probe = None
        matched_city = "Custom_Probe"

        # Find probe across clusters
        for city, cdata in clusters_data.items():
            for p in cdata.get("radar_probes", []):
                p_id = f"{city}_{p.get('centroid_lat')}_{p.get('centroid_lng')}"
                if probe_input == p_id or probe_input == p.get("h3_index"):
                    matched_probe = p
                    matched_city = city
                    break
            if matched_probe:
                break

        if not matched_probe:
            print("⚠️ Probe ID not found in clusters. Parsing coordinate input...")
            try:
                parts = probe_input.split("_")
                if len(parts) >= 3:
                    matched_city = parts[0]
                    matched_probe = {"centroid_lat": float(parts[1]), "centroid_lng": float(parts[2]), "h3_index": "custom"}
                else:
                    coords = [float(x) for x in probe_input.replace(",", " ").split()]
                    matched_probe = {"centroid_lat": coords[0], "centroid_lng": coords[1], "h3_index": "custom"}
            except Exception:
                print("❌ Invalid probe input. Aborting.")
                return

        batch_choice = input("Select batches to execute [1, 2, 3 or comma-separated e.g. '1,2'] (Default: all): ").strip()
        if not batch_choice:
            requested_batches = [1, 2, 3]
        else:
            requested_batches = [int(b.strip()) for b in batch_choice.split(",") if b.strip().isdigit()]

        tasks.append((matched_city, matched_probe, requested_batches))

    elif mode == "2":
        cities = sorted(list(clusters_data.keys()))
        print("\nAvailable Cities:")
        for i, city in enumerate(cities, 1):
            p_count = len(clusters_data[city].get("radar_probes", []))
            print(f"  [{i:2d}] {city:30s} ({p_count} probes)")

        selection = input("\nEnter city number(s) separated by comma (e.g. '1' or '1, 4, 7'): ").strip()
        selected_indices = [int(x.strip()) for x in selection.split(",") if x.strip().isdigit()]

        for idx in selected_indices:
            if 1 <= idx <= len(cities):
                city_name = cities[idx - 1]
                probes = clusters_data[city_name].get("radar_probes", [])
                for p in probes:
                    tasks.append((city_name, p, [1, 2, 3]))

        if not tasks:
            print("❌ No valid cities selected. Aborting.")
            return

        est_calls = len(tasks) * 3
        print(f"\n📋 Plan: {len(selected_indices)} cities, {len(tasks)} probes, up to {est_calls} API calls.")
        confirm = input("Proceed with API execution? (y/n): ").strip().lower()
        if confirm not in ["y", "yes", "s", "si"]:
            print("🛑 Operation cancelled by user.")
            return

    elif mode == "3":
        for city_name, cdata in clusters_data.items():
            for p in cdata.get("radar_probes", []):
                tasks.append((city_name, p, [1, 2, 3]))

        est_calls = len(tasks) * 3
        print(f"\n⚠️  NATIONWIDE SCAN WARNING: {len(tasks)} total probes across Mexico (~{est_calls} API calls).")
        confirm = input("Type 'EXECUTE' to confirm nationwide API scan: ").strip()
        if confirm != "EXECUTE":
            print("🛑 Nationwide scan aborted.")
            return

    else:
        print("❌ Invalid mode selected.")
        return

    # Execute extraction tasks
    total_tasks = len(tasks)
    total_new_leads = 0
    print(f"\n🚀 Launching Phase 1 Extraction ({total_tasks} probe tasks)...\n")

    for i, (city_name, probe, requested_batches) in enumerate(tasks, 1):
        new_leads, budget_stopped = extract_probe(
            city_name=city_name,
            probe=probe,
            probe_idx=i,
            total_probes=total_tasks,
            requested_batches=requested_batches,
            all_leads=all_leads,
            scanned_state=scanned_state,
            budget=budget
        )
        total_new_leads += new_leads

        if budget_stopped:
            print("🛑 Execution halted due to budget quota limits.")
            break

    print(f"\n🎉 Phase 1 Extraction Complete! Captured {total_new_leads} new prospects ({len(all_leads)} total in database).")
    
    # Auto-synchronize maps and budget dashboard
    trigger_ui_updates(update_dashboard=True, update_fog_map=True, update_crm=False)

if __name__ == "__main__":
    run_cli()
