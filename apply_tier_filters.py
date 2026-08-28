import json
import math
import subprocess
from pathlib import Path

BASE_DIR = Path("/Users/book/Documents/MESLATT")
PROCESSED_LEADS_FILE = BASE_DIR / "Datasets" / "processed_leads_v4.json"
BNAI_JSON_FILE = BASE_DIR / "scripts/allocation_v4/bnai_niches.json"

def load_bnai_map():
    bnai_map = {}
    if BNAI_JSON_FILE.exists():
        with open(BNAI_JSON_FILE, "r", encoding="utf-8") as f:
            niches = json.load(f)
            for n in niches:
                bnai_map[n["type"]] = n["BNAI"]
    return bnai_map

def calculate_b2b_whales_score(lead, rating, reviews, bnai_score):
    """
    FILTRO 1: B2B SaaS Whales (Escala Masiva)
    - Enfocado puramente en Rentabilidad BNAI sin tope de reseñas.
    - Captura a los gigantes y a los nichos más valiosos.
    """
    safe_rating = rating if rating else 0
    base_math = round(safe_rating * math.log(reviews + 1), 2)
    
    # Solo requiere un mínimo de actividad para no ser fantasma absoluto
    if reviews >= 5 and safe_rating >= 3.0:
        lead["is_hot_lead"] = True
        # El score final es principalmente impulsado por la rentabilidad del nicho (BNAI)
        lead["phase2_score"] = float(bnai_score) + base_math
        
        # Tier 1 si el nicho es Top (BNAI > 400)
        lead["hot_lead_tier"] = 1 if bnai_score > 400 else 2
        
        if lead.get("phone"):
            lead["phase2_score"] += 50.0 # Bono masivo por contactabilidad
    else:
        lead["is_hot_lead"] = False
        lead["hot_lead_tier"] = 0
        lead["phase2_score"] = 0.0

def calculate_tier2_mvp_score(lead, rating, reviews, bnai_score):
    """
    FILTRO 2: MVP Mid-Size (Talla Media)
    - Rechaza corporativos grandes (>500 reseñas)
    - Rechaza fantasmas (<20 reseñas)
    - Prioriza negocios "bananeros" pero con flujo de caja.
    """
    safe_rating = rating if rating else 0
    base_math = round(safe_rating * math.log(reviews + 1), 2)
    pl = lead.get("price_level", "")
    
    if 20 <= reviews <= 500 and "VERY_EXPENSIVE" not in pl and safe_rating >= 3.5:
        lead["is_hot_lead"] = True
        lead["phase2_score"] = float(bnai_score) + base_math
        
        # Bono para clase media (Moderate)
        if "MODERATE" in pl:
            lead["phase2_score"] += 30.0
            
        if lead.get("phone"):
            lead["phase2_score"] += 20.0
            
        # Clasificamos el Tier dentro de este grupo basado en BNAI
        lead["hot_lead_tier"] = 1 if bnai_score > 350 else 2
    else:
        lead["is_hot_lead"] = False
        lead["hot_lead_tier"] = 0
        lead["phase2_score"] = 0.0

def main():
    print("==================================================")
    print("   MESLATT BNAI-POWERED FILTER RECALCULATOR")
    print("==================================================")
    print("[1] B2B SaaS Whales (Massive Scale, High BNAI, No limit)")
    print("[2] MVP Sweet Spot (Mid-Size, 20-500 reviews, Strict)")
    
    choice = input("\nSelect the filter strategy to apply (1/2): ").strip()
    
    if choice not in ['1', '2']:
        print("Invalid choice. Exiting.")
        return
        
    bnai_map = load_bnai_map()
    if not bnai_map:
        print("⚠️ Warning: bnai_niches.json not found! BNAI scores will default to 100.")
        
    with open(PROCESSED_LEADS_FILE, "r", encoding="utf-8") as f:
        master_data = json.load(f)
        all_leads = master_data.get("leads", {})
        
    print(f"\n🔄 Recalculating scores for {len(all_leads)} businesses using BNAI Matrix...")
    
    hot_count = 0
    for pid, lead in all_leads.items():
        # Reset current scores
        lead["is_hot_lead"] = False
        lead["hot_lead_tier"] = 0
        lead["phase2_score"] = 0.0
        
        website = lead.get("website", "")
        # Regla de Oro: Solo evaluar a los que NO tienen sitio web real
        is_generic_web = not website or "facebook.com" in website.lower() or "instagram.com" in website.lower() or "linktr.ee" in website.lower()
        
        if is_generic_web:
            rating = lead.get("rating", 0)
            reviews = lead.get("reviews_count", 0)
            primary_type = lead.get("primary_type", "")
            
            # Obtener el score BNAI de este nicho (por defecto 100 si no es nicho principal)
            bnai_score = bnai_map.get(primary_type, 100)
            
            if choice == '1':
                calculate_b2b_whales_score(lead, rating, reviews, bnai_score)
            elif choice == '2':
                calculate_tier2_mvp_score(lead, rating, reviews, bnai_score)
                
            if lead["is_hot_lead"]:
                hot_count += 1
                
    # Save the updated JSON
    with open(PROCESSED_LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)
        
    print(f"✅ Recalculation complete. {hot_count} Hot Leads identified.")
    
    print("🔄 Re-generating UI Dashboards and Maps...")
    try:
        subprocess.run(["venv/bin/python3", "scripts/allocation_v4/generate_fog_map_v4.py"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["venv/bin/python3", "scripts/allocation_v4/generate_dashboard_v4.py"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["venv/bin/python3", "scripts/allocation_v4/generate_crm_dashboard.py"], cwd=str(BASE_DIR), check=True)
        print("🎉 All UI files successfully updated!")
    except Exception as e:
        print(f"❌ Error updating UI: {e}")

if __name__ == "__main__":
    main()
