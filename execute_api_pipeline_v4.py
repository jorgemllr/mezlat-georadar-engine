import h3
import os
import json
import time
import math
import requests
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# ── Setup & Constants ─────────────────────────────────────────────────────────
BASE_DIR = Path("/Users/book/Documents/MESLATT")
load_dotenv(BASE_DIR / '.env')
API_KEY = os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")

if not API_KEY:
    raise ValueError("❌ GOOGLE_PLACES_API_KEY not found in .env")

V4_DIR = BASE_DIR / "scripts/allocation_v4"
DATA_DIR = BASE_DIR / "Datasets"

CLUSTERS_FILE = V4_DIR / "commercial_clusters_v4.json"
BUDGET_FILE = V4_DIR / "budget_state.json"
PROCESSED_LEADS_FILE = DATA_DIR / "processed_leads_v4.json"
SCANNED_PROBES_FILE = DATA_DIR / "scanned_probes_v4.json"

# 🚀 METROPOLITAN SCAN MODE
# When TEST_MODE is True, we scan the target list while strictly filtering to TARGET_CITIES.
TEST_MODE = True
TEST_BATCH_3_PHASE2 = True
TARGET_CITIES = ["queretaro", "juriquilla", "el pueblito", "el pueblito (centro)"]

API_SEARCH_RADIUS_M = 375
MAX_PHOTOS_TO_EXTRACT = 3

# Niche Batches (24 Niches total - Balanced Density)
BATCH_NICHES = {
    1: ["restaurant", "plumber", "electrician", "painter", 
        "roofing_contractor", "car_repair", "locksmith"],
    2: ["cafe", "bakery", "dentist", "medical_clinic", "veterinary_care", 
        "physiotherapist", "lawyer", "accounting"],
    3: ["beauty_salon", "barber_shop", "gym", "sports_club", "spa", 
        "yoga_studio", "night_club", "real_estate_agency", "florist"]
}

# ── Budget Management ─────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    """Calculates great-circle distance between two geographic coordinates in meters."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def load_budget():
    """Loads current budget state or initializes default monthly quota limits."""
    if BUDGET_FILE.exists():
        with open(BUDGET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "billing_month": time.strftime("%Y-%m"),
        "used": {"phase1_calls": 0, "phase2_calls": 0},
        "limits": {"phase1_monthly": 10000, "phase2_monthly": 5000}
    }

def save_budget(budget):
    """Persists budget state to disk."""
    with open(BUDGET_FILE, "w", encoding="utf-8") as f:
        json.dump(budget, f, indent=2)

def check_and_deduct_budget(budget, phase="phase1_calls", cost=1):
    """Verifies that API call limit has not been exceeded before deducting cost."""
    limit = budget["limits"][phase.replace("_calls", "_monthly")]
    used = budget["used"][phase]
    
    if used + cost > limit:
        print(f"⚠️ BUDGET ALERT: {phase} limit reached ({used}/{limit}). Aborting.")
        return False
    
    budget["used"][phase] += cost
    return True

# ── Photo Resolver (CDN) ──────────────────────────────────────────────────────

def resolve_photo_cdn_url(photo_name):
    """Fetches redirect URL for Google Places photo reference to store static CDN links."""
    url = f"https://places.googleapis.com/v1/{photo_name}/media?maxHeightPx=800&maxWidthPx=800&key={API_KEY}"
    try:
        response = requests.get(url, allow_redirects=True, timeout=5)
        if response.status_code == 200:
            return response.url
    except Exception:
        pass
    return None

# ── Utils ─────────────────────────────────────────────────────────────────────

def update_ui_files():
    """Triggers generation scripts for maps and CRM dashboards."""
    print("🔄 Updating Maps and Dashboards...")
    try:
        subprocess.run(["venv/bin/python3", "scripts/allocation_v4/generate_fog_map_v4.py"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["venv/bin/python3", "scripts/allocation_v4/generate_dashboard_v4.py"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["venv/bin/python3", "scripts/allocation_v4/generate_crm_dashboard.py"], cwd=str(BASE_DIR), check=True)
    except Exception as e:
        print(f"   [!] Error updating UI: {e}")

# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_phase_1():
    """Executes Phase 1: Nearby Search V4 extraction across radar probes."""
    print("🚀 Starting Phase 1: Nearby Search V4 Extraction...")
    budget = load_budget()
    
    with open(CLUSTERS_FILE, 'r', encoding='utf-8') as f:
        clusters_data = json.load(f)

    # Checkpointing - Load existing leads and scanned probes
    all_leads = {}
    if PROCESSED_LEADS_FILE.exists():
        with open(PROCESSED_LEADS_FILE, 'r', encoding='utf-8') as f:
            try:
                all_leads = json.load(f).get("leads", {})
                print(f"🔄 Loaded {len(all_leads)} previous prospects from disk.")
            except Exception:
                pass
                
    scanned_probes_set = set()
    if SCANNED_PROBES_FILE.exists():
        with open(SCANNED_PROBES_FILE, 'r', encoding='utf-8') as f:
            try:
                scanned_probes_set = set(json.load(f))
                print(f"🔄 Resuming scan: {len(scanned_probes_set)} probes already scanned.")
            except Exception:
                pass

    budget_exceeded = False
    
    for city_name, cData in clusters_data.items():
        if budget_exceeded:
            break
            
        # 🔒 Metropolitan Filter
        if city_name.lower() not in TARGET_CITIES:
            continue
            
        probes = cData.get("radar_probes", [])
        if not probes:
            continue
            
        for probe_num, probe in enumerate(probes, 1):
            lat, lng = probe['centroid_lat'], probe['centroid_lng']
            probe_id = f"{city_name}_{lat}_{lng}"
            
            if probe_id in scanned_probes_set:
                print(f"   ⏭️ Probe {probe_num} already scanned. Skipping...")
                continue
            
            # --- Dynamic Radius Calculation ---
            dynamic_radius = 450
            hex_id = probe.get("h3_index")
            if hex_id:
                try:
                    boundary = h3.cell_to_boundary(hex_id)
                    if boundary:
                        v0_lat, v0_lng = boundary[0]
                        dist = haversine(lat, lng, v0_lat, v0_lng)
                        dynamic_radius = int(math.ceil(dist / 10.0)) * 10
                except Exception:
                    pass
            print(f"\n📍 Scanning hexagon {hex_id} in {city_name} (Probe {probe_num}/{len(probes)})...")
            print(f"   📡 Executing Phase 1 (Batches)...")
            active_batches = probe.get("active_batches", [1, 2, 3])
            
            for batch_idx in active_batches:
                if not check_and_deduct_budget(budget, "phase1_calls", 1):
                    budget_exceeded = True
                    break
                    
                url = "https://places.googleapis.com/v1/places:searchNearby"
                headers = {
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": API_KEY,
                    "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.primaryType,places.types,places.rating,places.userRatingCount,places.websiteUri,places.formattedAddress,places.businessStatus,places.nationalPhoneNumber,places.internationalPhoneNumber,places.regularOpeningHours,places.priceLevel,places.googleMapsUri,places.photos,places.paymentOptions,places.editorialSummary,places.reservable,places.delivery,places.allowsDogs,places.goodForChildren,places.goodForGroups,places.goodForWatchingSports,places.liveMusic,places.menuForChildren,places.outdoorSeating,places.restroom,places.servesBeer,places.servesBreakfast,places.servesBrunch,places.servesCocktails,places.servesCoffee,places.servesDessert,places.servesDinner,places.servesLunch,places.servesVegetarianFood,places.servesWine,places.parkingOptions"
                }
                
                # Use Nearby Search with targeted category types per batch
                payload = {
                    "includedTypes": BATCH_NICHES[batch_idx],
                    "maxResultCount": 20,
                    "locationRestriction": {
                        "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": dynamic_radius}
                    }
                }
                
                try:
                    res = requests.post(url, headers=headers, json=payload, timeout=10).json()
                    results = res.get('places', [])
                    print(f"   ✅ Batch {batch_idx}: {len(results)} raw prospects.")
                    
                    for p in results:
                        place_id = p.get('id')
                        if not place_id:
                            continue
                        
                        # Filter out closed businesses
                        status = p.get('businessStatus', 'OPERATIONAL')
                        if status in ['CLOSED_TEMPORARILY', 'CLOSED_PERMANENTLY']:
                            continue
                        
                        rating = p.get('rating', 0)
                        reviews = p.get('userRatingCount', 0)
                        website = p.get('websiteUri', '')
                        
                        # Phase 1 base extraction
                        if place_id not in all_leads:
                            all_leads[place_id] = {
                                "place_id": place_id,
                                "business_name": p.get('displayName', {}).get('text', 'Unknown'),
                                "lat": p.get('location', {}).get('latitude', lat),
                                "lng": p.get('location', {}).get('longitude', lng),
                                "address": p.get('formattedAddress', ''),
                                "rating": rating,
                                "reviews_count": reviews,
                                "website": website,
                                "phone": p.get('nationalPhoneNumber') or p.get('internationalPhoneNumber', ''),
                                "price_level": p.get('priceLevel', 'UNKNOWN'),
                                "opening_hours": p.get('regularOpeningHours', {}).get('weekdayDescriptions', []),
                                "payment_options": p.get('paymentOptions', {}),
                                "editorial_summary": p.get('editorialSummary', {}).get('text', ''),
                                "reservable": p.get('reservable'),
                                "delivery": p.get('delivery'),
                                "primary_type": p.get('primaryType', 'UNKNOWN'),
                                "google_maps_url": p.get('googleMapsUri', ''),
                                "photo_count": len(p.get('photos', [])),
                                "batch_origin": batch_idx,
                                "chatbot_context": {
                                    "allows_dogs": p.get('allowsDogs'),
                                    "good_for_children": p.get('goodForChildren'),
                                    "good_for_groups": p.get('goodForGroups'),
                                    "live_music": p.get('liveMusic'),
                                    "outdoor_seating": p.get('outdoorSeating'),
                                    "restroom": p.get('restroom'),
                                    "serves_alcohol": any([p.get('servesBeer'), p.get('servesWine'), p.get('servesCocktails')]),
                                    "serves_meals": any([p.get('servesBreakfast'), p.get('servesLunch'), p.get('servesDinner')]),
                                    "parking_options": p.get('parkingOptions', {})
                                },
                                "photos": [],
                                "is_hot_lead": False,
                                "phase2_score": 0.0
                            }
                        
                        # Calculate Score (Hot Lead logic)
                        lead = all_leads[place_id]
                        is_generic_web = not website or "facebook.com" in website.lower() or "instagram.com" in website.lower() or "linktr.ee" in website.lower()
                        
                        if is_generic_web:
                            # Base logarithmic formula for all prospects
                            safe_rating = rating if rating else 0
                            base_score = round(safe_rating * math.log(reviews + 1), 2)
                            
                            # Dynamic rating threshold by niche (Bars/clubs naturally have lower ratings)
                            forgiving_niches = ["night_club", "bar", "car_repair"]
                            lead_type = lead.get("primary_type", "")
                            min_rating = 2.5 if lead_type in forgiving_niches else 3.8
                            
                            if reviews >= 10 and safe_rating >= min_rating:
                                # TIER 1: Sweet Spot (Healthy reputation, lacking custom website)
                                lead["is_hot_lead"] = True
                                lead["hot_lead_tier"] = 1
                                # Add 100 bonus so Tier 1 is always prioritized ahead of Tier 2
                                lead["phase2_score"] = 100.0 + base_score 
                            else:
                                # TIER 2: New businesses (1-9 reviews), Ghosts (0), or In Crisis (<3.8)
                                lead["is_hot_lead"] = True
                                lead["hot_lead_tier"] = 2
                                # Give 1.0 minimum score if 0 reviews
                                lead["phase2_score"] = base_score if reviews > 0 else 1.0
                            
                            # --- B2B BONUS INJECTION ---
                            # 1. Reachability Bonus (Phone present = Immediate sales outreach)
                            if lead.get("phone"):
                                lead["phase2_score"] += 15.0
                            
                            # 2. Purchasing Power Bonus (Higher price tier = Better cash flow)
                            pl = lead.get("price_level", "")
                            if "VERY_EXPENSIVE" in pl or "EXPENSIVE" in pl:
                                lead["phase2_score"] += 20.0
                            elif "MODERATE" in pl:
                                lead["phase2_score"] += 10.0
                            # ------------------------------
                            
                except Exception as e:
                    print(f"   ❌ Error in Batch {batch_idx}: {e}")

            # Incremental checkpointing
            scanned_probes_set.add(probe_id)
            save_budget(budget)
            with open(PROCESSED_LEADS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"leads": all_leads}, f, indent=2, ensure_ascii=False)
            with open(SCANNED_PROBES_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(scanned_probes_set), f, indent=2)
                
    return all_leads

def run_phase_2():
    """Executes Phase 2: Deep Extraction (Place Details + CDN Photo URLs)."""
    print("\n🚀 Starting Phase 2: Deep Extraction (Place Details + CDN Photos)...")
    budget = load_budget()
    
    # Load all leads from dataset for global enrichment
    with open(PROCESSED_LEADS_FILE, "r", encoding="utf-8") as f:
        master_data = json.load(f)
        all_leads = master_data.get("leads", {})

    # Filter and sort globally (Ignore those already completed in Phase 2 or not hot leads)
    valid_leads = [
        lead for lead in all_leads.values() 
        if lead.get('is_hot_lead') and not lead.get('phase2_done') and not lead.get('photos')
    ]
    if globals().get('TEST_MODE', False) and globals().get('TEST_BATCH_3_PHASE2', False):
        valid_leads = [lead for lead in valid_leads if lead.get('batch_origin') == 3]
        valid_leads = valid_leads[:5]
        
    valid_leads.sort(key=lambda x: x.get('phase2_score', 0), reverse=True)
    
    print(f"💰 Attempting to enrich {len(valid_leads)} hot leads ordered by priority.")
    
    for lead in valid_leads:
        # Skip if photos and opening hours already exist
        if lead.get('photos') and lead.get('opening_hours'):
            continue
            
        if not check_and_deduct_budget(budget, "phase2_calls", 1):
            print("🛑 PHASE 2 BUDGET LIMIT REACHED. Aborting.")
            break
            
        pid = lead['place_id']
        url = f"https://places.googleapis.com/v1/places/{pid}"
        headers = {
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": "id,internationalPhoneNumber,nationalPhoneNumber,regularOpeningHours,priceLevel,paymentOptions,photos,reviews,googleMapsUri"
        }
        
        try:
            print(f"   📞 Extracting details for {lead['business_name']} (Score: {lead.get('phase2_score')})...")
            res = requests.get(url, headers=headers, timeout=10).json()
            
            # Resolve Google CDN URLs (up to MAX_PHOTOS_TO_EXTRACT)
            static_photo_urls = []
            for photo in res.get("photos", [])[:MAX_PHOTOS_TO_EXTRACT]:
                if photo_name := photo.get("name"):
                    if cdn_url := resolve_photo_cdn_url(photo_name):
                        static_photo_urls.append(cdn_url)
            
            # Format customer reviews
            extracted_reviews = []
            for rev in res.get("reviews", []):
                extracted_reviews.append({
                    "author": rev.get("authorAttribution", {}).get("displayName"),
                    "rating": rev.get("rating"),
                    "text": rev.get("text", {}).get("text"),
                    "relative_time": rev.get("relativePublishTimeDescription")
                })
                
            lead['phone'] = res.get('nationalPhoneNumber') or res.get('internationalPhoneNumber')
            lead['google_maps_url'] = res.get('googleMapsUri', f"https://maps.google.com/?cid={pid}")
            lead['photos'] = static_photo_urls
            lead['opening_hours'] = res.get('regularOpeningHours', {}).get('weekdayDescriptions', [])
            lead['payment_options'] = res.get('paymentOptions', {})
            lead['reviews'] = extracted_reviews
            lead['price_level'] = res.get('priceLevel', 'UNKNOWN')
            
            # Mark lead as completed for Phase 2
            lead['phase2_done'] = True
            
            # Incremental checkpointing
            save_budget(budget)
            with open(PROCESSED_LEADS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"leads": all_leads}, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"   ❌ Error in Place Details: {e}")

    print("✅ Phase 2 completed.")

if __name__ == "__main__":
    leads = run_phase_1()
    
    update_ui_files()
        
    print("\n⚠️  SYSTEM PAUSE ⚠️")
    print("👉 Open 'fog_of_war_map_v4.html' (JUST UPDATED) and review the data.")
    
    if globals().get('TEST_MODE', False) and globals().get('TEST_BATCH_3_PHASE2', False):
        print("\n🧪 [TEST MODE ACTIVE] Phase 2 will ONLY process a MAXIMUM of 5 Hot Leads from Batch 3.")
        
    resp = input("\nExecute Phase 2 (Deep Extraction & CDN Photos)? (y/n): ")
    
    if resp.lower().strip() in ['y', 'yes', 's', 'si']:
        run_phase_2()
        update_ui_files()
        print("\n🎉 Process finished. Reload the map to view complete data.")
    else:
        print("\n🛑 Phase 2 aborted manually.")

