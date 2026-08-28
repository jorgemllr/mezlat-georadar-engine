"""
MEZLAT Allocation V4 Pipeline — Shared Configuration & Core Utilities
======================================================================
Central configuration module for paths, API credentials, budget state,
batch definitions, and UI generation hooks.
"""

import os
import json
import time
import math
import requests
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────
PIPELINE_DIR = Path(__file__).resolve().parent
V4_DIR = PIPELINE_DIR.parent

# Detect if running in standalone georadar repo or inside MEZLAT monorepo
if (V4_DIR / "commercial_clusters_v4.json").exists():
    REPO_ROOT = V4_DIR
elif (PIPELINE_DIR.parent / "Datasets").exists():
    REPO_ROOT = PIPELINE_DIR.parent
elif (PIPELINE_DIR.parent.parent / "Datasets").exists():
    REPO_ROOT = PIPELINE_DIR.parent.parent
else:
    REPO_ROOT = V4_DIR.parent.parent  # Default monorepo fallback

BASE_DIR = REPO_ROOT
DATASETS_DIR = REPO_ROOT / "Datasets" if (REPO_ROOT / "Datasets").exists() else (REPO_ROOT.parent.parent / "Datasets")

# Fallback search for config and cluster files
CLUSTERS_FILE = V4_DIR / "commercial_clusters_v4.json" if (V4_DIR / "commercial_clusters_v4.json").exists() else (REPO_ROOT / "commercial_clusters_v4.json")
ALLOCATION_FILE = V4_DIR / "api_budget_allocation_v4.json" if (V4_DIR / "api_budget_allocation_v4.json").exists() else (REPO_ROOT / "api_budget_allocation_v4.json")
BUDGET_FILE = V4_DIR / "budget_state.json" if (V4_DIR / "budget_state.json").exists() else (REPO_ROOT / "budget_state.json")
BNAI_FILE = V4_DIR / "bnai_niches.json" if (V4_DIR / "bnai_niches.json").exists() else (REPO_ROOT / "bnai_niches.json")

PROCESSED_LEADS_FILE = DATASETS_DIR / "processed_leads_v4.json"
SCANNED_PROBES_FILE = DATASETS_DIR / "scanned_probes_v4.json"

# Generated UI files
FOG_MAP_HTML = V4_DIR / "fog_of_war_map_v4.html"
CRM_HTML = V4_DIR / "crm_pipeline_v4.html"
ALLOCATION_DASHBOARD_HTML = V4_DIR / "allocation_dashboard_v4.html"

# ── API Setup ─────────────────────────────────────────────────────────────────
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT.parent.parent / ".env" if (REPO_ROOT.parent.parent / ".env").exists() else REPO_ROOT / ".env")
API_KEY = os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")

if not API_KEY:
    raise ValueError("❌ GOOGLE_PLACES_API_KEY not found in .env")

# ── Constants & Batch Definitions ─────────────────────────────────────────────
DEFAULT_SEARCH_RADIUS_M = 375
MAX_PHOTOS_TO_EXTRACT = 3

# 24 Niches organized into 3 balanced density batches
BATCH_NICHES = {
    1: [
        "restaurant", "plumber", "electrician", "painter",
        "roofing_contractor", "car_repair", "locksmith"
    ],
    2: [
        "cafe", "bakery", "dentist", "medical_clinic", "veterinary_care",
        "physiotherapist", "lawyer", "accounting"
    ],
    3: [
        "beauty_salon", "barber_shop", "gym", "sports_club", "spa",
        "yoga_studio", "night_club", "real_estate_agency", "florist"
    ]
}

# ── Math & Geometry ───────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two coordinates in meters."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ── Budget State Management ───────────────────────────────────────────────────

def load_budget() -> dict:
    """Loads budget state from disk or initializes default monthly limits."""
    current_month = time.strftime("%Y-%m")
    if BUDGET_FILE.exists():
        try:
            with open(BUDGET_FILE, "r", encoding="utf-8") as f:
                b = json.load(f)
                if b.get("billing_month") != current_month:
                    b["billing_month"] = current_month
                    b["used"] = {"phase1_calls": 0, "phase2_calls": 0}
                    save_budget(b)
                return b
        except Exception:
            pass

    default_budget = {
        "billing_month": current_month,
        "used": {"phase1_calls": 0, "phase2_calls": 0},
        "limits": {"phase1_monthly": 10000, "phase2_monthly": 5000}
    }
    save_budget(default_budget)
    return default_budget

def save_budget(budget: dict) -> None:
    """Persists budget state to budget_state.json."""
    with open(BUDGET_FILE, "w", encoding="utf-8") as f:
        json.dump(budget, f, indent=2)

def check_and_deduct_budget(budget: dict, phase: str = "phase1_calls", cost: int = 1) -> bool:
    """Checks whether API quota is available before deducting."""
    limit_key = phase.replace("_calls", "_monthly")
    limit = budget.get("limits", {}).get(limit_key, 5000)
    used = budget.get("used", {}).get(phase, 0)

    if used + cost > limit:
        print(f"⚠️ BUDGET LIMIT EXCEEDED: {phase} reached ({used}/{limit}). Operation stopped.")
        return False

    budget["used"][phase] = used + cost
    return True

# ── Checkpointing Data Management ─────────────────────────────────────────────

def load_processed_leads() -> dict:
    """Loads all existing prospects from processed_leads_v4.json."""
    if PROCESSED_LEADS_FILE.exists():
        try:
            with open(PROCESSED_LEADS_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("leads", {})
        except Exception:
            pass
    return {}

def save_processed_leads(all_leads: dict) -> None:
    """Saves leads dictionary atomically to processed_leads_v4.json."""
    with open(PROCESSED_LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump({"leads": all_leads}, f, indent=2, ensure_ascii=False)

def load_scanned_state() -> dict:
    """
    Loads scanned probes state. Returns dict mapping probe_id -> set of completed batch indices.
    Supports backward compatibility with legacy list format.
    """
    if SCANNED_PROBES_FILE.exists():
        try:
            with open(SCANNED_PROBES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    return {pid: {1, 2, 3} for pid in raw}
                elif isinstance(raw, dict):
                    return {pid: set(batches) for pid, batches in raw.items()}
        except Exception:
            pass
    return {}

def save_scanned_state(scanned_state: dict) -> None:
    """Saves scanned state to scanned_probes_v4.json, preserving flat list for compatibility."""
    legacy_list = [pid for pid, batches in scanned_state.items() if len(batches) >= 1]
    with open(SCANNED_PROBES_FILE, "w", encoding="utf-8") as f:
        json.dump(legacy_list, f, indent=2)

def load_commercial_clusters() -> dict:
    """Loads commercial clusters and radar probes data."""
    if CLUSTERS_FILE.exists():
        with open(CLUSTERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_bnai_matrix() -> dict:
    """Loads BNAI niche attractiveness scores."""
    if BNAI_FILE.exists():
        try:
            with open(BNAI_FILE, "r", encoding="utf-8") as f:
                niches = json.load(f)
                return {n["type"]: n["BNAI"] for n in niches}
        except Exception:
            pass
    return {}

# ── Google Places CDN Photo Resolver ──────────────────────────────────────────

def resolve_photo_cdn_url(photo_name: str) -> str | None:
    """Resolves photo reference into static Google CDN redirect URL."""
    url = f"https://places.googleapis.com/v1/{photo_name}/media?maxHeightPx=800&maxWidthPx=800&key={API_KEY}"
    try:
        response = requests.get(url, allow_redirects=True, timeout=5)
        if response.status_code == 200:
            return response.url
    except Exception:
        pass
    return None

# ── UI Synchronization Hooks ──────────────────────────────────────────────────

def trigger_ui_updates(update_dashboard: bool = True, update_fog_map: bool = True, update_crm: bool = True) -> None:
    """Executes UI generator scripts to keep visualizers synchronized with latest data."""
    print("\n🔄 Updating Visualizers & Dashboards...")
    python_bin = BASE_DIR / "venv" / "bin" / "python3"
    if not python_bin.exists():
        python_bin = "python3"
    else:
        python_bin = str(python_bin)

    if update_dashboard:
        try:
            subprocess.run([python_bin, str(V4_DIR / "generate_dashboard_v4.py")], cwd=str(BASE_DIR), check=True)
        except Exception as e:
            print(f"   [!] Dashboard update notice: {e}")

    if update_fog_map:
        try:
            pipeline_map_gen = PIPELINE_DIR / "generate_pipeline_fog_map.py"
            target_map_gen = str(pipeline_map_gen) if pipeline_map_gen.exists() else str(V4_DIR / "generate_fog_map_v4.py")
            subprocess.run([python_bin, target_map_gen], cwd=str(BASE_DIR), check=True)
        except Exception as e:
            print(f"   [!] Fog Map update notice: {e}")

    if update_crm:
        try:
            pipeline_crm_gen = PIPELINE_DIR / "generate_pipeline_crm_dashboard.py"
            target_crm_gen = str(pipeline_crm_gen) if pipeline_crm_gen.exists() else str(V4_DIR / "generate_crm_dashboard.py")
            subprocess.run([python_bin, target_crm_gen], cwd=str(BASE_DIR), check=True)
        except Exception as e:
            print(f"   [!] CRM Dashboard update notice: {e}")
