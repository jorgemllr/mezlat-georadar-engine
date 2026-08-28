"""
MEZLAT V4 Pipeline — Manual Lead Injector (Ambassadors / Hidden Gems)
======================================================================
Allows a sales ambassador to paste a Google Maps Place ID or URL.
Extracts the full Place Details from Google API and injects it into the
processed_leads_v4.json database, regardless of algorithmic rules.
"""

import sys
import json
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_config import (
    API_KEY,
    load_processed_leads,
    save_processed_leads,
    trigger_ui_updates
)

def fetch_place_details(place_id: str) -> dict:
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": (
            "id,displayName,location,primaryType,types,rating,userRatingCount,"
            "websiteUri,formattedAddress,nationalPhoneNumber,internationalPhoneNumber,"
            "priceLevel,googleMapsUri,photos"
        )
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"❌ API Error: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Network Error: {e}")
    return {}

def run_cli():
    print("=" * 60)
    print("   MEZLAT PIPELINE V4 — MANUAL LEAD INJECTOR (AMBASSADORS)")
    print("=" * 60)
    print("Use this to manually add 'Hidden Gems' (businesses not caught by the radar).")
    
    place_id = input("\nEnter Google Place ID (e.g., ChIJ...): ").strip()
    if not place_id:
        print("❌ Invalid input.")
        return

    all_leads = load_processed_leads()
    if place_id in all_leads:
        print("⚠️ This lead is already in the database!")
        return
        
    print(f"🔍 Fetching details for Place ID: {place_id}...")
    details = fetch_place_details(place_id)
    
    if not details:
        return
        
    # Build lead object
    lat = details.get("location", {}).get("latitude", 0)
    lng = details.get("location", {}).get("longitude", 0)
    
    new_lead = {
        "place_id": details.get("id", place_id),
        "business_name": details.get("displayName", {}).get("text", "Unknown"),
        "lat": lat,
        "lng": lng,
        "address": details.get("formattedAddress", ""),
        "rating": details.get("rating", 0),
        "reviews_count": details.get("userRatingCount", 0),
        "website": details.get("websiteUri", ""),
        "phone": details.get("nationalPhoneNumber") or details.get("internationalPhoneNumber", ""),
        "price_level": details.get("priceLevel", "UNKNOWN"),
        "primary_type": details.get("primaryType", "UNKNOWN"),
        "google_maps_url": details.get("googleMapsUri", ""),
        "city_zone": "MANUAL_INJECTION",
        "is_hot_lead": True,  # Forzamos que sea hot lead porque es inyección manual
        "sales_status": "NEW",
        "target_tier": 2,     # Default to Growth, user can negotiate
        "suggested_price": 5900,
        "phase2_score": 999.0 # Maximum priority
    }
    
    print(f"✅ Injected: {new_lead['business_name']} ({new_lead['address']})")
    all_leads[place_id] = new_lead
    
    save_processed_leads(all_leads)
    trigger_ui_updates(update_dashboard=False, update_fog_map=True, update_crm=True)
    print("✅ Database updated and UI regenerated.")

if __name__ == "__main__":
    run_cli()
