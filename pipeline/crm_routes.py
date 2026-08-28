import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file
import h3

PIPELINE_DIR = Path(__file__).resolve().parent

import sys
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from pipeline_config import (
    load_processed_leads,
    save_processed_leads,
    load_commercial_clusters,
    load_scanned_state
)

crm_bp = Blueprint('crm_pipeline', __name__, url_prefix='/crm')

CRM_TEMPLATE_PATH = PIPELINE_DIR / "crm_app_template.html"
MAP_TEMPLATE_PATH = PIPELINE_DIR / "map_app_template.html"
DASHBOARD_TEMPLATE_PATH = PIPELINE_DIR / "dashboard_app_template.html"
QUEUE_TEMPLATE_PATH = PIPELINE_DIR / "queue_app_template.html"
QUEUE_DATA_PATH = PIPELINE_DIR.parent.parent.parent / "Datasets" / "phase2_round_robin_queue.json"

@crm_bp.route('/')
def index():
    return send_file(CRM_TEMPLATE_PATH)

@crm_bp.route('/map')
def fog_map():
    return send_file(MAP_TEMPLATE_PATH)

@crm_bp.route('/dashboard')
def dashboard():
    return send_file(DASHBOARD_TEMPLATE_PATH)

@crm_bp.route('/queue')
def queue_dashboard():
    return send_file(QUEUE_TEMPLATE_PATH)

@crm_bp.route('/api/queue', methods=['GET', 'POST'])
def get_queue():
    rebuild = request.args.get('rebuild', '').lower() in ('true', '1') or request.method == 'POST'
    if rebuild or not QUEUE_DATA_PATH.exists():
        try:
            import importlib
            mod = importlib.import_module("04_build_round_robin_queue")
            mod.build_round_robin_queue()
        except Exception as e:
            print(f"[QUEUE] Error recalculating queue: {e}")
            
    if QUEUE_DATA_PATH.exists():
        with open(QUEUE_DATA_PATH, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Queue file not found.", "rounds": []}), 404



@crm_bp.route('/api/leads', methods=['GET'])
def get_leads():
    leads = load_processed_leads()
    now = datetime.now()
    changed = False
    for pid, lead in leads.items():
        if lead.get("locked_by"):
            locked_at_str = lead.get("locked_at")
            if locked_at_str:
                try:
                    locked_at = datetime.fromisoformat(locked_at_str)
                    if now > locked_at + timedelta(days=7) and lead.get("sales_status") != "SOLD":
                        lead["locked_by"] = None
                        lead["locked_at"] = None
                        changed = True
                except:
                    pass
    
    if changed:
        save_processed_leads(leads)
        
    return jsonify(list(leads.values()))

@crm_bp.route('/api/leads/<place_id>', methods=['POST'])
def update_lead(place_id):
    leads = load_processed_leads()
    if place_id not in leads:
        return jsonify({"error": "Lead not found"}), 404
        
    data = request.json or {}
    lead = leads[place_id]
    action = data.get("action")
    
    if action == "lock":
        locked_count = sum(1 for L in leads.values() if L.get("locked_by") == "admin")
        if locked_count >= 5:
            return jsonify({"error": "LIMIT_REACHED", "message": "You can only lock 5 leads at a time."}), 400
            
        lead["locked_by"] = "admin"
        lead["locked_at"] = datetime.now().isoformat()
        
    elif action == "unlock":
        lead["locked_by"] = None
        lead["locked_at"] = None
        
    elif action == "update_data":
        if "sales_status" in data:
            lead["sales_status"] = data["sales_status"]
        if "final_price" in data:
            lead["final_price"] = data["final_price"]
        if "notes" in data:
            lead["notes"] = data["notes"]
            
    save_processed_leads(leads)
    return jsonify({"success": True, "lead": lead})

@crm_bp.route('/api/clusters', methods=['GET'])
def get_clusters():
    clusters_data = load_commercial_clusters()
    leads_data = load_processed_leads()
    scanned_state = load_scanned_state()
    scanned_set = set(scanned_state.keys())
    phase2_leads = [ld for ld in leads_data.values() if ld.get("photos")]

    for city, cData in clusters_data.items():
        for cl in cData.get("all_clusters", []):
            phase1 = False
            for p in cl.get("radar_probes", []):
                pid = f"{cl['city']}_{p['centroid_lat']}_{p['centroid_lng']}"
                if pid in scanned_set:
                    phase1 = True
                    break

            phase2 = False
            for ld in phase2_leads:
                try:
                    if h3.latlng_to_cell(ld["lat"], ld["lng"], 8) == cl.get("h3_index"):
                        phase2 = True
                        break
                except Exception:
                    pass

            cl["phase1_done"] = phase1
            cl["phase2_done"] = phase2

    return jsonify({
        "clusters": clusters_data,
        "scanned_probes": list(scanned_set)
    })

@crm_bp.route('/api/probes', methods=['GET'])
def get_probes():
    clusters_data = load_commercial_clusters()
    scanned_state = load_scanned_state()
    hexagons = []
    
    for city, cData in clusters_data.items():
        for p in cData.get("radar_probes", []):
            pid = f"{city}_{p['centroid_lat']}_{p['centroid_lng']}"
            batches_done = len(scanned_state.get(pid, []))
            color = '#38bdf8' if batches_done > 0 else '#f43f5e'
            hex_id = p.get("h3_index")
            latlng_poly = []
            if hex_id:
                try:
                    latlng_poly = h3.cell_to_boundary(hex_id)
                except Exception:
                    pass
            hexagons.append({
                "id": pid,
                "h3_index": hex_id,
                "polygon": latlng_poly,
                "lat": p['centroid_lat'],
                "lng": p['centroid_lng'],
                "color": color,
                "city": city,
                "establishment_count": p.get("establishment_count", 0),
                "batches_done": batches_done
            })
    return jsonify(hexagons)

@crm_bp.route('/api/allocation_stats', methods=['GET'])
def get_allocation_stats():
    base_dir = PIPELINE_DIR.parent
    budget_file = base_dir / "api_budget_allocation_v4.json"
    state_file = base_dir / "budget_state.json"
    
    budget_data = {}
    if budget_file.exists():
        with open(budget_file, "r") as f:
            budget_data = json.load(f)
            
    state_data = {}
    if state_file.exists():
        with open(state_file, "r") as f:
            state_data = json.load(f)
            
    return jsonify({
        "budget": budget_data,
        "state": state_data
    })

@crm_bp.route('/api/zones', methods=['GET'])
def get_zones():
    clusters_data = load_commercial_clusters()
    return jsonify(clusters_data)
