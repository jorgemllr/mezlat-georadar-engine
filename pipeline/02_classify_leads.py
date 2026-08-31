"""
MEZLAT Allocation V4 Pipeline — Lead Classifier & BNAI Scoring Engine
======================================================================
Applies multi-strategy intelligence filters to classify raw business prospects
into 3 Commercial Target Tiers:
  - TIER 3: Enterprise VIP ($6,000 - $12,000 MXN)
  - TIER 2: Growth ($2,500 - $5,900 MXN)
  - TIER 1: Starter ($300 - $990 MXN)

Updates Datasets/processed_leads_v4.json and regenerates CRM + Fog of War map.
"""

import sys
import json
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_config import (
    load_processed_leads,
    save_processed_leads,
    load_bnai_matrix,
    trigger_ui_updates
)

def is_generic_or_missing_website(website: str) -> bool:
    """Checks if website is absent, social media page, or generic linktree."""
    if not website:
        return True
    w = website.lower()
    generic_domains = [
        "facebook.com", "fb.me", "instagram.com", "linktr.ee",
        "wa.me", "whatsapp.com", "tiktok.com", "t.me"
    ]
    return any(domain in w for domain in generic_domains)

def classify_lead_commercial_tiers(lead: dict, bnai_score: float) -> None:
    """
    Evaluates the lead and assigns it to Target Tier 1, 2, or 3 based on
    Google Maps metrics, determining its Hot Lead status and Suggested Price Anchor.
    """
    rating = lead.get("rating", 0) or 0
    reviews = lead.get("reviews_count", 0) or 0
    website = lead.get("website", "")
    pl = lead.get("price_level", "")
    p_type = lead.get("primary_type", "")
    
    # Initialize pipeline status if not present
    if not lead.get("sales_status"):
        lead["sales_status"] = "NEW"

    base_math = round(rating * math.log(reviews + 1), 2) if reviews > 0 else 0
    score = float(bnai_score) + base_math
    if lead.get("phone"):
        score += 20.0

    is_nightlife = p_type in ["night_club", "bar"]

    # === VIP NIGHTLIFE EXCEPTION LOGIC ===
    if is_nightlife:
        # Forgive website entirely.
        # Only reject if it's completely fake/dead (0 reviews or terrible rating + tiny reviews)
        if rating < 2.0 and reviews < 5:
            lead["is_hot_lead"] = False
            lead["target_tier"] = 1
            lead["suggested_price"] = 0
            lead["phase2_score"] = 0.0
            return
            
        lead["is_hot_lead"] = True
        
        # Fast-track to Tier 3 (Enterprise)
        if reviews >= 40:
            lead["target_tier"] = 3
            lead["suggested_price"] = 12000 if reviews >= 100 else 8500
            score += 150.0  # Massive priority boost for Enterprise Nightlife
        # Fast-track to Tier 2 (Growth)
        else:
            lead["target_tier"] = 2
            lead["suggested_price"] = 5900
            score += 80.0
            
        lead["phase2_score"] = round(score, 2)
        return

    # === NORMAL BUSINESS LOGIC ===
    # Strict Rule: Must lack a custom website
    if not is_generic_or_missing_website(website):
        lead["is_hot_lead"] = False
        lead["target_tier"] = 1
        lead["suggested_price"] = 0
        lead["phase2_score"] = 0.0
        return

    # Dynamic minimum rating
    min_rating = 2.5 if p_type in ["car_repair"] else 3.5
    if rating < min_rating or reviews < 5:
        lead["is_hot_lead"] = False
        lead["target_tier"] = 1
        lead["suggested_price"] = 0
        lead["phase2_score"] = 0.0
        return

    is_hot = False
    tier = 1
    price_anchor = 0

    # TIER 3: Enterprise VIP
    if reviews >= 200 and "EXPENSIVE" in pl:
        is_hot = True
        tier = 3
        price_anchor = 12000 if reviews >= 500 else 8500
        score += 50.0

    # TIER 2: Growth
    elif 30 <= reviews <= 400 and ("EXPENSIVE" not in pl):
        is_hot = True
        tier = 2
        price_anchor = 5900 if reviews >= 150 else 3500
        if "MODERATE" in pl:
            score += 30.0

    # TIER 1: Starter
    elif 5 <= reviews <= 40:
        is_hot = True
        tier = 1
        price_anchor = 990 if reviews >= 20 else 490
        
    else:
        # Fallback for weird combos that don't perfectly fit MVP but are hot
        if reviews > 5:
            is_hot = True
            tier = 1
            price_anchor = 990

    lead["is_hot_lead"] = is_hot
    lead["target_tier"] = tier
    lead["suggested_price"] = price_anchor
    lead["phase2_score"] = round(score, 2) if is_hot else 0.0


def run_cli():
    print("=" * 60)
    print("   MEZLAT COMMERCIAL PIPELINE V4 — LEAD CLASSIFIER")
    print("=" * 60)
    print("🤖 Automatic Classification Mode: Active")
    print("Categorizing into TIER 1 (Starter), TIER 2 (Growth), TIER 3 (Enterprise).")

    all_leads = load_processed_leads()
    if not all_leads:
        print("❌ No processed leads found.")
        return

    bnai_matrix = load_bnai_matrix()

    total = len(all_leads)
    print(f"⚙️ Applying commercial tiers across {total} prospects...")

    hot_count = 0
    t3_count = 0
    t2_count = 0
    t1_count = 0

    # Process leads in chunks to avoid OOM kills on VMs with limited RAM (55k+ leads)
    CHUNK_SIZE = 5000
    lead_items = list(all_leads.items())

    for chunk_start in range(0, total, CHUNK_SIZE):
        chunk = lead_items[chunk_start:chunk_start + CHUNK_SIZE]
        chunk_end = min(chunk_start + CHUNK_SIZE, total)
        print(f"   🔄 Processing leads {chunk_start + 1}–{chunk_end} of {total}...", flush=True)

        for pid, lead in chunk:
            p_type = lead.get("primary_type", "")
            bnai_score = bnai_matrix.get(p_type, 100.0)
            classify_lead_commercial_tiers(lead, bnai_score)

            if lead.get("is_hot_lead"):
                hot_count += 1
                t = lead.get("target_tier")
                if t == 3: t3_count += 1
                elif t == 2: t2_count += 1
                else: t1_count += 1

        # Save incrementally after each chunk to protect against future OOM kills
        save_processed_leads(all_leads)
        print(f"   ✅ Chunk saved. Hot leads so far: {hot_count}", flush=True)

    print("\n" + "=" * 45)
    print("🎯 CLASSIFICATION RESULTS SUMMARY")
    print("=" * 45)
    print(f"  Total Qualified Hot Leads: {hot_count} / {total}")
    print(f"  ├─ TIER 3 (Enterprise VIP): {t3_count}")
    print(f"  ├─ TIER 2 (Growth):         {t2_count}")
    print(f"  └─ TIER 1 (Starter):        {t1_count}")
    print("=" * 45)
    print("\n✅ Classification complete. Database updated successfully.")
    print("✨ Dynamic CRM and Tactical Map reflect new tiers live on crm_server.py")

if __name__ == "__main__":
    run_cli()
