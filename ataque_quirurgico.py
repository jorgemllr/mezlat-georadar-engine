import os, json, requests, subprocess, math
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
PROCESSED_FILE = BASE_DIR / "Datasets" / "processed_leads_v4.json"

LAT = 20.672822884978952
LNG = -100.43959300366863
RADIUS = 600 # Expanded to catch Cabaret

TARGET_NICHES = ["night_club", "bar"]

def inyectar_peces_chicos():
    print(f"🎯 Iniciando rescate de Antros en Plaza Antea (Radio {RADIUS}m)...")
    
    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.types,places.rating,places.userRatingCount,places.websiteUri,places.location,places.primaryType"
    }
    
    payload = {
        "includedTypes": TARGET_NICHES,
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": LAT, "longitude": LNG},
                "radius": RADIUS
            }
        }
    }
    
    res = requests.post(url, headers=headers, json=payload, timeout=15).json()
    places = res.get("places", [])
    print(f"✅ Se atraparon {len(places)} prospectos!")
    
    if not places: return
        
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    nuevos = 0
    for p in places:
        pid = p.get("id")
        if not pid: continue
        
        name = p.get("displayName", {}).get("text", "")
        print(f"   - {name}")
        
        if pid not in data["leads"]:
            lat_p = p.get("location", {}).get("latitude", LAT)
            lng_p = p.get("location", {}).get("longitude", LNG)
            rating = p.get("rating", 0)
            reviews = p.get("userRatingCount", 0)
            website = p.get("websiteUri", "")
            p_type = p.get("primaryType", "night_club")
            
            lead = {
                "place_id": pid,
                "business_name": name,
                "lat": lat_p, 
                "lng": lng_p,
                "rating": rating,
                "reviews_count": reviews,
                "website": website,
                "primary_type": p_type,
                "phase1_done": True,
                "phase2_done": False,
                "is_hot_lead": False,
                "phase2_score": 0.0
            }
            
            # Hot lead logic
            is_generic_web = not website or "facebook.com" in website.lower() or "instagram.com" in website.lower() or "linktr.ee" in website.lower()
            if is_generic_web:
                safe_rating = rating if rating else 0
                base_score = round(safe_rating * math.log(reviews + 1), 2)
                
                min_rating = 2.5 # Since they are night_clubs
                
                if reviews >= 10 and safe_rating >= min_rating:
                    lead["is_hot_lead"] = True
                    lead["hot_lead_tier"] = 1
                    lead["phase2_score"] = 100.0 + base_score
                else:
                    lead["is_hot_lead"] = True
                    lead["hot_lead_tier"] = 2
                    lead["phase2_score"] = base_score if reviews > 0 else 1.0
            
            data["leads"][pid] = lead
            nuevos += 1
            
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    print(f"💾 Inyectados {nuevos} prospectos en processed_leads_v4.json")
    
    # Render map
    map_script = BASE_DIR / "scripts" / "allocation_v4" / "generate_fog_map_v4.py"
    subprocess.run(["python3", str(map_script)])

if __name__ == "__main__":
    inyectar_peces_chicos()
